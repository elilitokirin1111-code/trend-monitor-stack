"""Pure deterministic normalizer and near-zero-risk basic dedup engine."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo

from app.domain.hotspot import (
    DedupGroup,
    DedupMember,
    NormalizationBatch,
    NormalizationStatus,
    NormalizedHotItem,
    PublishedAtPrecision,
    SnapshotRawItem,
    utc_now,
)

from .rules import NormalizationRules

SHANGHAI = ZoneInfo("Asia/Shanghai")
HOT_SCORE_PATTERN = re.compile(
    r"^\+?(?P<number>\d+(?:\.\d+)?)(?P<unit>[A-Za-z万亿]?)(?:次|热度)?$"
)
RELATIVE_PATTERN = re.compile(r"^(?P<count>\d+)\s*(?P<unit>分钟|小时|天)前$")
YESTERDAY_PATTERN = re.compile(r"^昨天(?:\s*(?P<hour>\d{1,2}):(?P<minute>\d{2}))?$")
MONTH_DAY_PATTERN = re.compile(
    r"^(?P<month>\d{1,2})-(?P<day>\d{1,2})(?:\s+(?P<hour>\d{1,2}):(?P<minute>\d{2}))?$"
)
PUNCTUATION_TRANSLATION = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "‘": "'",
        "’": "'",
        "…": "...",
    }
)


class HotspotNormalizer:
    def __init__(
        self,
        rules: NormalizationRules,
        *,
        clock: Callable[[], datetime] = utc_now,
        run_id_factory: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        self.rules = rules
        self._clock = clock
        self._run_id_factory = run_id_factory

    def normalize_snapshot(
        self,
        snapshot_id: str,
        raw_items: Iterable[SnapshotRawItem],
    ) -> NormalizationBatch:
        started_at = self._clock()
        run_id = self._run_id_factory()
        normalized = tuple(
            self.normalize_item(item, run_id)
            for item in sorted(raw_items, key=lambda value: value.position)
        )
        groups = self._deduplicate(run_id, snapshot_id, normalized)
        return NormalizationBatch(
            normalization_run_id=run_id,
            snapshot_id=snapshot_id,
            rule_version=self.rules.version,
            config_hash=self.rules.config_hash,
            config_json=self.rules.config_json,
            algorithm_version=self.rules.dedup_algorithm_version,
            started_at=started_at,
            finished_at=self._clock(),
            items=normalized,
            groups=groups,
        )

    def normalize_item(
        self,
        source: SnapshotRawItem,
        normalization_run_id: str,
    ) -> NormalizedHotItem:
        warnings: list[str] = []
        title = normalize_title(source.title)
        fingerprint = strict_title_fingerprint(title)
        if not title or not fingerprint:
            return self._failed_item(source, normalization_run_id, "empty_title")

        canonical_url = canonicalize_url(
            source.url,
            self.rules.tracking_parameters,
        )
        if source.url.strip() and canonical_url is None:
            warnings.append("invalid_url")
        elif not source.url.strip():
            warnings.append("missing_url")

        hot_score_value, hot_score_unit = normalize_hot_score(
            source.hot_score,
            self.rules.hot_score_multipliers,
        )
        if source.hot_score and hot_score_value is None:
            warnings.append("invalid_hot_score")

        published_at, precision, time_warning = self._published_at(source)
        if time_warning is not None:
            warnings.append(time_warning)

        return NormalizedHotItem(
            normalized_item_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"normalized:{normalization_run_id}:{source.raw_item_id}",
                )
            ),
            normalization_run_id=normalization_run_id,
            snapshot_id=source.snapshot_id,
            raw_item_id=source.raw_item_id,
            position=source.position,
            platform=source.platform,
            provider_id=source.provider_id,
            rank=source.rank,
            external_id_normalized=normalize_external_id(source.external_id),
            normalized_title=title,
            title_fingerprint=fingerprint,
            canonical_url=canonical_url,
            hot_score_value=hot_score_value,
            hot_score_unit=hot_score_unit,
            published_at=published_at,
            published_at_precision=precision,
            status=(
                NormalizationStatus.PARTIAL if warnings else NormalizationStatus.SUCCESS
            ),
            warnings=tuple(warnings),
            error_code=None,
            rule_version=self.rules.version,
        )

    def _failed_item(
        self,
        source: SnapshotRawItem,
        normalization_run_id: str,
        error_code: str,
    ) -> NormalizedHotItem:
        return NormalizedHotItem(
            normalized_item_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"normalized:{normalization_run_id}:{source.raw_item_id}",
                )
            ),
            normalization_run_id=normalization_run_id,
            snapshot_id=source.snapshot_id,
            raw_item_id=source.raw_item_id,
            position=source.position,
            platform=source.platform,
            provider_id=source.provider_id,
            rank=source.rank,
            external_id_normalized=normalize_external_id(source.external_id),
            normalized_title=None,
            title_fingerprint=None,
            canonical_url=None,
            hot_score_value=None,
            hot_score_unit=None,
            published_at=None,
            published_at_precision=PublishedAtPrecision.UNKNOWN,
            status=NormalizationStatus.FAILED,
            warnings=(),
            error_code=error_code,
            rule_version=self.rules.version,
        )

    def _published_at(
        self,
        source: SnapshotRawItem,
    ) -> tuple[datetime | None, PublishedAtPrecision, str | None]:
        if source.published_at is not None:
            return (
                source.published_at.astimezone(timezone.utc),
                PublishedAtPrecision.EXACT,
                None,
            )
        raw_value = next(
            (
                source.raw_data.get(field)
                for field in self.rules.published_at_fields
                if source.raw_data.get(field) not in (None, "")
            ),
            None,
        )
        if raw_value is None:
            return None, PublishedAtPrecision.UNKNOWN, None
        parsed = parse_platform_time(raw_value, source.observed_at)
        if parsed is None:
            return None, PublishedAtPrecision.UNKNOWN, "invalid_published_at"
        return parsed[0], parsed[1], None

    def _deduplicate(
        self,
        run_id: str,
        snapshot_id: str,
        items: tuple[NormalizedHotItem, ...],
    ) -> tuple[DedupGroup, ...]:
        usable = tuple(
            item for item in items if item.status is not NormalizationStatus.FAILED
        )
        parent = list(range(len(usable)))
        edges: list[tuple[int, int, str, str]] = []
        seen: dict[tuple[str, str], int] = {}

        def find(index: int) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        def union(left: int, right: int) -> None:
            left_root, right_root = find(left), find(right)
            if left_root != right_root:
                parent[right_root] = left_root

        for index, item in enumerate(usable):
            for kind, scoped_value in _dedup_keys(item):
                key = (kind, scoped_value)
                previous = seen.get(key)
                if previous is None:
                    seen[key] = index
                    continue
                union(previous, index)
                edges.append(
                    (previous, index, kind, _evidence_hash(kind, scoped_value))
                )

        components: dict[int, list[int]] = defaultdict(list)
        for index in range(len(usable)):
            components[find(index)].append(index)

        groups = []
        for indexes in components.values():
            representative_index = min(
                indexes,
                key=lambda index: (
                    usable[index].rank is None,
                    usable[index].rank or 0,
                    usable[index].position,
                    usable[index].normalized_item_id,
                ),
            )
            representative = usable[representative_index]
            member_ids = sorted(usable[index].normalized_item_id for index in indexes)
            group_id = str(
                uuid5(NAMESPACE_URL, f"dedup:{run_id}:{'|'.join(member_ids)}")
            )
            index_set = set(indexes)
            members = []
            for index in indexes:
                item_edges = [
                    _edge_evidence(edge, usable, index)
                    for edge in edges
                    if index in edge[:2]
                    and edge[0] in index_set
                    and edge[1] in index_set
                ]
                item_edges.sort(
                    key=lambda value: (
                        _match_priority(value["match_kind"]),
                        value["matched_normalized_item_id"],
                    )
                )
                is_representative = index == representative_index
                members.append(
                    DedupMember(
                        normalized_item_id=usable[index].normalized_item_id,
                        is_representative=is_representative,
                        match_kind=(
                            "representative"
                            if is_representative
                            else item_edges[0]["match_kind"]
                            if item_edges
                            else "transitive"
                        ),
                        evidence=tuple(item_edges),
                    )
                )
            groups.append(
                DedupGroup(
                    group_id=group_id,
                    normalization_run_id=run_id,
                    snapshot_id=snapshot_id,
                    algorithm_version=self.rules.dedup_algorithm_version,
                    representative_normalized_item_id=representative.normalized_item_id,
                    members=tuple(members),
                )
            )
        return tuple(sorted(groups, key=lambda group: group.group_id))


def normalize_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).translate(PUNCTUATION_TRANSLATION)
    normalized = re.sub(r"[‐‑‒–—―]+", "-", normalized)
    normalized = "".join(
        character for character in normalized if unicodedata.category(character) != "Cf"
    )
    return " ".join(normalized.split()).strip()


def strict_title_fingerprint(value: str) -> str:
    normalized = normalize_title(value).casefold()
    return "".join(
        character
        for character in normalized
        if not character.isspace()
        and not unicodedata.category(character).startswith("P")
    )


def normalize_external_id(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = normalize_title(value).casefold()
    return normalized or None


def canonicalize_url(value: str, tracking_parameters: frozenset[str]) -> str | None:
    raw = unicodedata.normalize("NFKC", value).strip()
    if not raw:
        return None
    try:
        parsed = urlsplit(raw)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username is not None or parsed.password is not None:
            return None
        hostname = parsed.hostname.encode("idna").decode("ascii").casefold()
        port = parsed.port
    except (UnicodeError, ValueError):
        return None
    scheme = parsed.scheme.casefold()
    if (
        port is None
        or (scheme == "http" and port == 80)
        or (scheme == "https" and port == 443)
    ):
        netloc = hostname
    else:
        netloc = f"{hostname}:{port}"
    path = quote(unquote(parsed.path or "/"), safe="/:@-._~!$&'()*+,;=")
    query = [
        (key, item_value)
        for key, item_value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.casefold() not in tracking_parameters
        and not key.casefold().startswith("utm_")
    ]
    query.sort(key=lambda item: (item[0].casefold(), item[0], item[1]))
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def normalize_hot_score(
    value: str | None,
    multipliers,
) -> tuple[str | None, str | None]:
    if value is None or not str(value).strip():
        return None, None
    compact = str(value).replace(",", "").replace(" ", "").strip()
    match = HOT_SCORE_PATTERN.fullmatch(compact)
    if match is None:
        return None, None
    unit = match.group("unit")
    normalized_unit = unit.casefold() if unit.isascii() else unit
    multiplier = multipliers.get(normalized_unit)
    if multiplier is None:
        return None, None
    try:
        normalized = Decimal(match.group("number")) * multiplier
    except InvalidOperation:
        return None, None
    rendered = format(normalized, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered, unit or None


def parse_platform_time(
    value,
    observed_at: datetime,
) -> tuple[datetime, PublishedAtPrecision] | None:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc), PublishedAtPrecision.EXACT
    if isinstance(value, (int, float)) or (
        isinstance(value, str) and re.fullmatch(r"\d{10,13}", value.strip())
    ):
        numeric = float(value)
        if numeric > 10_000_000_000:
            numeric /= 1000
        try:
            return (
                datetime.fromtimestamp(numeric, tz=timezone.utc),
                PublishedAtPrecision.EXACT,
            )
        except (OSError, OverflowError, ValueError):
            return None

    text = normalize_title(str(value))
    if not text:
        return None
    observed_local = observed_at.astimezone(SHANGHAI)
    if text == "刚刚":
        return observed_at.astimezone(timezone.utc), PublishedAtPrecision.MINUTE
    relative = RELATIVE_PATTERN.fullmatch(text)
    if relative:
        count = int(relative.group("count"))
        unit = relative.group("unit")
        delta = {
            "分钟": timedelta(minutes=count),
            "小时": timedelta(hours=count),
            "天": timedelta(days=count),
        }[unit]
        return (
            (observed_local - delta).astimezone(timezone.utc),
            PublishedAtPrecision.MINUTE if unit != "天" else PublishedAtPrecision.DAY,
        )
    yesterday = YESTERDAY_PATTERN.fullmatch(text)
    if yesterday:
        local = observed_local - timedelta(days=1)
        if yesterday.group("hour") is None:
            local = local.replace(hour=0, minute=0, second=0, microsecond=0)
            precision = PublishedAtPrecision.DAY
        else:
            local = local.replace(
                hour=int(yesterday.group("hour")),
                minute=int(yesterday.group("minute")),
                second=0,
                microsecond=0,
            )
            precision = PublishedAtPrecision.MINUTE
        return local.astimezone(timezone.utc), precision
    month_day = MONTH_DAY_PATTERN.fullmatch(text)
    if month_day:
        try:
            local = datetime(
                observed_local.year,
                int(month_day.group("month")),
                int(month_day.group("day")),
                int(month_day.group("hour") or 0),
                int(month_day.group("minute") or 0),
                tzinfo=SHANGHAI,
            )
        except ValueError:
            return None
        if local > observed_local + timedelta(days=1):
            local = local.replace(year=local.year - 1)
        precision = (
            PublishedAtPrecision.MINUTE
            if month_day.group("hour") is not None
            else PublishedAtPrecision.DAY
        )
        return local.astimezone(timezone.utc), precision
    iso_candidate = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(iso_candidate)
    except ValueError:
        parsed = None
    if parsed is not None:
        precision = (
            PublishedAtPrecision.DAY
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text)
            else PublishedAtPrecision.EXACT
        )
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=SHANGHAI)
        return parsed.astimezone(timezone.utc), precision
    return None


def _dedup_keys(item: NormalizedHotItem):
    platform = item.platform.value
    if item.external_id_normalized:
        yield (
            "external_id",
            f"{platform}\0{item.provider_id}\0{item.external_id_normalized}",
        )
    if item.canonical_url:
        yield "canonical_url", f"{platform}\0{item.canonical_url}"
    if item.title_fingerprint:
        yield "strict_title", f"{platform}\0{item.title_fingerprint}"


def _evidence_hash(kind: str, scoped_value: str) -> str:
    return hashlib.sha256(f"{kind}\0{scoped_value}".encode()).hexdigest()


def _edge_evidence(edge, items, current_index: int) -> dict[str, str]:
    left, right, kind, value_hash = edge
    other_index = right if current_index == left else left
    return {
        "match_kind": kind,
        "matched_normalized_item_id": items[other_index].normalized_item_id,
        "value_sha256": value_hash,
    }


def _match_priority(kind: str) -> int:
    return {"external_id": 0, "canonical_url": 1, "strict_title": 2}.get(kind, 99)
