"""Immutable contracts for the versioned daily/weekly hotspot report engine.

Reports are derived artifacts: they consume already-versioned trend states,
events and AI classifications, and never read transient Provider responses.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from .models import CollectionStatus, Freshness, Platform
from .normalization import _require_aware


class ReportType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"


class ReportStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    NO_INPUT = "no_input"


class ReportDataQuality(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    STALE_ONLY = "stale_only"
    NO_FRESH_DATA = "no_fresh_data"


@dataclass(frozen=True, slots=True)
class ReportPlatformSignal:
    platform: Platform
    status: CollectionStatus
    freshness: Freshness
    observed_at: datetime | None

    def __post_init__(self) -> None:
        if self.observed_at is not None:
            _require_aware(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class ReportEventItem:
    """One event row consumed by the report, with its trend and AI evidence."""

    event_id: str
    trend_series_id: str
    canonical_title: str
    trend_state: str
    trend_score: Decimal
    data_quality: str
    platforms: tuple[str, ...]
    hospitality_relevance: str | None
    hospitality_score: Decimal | None
    summary: str | None

    def __post_init__(self) -> None:
        required = (self.event_id, self.trend_series_id, self.canonical_title)
        if any(not value for value in required):
            raise ValueError("report event identifiers and title are required")
        if not self.trend_state or not self.data_quality:
            raise ValueError("report event trend state and quality are required")
        score = Decimal(str(self.trend_score))
        if not Decimal(0) <= score <= Decimal(1):
            raise ValueError("report event trend score must be between zero and one")
        object.__setattr__(self, "trend_score", score)
        if self.hospitality_score is not None:
            related = Decimal(str(self.hospitality_score))
            if not Decimal(0) <= related <= Decimal(1):
                raise ValueError(
                    "report event hospitality score must be between zero and one"
                )
            object.__setattr__(self, "hospitality_score", related)
        object.__setattr__(self, "platforms", tuple(sorted(self.platforms)))


@dataclass(frozen=True, slots=True)
class ReportInput:
    report_type: ReportType
    period_start: datetime
    period_end: datetime
    source_trend_run_id: str
    source_classification_run_id: str | None
    events: tuple[ReportEventItem, ...]
    platform_signals: tuple[ReportPlatformSignal, ...]

    def __post_init__(self) -> None:
        if not self.source_trend_run_id:
            raise ValueError("report requires a source trend run")
        for name in ("period_start", "period_end"):
            _require_aware(getattr(self, name), name)
        if self.period_end < self.period_start:
            raise ValueError("report period is invalid")
        if self.period_end - self.period_start > timedelta(days=31):
            raise ValueError("report period cannot exceed 31 days")
        object.__setattr__(self, "events", tuple(self.events))
        object.__setattr__(self, "platform_signals", tuple(self.platform_signals))
        if len({item.event_id for item in self.events}) != len(self.events):
            raise ValueError("report input must contain unique events")
        signals = [signal.platform for signal in self.platform_signals]
        if len(signals) != len(set(signals)):
            raise ValueError("report platform signals must be unique")


@dataclass(frozen=True, slots=True)
class ReportBatch:
    report_run_id: str
    report_type: ReportType
    period_start: datetime
    period_end: datetime
    report_version: str
    config_hash: str
    config_json: str
    input_hash: str
    status: ReportStatus
    data_quality: ReportDataQuality
    stale_platforms: tuple[str, ...]
    missing_platforms: tuple[str, ...]
    content: str
    template: str
    source_trend_run_id: str
    source_classification_run_id: str | None
    attempt: int
    started_at: datetime
    finished_at: datetime

    def __post_init__(self) -> None:
        required = (
            self.report_run_id,
            self.report_version,
            self.config_hash,
            self.input_hash,
            self.source_trend_run_id,
        )
        if any(not value for value in required):
            raise ValueError("report identifiers and versions are required")
        if self.attempt < 1:
            raise ValueError("report attempt must be positive")
        for name in ("period_start", "period_end", "started_at", "finished_at"):
            _require_aware(getattr(self, name), name)
        if self.finished_at < self.started_at:
            raise ValueError("report cannot finish before it starts")
        if self.period_end < self.period_start:
            raise ValueError("report period is invalid")
        object.__setattr__(self, "stale_platforms", tuple(self.stale_platforms))
        object.__setattr__(self, "missing_platforms", tuple(self.missing_platforms))
        stale = set(self.stale_platforms)
        missing = set(self.missing_platforms)
        if stale & missing:
            raise ValueError("a platform cannot be both stale and missing")
        if not self.content.strip():
            raise ValueError("report content cannot be empty")
