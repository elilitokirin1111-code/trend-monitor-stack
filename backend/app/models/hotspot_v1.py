"""Stable response contracts for the Phase 8 read-only API."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from app.models.hotspot_annotations import (
    EventAnnotationView,
    KnowledgeIntegrationStatus,
    KnowledgeSyncView,
)


class DashboardModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ProviderAttemptView(DashboardModel):
    provider_id: str
    attempt_number: int
    status: str
    freshness: str
    item_count: int
    error_code: str | None = None
    error_message: str | None = None


class CollectionErrorView(DashboardModel):
    kind: str | None = None
    code: str | None = None
    message: str | None = None
    retryable: bool = False
    upstream_status: int | None = None


class PlatformHealthView(DashboardModel):
    platform: Literal["douyin", "weibo", "bilibili", "xiaohongshu"]
    status: Literal["fresh", "stale", "failed", "unavailable"]
    freshness: Literal["fresh", "stale", "unknown"]
    data_age_minutes: int | None = None
    last_run_at: str | None = None
    snapshot_id: str | None = None
    snapshot_observed_at: str | None = None
    winning_provider_id: str | None = None
    fallback_used: bool
    stale_reason: str | None = None
    error: CollectionErrorView | None = None
    attempts: list[ProviderAttemptView]


class TrendRunView(DashboardModel):
    trend_run_id: str
    evaluated_at: str
    status: str
    event_count: int
    complete_count: int
    partial_count: int
    algorithm_version: str


class HotspotOverviewResponse(DashboardModel):
    generated_at: str
    has_data: bool
    event_count: int
    trend_run: TrendRunView | None = None
    platforms: list[PlatformHealthView]


class ClassificationView(DashboardModel):
    status: str
    topic_category: str | None = None
    tags: list[str]
    hospitality_relevance: str | None = None
    hospitality_score: float | None = None
    confidence: float | None = None
    rationale: str | None = None
    summary: str | None = None
    evidence_ids: list[str]


class EventSummaryView(DashboardModel):
    event_id: str
    trend_state_id: str
    trend_series_id: str
    canonical_title: str
    lifecycle_state: str
    previous_state: str | None = None
    trend_score: float
    data_quality: str
    evaluated_at: str
    first_seen_at: str
    last_seen_at: str
    platforms: list[str]
    platform_count: int
    member_count: int
    observation_count: int
    fresh_observation_count: int
    stale_observation_count: int
    fresh_platform_count: int
    failed_platform_count: int
    stale_platform_count: int
    missing_platform_count: int
    data_completeness: float
    velocity: float
    acceleration: float
    latest_fresh_age_hours: float | None = None
    classification: ClassificationView | None = None
    detail_url: str


class HotspotEventListResponse(DashboardModel):
    trend_run_id: str | None = None
    classification_run_id: str | None = None
    total: int
    limit: int
    offset: int
    items: list[EventSummaryView]


class EventMemberView(DashboardModel):
    group_id: str
    normalized_item_id: str
    snapshot_id: str
    platform: str
    is_representative: bool
    title: str | None = None
    source_url: str | None = None
    rank: int | None = None
    hot_score: str | None = None
    hot_score_unit: str | None = None


class EventEvidenceView(DashboardModel):
    group_id: str
    normalized_item_id: str
    raw_item_id: str
    raw_item_url: str
    platform: str
    provider_id: str
    title: str
    source_url: str
    rank: int | None = None
    hot_score: str | None = None
    freshness: str
    observed_at: str
    fetched_at: str
    match_kind: str
    dedup_evidence: Any


class HotspotEventDetailResponse(EventSummaryView):
    members: list[EventMemberView]
    evidence: list[EventEvidenceView]
    annotation: EventAnnotationView | None = None
    knowledge_sync: KnowledgeSyncView | None = None
    knowledge_integration: KnowledgeIntegrationStatus


class RawHotItemResponse(DashboardModel):
    raw_item_id: str
    run_id: str
    platform: str
    provider_id: str
    provider_attempt_number: int | None = None
    source_item_position: int
    is_selected: bool
    freshness: str
    external_id: str | None = None
    title: str
    url: str
    rank: int | None = None
    hot_score: str | None = None
    published_at: str | None = None
    observed_at: str
    fetched_at: str
    raw_data: Any
    raw_payload_sha256: str | None = None
