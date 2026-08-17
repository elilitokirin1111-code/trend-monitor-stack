"""Feishu group-bot delivery adapter with signing, retry and business codes.

The adapter performs one bounded delivery attempt sequence for a single text
chunk: signing (timestamp + secret per Feishu docs), timeout, exponential
backoff retries on retryable failures, and business-code validation of the
Feishu response. Credentials are never logged: URLs are masked and secrets
never leave the request builder.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from app.delivery.rules import FeishuDeliveryRules
from app.domain.hotspot import DeliveryErrorKind


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    attempt: int
    status: str  # "success" | "failed"
    error_kind: DeliveryErrorKind | None
    error_message: str | None
    response: str | None
    latency_ms: int


def feishu_sign(timestamp: int, secret: str) -> str:
    """Feishu group-bot signature: HMAC-SHA256 of ``timestamp + '\\n' + secret``."""
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(
        secret.encode("utf-8"), string_to_sign, digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def mask_webhook_url(url: str) -> str:
    """Redact the query string (tokens/keys) of a webhook URL for logs."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        if parts.query:
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "***", ""))
    except ValueError:
        pass
    return url


def split_content(content: str, max_chars: int) -> tuple[str, ...]:
    """Split report text into bounded chunks for delivery."""
    if max_chars < 100:
        raise ValueError("chunk size too small")
    if len(content) <= max_chars:
        return (content,)
    chunks: list[str] = []
    remaining = content
    while len(remaining) > max_chars:
        cut = max_chars
        # Prefer a newline boundary for readability.
        newline = remaining.rfind("\n", 0, max_chars)
        if newline > max_chars * 3 // 4:
            cut = newline + 1
        chunks.append(remaining[:cut])
        remaining = remaining[cut:]
    if remaining:
        chunks.append(remaining)
    return tuple(chunks)


class FeishuDeliveryAdapter:
    def __init__(
        self,
        rules: FeishuDeliveryRules,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        alert_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._rules = rules
        self._transport = transport
        self._alert_transport = alert_transport or transport

    def is_configured(self) -> bool:
        return bool(self._rules.webhook_url)

    async def send_text(self, text: str, *, title: str | None = None) -> DeliveryAttempt:
        """Send one chunk with bounded retries; returns a single final attempt."""
        if not self.is_configured():
            return DeliveryAttempt(
                attempt=1,
                status="failed",
                error_kind=DeliveryErrorKind.NOT_CONFIGURED,
                error_message="feishu webhook is not configured",
                response=None,
                latency_ms=0,
            )
        timeout = httpx.Timeout(self._rules.timeout_seconds)
        attempt_count = 0
        last: DeliveryAttempt | None = None
        async with httpx.AsyncClient(
            timeout=timeout, transport=self._transport
        ) as client:
            while True:
                attempt_count += 1
                last = await self._send_once(client, text, title=title)
                if last.status == "success" or not _retryable(last.error_kind):
                    break
                if attempt_count > self._rules.max_retries:
                    break
                delay = min(
                    self._rules.backoff_base_seconds * (2 ** (attempt_count - 1)),
                    self._rules.backoff_max_seconds,
                )
                await asyncio.sleep(delay)
        return replace(last, attempt=attempt_count)

    async def send_alert(self, text: str) -> DeliveryAttempt:
        """Best-effort alert message; never retried and never blocks delivery."""
        if not self._rules.alert_webhook_url:
            return DeliveryAttempt(
                attempt=1,
                status="failed",
                error_kind=DeliveryErrorKind.NOT_CONFIGURED,
                error_message="alert webhook is not configured",
                response=None,
                latency_ms=0,
            )
        timeout = httpx.Timeout(min(self._rules.timeout_seconds, 10))
        async with httpx.AsyncClient(
            timeout=timeout, transport=self._alert_transport
        ) as client:
            return await self._post(client, self._rules.alert_webhook_url, text, None)

    async def _send_once(
        self, client: httpx.AsyncClient, text: str, *, title: str | None
    ) -> DeliveryAttempt:
        return await self._post(
            client, self._rules.webhook_url, text, title, self._rules.secret
        )

    async def _post(
        self,
        client: httpx.AsyncClient,
        url: str,
        text: str,
        title: str | None,
        secret: str | None = None,
    ) -> DeliveryAttempt:
        payload: dict[str, Any] = {"msg_type": "text", "content": {"text": text}}
        if title:
            payload["content"]["text"] = f"{title}\n{text}"
        if secret:
            timestamp = int(time.time())
            payload["timestamp"] = str(timestamp)
            payload["sign"] = feishu_sign(timestamp, secret)
        started = time.monotonic()
        try:
            response = await client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            return _failed(DeliveryErrorKind.TIMEOUT, "feishu request timed out", exc, started)
        except httpx.HTTPError as exc:
            return _failed(
                DeliveryErrorKind.NETWORK,
                f"feishu request failed: {exc.__class__.__name__}",
                exc,
                started,
            )
        latency = int((time.monotonic() - started) * 1000)
        if response.status_code < 200 or response.status_code >= 300:
            return DeliveryAttempt(
                attempt=1,
                status="failed",
                error_kind=DeliveryErrorKind.HTTP_ERROR,
                error_message=f"feishu http {response.status_code}",
                response=_snippet(response.text),
                latency_ms=latency,
            )
        try:
            body = response.json()
        except ValueError:
            return DeliveryAttempt(
                attempt=1,
                status="failed",
                error_kind=DeliveryErrorKind.INVALID_RESPONSE,
                error_message="feishu returned non-JSON response",
                response=_snippet(response.text),
                latency_ms=latency,
            )
        code = body.get("code") if isinstance(body, dict) else None
        if code == 0:
            return DeliveryAttempt(
                attempt=1,
                status="success",
                error_kind=None,
                error_message=None,
                response=_snippet(json.dumps(body, ensure_ascii=False)),
                latency_ms=latency,
            )
        message = body.get("msg") if isinstance(body, dict) else "unknown"
        return DeliveryAttempt(
            attempt=1,
            status="failed",
            error_kind=DeliveryErrorKind.BUSINESS_ERROR,
            error_message=f"feishu business code {code}: {message}",
            response=_snippet(json.dumps(body, ensure_ascii=False)),
            latency_ms=latency,
        )


def _retryable(kind: DeliveryErrorKind | None) -> bool:
    return kind in {
        DeliveryErrorKind.TIMEOUT,
        DeliveryErrorKind.NETWORK,
        DeliveryErrorKind.HTTP_ERROR,
        DeliveryErrorKind.INVALID_RESPONSE,
    }


def _failed(kind, message, exc, started) -> DeliveryAttempt:
    return DeliveryAttempt(
        attempt=1,
        status="failed",
        error_kind=kind,
        error_message=message,
        response=None,
        latency_ms=int((time.monotonic() - started) * 1000),
    )


def _snippet(text: str, limit: int = 500) -> str:
    return text[:limit]
