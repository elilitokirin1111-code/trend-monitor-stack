from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

from app.observability.monitor import PipelineMonitor
from app.repositories.hotspot import HotspotRepository

from .test_dashboard_repository import _classified_database
from .test_hotspot_repository import AT
from .test_trend_repository import _failed_result


def _monitor(database, at=AT + timedelta(hours=6)):
    return PipelineMonitor(database, as_of=at)


def test_provider_metrics_aggregate_success_latency_and_empty(
    tmp_path: Path,
) -> None:
    database = _classified_database(tmp_path)
    monitor = _monitor(database)

    summary = asyncio.run(monitor.provider_metrics(hours=24))

    assert summary["total_attempts"] >= 1
    newsnow = [
        item
        for item in summary["items"]
        if item["provider_id"] == "newsnow"
    ]
    assert newsnow
    entry = newsnow[0]
    assert entry["success_rate"] is not None
    assert entry["attempts"] >= 1
    assert entry["avg_latency_seconds"] is not None
    assert entry["fallback_ratio"] is not None


def test_collection_overview_counts_failures_and_stale_age(
    tmp_path: Path,
) -> None:
    database = _classified_database(tmp_path)
    asyncio.run(
        HotspotRepository(database).save_collection(
            _failed_result(AT + timedelta(hours=2))
        )
    )
    monitor = _monitor(database, at=AT + timedelta(hours=3))

    overview = asyncio.run(monitor.collection_overview(hours=24))

    assert overview["runs"] >= 3
    assert overview["failed_runs"] >= 1
    weibo = next(
        item for item in overview["platforms"] if item["platform"] == "weibo"
    )
    assert weibo["runs"] >= 1


def test_pipeline_status_reports_backlog_and_latest_runs(
    tmp_path: Path,
) -> None:
    database = _classified_database(tmp_path)
    monitor = _monitor(database)

    status = asyncio.run(monitor.pipeline_status())

    assert status["pending_normalization_snapshots"] == 0
    assert status["last_clustering"] is not None
    assert status["last_clustering"]["status"] in {"success", "partial"}
    assert status["last_trend"] is not None
    assert status["last_classification"] is not None
    assert status["last_report"] is None  # 分类库没有报告
    assert status["failed_deliveries_total"] == 0


def test_summary_returns_full_shape(tmp_path: Path) -> None:
    database = _classified_database(tmp_path)

    summary = asyncio.run(_monitor(database).summary(hours=24))

    assert summary["as_of"]
    assert summary["window_hours"] == 24
    assert set(summary) == {"as_of", "window_hours", "provider", "collection", "pipeline"}
    assert summary["provider"]["items"]
    assert summary["collection"]["platforms"]
    assert summary["pipeline"]["last_trend"]["trend_run_id"]


def test_empty_database_monitor_returns_empty_signal(tmp_path: Path) -> None:
    from app.services.database import Database

    database = Database(f"sqlite:///{tmp_path / 'empty-monitor.db'}")
    monitor = _monitor(database)

    summary = asyncio.run(monitor.summary(hours=24))

    assert summary["provider"]["total_attempts"] == 0
    assert summary["collection"]["runs"] == 0
    assert summary["pipeline"]["pending_normalization_snapshots"] == 0
    assert summary["pipeline"]["last_clustering"] is None
