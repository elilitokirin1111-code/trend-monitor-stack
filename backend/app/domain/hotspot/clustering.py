"""Immutable contracts for bounded, versioned hotspot event clustering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType

from .models import Platform
from .normalization import _require_aware


class CandidateDecision(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SEMANTIC_ACCEPTED = "semantic_accepted"
    SEMANTIC_REJECTED = "semantic_rejected"
    DEGRADED_REJECTED = "degraded_rejected"


class SemanticStatus(str, Enum):
    NOT_REQUESTED = "not_requested"
    COMPLETED = "completed"
    UNAVAILABLE = "unavailable"
    ERROR = "error"
    INVALID = "invalid"
    BUDGET_EXHAUSTED = "budget_exhausted"


class ClusteringStatus(str, Enum):
    SUCCESS = "success"
    DEGRADED = "degraded"


@dataclass(frozen=True, slots=True)
class ClusterInputItem:
    group_id: str
    normalization_run_id: str
    normalized_item_id: str
    snapshot_id: str
    platform: Platform
    provider_id: str
    normalized_title: str
    title_fingerprint: str
    canonical_url: str | None
    rank: int | None
    observed_at: datetime
    published_at: datetime | None

    def __post_init__(self) -> None:
        required = (
            self.group_id,
            self.normalization_run_id,
            self.normalized_item_id,
            self.snapshot_id,
            self.provider_id,
            self.normalized_title,
            self.title_fingerprint,
        )
        if any(not value for value in required):
            raise ValueError(
                "cluster input identifiers and normalized title are required"
            )
        if self.rank is not None and self.rank < 1:
            raise ValueError("rank must be positive")
        _require_aware(self.observed_at, "observed_at")
        if self.published_at is not None:
            _require_aware(self.published_at, "published_at")


@dataclass(frozen=True, slots=True)
class ClusterCandidate:
    candidate_id: str
    clustering_run_id: str
    left_group_id: str
    right_group_id: str
    recall_reasons: tuple[str, ...]
    components: Mapping[str, str]
    deterministic_score: Decimal
    decision: CandidateDecision
    semantic_status: SemanticStatus
    semantic_same_event: bool | None = None
    semantic_confidence: Decimal | None = None
    semantic_reason: str | None = None
    semantic_model_id: str | None = None
    semantic_error: str | None = None

    def __post_init__(self) -> None:
        if not all(
            (
                self.candidate_id,
                self.clustering_run_id,
                self.left_group_id,
                self.right_group_id,
            )
        ):
            raise ValueError("candidate identifiers are required")
        if self.left_group_id == self.right_group_id:
            raise ValueError("candidate sides must be different")
        if not Decimal(0) <= self.deterministic_score <= Decimal(1):
            raise ValueError("deterministic score must be between zero and one")
        if self.semantic_confidence is not None and not (
            Decimal(0) <= self.semantic_confidence <= Decimal(1)
        ):
            raise ValueError("semantic confidence must be between zero and one")
        object.__setattr__(self, "recall_reasons", tuple(self.recall_reasons))
        object.__setattr__(self, "components", MappingProxyType(dict(self.components)))


@dataclass(frozen=True, slots=True)
class EventMember:
    group_id: str
    normalized_item_id: str
    snapshot_id: str
    platform: Platform
    is_representative: bool

    def __post_init__(self) -> None:
        if not all((self.group_id, self.normalized_item_id, self.snapshot_id)):
            raise ValueError("event member identifiers are required")


@dataclass(frozen=True, slots=True)
class EventCluster:
    event_id: str
    clustering_run_id: str
    canonical_title: str
    representative_group_id: str
    representative_normalized_item_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    platforms: tuple[Platform, ...]
    members: tuple[EventMember, ...]

    def __post_init__(self) -> None:
        required = (
            self.event_id,
            self.clustering_run_id,
            self.canonical_title,
            self.representative_group_id,
            self.representative_normalized_item_id,
        )
        if any(not value for value in required):
            raise ValueError("event identifiers and canonical title are required")
        _require_aware(self.first_seen_at, "first_seen_at")
        _require_aware(self.last_seen_at, "last_seen_at")
        if self.last_seen_at < self.first_seen_at:
            raise ValueError("event cannot end before it starts")
        object.__setattr__(self, "platforms", tuple(self.platforms))
        object.__setattr__(self, "members", tuple(self.members))
        if not self.members:
            raise ValueError("event must contain at least one member")
        representatives = [
            member for member in self.members if member.is_representative
        ]
        if len(representatives) != 1:
            raise ValueError("event must contain exactly one representative")
        if representatives[0].group_id != self.representative_group_id:
            raise ValueError("representative member must match event representative")
        if set(self.platforms) != {member.platform for member in self.members}:
            raise ValueError("event platforms must match member platforms")


@dataclass(frozen=True, slots=True)
class ClusteringBatch:
    clustering_run_id: str
    algorithm_version: str
    config_hash: str
    config_json: str
    normalization_rule_version: str
    normalization_config_hash: str
    input_hash: str
    window_start: datetime
    window_end: datetime
    started_at: datetime
    finished_at: datetime
    input_group_count: int
    candidate_pair_count: int
    truncated_candidate_count: int
    semantic_call_count: int
    candidates: tuple[ClusterCandidate, ...]
    events: tuple[EventCluster, ...]

    def __post_init__(self) -> None:
        required = (
            self.clustering_run_id,
            self.algorithm_version,
            self.config_hash,
            self.normalization_rule_version,
            self.normalization_config_hash,
            self.input_hash,
        )
        if any(not value for value in required):
            raise ValueError("clustering batch identifiers and versions are required")
        for name in ("window_start", "window_end", "started_at", "finished_at"):
            _require_aware(getattr(self, name), name)
        if self.window_end < self.window_start or self.finished_at < self.started_at:
            raise ValueError("clustering time ranges are invalid")
        counts = (
            self.input_group_count,
            self.candidate_pair_count,
            self.truncated_candidate_count,
            self.semantic_call_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("clustering counts cannot be negative")
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(self, "events", tuple(self.events))
        if self.candidate_pair_count != len(self.candidates):
            raise ValueError("candidate count must match persisted candidates")
        member_ids = [
            member.group_id for event in self.events for member in event.members
        ]
        if len(member_ids) != self.input_group_count or len(member_ids) != len(
            set(member_ids)
        ):
            raise ValueError("events must cover each input group exactly once")

    @property
    def status(self) -> ClusteringStatus:
        degraded = {
            SemanticStatus.UNAVAILABLE,
            SemanticStatus.ERROR,
            SemanticStatus.INVALID,
            SemanticStatus.BUDGET_EXHAUSTED,
        }
        return (
            ClusteringStatus.DEGRADED
            if any(
                candidate.semantic_status in degraded for candidate in self.candidates
            )
            else ClusteringStatus.SUCCESS
        )
