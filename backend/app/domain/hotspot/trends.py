"""Immutable contracts for the versioned hotspot trend lifecycle engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from .models import CollectionStatus, Freshness, Platform
from .normalization import _require_aware


class TrendLifecycleState(str, Enum):
    EMERGING = "emerging"
    RISING = "rising"
    PEAKING = "peaking"
    DECLINING = "declining"
    DORMANT = "dormant"
    RECURRENT = "recurrent"


class TrendDataQuality(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    STALE_ONLY = "stale_only"
    NO_FRESH_DATA = "no_fresh_data"


class TrendRunStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class TrendObservation:
    group_id: str
    normalized_item_id: str
    snapshot_id: str
    platform: Platform
    observed_at: datetime
    freshness: Freshness
    rank: int | None
    hot_score: Decimal | None

    def __post_init__(self) -> None:
        if not all((self.group_id, self.normalized_item_id, self.snapshot_id)):
            raise ValueError("trend observation identifiers are required")
        _require_aware(self.observed_at, "observed_at")
        if self.rank is not None and self.rank < 1:
            raise ValueError("rank must be positive")
        if self.hot_score is not None:
            score = Decimal(str(self.hot_score))
            if not score.is_finite() or score < 0:
                raise ValueError("hot score must be a finite non-negative decimal")
            object.__setattr__(self, "hot_score", score)


@dataclass(frozen=True, slots=True)
class TrendEventInput:
    event_id: str
    clustering_run_id: str
    canonical_title: str
    representative_title_fingerprint: str
    window_start: datetime
    window_end: datetime
    observations: tuple[TrendObservation, ...]

    def __post_init__(self) -> None:
        required = (
            self.event_id,
            self.clustering_run_id,
            self.canonical_title,
            self.representative_title_fingerprint,
        )
        if any(not value for value in required):
            raise ValueError("trend event identifiers and title are required")
        _require_aware(self.window_start, "window_start")
        _require_aware(self.window_end, "window_end")
        if self.window_end < self.window_start:
            raise ValueError("trend event window is invalid")
        object.__setattr__(self, "observations", tuple(self.observations))
        if not self.observations:
            raise ValueError("trend event requires at least one observation")
        if len({item.group_id for item in self.observations}) != len(self.observations):
            raise ValueError("trend event observations must have unique group ids")
        if any(
            item.observed_at < self.window_start or item.observed_at > self.window_end
            for item in self.observations
        ):
            raise ValueError("trend observations must fit the clustering window")


@dataclass(frozen=True, slots=True)
class PlatformSignal:
    platform: Platform
    status: CollectionStatus
    freshness: Freshness
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_aware(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class TrendEvaluationContext:
    evaluation_id: str
    evaluated_at: datetime
    platform_signals: tuple[PlatformSignal, ...]

    def __post_init__(self) -> None:
        if not self.evaluation_id:
            raise ValueError("trend evaluation identifier is required")
        _require_aware(self.evaluated_at, "evaluated_at")
        object.__setattr__(self, "platform_signals", tuple(self.platform_signals))
        platforms = [signal.platform for signal in self.platform_signals]
        if len(platforms) != len(set(platforms)):
            raise ValueError("platform evaluation signals must be unique")


@dataclass(frozen=True, slots=True)
class PreviousTrendState:
    trend_series_id: str
    source_event_id: str
    state: TrendLifecycleState
    last_fresh_seen_at: datetime | None
    velocity: Decimal

    def __post_init__(self) -> None:
        if not self.trend_series_id or not self.source_event_id:
            raise ValueError("previous trend identifiers are required")
        if self.last_fresh_seen_at is not None:
            _require_aware(self.last_fresh_seen_at, "last_fresh_seen_at")
        velocity = Decimal(str(self.velocity))
        if not velocity.is_finite() or not Decimal(-1) <= velocity <= Decimal(1):
            raise ValueError("previous velocity must be between minus one and one")
        object.__setattr__(self, "velocity", velocity)


@dataclass(frozen=True, slots=True)
class TrendFeatures:
    observation_count: int
    fresh_observation_count: int
    stale_observation_count: int
    fresh_platform_count: int
    failed_platform_count: int
    stale_platform_count: int
    missing_platform_count: int
    data_completeness: Decimal
    current_strength: Decimal
    previous_strength: Decimal
    earlier_strength: Decimal
    velocity: Decimal
    acceleration: Decimal
    coverage_score: Decimal
    persistence_score: Decimal
    active_duration_hours: Decimal
    latest_fresh_age_hours: Decimal | None
    recurrence_gap_hours: Decimal | None
    first_fresh_seen_at: datetime | None
    last_fresh_seen_at: datetime | None

    def __post_init__(self) -> None:
        counts = (
            self.observation_count,
            self.fresh_observation_count,
            self.stale_observation_count,
            self.fresh_platform_count,
            self.failed_platform_count,
            self.stale_platform_count,
            self.missing_platform_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("trend feature counts cannot be negative")
        for name in (
            "data_completeness",
            "current_strength",
            "previous_strength",
            "earlier_strength",
            "coverage_score",
            "persistence_score",
        ):
            value = Decimal(str(getattr(self, name)))
            if not Decimal(0) <= value <= Decimal(1):
                raise ValueError(f"{name} must be between zero and one")
            object.__setattr__(self, name, value)
        for name in ("velocity", "acceleration"):
            value = Decimal(str(getattr(self, name)))
            if not Decimal(-2) <= value <= Decimal(2):
                raise ValueError(f"{name} is outside the supported range")
            object.__setattr__(self, name, value)
        for name in (
            "active_duration_hours",
            "latest_fresh_age_hours",
            "recurrence_gap_hours",
        ):
            value = getattr(self, name)
            if value is not None and Decimal(str(value)) < 0:
                raise ValueError(f"{name} cannot be negative")
        for name in ("first_fresh_seen_at", "last_fresh_seen_at"):
            value = getattr(self, name)
            if value is not None:
                _require_aware(value, name)


@dataclass(frozen=True, slots=True)
class TrendStateRecord:
    trend_state_id: str
    trend_run_id: str
    trend_series_id: str
    source_event_id: str
    predecessor_event_id: str | None
    lineage_match_kind: str
    lineage_overlap_count: int
    canonical_title: str
    state: TrendLifecycleState
    previous_state: TrendLifecycleState | None
    trend_score: Decimal
    data_quality: TrendDataQuality
    evaluated_at: datetime
    features: TrendFeatures

    def __post_init__(self) -> None:
        required = (
            self.trend_state_id,
            self.trend_run_id,
            self.trend_series_id,
            self.source_event_id,
            self.lineage_match_kind,
            self.canonical_title,
        )
        if any(not value for value in required):
            raise ValueError("trend state identifiers and evidence are required")
        if self.lineage_overlap_count < 0:
            raise ValueError("lineage overlap count cannot be negative")
        score = Decimal(str(self.trend_score))
        if not Decimal(0) <= score <= Decimal(1):
            raise ValueError("trend score must be between zero and one")
        object.__setattr__(self, "trend_score", score)
        _require_aware(self.evaluated_at, "evaluated_at")


@dataclass(frozen=True, slots=True)
class TrendBatch:
    trend_run_id: str
    source_clustering_run_id: str
    evaluation_id: str
    algorithm_version: str
    config_hash: str
    config_json: str
    input_hash: str
    evaluated_at: datetime
    started_at: datetime
    finished_at: datetime
    states: tuple[TrendStateRecord, ...]

    def __post_init__(self) -> None:
        required = (
            self.trend_run_id,
            self.source_clustering_run_id,
            self.evaluation_id,
            self.algorithm_version,
            self.config_hash,
            self.input_hash,
        )
        if any(not value for value in required):
            raise ValueError("trend batch identifiers and versions are required")
        for name in ("evaluated_at", "started_at", "finished_at"):
            _require_aware(getattr(self, name), name)
        if self.finished_at < self.started_at:
            raise ValueError("trend batch cannot finish before it starts")
        object.__setattr__(self, "states", tuple(self.states))
        if len({state.source_event_id for state in self.states}) != len(self.states):
            raise ValueError("trend batch must contain one state per source event")
        if any(state.trend_run_id != self.trend_run_id for state in self.states):
            raise ValueError("trend states must belong to their batch")

    @property
    def status(self) -> TrendRunStatus:
        return (
            TrendRunStatus.SUCCESS
            if all(
                state.data_quality is TrendDataQuality.COMPLETE for state in self.states
            )
            else TrendRunStatus.PARTIAL
        )
