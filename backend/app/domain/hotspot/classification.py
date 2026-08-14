"""Immutable contracts for evidence-grounded hotspot AI classification."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from .models import Platform
from .normalization import _require_aware
from .trends import TrendDataQuality, TrendLifecycleState


class TopicCategory(str, Enum):
    HOTEL_TRAVEL = "hotel_travel"
    LOCAL_LIFE = "local_life"
    TRANSPORT = "transport"
    CULTURE_ENTERTAINMENT = "culture_entertainment"
    SOCIAL_PUBLIC = "social_public"
    FINANCE_BUSINESS = "finance_business"
    TECHNOLOGY = "technology"
    SPORTS = "sports"
    OTHER = "other"


class HospitalityRelevance(str, Enum):
    IRRELEVANT = "irrelevant"
    ADJACENT = "adjacent"
    RELEVANT = "relevant"
    HIGH = "high"


class ClassificationStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class ClassificationErrorKind(str, Enum):
    DISABLED = "disabled"
    MISSING_API_KEY = "missing_api_key"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    INVALID_JSON = "invalid_json"
    INVALID_SCHEMA = "invalid_schema"
    PROVIDER_ERROR = "provider_error"


class ClassificationRunStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class ClassificationEvidence:
    evidence_id: str
    platform: Platform
    title: str
    observed_at: datetime
    rank: int | None = None
    hot_score: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.evidence_id or not self.title.strip():
            raise ValueError("classification evidence requires an id and title")
        _require_aware(self.observed_at, "observed_at")
        if self.rank is not None and self.rank < 1:
            raise ValueError("evidence rank must be positive")
        if self.hot_score is not None:
            value = Decimal(str(self.hot_score))
            if not value.is_finite() or value < 0:
                raise ValueError("evidence hot score must be finite and non-negative")
            object.__setattr__(self, "hot_score", value)


@dataclass(frozen=True, slots=True)
class ClassificationInput:
    trend_state_id: str
    source_event_id: str
    canonical_title: str
    lifecycle_state: TrendLifecycleState
    trend_score: Decimal
    data_quality: TrendDataQuality
    evaluated_at: datetime
    evidence: tuple[ClassificationEvidence, ...]

    def __post_init__(self) -> None:
        if not self.trend_state_id or not self.source_event_id:
            raise ValueError("classification input identifiers are required")
        if not self.canonical_title.strip():
            raise ValueError("classification input title is required")
        score = Decimal(str(self.trend_score))
        if not score.is_finite() or not Decimal(0) <= score <= Decimal(1):
            raise ValueError("trend score must be between zero and one")
        object.__setattr__(self, "trend_score", score)
        _require_aware(self.evaluated_at, "evaluated_at")
        object.__setattr__(self, "evidence", tuple(self.evidence))
        if not self.evidence:
            raise ValueError("classification input requires source evidence")
        identifiers = [item.evidence_id for item in self.evidence]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("classification evidence identifiers must be unique")


@dataclass(frozen=True, slots=True)
class ClassificationDecision:
    category: TopicCategory
    tags: tuple[str, ...]
    hospitality_relevance: HospitalityRelevance
    hospitality_score: Decimal
    confidence: Decimal
    rationale: str
    summary: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "evidence_ids", tuple(self.evidence_ids))
        if not 1 <= len(self.tags) <= 5 or any(
            not tag.strip() or len(tag) > 30 for tag in self.tags
        ):
            raise ValueError("classification tags must contain 1-5 short values")
        if len(set(self.tags)) != len(self.tags):
            raise ValueError("classification tags must be unique")
        if not self.rationale.strip() or not self.summary.strip():
            raise ValueError("classification rationale and summary are required")
        if not self.evidence_ids or len(set(self.evidence_ids)) != len(
            self.evidence_ids
        ):
            raise ValueError("classification evidence ids must be non-empty and unique")
        for name in ("hospitality_score", "confidence"):
            value = Decimal(str(getattr(self, name)))
            if not value.is_finite() or not Decimal(0) <= value <= Decimal(1):
                raise ValueError(f"{name} must be between zero and one")
            object.__setattr__(self, name, value)


@dataclass(frozen=True, slots=True)
class ClassificationRecord:
    classification_id: str
    classification_run_id: str
    trend_state_id: str
    source_event_id: str
    status: ClassificationStatus
    model: str
    prompt_version: str
    request_hash: str
    response_json: str | None
    response_hash: str | None
    decision: ClassificationDecision | None
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost: Decimal | None = None
    error_kind: ClassificationErrorKind | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.classification_id,
            self.classification_run_id,
            self.trend_state_id,
            self.source_event_id,
            self.model,
            self.prompt_version,
            self.request_hash,
        )
        if any(not value for value in required):
            raise ValueError("classification record identifiers are required")
        if len(self.model) > 191 or len(self.prompt_version) > 64:
            raise ValueError("classification model or prompt version is too long")
        if self.status is ClassificationStatus.SUCCESS:
            if (
                self.decision is None
                or not self.response_json
                or not self.response_hash
            ):
                raise ValueError(
                    "successful classification requires response and decision"
                )
            if self.error_kind is not None:
                raise ValueError("successful classification cannot contain an error")
        elif self.decision is not None:
            raise ValueError(
                "failed or skipped classification cannot contain a decision"
            )
        elif self.error_kind is None:
            raise ValueError("failed or skipped classification requires an error kind")
        if (self.response_json is None) != (self.response_hash is None):
            raise ValueError("classification response and hash must be stored together")
        for name in ("latency_ms", "prompt_tokens", "completion_tokens"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.cost is not None:
            value = Decimal(str(self.cost))
            if not value.is_finite() or value < 0:
                raise ValueError("classification cost must be finite and non-negative")
            object.__setattr__(self, "cost", value)


@dataclass(frozen=True, slots=True)
class ClassificationBatch:
    classification_run_id: str
    source_trend_run_id: str
    classifier_version: str
    prompt_version: str
    model: str
    config_hash: str
    config_json: str
    input_hash: str
    started_at: datetime
    finished_at: datetime
    records: tuple[ClassificationRecord, ...]

    def __post_init__(self) -> None:
        required = (
            self.classification_run_id,
            self.source_trend_run_id,
            self.classifier_version,
            self.prompt_version,
            self.model,
            self.config_hash,
            self.input_hash,
        )
        if any(not value for value in required):
            raise ValueError(
                "classification batch identifiers and versions are required"
            )
        _require_aware(self.started_at, "started_at")
        _require_aware(self.finished_at, "finished_at")
        if self.finished_at < self.started_at:
            raise ValueError("classification batch cannot finish before it starts")
        object.__setattr__(self, "records", tuple(self.records))
        if not self.records:
            raise ValueError("classification batch requires records")
        if any(
            record.classification_run_id != self.classification_run_id
            for record in self.records
        ):
            raise ValueError("classification records must belong to their batch")

    @property
    def status(self) -> ClassificationRunStatus:
        statuses = {record.status for record in self.records}
        if statuses == {ClassificationStatus.SUCCESS}:
            return ClassificationRunStatus.SUCCESS
        if statuses == {ClassificationStatus.SKIPPED}:
            return ClassificationRunStatus.SKIPPED
        if statuses == {ClassificationStatus.FAILED}:
            return ClassificationRunStatus.FAILED
        return ClassificationRunStatus.PARTIAL
