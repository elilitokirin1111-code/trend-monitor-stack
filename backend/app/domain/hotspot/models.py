"""Immutable contracts shared by hotspot collectors and providers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _freeze_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


class Platform(str, Enum):
    DOUYIN = "douyin"
    WEIBO = "weibo"
    BILIBILI = "bilibili"
    XIAOHONGSHU = "xiaohongshu"


class ProviderStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class CollectionStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class Freshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"


class ProviderErrorKind(str, Enum):
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    RATE_LIMIT = "rate_limit"
    AUTHENTICATION = "authentication"
    INVALID_RESPONSE = "invalid_response"
    UPSTREAM = "upstream"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class ProviderHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ProviderError:
    kind: ProviderErrorKind
    code: str
    message: str
    retryable: bool
    upstream_status: int | None = None

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("provider error code cannot be empty")
        if not self.message.strip():
            raise ValueError("provider error message cannot be empty")


@dataclass(frozen=True, slots=True)
class ProviderHotItem:
    title: str
    url: str
    external_id: str | None = None
    rank: int | None = None
    hot_score: str | None = None
    published_at: datetime | None = None
    raw_data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("provider item title cannot be empty")
        if self.rank is not None and self.rank < 1:
            raise ValueError("provider item rank must be positive")
        if self.published_at is not None:
            _require_aware(self.published_at, "published_at")
        object.__setattr__(self, "raw_data", _freeze_mapping(self.raw_data))


@dataclass(frozen=True, slots=True)
class ProviderResult:
    provider_id: str
    platform: Platform
    status: ProviderStatus
    freshness: Freshness
    fetched_at: datetime
    observed_at: datetime
    items: tuple[ProviderHotItem, ...] = ()
    source_updated_at: datetime | None = None
    raw_payload: bytes | None = None
    raw_content_type: str | None = None
    error: ProviderError | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id cannot be empty")
        _require_aware(self.fetched_at, "fetched_at")
        _require_aware(self.observed_at, "observed_at")
        if self.source_updated_at is not None:
            _require_aware(self.source_updated_at, "source_updated_at")

        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

        if self.status is ProviderStatus.SUCCESS and self.error is not None:
            raise ValueError("successful provider result cannot contain an error")
        if self.status is ProviderStatus.PARTIAL:
            if not self.items:
                raise ValueError("partial provider result must contain items")
            if self.error is None:
                raise ValueError("partial provider result must explain its error")
        if self.status is ProviderStatus.FAILED:
            if self.items:
                raise ValueError("failed provider result cannot contain items")
            if self.error is None:
                raise ValueError("failed provider result must contain an error")

    @classmethod
    def failure(
        cls,
        *,
        provider_id: str,
        platform: Platform,
        error: ProviderError,
        at: datetime | None = None,
    ) -> ProviderResult:
        timestamp = at or utc_now()
        return cls(
            provider_id=provider_id,
            platform=platform,
            status=ProviderStatus.FAILED,
            freshness=Freshness.FRESH,
            fetched_at=timestamp,
            observed_at=timestamp,
            error=error,
        )


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    provider_id: str
    status: ProviderHealthStatus
    checked_at: datetime
    detail: str | None = None

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("provider_id cannot be empty")
        _require_aware(self.checked_at, "checked_at")


@dataclass(frozen=True, slots=True)
class CollectRequest:
    platform: Platform
    requested_at: datetime = field(default_factory=utc_now)
    allow_stale: bool | None = None

    def __post_init__(self) -> None:
        _require_aware(self.requested_at, "requested_at")


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    provider_id: str
    attempt_number: int
    started_at: datetime
    finished_at: datetime
    result: ProviderResult

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError("attempt_number must be positive")
        _require_aware(self.started_at, "started_at")
        _require_aware(self.finished_at, "finished_at")
        if self.finished_at < self.started_at:
            raise ValueError("provider attempt cannot finish before it starts")
        if self.provider_id != self.result.provider_id:
            raise ValueError("attempt provider_id must match its result")


@dataclass(frozen=True, slots=True)
class RawHotItem:
    raw_item_id: str
    run_id: str
    platform: Platform
    provider_id: str
    title: str
    url: str
    external_id: str | None
    rank: int | None
    hot_score: str | None
    published_at: datetime | None
    observed_at: datetime
    fetched_at: datetime
    raw_data: Mapping[str, Any]
    raw_payload_sha256: str | None

    def __post_init__(self) -> None:
        if not self.raw_item_id or not self.run_id:
            raise ValueError("raw item and run identifiers cannot be empty")
        _require_aware(self.observed_at, "observed_at")
        _require_aware(self.fetched_at, "fetched_at")
        object.__setattr__(self, "raw_data", _freeze_mapping(self.raw_data))


@dataclass(frozen=True, slots=True)
class CollectorResult:
    run_id: str
    platform: Platform
    status: CollectionStatus
    freshness: Freshness
    started_at: datetime
    finished_at: datetime
    items: tuple[RawHotItem, ...]
    attempts: tuple[ProviderAttempt, ...]
    winning_provider_id: str | None = None
    stale_reason: str | None = None
    error: ProviderError | None = None

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id cannot be empty")
        _require_aware(self.started_at, "started_at")
        _require_aware(self.finished_at, "finished_at")
        if self.finished_at < self.started_at:
            raise ValueError("collection cannot finish before it starts")
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "attempts", tuple(self.attempts))

        if self.status is CollectionStatus.FAILED:
            if self.items:
                raise ValueError("failed collection cannot contain items")
            if self.error is None:
                raise ValueError("failed collection must contain an error")
            if self.winning_provider_id is not None:
                raise ValueError("failed collection cannot have a winning provider")
        elif self.error is not None:
            raise ValueError("non-failed collection cannot contain a terminal error")

        if self.freshness is Freshness.STALE and not self.stale_reason:
            raise ValueError("stale collection must include stale_reason")
        if self.freshness is Freshness.FRESH and self.stale_reason is not None:
            raise ValueError("fresh collection cannot include stale_reason")
