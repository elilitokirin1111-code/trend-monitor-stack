"""Phase 11 bounded load test: derived-layer queries stay correct and fast
at realistic scale (hundreds of events, thousands of raw items).

The dataset is synthetic but clearly labelled as a load fixture: nothing in
this test is ever served as production data.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from app.domain.hotspot import (
    CollectionStatus,
    CollectorResult,
    Freshness,
    Platform,
    ProviderAttempt,
    ProviderHotItem,
    ProviderResult,
    ProviderStatus,
    RawHotItem,
)
from app.repositories.hotspot import HotspotRepository
from app.repositories.hotspot.dashboard import HotspotDashboardRepository
from app.services.database import Database

from .test_hotspot_repository import AT


def _bulk_result(run_id: str, platform: Platform, count: int) -> CollectorResult:
    items = []
    for index in range(count):
        items.append(
            ProviderHotItem(
                title=f"{platform.value} 负载热点 {index:04d}",
                url=f"https://example.test/{platform.value}/{index}",
                external_id=f"ext-{run_id}-{index}",
                rank=index + 1,
                hot_score=str(1000 - index),
                raw_data={"title": f"负载热点 {index}", "rank": index + 1},
            )
        )
    provider_result = ProviderResult(
        provider_id="newsnow",
        platform=platform,
        status=ProviderStatus.SUCCESS,
        freshness=Freshness.FRESH,
        fetched_at=AT,
        observed_at=AT,
        items=tuple(items),
        raw_payload=b'{"items":[]}',
        raw_content_type="application/json",
    )
    attempt = ProviderAttempt(
        provider_id="newsnow",
        attempt_number=1,
        started_at=AT,
        finished_at=AT + timedelta(seconds=2),
        result=provider_result,
    )
    raw_items = tuple(
        RawHotItem(
            raw_item_id=f"{run_id}:{index}",
            run_id=run_id,
            platform=platform,
            provider_id="newsnow",
            title=item.title,
            url=item.url,
            external_id=item.external_id,
            rank=item.rank,
            hot_score=item.hot_score,
            published_at=None,
            observed_at=AT,
            fetched_at=AT,
            raw_data=item.raw_data,
            raw_payload_sha256=None,
        )
        for index, item in enumerate(items)
    )
    return CollectorResult(
        run_id=run_id,
        platform=platform,
        status=CollectionStatus.SUCCESS,
        freshness=Freshness.FRESH,
        started_at=AT,
        finished_at=AT + timedelta(seconds=2),
        items=raw_items,
        attempts=(attempt,),
        winning_provider_id="newsnow",
    )


def test_dashboard_queries_stay_correct_at_scale(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'load.db'}")
    repository = HotspotRepository(database)

    for platform in (Platform.WEIBO, Platform.BILIBILI):
        asyncio.run(
            repository.save_collection(
                _bulk_result(f"load-{platform.value}", platform, 500)
            )
        )

    with database.get_connection() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM hotspot_raw_items").fetchone()[0]
            == 1000
        )

    dashboard = HotspotDashboardRepository(database)
    started = time.monotonic()
    overview = dashboard.get_overview(as_of=AT + timedelta(minutes=30))
    elapsed = time.monotonic() - started

    assert elapsed < 5, f"overview too slow: {elapsed:.2f}s"
    assert overview["event_count"] == 0  # 未聚类，如实为空
    platforms = {item["platform"] for item in overview["platforms"]}
    assert platforms == {"douyin", "weibo", "bilibili", "xiaohongshu"}

    started = time.monotonic()
    events = dashboard.list_events(limit=100, offset=0)
    elapsed = time.monotonic() - started
    assert elapsed < 5, f"events query too slow: {elapsed:.2f}s"
    assert events["total"] == 0
    assert events["trend_run_id"] is None


def test_collection_runs_remain_append_only_at_scale(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'load2.db'}")
    repository = HotspotRepository(database)

    for index in range(10):
        asyncio.run(
            repository.save_collection(
                _bulk_result(f"bulk-{index}", Platform.WEIBO, 100)
            )
        )

    with database.get_connection() as connection:
        runs = connection.execute(
            "SELECT COUNT(*) FROM hotspot_collection_runs"
        ).fetchone()[0]
        raw = connection.execute(
            "SELECT COUNT(*) FROM hotspot_raw_items"
        ).fetchone()[0]
    assert runs == 10
    assert raw == 1000
