"""Immutable contracts for channel delivery of versioned reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .normalization import _require_aware


class DeliveryStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PENDING = "pending"


class DeliveryErrorKind(str, Enum):
    NOT_CONFIGURED = "not_configured"
    TIMEOUT = "timeout"
    NETWORK = "network"
    HTTP_ERROR = "http_error"
    BUSINESS_ERROR = "business_error"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    delivery_id: str
    report_run_id: str
    channel: str
    content_version: str
    chunk_index: int
    total_chunks: int
    status: DeliveryStatus
    attempt: int
    latency_ms: int | None
    error_kind: DeliveryErrorKind | None
    error_message: str | None
    response_json: str | None
    created_at: datetime
    finished_at: datetime

    def __post_init__(self) -> None:
        required = (
            self.delivery_id,
            self.report_run_id,
            self.channel,
            self.content_version,
        )
        if any(not value for value in required):
            raise ValueError("delivery identifiers are required")
        if self.chunk_index < 0:
            raise ValueError("delivery chunk index cannot be negative")
        if self.total_chunks < 1:
            raise ValueError("delivery total chunks must be positive")
        if self.chunk_index >= self.total_chunks:
            raise ValueError("delivery chunk index exceeds total chunks")
        if self.attempt < 1:
            raise ValueError("delivery attempt must be positive")
        for name in ("created_at", "finished_at"):
            _require_aware(getattr(self, name), name)
        if self.finished_at < self.created_at:
            raise ValueError("delivery cannot finish before it starts")
        if self.latency_ms is not None and self.latency_ms < 0:
            raise ValueError("delivery latency cannot be negative")
        if (
            self.status is DeliveryStatus.SUCCESS
            and self.error_kind is not None
        ):
            raise ValueError("successful delivery cannot carry an error kind")
