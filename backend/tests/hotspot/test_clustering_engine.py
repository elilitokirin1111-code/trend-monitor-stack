from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.clustering import (
    ClusteringRules,
    HotspotEventClusterer,
    SemanticBoundaryResult,
)
from app.domain.hotspot import (
    CandidateDecision,
    ClusterInputItem,
    Platform,
    SemanticStatus,
)

AT = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)


def _item(
    number: int,
    title: str,
    *,
    platform: Platform = Platform.WEIBO,
    observed_at: datetime = AT,
    url: str | None = None,
) -> ClusterInputItem:
    return ClusterInputItem(
        group_id=f"group-{number}",
        normalization_run_id=f"normalization-{number}",
        normalized_item_id=f"normalized-{number}",
        snapshot_id=f"snapshot-{number}",
        platform=platform,
        provider_id="provider",
        normalized_title=title,
        title_fingerprint="".join(
            character for character in title if character.isalnum()
        ),
        canonical_url=url,
        rank=number,
        observed_at=observed_at,
        published_at=None,
    )


class _RecordingJudge:
    def __init__(self, same_event: bool = True) -> None:
        self.same_event = same_event
        self.calls: list[tuple[str, str]] = []

    async def judge(self, left, right, evidence):
        self.calls.append((left.group_id, right.group_id))
        return SemanticBoundaryResult(
            same_event=self.same_event,
            confidence=Decimal("0.91"),
            reason="same incident" if self.same_event else "different incidents",
            model_id="test-boundary-judge",
        )


def test_exact_cross_platform_titles_form_one_auditable_event() -> None:
    items = (
        _item(1, "台风登陆广东", platform=Platform.WEIBO),
        _item(2, "台风登陆广东", platform=Platform.BILIBILI),
    )

    batch = asyncio.run(HotspotEventClusterer().cluster(items))

    assert batch.input_group_count == 2
    assert len(batch.candidates) == 1
    assert batch.candidates[0].decision is CandidateDecision.ACCEPTED
    assert batch.candidates[0].semantic_status is SemanticStatus.NOT_REQUESTED
    assert len(batch.events) == 1
    assert batch.events[0].platforms == (Platform.WEIBO, Platform.BILIBILI)
    assert {member.group_id for member in batch.events[0].members} == {
        "group-1",
        "group-2",
    }


def test_time_window_prevents_old_topics_from_becoming_candidates() -> None:
    items = (
        _item(1, "某景区发布暑期新规", observed_at=AT),
        _item(
            2,
            "某景区发布暑期新规",
            platform=Platform.BILIBILI,
            observed_at=AT + timedelta(hours=37),
        ),
    )

    batch = asyncio.run(HotspotEventClusterer().cluster(items))

    assert batch.candidates == ()
    assert len(batch.events) == 2


def test_only_gray_zone_candidates_call_semantic_boundary_judge() -> None:
    rules = ClusteringRules(
        semantic_enabled=True,
        semantic_lower_threshold=Decimal("0.25"),
        accept_threshold=Decimal("0.99"),
    )
    judge = _RecordingJudge()
    items = (
        _item(1, "广州暴雨多个景区临时关闭", platform=Platform.WEIBO),
        _item(2, "广州强降雨景点临时闭园", platform=Platform.BILIBILI),
        _item(3, "新能源汽车销量创新高", platform=Platform.DOUYIN),
    )

    batch = asyncio.run(HotspotEventClusterer(rules, judge).cluster(items))

    semantic_candidates = [
        candidate
        for candidate in batch.candidates
        if candidate.semantic_status is SemanticStatus.COMPLETED
    ]
    assert len(judge.calls) == len(semantic_candidates) == 1
    assert semantic_candidates[0].decision is CandidateDecision.SEMANTIC_ACCEPTED
    assert len(batch.events) == 2


def test_semantic_failure_is_recorded_and_conservatively_rejected() -> None:
    class FailingJudge:
        async def judge(self, left, right, evidence):
            raise TimeoutError("boundary timeout")

    rules = ClusteringRules(
        semantic_enabled=True,
        semantic_lower_threshold=Decimal("0.20"),
        accept_threshold=Decimal("0.99"),
    )
    items = (
        _item(1, "上海酒店暑期价格上涨", platform=Platform.WEIBO),
        _item(2, "上海暑期酒店房价上升", platform=Platform.DOUYIN),
    )

    batch = asyncio.run(HotspotEventClusterer(rules, FailingJudge()).cluster(items))

    assert len(batch.candidates) == 1
    assert batch.candidates[0].decision is CandidateDecision.DEGRADED_REJECTED
    assert batch.candidates[0].semantic_status is SemanticStatus.ERROR
    assert "TimeoutError" in (batch.candidates[0].semantic_error or "")
    assert batch.status.value == "degraded"
    assert len(batch.events) == 2


def test_candidate_recall_is_bounded_and_does_not_compare_all_pairs() -> None:
    rules = ClusteringRules(
        max_candidates_per_item=5,
        min_shared_ngrams=1,
        max_postings_per_key=25,
    )
    items = tuple(
        _item(
            number,
            f"酒店暑期套餐城市{number:04d}",
            platform=(Platform.WEIBO if number % 2 else Platform.DOUYIN),
            observed_at=AT + timedelta(minutes=number % 30),
        )
        for number in range(1, 1001)
    )

    batch = asyncio.run(HotspotEventClusterer(rules).cluster(items))

    assert batch.candidate_pair_count <= len(items) * rules.max_candidates_per_item
    assert batch.candidate_pair_count < len(items) * (len(items) - 1) // 100
    assert batch.semantic_call_count == 0
    assert batch.truncated_candidate_count > 0


def test_replay_is_deterministic_for_same_inputs_and_config() -> None:
    items = (
        _item(1, "暑期文旅消费升温", platform=Platform.WEIBO),
        _item(2, "暑期文旅消费升温", platform=Platform.XIAOHONGSHU),
    )
    clusterer = HotspotEventClusterer()

    first = asyncio.run(clusterer.cluster(items))
    second = asyncio.run(clusterer.cluster(tuple(reversed(items))))

    assert first.clustering_run_id == second.clustering_run_id
    assert first.input_hash == second.input_hash
    assert [event.event_id for event in first.events] == [
        event.event_id for event in second.events
    ]
    assert first.candidates == second.candidates
