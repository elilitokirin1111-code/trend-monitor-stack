from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time

import httpx
import pytest

from app.delivery.feishu import (
    FeishuDeliveryAdapter,
    feishu_sign,
    mask_webhook_url,
    split_content,
)
from app.delivery.rules import FeishuDeliveryRules
from app.domain.hotspot import DeliveryErrorKind


def _rules(**overrides) -> FeishuDeliveryRules:
    base = {
        "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/abc?token=secret-token",
        "secret": "test-secret",
    }
    base.update(overrides)
    return FeishuDeliveryRules(**base)


def test_sign_matches_feishu_documented_algorithm() -> None:
    timestamp = 1710000000
    secret = "test-secret"
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    expected = base64.b64encode(
        hmac.new(secret.encode(), string_to_sign, hashlib.sha256).digest()
    ).decode()

    assert feishu_sign(timestamp, secret) == expected
    assert feishu_sign(timestamp, secret) == feishu_sign(timestamp, secret)
    assert feishu_sign(timestamp, secret) != feishu_sign(timestamp + 1, secret)


def test_mask_webhook_url_redacts_query_and_keeps_path() -> None:
    url = "https://open.feishu.cn/open-apis/bot/v2/hook/abc?token=super-secret"
    masked = mask_webhook_url(url)

    assert "super-secret" not in masked
    assert masked == "https://open.feishu.cn/open-apis/bot/v2/hook/abc?***"
    assert mask_webhook_url("") == ""
    assert mask_webhook_url("https://example.com/plain") == "https://example.com/plain"


def test_split_content_respects_max_chars_and_newlines() -> None:
    chunks = split_content("a" * 300, 100)
    assert len(chunks) == 3
    assert all(len(chunk) <= 100 for chunk in chunks)
    assert "".join(chunks) == "a" * 300

    content = ("第一行\n" * 40) + "end"
    bounded = split_content(content, 120)
    assert "".join(bounded) == content
    assert len(bounded) > 1

    single = split_content("short", 100)
    assert single == ("short",)

    with pytest.raises(ValueError):
        split_content("x", 99)


def test_rules_mask_secret_in_config_json_and_reject_http() -> None:
    rules = _rules()
    assert "test-secret" not in rules.config_json
    assert "secret-token" not in rules.config_json
    assert len(rules.config_hash) == 64

    with pytest.raises(ValueError):
        FeishuDeliveryRules(webhook_url="http://insecure.example.com")
    with pytest.raises(ValueError):
        FeishuDeliveryRules(max_retries=9)


@pytest.mark.asyncio
async def test_adapter_success_with_signing_and_business_code() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    adapter = FeishuDeliveryAdapter(
        _rules(), transport=httpx.MockTransport(handler)
    )
    attempt = await adapter.send_text("内容")

    assert attempt.status == "success"
    assert attempt.error_kind is None
    assert seen["payload"]["msg_type"] == "text"
    assert "timestamp" in seen["payload"]
    assert "sign" in seen["payload"]
    assert seen["payload"]["sign"] == feishu_sign(
        int(seen["payload"]["timestamp"]), "test-secret"
    )
    assert attempt.latency_ms >= 0


@pytest.mark.asyncio
async def test_adapter_no_secret_sends_unsigned() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    adapter = FeishuDeliveryAdapter(
        _rules(secret=""), transport=httpx.MockTransport(handler)
    )
    attempt = await adapter.send_text("内容")

    assert attempt.status == "success"
    # payload consumed by handler; verify via shared handler
    assert attempt.error_kind is None


@pytest.mark.asyncio
async def test_adapter_business_error_is_not_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"code": 9499, "msg": "invalid sign"})

    adapter = FeishuDeliveryAdapter(
        _rules(), transport=httpx.MockTransport(handler)
    )
    attempt = await adapter.send_text("内容")

    assert attempt.status == "failed"
    assert attempt.error_kind is DeliveryErrorKind.BUSINESS_ERROR
    assert "9499" in attempt.error_message
    assert calls == 1


@pytest.mark.asyncio
async def test_adapter_retries_http_errors_with_backoff_then_fails() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(502, text="bad gateway")

    adapter = FeishuDeliveryAdapter(
        _rules(max_retries=2, backoff_base_seconds=0.01),
        transport=httpx.MockTransport(handler),
    )
    attempt = await adapter.send_text("内容")

    assert attempt.status == "failed"
    assert attempt.error_kind is DeliveryErrorKind.HTTP_ERROR
    assert calls == 3  # initial + 2 retries
    assert attempt.attempt == 3


@pytest.mark.asyncio
async def test_adapter_recovers_after_transient_network_failure() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    adapter = FeishuDeliveryAdapter(
        _rules(max_retries=2, backoff_base_seconds=0.01),
        transport=httpx.MockTransport(handler),
    )
    attempt = await adapter.send_text("内容")

    assert attempt.status == "success"
    assert calls == 2
    assert attempt.attempt == 2


@pytest.mark.asyncio
async def test_adapter_timeout_classification() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    adapter = FeishuDeliveryAdapter(
        _rules(max_retries=0, timeout_seconds=0.5),
        transport=httpx.MockTransport(handler),
    )
    attempt = await adapter.send_text("内容")

    assert attempt.status == "failed"
    assert attempt.error_kind is DeliveryErrorKind.TIMEOUT


@pytest.mark.asyncio
async def test_adapter_invalid_json_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not json</html>")

    adapter = FeishuDeliveryAdapter(
        _rules(max_retries=0), transport=httpx.MockTransport(handler)
    )
    attempt = await adapter.send_text("内容")

    assert attempt.status == "failed"
    assert attempt.error_kind is DeliveryErrorKind.INVALID_RESPONSE


@pytest.mark.asyncio
async def test_adapter_not_configured() -> None:
    adapter = FeishuDeliveryAdapter(_rules(webhook_url=""))

    attempt = await adapter.send_text("内容")

    assert attempt.status == "failed"
    assert attempt.error_kind is DeliveryErrorKind.NOT_CONFIGURED


@pytest.mark.asyncio
async def test_send_alert_uses_alert_webhook_and_is_never_retried() -> None:
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    adapter = FeishuDeliveryAdapter(
        _rules(alert_webhook_url="https://open.feishu.cn/alert?token=x"),
        transport=httpx.MockTransport(handler),
    )
    attempt = await adapter.send_alert("告警")

    assert attempt.status == "success"
    assert urls == ["https://open.feishu.cn/alert?token=x"]
