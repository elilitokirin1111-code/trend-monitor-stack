"""Bounded candidate recall and deterministic cross-platform event clustering."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from difflib import SequenceMatcher

from app.domain.hotspot import (
    CandidateDecision,
    ClusterCandidate,
    ClusteringBatch,
    ClusterInputItem,
    EventCluster,
    EventMember,
    Platform,
    SemanticStatus,
    utc_now,
)

from .rules import ClusteringRules
from .semantic import SemanticBoundaryJudge, SemanticBoundaryResult

_CHINESE_CHARACTER = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")
_ASCII_WORD = re.compile(r"[a-z0-9]+")
_SCORE_QUANTUM = Decimal("0.000001")


class HotspotEventClusterer:
    def __init__(
        self,
        rules: ClusteringRules | None = None,
        semantic_judge: SemanticBoundaryJudge | None = None,
    ) -> None:
        self.rules = rules or ClusteringRules()
        self._semantic_judge = semantic_judge

    async def cluster(
        self,
        input_items: tuple[ClusterInputItem, ...],
        *,
        normalization_config_hash: str = "0" * 64,
    ) -> ClusteringBatch:
        if not input_items:
            raise ValueError("event clustering requires at least one input group")
        items = tuple(
            sorted(input_items, key=lambda item: (item.observed_at, item.group_id))
        )
        group_ids = [item.group_id for item in items]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("clustering input group identifiers must be unique")

        started_at = utc_now()
        input_hash = _input_hash(items)
        run_id = _identifier(
            "clustering-run",
            self.rules.algorithm_version,
            self.rules.config_hash,
            normalization_config_hash,
            input_hash,
        )
        recalled, truncated_count = self._recall(items)
        union = _UnionFind(group_ids)
        candidates: list[ClusterCandidate] = []
        semantic_calls = 0

        for left_index, right_index, reasons in recalled:
            left = items[left_index]
            right = items[right_index]
            components, score = self._score(left, right)
            decision = CandidateDecision.REJECTED
            semantic_status = SemanticStatus.NOT_REQUESTED
            semantic_result: SemanticBoundaryResult | None = None
            semantic_error: str | None = None

            if score >= self.rules.accept_threshold:
                decision = CandidateDecision.ACCEPTED
            elif score >= self.rules.semantic_lower_threshold:
                if not self.rules.semantic_enabled:
                    decision = CandidateDecision.REJECTED
                elif semantic_calls >= self.rules.max_semantic_calls:
                    decision = CandidateDecision.DEGRADED_REJECTED
                    semantic_status = SemanticStatus.BUDGET_EXHAUSTED
                    semantic_error = "semantic call budget exhausted"
                elif self._semantic_judge is None:
                    decision = CandidateDecision.DEGRADED_REJECTED
                    semantic_status = SemanticStatus.UNAVAILABLE
                    semantic_error = "semantic boundary judge is not configured"
                else:
                    semantic_calls += 1
                    try:
                        result = await self._semantic_judge.judge(
                            left,
                            right,
                            components,
                        )
                        if not isinstance(result, SemanticBoundaryResult):
                            raise TypeError(
                                "semantic judge returned an invalid result type"
                            )
                        semantic_result = result
                        semantic_status = SemanticStatus.COMPLETED
                        decision = (
                            CandidateDecision.SEMANTIC_ACCEPTED
                            if result.same_event
                            else CandidateDecision.SEMANTIC_REJECTED
                        )
                    except (TypeError, ValueError) as exc:
                        decision = CandidateDecision.DEGRADED_REJECTED
                        semantic_status = SemanticStatus.INVALID
                        semantic_error = f"{type(exc).__name__}: {exc}"
                    except Exception as exc:  # noqa: BLE001 - isolate model boundary
                        decision = CandidateDecision.DEGRADED_REJECTED
                        semantic_status = SemanticStatus.ERROR
                        semantic_error = f"{type(exc).__name__}: {exc}"

            candidate = ClusterCandidate(
                candidate_id=_identifier(
                    "candidate", run_id, left.group_id, right.group_id
                ),
                clustering_run_id=run_id,
                left_group_id=left.group_id,
                right_group_id=right.group_id,
                recall_reasons=reasons,
                components=components,
                deterministic_score=score,
                decision=decision,
                semantic_status=semantic_status,
                semantic_same_event=(
                    semantic_result.same_event if semantic_result else None
                ),
                semantic_confidence=(
                    semantic_result.confidence if semantic_result else None
                ),
                semantic_reason=(semantic_result.reason if semantic_result else None),
                semantic_model_id=(
                    semantic_result.model_id if semantic_result else None
                ),
                semantic_error=semantic_error,
            )
            candidates.append(candidate)
            if decision in {
                CandidateDecision.ACCEPTED,
                CandidateDecision.SEMANTIC_ACCEPTED,
            }:
                union.union(left.group_id, right.group_id)

        events = self._events(items, union, run_id)
        finished_at = utc_now()
        window_end = max(item.observed_at for item in items)
        return ClusteringBatch(
            clustering_run_id=run_id,
            algorithm_version=self.rules.algorithm_version,
            config_hash=self.rules.config_hash,
            config_json=self.rules.config_json,
            normalization_rule_version=self.rules.normalization_rule_version,
            normalization_config_hash=normalization_config_hash,
            input_hash=input_hash,
            window_start=window_end - timedelta(hours=self.rules.lookback_hours),
            window_end=window_end,
            started_at=started_at,
            finished_at=finished_at,
            input_group_count=len(items),
            candidate_pair_count=len(candidates),
            truncated_candidate_count=truncated_count,
            semantic_call_count=semantic_calls,
            candidates=tuple(candidates),
            events=events,
        )

    def _recall(
        self, items: tuple[ClusterInputItem, ...]
    ) -> tuple[tuple[tuple[int, int, tuple[str, ...]], ...], int]:
        exact_titles: dict[str, deque[int]] = defaultdict(
            lambda: deque(maxlen=self.rules.max_postings_per_key)
        )
        canonical_urls: dict[str, deque[int]] = defaultdict(
            lambda: deque(maxlen=self.rules.max_postings_per_key)
        )
        ngram_postings: dict[str, deque[int]] = defaultdict(
            lambda: deque(maxlen=self.rules.max_postings_per_key)
        )
        recalled: list[tuple[int, int, tuple[str, ...]]] = []
        truncated_count = 0
        window = timedelta(hours=self.rules.candidate_window_hours)

        for right_index, right in enumerate(items):
            right_ngrams = _ngrams(right.title_fingerprint, self.rules.ngram_size)
            shared_counts: dict[int, int] = defaultdict(int)
            exact_reasons: dict[int, set[str]] = defaultdict(set)

            for left_index in exact_titles[right.title_fingerprint]:
                exact_reasons[left_index].add("exact_title")
            if right.canonical_url:
                for left_index in canonical_urls[right.canonical_url]:
                    exact_reasons[left_index].add("canonical_url")
            for gram in right_ngrams:
                for left_index in ngram_postings[gram]:
                    shared_counts[left_index] += 1

            eligible: list[tuple[int, int, set[str]]] = []
            for left_index in set(shared_counts) | set(exact_reasons):
                left = items[left_index]
                if right.observed_at - left.observed_at > window:
                    continue
                if left.snapshot_id == right.snapshot_id:
                    continue
                shared = shared_counts.get(left_index, 0)
                reasons = exact_reasons.get(left_index, set()).copy()
                if shared >= self.rules.min_shared_ngrams:
                    reasons.add("title_ngram")
                if not reasons:
                    continue
                strength = shared + (10000 if reasons - {"title_ngram"} else 0)
                eligible.append((left_index, strength, reasons))

            eligible.sort(key=lambda value: (-value[1], items[value[0]].group_id))
            selected = eligible[: self.rules.max_candidates_per_item]
            truncated_count += max(0, len(eligible) - len(selected))
            for left_index, _strength, reasons in selected:
                recalled.append((left_index, right_index, tuple(sorted(reasons))))

            exact_titles[right.title_fingerprint].append(right_index)
            if right.canonical_url:
                canonical_urls[right.canonical_url].append(right_index)
            for gram in right_ngrams:
                ngram_postings[gram].append(right_index)

        return tuple(recalled), truncated_count

    def _score(
        self, left: ClusterInputItem, right: ClusterInputItem
    ) -> tuple[dict[str, str], Decimal]:
        if left.title_fingerprint == right.title_fingerprint or (
            left.canonical_url
            and right.canonical_url
            and left.canonical_url == right.canonical_url
        ):
            components = {
                "exact_title": str(
                    int(left.title_fingerprint == right.title_fingerprint)
                ),
                "exact_url": str(
                    int(
                        bool(left.canonical_url)
                        and left.canonical_url == right.canonical_url
                    )
                ),
                "keyword": "1.000000",
                "ngram": "1.000000",
                "sequence": "1.000000",
                "time": _time_similarity(left, right, self.rules),
            }
            return components, Decimal(1)

        sequence = Decimal(
            str(
                SequenceMatcher(
                    None, left.title_fingerprint, right.title_fingerprint
                ).ratio()
            )
        )
        ngram = _jaccard(
            _ngrams(left.title_fingerprint, self.rules.ngram_size),
            _ngrams(right.title_fingerprint, self.rules.ngram_size),
        )
        keyword = _jaccard(
            _keywords(left.title_fingerprint), _keywords(right.title_fingerprint)
        )
        time = Decimal(_time_similarity(left, right, self.rules))
        values = {
            "sequence": sequence,
            "ngram": ngram,
            "keyword": keyword,
            "time": time,
        }
        score = sum(
            (values[key] * self.rules.weights[key] for key in values), Decimal(0)
        ).quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)
        components = {
            "exact_title": "0",
            "exact_url": "0",
            **{
                key: str(value.quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP))
                for key, value in values.items()
            },
        }
        return components, score

    @staticmethod
    def _events(
        items: tuple[ClusterInputItem, ...],
        union: _UnionFind,
        run_id: str,
    ) -> tuple[EventCluster, ...]:
        groups: dict[str, list[ClusterInputItem]] = defaultdict(list)
        for item in items:
            groups[union.find(item.group_id)].append(item)

        events: list[EventCluster] = []
        for members in groups.values():
            members.sort(key=_representative_key)
            representative = members[0]
            member_ids = tuple(sorted(member.group_id for member in members))
            event_id = _identifier("event", run_id, *member_ids)
            event_members = tuple(
                EventMember(
                    group_id=member.group_id,
                    normalized_item_id=member.normalized_item_id,
                    snapshot_id=member.snapshot_id,
                    platform=member.platform,
                    is_representative=member.group_id == representative.group_id,
                )
                for member in sorted(members, key=lambda value: value.group_id)
            )
            platforms = tuple(
                platform
                for platform in Platform
                if any(member.platform is platform for member in members)
            )
            events.append(
                EventCluster(
                    event_id=event_id,
                    clustering_run_id=run_id,
                    canonical_title=representative.normalized_title,
                    representative_group_id=representative.group_id,
                    representative_normalized_item_id=(
                        representative.normalized_item_id
                    ),
                    first_seen_at=min(member.observed_at for member in members),
                    last_seen_at=max(member.observed_at for member in members),
                    platforms=platforms,
                    members=event_members,
                )
            )
        return tuple(sorted(events, key=lambda event: event.event_id))


class _UnionFind:
    def __init__(self, values: list[str]) -> None:
        self._parent = {value: value for value in values}

    def find(self, value: str) -> str:
        root = value
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[value] != value:
            parent = self._parent[value]
            self._parent[value] = root
            value = parent
        return root

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        first, second = sorted((left_root, right_root))
        self._parent[second] = first


def _representative_key(item: ClusterInputItem) -> tuple[int, object, str]:
    return (
        item.rank if item.rank is not None else 2**31,
        item.observed_at,
        item.group_id,
    )


def _ngrams(value: str, size: int) -> frozenset[str]:
    normalized = value.casefold()
    if len(normalized) <= size:
        return frozenset({normalized}) if normalized else frozenset()
    return frozenset(
        normalized[index : index + size] for index in range(len(normalized) - size + 1)
    )


def _keywords(value: str) -> frozenset[str]:
    normalized = value.casefold()
    return frozenset(_ASCII_WORD.findall(normalized)) | frozenset(
        _CHINESE_CHARACTER.findall(normalized)
    )


def _jaccard(left: frozenset[str], right: frozenset[str]) -> Decimal:
    if not left and not right:
        return Decimal(1)
    union = left | right
    return Decimal(len(left & right)) / Decimal(len(union)) if union else Decimal(0)


def _time_similarity(
    left: ClusterInputItem,
    right: ClusterInputItem,
    rules: ClusteringRules,
) -> str:
    window_seconds = Decimal(rules.candidate_window_hours * 3600)
    delta = Decimal(str(abs((right.observed_at - left.observed_at).total_seconds())))
    value = max(Decimal(0), Decimal(1) - (delta / window_seconds))
    return str(value.quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP))


def _input_hash(items: tuple[ClusterInputItem, ...]) -> str:
    body = json.dumps(
        [
            {
                "canonical_url": item.canonical_url,
                "group_id": item.group_id,
                "normalization_run_id": item.normalization_run_id,
                "normalized_item_id": item.normalized_item_id,
                "normalized_title": item.normalized_title,
                "observed_at": item.observed_at.isoformat(),
                "platform": item.platform.value,
                "snapshot_id": item.snapshot_id,
                "title_fingerprint": item.title_fingerprint,
            }
            for item in items
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def _identifier(kind: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join((kind, *parts)).encode()).hexdigest()
    return f"{kind}-{digest}"
