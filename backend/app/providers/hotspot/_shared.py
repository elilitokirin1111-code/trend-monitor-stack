"""Shared parsing and failure helpers for external hotspot providers."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import httpx

from app.domain.hotspot import (
    Freshness,
    Platform,
    ProviderError,
    ProviderErrorKind,
    ProviderResult,
    ProviderStatus,
    utc_now,
)


def parse_json_object(payload: bytes) -> dict[str, Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("response body is not valid JSON") from exc
    if not isinstance(value, dict):
        raise TypeError("response JSON root must be an object")
    return value


def parse_json_array(payload: bytes) -> list[Any]:
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("response body is not valid JSON") from exc
    if not isinstance(value, list):
        raise TypeError("response JSON root must be an array")
    return value


def parse_datetime(value: Any) -> datetime | None:
    """Parse provider timestamps without inventing a time when input is absent."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        if abs(seconds) >= 100_000_000_000:
            seconds /= 1000
        try:
            return datetime.fromtimestamp(seconds, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return parse_datetime(float(stripped))
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    return None


def text_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def response_failure(
    *,
    provider_id: str,
    platform: Platform,
    error: ProviderError,
    raw_payload: bytes | None = None,
    raw_content_type: str | None = None,
    metadata: dict[str, Any] | None = None,
    at: datetime | None = None,
) -> ProviderResult:
    timestamp = at or utc_now()
    return ProviderResult(
        provider_id=provider_id,
        platform=platform,
        status=ProviderStatus.FAILED,
        freshness=Freshness.FRESH,
        fetched_at=timestamp,
        observed_at=timestamp,
        raw_payload=raw_payload,
        raw_content_type=raw_content_type,
        error=error,
        metadata=metadata or {},
    )


def http_status_error(status_code: int) -> ProviderError:
    if status_code == 401:
        return ProviderError(
            kind=ProviderErrorKind.AUTHENTICATION,
            code="http_401",
            message="provider authentication was rejected",
            retryable=False,
            upstream_status=status_code,
        )
    if status_code == 429:
        return ProviderError(
            kind=ProviderErrorKind.RATE_LIMIT,
            code="http_429",
            message="provider rate limit was reached",
            retryable=True,
            upstream_status=status_code,
        )
    if status_code == 403:
        return ProviderError(
            kind=ProviderErrorKind.UPSTREAM,
            code="http_403",
            message="provider or edge service denied access with HTTP 403",
            retryable=False,
            upstream_status=status_code,
        )
    return ProviderError(
        kind=ProviderErrorKind.UPSTREAM,
        code=f"http_{status_code}",
        message=f"provider returned HTTP {status_code}",
        retryable=status_code >= 500,
        upstream_status=status_code,
    )


def request_error(exc: httpx.RequestError) -> ProviderError:
    return ProviderError(
        kind=ProviderErrorKind.CONNECTION,
        code="http_connection_error",
        message=f"provider request failed: {type(exc).__name__}",
        retryable=True,
    )


def invalid_response_error(
    message: str, *, code: str = "invalid_response"
) -> ProviderError:
    return ProviderError(
        kind=ProviderErrorKind.INVALID_RESPONSE,
        code=code,
        message=message,
        retryable=False,
    )
