from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.hotspot import (
    NormalizationStatus,
    Platform,
    PublishedAtPrecision,
    SnapshotRawItem,
)
from app.normalization import HotspotNormalizer, NormalizationRules
from app.normalization import engine as engine_module
from app.normalization.engine import (
    canonicalize_url,
    normalize_hot_score,
    normalize_title,
    parse_platform_time,
    strict_title_fingerprint,
)

AT = datetime(2026, 8, 14, 8, 30, tzinfo=timezone.utc)


def _raw(
    raw_id: str,
    *,
    title: str = "酒店暑期套餐",
    url: str = "https://example.test/topic",
    external_id: str | None = None,
    provider_id: str = "newsnow",
    rank: int | None = 1,
    hot_score: str | None = "1.2万",
    raw_data: dict | None = None,
    platform: Platform = Platform.WEIBO,
    position: int = 1,
) -> SnapshotRawItem:
    return SnapshotRawItem(
        snapshot_id="snapshot-1",
        raw_item_id=raw_id,
        position=position,
        platform=platform,
        provider_id=provider_id,
        title=title,
        url=url,
        external_id=external_id,
        rank=rank,
        hot_score=hot_score,
        published_at=None,
        observed_at=AT,
        raw_data=raw_data or {},
    )


def test_title_normalization_is_unicode_aware_but_fingerprint_is_strict() -> None:
    title = "  Ａ酒店\u200b　暑期——套餐！  "

    normalized = normalize_title(title)

    assert normalized == "A酒店 暑期-套餐!"
    assert strict_title_fingerprint(normalized) == "a酒店暑期套餐"


def test_url_canonicalization_removes_tracking_fragment_and_sorts_query() -> None:
    result = canonicalize_url(
        "HTTPS://例子.测试:443/a%20b?z=2&utm_source=x&a=1#detail",
        frozenset(),
    )

    assert result == "https://xn--fsqu00a.xn--0zwm56d/a%20b?a=1&z=2"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "https://user:secret@example.test/path",
        "https://example.test:invalid/path",
        "not-a-url",
    ],
)
def test_url_canonicalization_rejects_unsafe_or_invalid_values(url: str) -> None:
    assert canonicalize_url(url, frozenset()) is None


@pytest.mark.parametrize(
    "raw, expected, unit",
    [
        ("1,234", "1234", None),
        ("1.25万", "12500", "万"),
        ("2亿热度", "200000000", "亿"),
        ("3K", "3000", "K"),
        ("0", "0", None),
    ],
)
def test_hot_score_normalization_is_decimal_and_lossless(raw, expected, unit) -> None:
    result, parsed_unit = normalize_hot_score(
        raw, NormalizationRules().hot_score_multipliers
    )

    assert result == expected
    assert parsed_unit == unit


def test_unknown_hot_score_unit_is_not_guessed() -> None:
    assert normalize_hot_score("12千", NormalizationRules().hot_score_multipliers) == (
        None,
        None,
    )


@pytest.mark.parametrize(
    "raw, expected, precision",
    [
        (
            "30分钟前",
            datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc),
            PublishedAtPrecision.MINUTE,
        ),
        (
            "昨天 10:15",
            datetime(2026, 8, 13, 2, 15, tzinfo=timezone.utc),
            PublishedAtPrecision.MINUTE,
        ),
        (
            "08-14",
            datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc),
            PublishedAtPrecision.DAY,
        ),
        (
            "2026-08-14T08:20:00Z",
            datetime(2026, 8, 14, 8, 20, tzinfo=timezone.utc),
            PublishedAtPrecision.EXACT,
        ),
        (
            "1786695600000",
            datetime.fromtimestamp(1786695600, tz=timezone.utc),
            PublishedAtPrecision.EXACT,
        ),
    ],
)
def test_platform_time_parser_uses_observation_as_relative_anchor(
    raw,
    expected,
    precision,
) -> None:
    assert parse_platform_time(raw, AT) == (expected, precision)


def test_invalid_time_is_not_fabricated() -> None:
    assert parse_platform_time("三小时前", AT) is None


def test_normalizer_records_partial_warnings_without_losing_item() -> None:
    normalizer = HotspotNormalizer(
        NormalizationRules(),
        clock=lambda: AT,
        run_id_factory=lambda: "normalization-run",
    )
    source = _raw(
        "raw-1",
        url="bad-url",
        hot_score="未知",
        raw_data={"time": "三小时前"},
    )

    batch = normalizer.normalize_snapshot("snapshot-1", (source,))

    item = batch.items[0]
    assert item.status is NormalizationStatus.PARTIAL
    assert item.warnings == (
        "invalid_url",
        "invalid_hot_score",
        "invalid_published_at",
    )
    assert len(batch.groups) == 1
    assert batch.groups[0].members[0].match_kind == "representative"


def test_empty_normalized_title_is_failed_and_excluded_from_dedup() -> None:
    normalizer = HotspotNormalizer(
        NormalizationRules(),
        clock=lambda: AT,
        run_id_factory=lambda: "normalization-run",
    )

    batch = normalizer.normalize_snapshot(
        "snapshot-1", (_raw("raw-1", title="\u200b"),)
    )

    assert batch.items[0].status is NormalizationStatus.FAILED
    assert batch.items[0].error_code == "empty_title"
    assert batch.groups == ()
    assert batch.status is NormalizationStatus.FAILED


def test_dedup_uses_linear_key_indexes_and_preserves_match_evidence() -> None:
    normalizer = HotspotNormalizer(
        NormalizationRules(),
        clock=lambda: AT,
        run_id_factory=lambda: "normalization-run",
    )
    first = _raw(
        "raw-a",
        external_id="same-id",
        title="标题甲",
        url="https://example.test/a",
        rank=3,
        position=1,
    )
    second = _raw(
        "raw-b",
        external_id="same-id",
        title="标题乙",
        url="https://example.test/b",
        rank=1,
        position=2,
    )
    third = _raw(
        "raw-c",
        external_id="other-id",
        title="标题丙",
        url="https://example.test/b?utm_source=share",
        rank=2,
        position=3,
    )

    batch = normalizer.normalize_snapshot("snapshot-1", (first, second, third))

    assert len(batch.groups) == 1
    group = batch.groups[0]
    representative = next(
        member for member in group.members if member.is_representative
    )
    assert representative.normalized_item_id == batch.items[1].normalized_item_id
    match_kinds = {
        evidence["match_kind"]
        for member in group.members
        for evidence in member.evidence
    }
    assert match_kinds == {"external_id", "canonical_url"}
    assert all(
        len(evidence["value_sha256"]) == 64
        for member in group.members
        for evidence in member.evidence
    )


def test_external_ids_are_scoped_by_provider_and_titles_by_platform() -> None:
    normalizer = HotspotNormalizer(
        NormalizationRules(),
        clock=lambda: AT,
        run_id_factory=lambda: "normalization-run",
    )
    items = (
        _raw(
            "raw-a",
            external_id="same",
            provider_id="newsnow",
            title="微博标题",
            url="https://a.test/1",
            platform=Platform.WEIBO,
            position=1,
        ),
        _raw(
            "raw-b",
            external_id="same",
            provider_id="dailyhotapi",
            title="另一个微博标题",
            url="https://b.test/2",
            platform=Platform.WEIBO,
            position=2,
        ),
        _raw(
            "raw-c",
            external_id="other",
            provider_id="newsnow",
            title="微博标题",
            url="https://c.test/3",
            platform=Platform.BILIBILI,
            position=3,
        ),
    )

    batch = normalizer.normalize_snapshot("snapshot-1", items)

    assert len(batch.groups) == 3


def test_month_day_in_future_rolls_back_one_year() -> None:
    observed = datetime(2026, 1, 2, 2, 0, tzinfo=timezone.utc)

    parsed = parse_platform_time("12-31 09:00", observed)

    assert parsed == (
        datetime(2025, 12, 31, 1, 0, tzinfo=timezone.utc),
        PublishedAtPrecision.MINUTE,
    )


def test_existing_aware_published_at_wins_over_raw_relative_field() -> None:
    source = _raw("raw-1", raw_data={"time": "30分钟前"})
    object.__setattr__(source, "published_at", AT - timedelta(days=2))
    normalizer = HotspotNormalizer(
        NormalizationRules(),
        clock=lambda: AT,
        run_id_factory=lambda: "normalization-run",
    )

    item = normalizer.normalize_snapshot("snapshot-1", (source,)).items[0]

    assert item.published_at == AT - timedelta(days=2)
    assert item.published_at_precision is PublishedAtPrecision.EXACT


def test_dedup_key_extraction_scales_once_per_item(monkeypatch) -> None:
    calls = 0
    original = engine_module._dedup_keys

    def counting_keys(item):
        nonlocal calls
        calls += 1
        yield from original(item)

    monkeypatch.setattr(engine_module, "_dedup_keys", counting_keys)
    normalizer = HotspotNormalizer(
        NormalizationRules(),
        clock=lambda: AT,
        run_id_factory=lambda: "scale-run",
    )
    items = tuple(
        _raw(
            f"raw-{index}",
            external_id=f"external-{index}",
            title=f"唯一标题 {index}",
            url=f"https://example.test/{index}",
            position=index + 1,
        )
        for index in range(2000)
    )

    batch = normalizer.normalize_snapshot("snapshot-1", items)

    assert calls == 2000
    assert len(batch.groups) == 2000
