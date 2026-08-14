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
from app.providers.hotspot.dailyhot import DailyHotApiProvider


def make_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_dailyhot_maps_contract_and_preserves_original_item():
    payload = {
        "name": "douyin",
        "total": 1,
        "updateTime": "2026-08-14T08:00:00.000Z",
        "fromCache": False,
        "data": [
            {
                "id": "9988",
                "title": "热点",
                "hot": 998877,
                "timestamp": 1_776_153_000,
                "url": "https://www.douyin.com/hot/9988",
                "mobileUrl": "https://www.douyin.com/hot/9988",
            }
        ],
    }
    client = make_client(lambda request: httpx.Response(200, json=payload))
    provider = DailyHotApiProvider(base_url="https://dailyhot.test", client=client)

    result = await provider.collect(CollectRequest(platform=Platform.DOUYIN))
    await client.aclose()

    assert result.status is ProviderStatus.SUCCESS
    assert result.freshness is Freshness.FRESH
    assert result.items[0].hot_score == "998877"
    assert result.items[0].raw_data["id"] == "9988"
    assert result.source_updated_at is not None
    assert json.loads(result.raw_payload) == payload


@pytest.mark.asyncio
async def test_dailyhot_cache_is_explicitly_stale_even_with_items():
    client = make_client(
        lambda request: httpx.Response(
            200,
            json={
                "name": "weibo",
                "total": 1,
                "updateTime": "2026-08-14T08:00:00Z",
                "fromCache": True,
                "data": [
                    {
                        "id": "topic",
                        "title": "旧榜单",
                        "url": "https://s.weibo.com/topic",
                    }
                ],
            },
        )
    )
    provider = DailyHotApiProvider(client=client)

    result = await provider.collect(CollectRequest(platform=Platform.WEIBO))
    await client.aclose()

    assert result.status is ProviderStatus.SUCCESS
    assert result.freshness is Freshness.STALE
    assert result.metadata["from_cache"] is True


@pytest.mark.asyncio
async def test_dailyhot_explicit_empty_data_is_real_empty_success():
    client = make_client(
        lambda request: httpx.Response(
            200,
            json={
                "name": "bilibili",
                "total": 0,
                "updateTime": "2026-08-14T08:00:00Z",
                "fromCache": False,
                "data": [],
            },
        )
    )
    provider = DailyHotApiProvider(client=client)

    result = await provider.collect(CollectRequest(platform=Platform.BILIBILI))
    await client.aclose()

    assert result.status is ProviderStatus.SUCCESS
    assert result.items == ()
    assert result.metadata["declared_total"] == 0


@pytest.mark.asyncio
async def test_dailyhot_schema_drift_is_failed_not_empty_success():
    raw = b'{"name":"weibo","fromCache":false,"items":[]}'
    client = make_client(lambda request: httpx.Response(200, content=raw))
    provider = DailyHotApiProvider(client=client)

    result = await provider.collect(CollectRequest(platform=Platform.WEIBO))
    await client.aclose()

    assert result.status is ProviderStatus.FAILED
    assert result.error.kind is ProviderErrorKind.INVALID_RESPONSE
    assert result.raw_payload == raw


@pytest.mark.asyncio
async def test_dailyhot_edge_access_denied_is_non_retryable_upstream_failure():
    client = make_client(lambda request: httpx.Response(403, content=b"forbidden"))
    provider = DailyHotApiProvider(client=client)

    result = await provider.collect(CollectRequest(platform=Platform.WEIBO))
    await client.aclose()

    assert result.status is ProviderStatus.FAILED
    assert result.error.kind is ProviderErrorKind.UPSTREAM
    assert result.error.retryable is False
    assert result.raw_payload == b"forbidden"
