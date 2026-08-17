from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

from app.repositories.hotspot import HotspotRepository
from app.repositories.hotspot.dashboard import HotspotDashboardRepository
from app.services.hotspot_classification import HotspotClassificationService

from .test_classification_repository import _database, _Provider
from .test_hotspot_repository import AT
from .test_trend_repository import _failed_result


def _classified_database(tmp_path: Path):
    database = _database(tmp_path)
    outcome = asyncio.run(
        HotspotClassificationService(database, provider=_Provider()).process_current()
    )
    assert outcome.state == "processed"
    return database


def test_overview_never_hides_unavailable_platforms_or_freshness(
    tmp_path: Path,
) -> None:
    repository = HotspotDashboardRepository(_classified_database(tmp_path))

    overview = repository.get_overview(as_of=AT + timedelta(minutes=45))

    platforms = {item["platform"]: item for item in overview["platforms"]}
    assert set(platforms) == {"douyin", "weibo", "bilibili", "xiaohongshu"}
    assert platforms["weibo"]["status"] == "fresh"
    assert platforms["weibo"]["data_age_minutes"] == 45
    assert platforms["weibo"]["snapshot_id"]
    assert platforms["weibo"]["fallback_used"] is False
    assert platforms["douyin"] == {
        "platform": "douyin",
        "status": "unavailable",
        "freshness": "unknown",
        "data_age_minutes": None,
        "last_run_at": None,
        "snapshot_id": None,
        "snapshot_observed_at": None,
        "winning_provider_id": None,
        "fallback_used": False,
        "stale_reason": "no_collection_run",
        "error": None,
        "attempts": [],
    }
    assert overview["event_count"] == 1
    assert overview["trend_run"]["status"] == "partial"


def test_dashboard_stale_threshold_is_runtime_configurable(tmp_path: Path) -> None:
    database = _classified_database(tmp_path)
    database.set_setting("hotspot_dashboard_stale_after_minutes", "30")

    overview = HotspotDashboardRepository(database).get_overview(
        as_of=AT + timedelta(minutes=45)
    )

    weibo = next(item for item in overview["platforms"] if item["platform"] == "weibo")
    assert weibo["status"] == "stale"
    assert weibo["freshness"] == "stale"
    assert weibo["stale_reason"] == "snapshot_age_exceeded"


def test_latest_failure_keeps_old_snapshot_but_marks_it_failed_and_stale(
    tmp_path: Path,
) -> None:
    database = _classified_database(tmp_path)
    asyncio.run(
        HotspotRepository(database).save_collection(
            _failed_result(AT + timedelta(hours=2))
        )
    )

    overview = HotspotDashboardRepository(database).get_overview(
        as_of=AT + timedelta(hours=2, minutes=1)
    )

    weibo = next(item for item in overview["platforms"] if item["platform"] == "weibo")
    assert weibo["snapshot_id"]
    assert weibo["status"] == "failed"
    assert weibo["freshness"] == "stale"
    assert weibo["stale_reason"] == "latest_collection_failed"
    assert weibo["error"]["code"] == "upstream_offline"


def test_event_list_uses_latest_trend_and_classification_with_filters(
    tmp_path: Path,
) -> None:
    repository = HotspotDashboardRepository(_classified_database(tmp_path))

    result = repository.list_events(
        lifecycle="emerging",
        hospitality_relevance="relevant",
        platform="weibo",
        limit=20,
        offset=0,
    )

    assert result["total"] == 1
    assert result["limit"] == 20
    event = result["items"][0]
    assert event["canonical_title"] == "台风登陆广东"
    assert event["lifecycle_state"] == "emerging"
    assert event["platforms"] == ["bilibili", "weibo"]
    assert event["classification"]["hospitality_relevance"] == "relevant"
    assert event["classification"]["topic_category"] == "hotel_travel"

    excluded = repository.list_events(
        hospitality_relevance="irrelevant", limit=20, offset=0
    )
    assert excluded["total"] == 0
    assert excluded["items"] == []


def test_event_detail_links_every_raw_evidence_record(tmp_path: Path) -> None:
    repository = HotspotDashboardRepository(_classified_database(tmp_path))
    event_id = repository.list_events(limit=20, offset=0)["items"][0]["event_id"]

    detail = repository.get_event(event_id)

    assert detail is not None
    assert len(detail["members"]) == 2
    assert len(detail["evidence"]) == 3
    for evidence in detail["evidence"]:
        assert evidence["raw_item_id"]
        assert evidence["raw_item_url"].endswith(evidence["raw_item_id"])
        assert evidence["source_url"].startswith("https://")
        assert evidence["freshness"] == "fresh"

    raw = repository.get_raw_item(detail["evidence"][0]["raw_item_id"])
    assert raw is not None
    assert raw["raw_data"] == {"rank": 1, "title": "真实热点"}
    assert raw["freshness"] == "fresh"


def test_empty_database_returns_explicit_empty_state(tmp_path: Path) -> None:
    from app.services.database import Database

    repository = HotspotDashboardRepository(
        Database(f"sqlite:///{tmp_path / 'empty-dashboard.db'}")
    )

    overview = repository.get_overview(as_of=AT)
    events = repository.list_events(limit=20, offset=0)

    assert overview["has_data"] is False
    assert overview["event_count"] == 0
    assert all(item["status"] == "unavailable" for item in overview["platforms"])
    assert events == {
        "trend_run_id": None,
        "classification_run_id": None,
        "total": 0,
        "limit": 20,
        "offset": 0,
        "items": [],
    }
