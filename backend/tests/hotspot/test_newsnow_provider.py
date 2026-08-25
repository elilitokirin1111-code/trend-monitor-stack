import json

import httpx
import pytest

from app.domain.hotspot import (
    CollectRequest,
    Freshness,
    Platform,
    ProviderErrorKind,
    ProviderStatus,
)
from app.providers.hotspot.newsnow import NewsNowProvider


def make_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_newsnow_maps_fresh_items_and_preserves_raw_payload():
    payload = {
        "status": "success",
        "id": "bilibili",
        "updatedTime": 1_723_456_789_000,
        "items": [
            {
                "id": "BV123",
                "title": "真实标题",
                "url": "https://www.bilibili.com/video/BV123",
                "pubDate": 1_723_456_000_000,
                "hot": 12345,
            }
        ],
    }
    client = make_client(lambda request: httpx.Response(200, json=payload))
    provider = NewsNowProvider(base_url="https://newsnow.test", client=client)

    result = await provider.collect(CollectRequest(platform=Platform.BILIBILI))
    await client.aclose()

    assert result.status is ProviderStatus.SUCCESS
    assert result.freshness is Freshness.STALE
    assert result.metadata["freshness_basis"] == (
        "newsnow_success_may_include_interval_cache"
    )
    assert result.items[0].external_id == "BV123"
    assert result.items[0].rank == 1
    assert result.items[0].hot_score == "12345"
    assert result.items[0].published_at is not None
    assert result.source_updated_at is not None
    assert json.loads(result.raw_payload) == payload


@pytest.mark.asyncio
async def test_newsnow_cache_is_explicitly_stale():
    client = make_client(
        lambda request: httpx.Response(
            200,
            json={
                "status": "cache",
                "id": "weibo",
                "updatedTime": 1_723_456_789_000,
                "items": [
                    {
                        "id": "topic",
                        "title": "缓存话题",
                        "url": "https://s.weibo.com/topic",
                    }
                ],
            },
        )
    )
    provider = NewsNowProvider(client=client)

    result = await provider.collect(CollectRequest(platform=Platform.WEIBO))
    await client.aclose()

    assert result.status is ProviderStatus.SUCCESS
    assert result.freshness is Freshness.STALE
    assert result.metadata["source_status"] == "cache"


@pytest.mark.asyncio
async def test_newsnow_can_be_fresh_only_with_explicit_operator_assertion():
    client = make_client(
        lambda request: httpx.Response(
            200,
            json={
                "status": "success",
                "id": "weibo",
                "updatedTime": 1_723_456_789_000,
                "items": [],
            },
        )
    )
    provider = NewsNowProvider(client=client, trust_success_as_fresh=True)

    result = await provider.collect(CollectRequest(platform=Platform.WEIBO))
    await client.aclose()

    assert result.freshness is Freshness.FRESH
    assert result.metadata["freshness_basis"] == "operator_asserted_cache_disabled"


@pytest.mark.asyncio
async def test_newsnow_invalid_rows_produce_partial_not_fake_success():
    client = make_client(
        lambda request: httpx.Response(
            200,
            json={
                "status": "success",
                "id": "douyin",
                "updatedTime": 1_723_456_789_000,
                "items": [
                    {"id": "1", "title": "有效", "url": "https://douyin.test/1"},
                    {"id": "2", "title": "缺少链接"},
                ],
            },
        )
    )
    provider = NewsNowProvider(client=client)

    result = await provider.collect(CollectRequest(platform=Platform.DOUYIN))
    await client.aclose()

    assert result.status is ProviderStatus.PARTIAL
    assert len(result.items) == 1
    assert result.error is not None
    assert result.error.kind is ProviderErrorKind.INVALID_RESPONSE
    assert result.metadata["invalid_item_count"] == 1


@pytest.mark.asyncio
async def test_newsnow_missing_items_is_failed_with_raw_evidence():
    raw = b'{"status":"success","id":"weibo"}'
    client = make_client(lambda request: httpx.Response(200, content=raw))
    provider = NewsNowProvider(client=client)

    result = await provider.collect(CollectRequest(platform=Platform.WEIBO))
    await client.aclose()

    assert result.status is ProviderStatus.FAILED
    assert result.error.kind is ProviderErrorKind.INVALID_RESPONSE
    assert result.raw_payload == raw


@pytest.mark.asyncio
async def test_newsnow_rate_limit_is_retryable_and_preserves_body():
    client = make_client(lambda request: httpx.Response(429, content=b"rate limited"))
    provider = NewsNowProvider(client=client)

    result = await provider.collect(CollectRequest(platform=Platform.WEIBO))
    await client.aclose()

    assert result.status is ProviderStatus.FAILED
    assert result.error.kind is ProviderErrorKind.RATE_LIMIT
    assert result.error.retryable is True
    assert result.raw_payload == b"rate limited"


@pytest.mark.asyncio
async def test_newsnow_connection_failure_is_retryable():
    def fail(request):
        raise httpx.ConnectError("offline", request=request)

    client = make_client(fail)
    provider = NewsNowProvider(client=client)

    result = await provider.collect(CollectRequest(platform=Platform.WEIBO))
    await client.aclose()

    assert result.status is ProviderStatus.FAILED
    assert result.error.kind is ProviderErrorKind.CONNECTION
    assert result.error.retryable is True
