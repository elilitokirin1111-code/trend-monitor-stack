import httpx
import pytest

from app.collectors.config import CollectorPolicy, ProviderPolicy
from app.collectors.hotspot import HotspotCollector
from app.domain.hotspot import CollectionStatus, CollectRequest, Platform
from app.providers.hotspot.dailyhot import DailyHotApiProvider
from app.providers.hotspot.newsnow import NewsNowProvider
from app.providers.hotspot.registry import ProviderRegistry


class RecordingWriter:
    def __init__(self):
        self.results = []

    async def save_collection(self, result):
        self.results.append(result)


@pytest.mark.asyncio
async def test_real_adapters_fallback_from_newsnow_failure_to_dailyhot_success():
    newsnow_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(403, content=b"cloudflare forbidden")
        )
    )
    dailyhot_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "name": "weibo",
                    "total": 1,
                    "updateTime": "2026-08-14T08:00:00Z",
                    "fromCache": False,
                    "data": [
                        {
                            "id": "topic",
                            "title": "真实契约测试",
                            "url": "https://s.weibo.com/topic",
                        }
                    ],
                },
            )
        )
    )
    registry = ProviderRegistry(
        (
            NewsNowProvider(client=newsnow_client),
            DailyHotApiProvider(client=dailyhot_client),
        )
    )
    writer = RecordingWriter()
    collector = HotspotCollector(
        registry=registry,
        policy=CollectorPolicy(
            {
                Platform.WEIBO: ProviderPolicy(
                    provider_ids=("newsnow", "dailyhotapi"),
                    max_retries_per_provider=0,
                )
            }
        ),
        writer=writer,
        run_id_factory=lambda: "phase-2-fallback",
    )

    result = await collector.collect(CollectRequest(platform=Platform.WEIBO))
    await newsnow_client.aclose()
    await dailyhot_client.aclose()

    assert result.status is CollectionStatus.SUCCESS
    assert result.winning_provider_id == "dailyhotapi"
    assert [attempt.provider_id for attempt in result.attempts] == [
        "newsnow",
        "dailyhotapi",
    ]
    assert result.attempts[0].result.raw_payload == b"cloudflare forbidden"
    assert writer.results == [result]
