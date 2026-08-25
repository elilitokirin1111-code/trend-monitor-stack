from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime

import httpx
import pytest

from app.domain.hotspot import (
    CollectRequest,
    Freshness,
    Platform,
    ProviderErrorKind,
    ProviderStatus,
)
from app.providers.hotspot.rsshub import RssHubProvider


def _feed(*, updated: datetime, item: str | None = None) -> bytes:
    item_xml = item or """
        <item>
            <guid>topic-1</guid>
            <title>真实热搜话题</title>
            <link>https://example.com/topic-1</link>
            <description>原始摘要</description>
        </item>
    """
    return f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
        <title>热点榜</title>
        <link>https://example.com</link>
        <description>真实榜单</description>
        <lastBuildDate>{format_datetime(updated)}</lastBuildDate>
        {item_xml}
    </channel></rss>""".encode()


@pytest.mark.asyncio
async def test_rsshub_maps_local_weibo_feed_and_preserves_raw_payload() -> None:
    body = _feed(updated=datetime.now(timezone.utc))

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/weibo/search/hot"
        return httpx.Response(200, content=body, headers={"content-type": "application/xml"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://rsshub:1200"
    ) as client:
        result = await RssHubProvider(client=client).collect(
            CollectRequest(platform=Platform.WEIBO)
        )

    assert result.status is ProviderStatus.SUCCESS
    assert result.freshness is Freshness.FRESH
    assert result.items[0].title == "真实热搜话题"
    assert result.items[0].external_id == "topic-1"
    assert result.raw_payload == body
    assert result.metadata["route"] == "/weibo/search/hot"


@pytest.mark.asyncio
async def test_rsshub_old_build_date_is_explicitly_stale() -> None:
    body = _feed(updated=datetime(2020, 1, 1, tzinfo=timezone.utc))

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await RssHubProvider(client=client, max_age_minutes=10).collect(
            CollectRequest(platform=Platform.BILIBILI)
        )

    assert result.status is ProviderStatus.SUCCESS
    assert result.freshness is Freshness.STALE
    assert result.metadata["freshness_basis"] == "rsshub_last_build_date_missing_or_old"


@pytest.mark.asyncio
async def test_rsshub_invalid_feed_is_failed_with_raw_evidence() -> None:
    body = b"<rss><broken>"

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await RssHubProvider(client=client).collect(
            CollectRequest(platform=Platform.WEIBO)
        )

    assert result.status is ProviderStatus.FAILED
    assert result.error.kind is ProviderErrorKind.INVALID_RESPONSE
    assert result.error.code == "invalid_rss_feed"
    assert result.raw_payload == body


@pytest.mark.asyncio
async def test_rsshub_does_not_claim_a_xiaohongshu_hot_list() -> None:
    provider = RssHubProvider()
    result = await provider.collect(CollectRequest(platform=Platform.XIAOHONGSHU))

    assert result.status is ProviderStatus.FAILED
    assert result.error.code == "unsupported_platform"
    assert result.items == ()
