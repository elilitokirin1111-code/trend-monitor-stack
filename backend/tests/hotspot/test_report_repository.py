from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.domain.hotspot import ReportType
from app.repositories.hotspot import ReportRepository
from app.services.hotspot_reports import HotspotReportService

from .test_dashboard_repository import _classified_database

PERIOD_START = datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 8, 14, 16, 0, tzinfo=timezone.utc)


def _load(database, report_type: ReportType = ReportType.DAILY):
    return asyncio.run(
        ReportRepository(database).load_current_input(
            report_type, period_start=PERIOD_START, period_end=PERIOD_END
        )
    )


def test_load_current_input_consumes_versioned_trend_and_classification(
    tmp_path: Path,
) -> None:
    database = _classified_database(tmp_path)

    source = _load(database)

    assert source is not None
    assert source.source_trend_run_id
    assert source.source_classification_run_id
    assert len(source.events) == 1
    event = source.events[0]
    assert event.canonical_title == "台风登陆广东"
    assert event.trend_state == "emerging"
    assert event.platforms == ("bilibili", "weibo")
    assert event.hospitality_relevance == "relevant"
    assert event.summary == "酒旅相关热点事件。"
    signals = {signal.platform.value: signal for signal in source.platform_signals}
    assert "weibo" in signals
    assert signals["weibo"].freshness.value == "fresh"


def test_save_and_load_round_trip_with_audit_metadata(tmp_path: Path) -> None:
    database = _classified_database(tmp_path)
    repository = ReportRepository(database)
    source = _load(database)
    batch = asyncio.run(
        _render_batch(repository, source, report_run_id="report-run-1")
    )

    assert batch is not None
    saved = asyncio.run(repository.save_batch(batch))
    assert saved is True
    second_save = asyncio.run(repository.save_batch(batch))
    assert second_save is False

    stored = asyncio.run(repository.get_run("report-run-1"))
    assert stored is not None
    assert stored["report_type"] == "daily"
    assert stored["status"] == "partial"
    assert stored["data_quality"] == "partial"
    assert stored["source_trend_run_id"] == batch.source_trend_run_id
    assert stored["source_classification_run_id"] == batch.source_classification_run_id
    assert stored["attempt"] == 1
    assert stored["content"].startswith("# 热点日报")
    assert stored["input_hash"] == batch.input_hash


def test_list_runs_filters_by_type_and_paginates(tmp_path: Path) -> None:
    database = _classified_database(tmp_path)
    repository = ReportRepository(database)
    source = _load(database)
    daily = asyncio.run(
        _render_batch(repository, source, report_run_id="report-daily")
    )
    weekly_source = _load(database, ReportType.WEEKLY)
    weekly = asyncio.run(
        _render_batch(repository, weekly_source, report_run_id="report-weekly")
    )
    asyncio.run(repository.save_batch(daily))
    asyncio.run(repository.save_batch(weekly))

    all_runs = asyncio.run(repository.list_runs(limit=10, offset=0))
    daily_runs = asyncio.run(
        repository.list_runs(report_type=ReportType.DAILY, limit=10, offset=0)
    )

    assert all_runs["total"] == 2
    assert daily_runs["total"] == 1
    assert daily_runs["items"][0]["report_run_id"] == "report-daily"
    assert (
        asyncio.run(repository.list_runs(limit=1, offset=0))["total"] == 2
    )


def test_empty_database_loads_no_input(tmp_path: Path) -> None:
    from app.services.database import Database

    database = Database(f"sqlite:///{tmp_path / 'empty-reports.db'}")
    assert _load(database) is None


def test_service_idempotent_generate_and_force_regenerate(tmp_path: Path) -> None:
    database = _classified_database(tmp_path)
    service = HotspotReportService(database)

    first = asyncio.run(service.generate(ReportType.DAILY))
    second = asyncio.run(service.generate(ReportType.DAILY))
    forced = asyncio.run(service.generate(ReportType.DAILY, force=True))

    assert first.state == "processed"
    assert first.report_run_id is not None
    assert second.state == "skipped_unchanged"
    assert second.report_run_id == first.report_run_id
    assert forced.state == "processed"
    assert forced.report_run_id != first.report_run_id
    with database.get_connection() as connection:
        rows = connection.execute(
            "SELECT report_run_id, attempt FROM hotspot_report_runs"
        ).fetchall()
    assert len(rows) == 2
    assert {row["attempt"] for row in rows} == {1, 2}


def test_service_weekly_and_empty_input(tmp_path: Path) -> None:
    database = _classified_database(tmp_path)

    weekly = asyncio.run(HotspotReportService(database).generate(ReportType.WEEKLY))

    assert weekly.state == "processed"
    assert weekly.report_run_id

    from app.services.database import Database

    empty = Database(f"sqlite:///{tmp_path / 'empty-reports2.db'}")
    outcome = asyncio.run(HotspotReportService(empty).generate(ReportType.DAILY))
    assert outcome.state == "no_input"


async def _render_batch(repository, source, *, report_run_id: str):
    from app.reports.engine import ReportEngine
    from app.reports.rules import ReportRules

    return ReportEngine(ReportRules.from_settings({})).render(
        source,
        report_run_id=report_run_id,
        started_at=datetime(2026, 8, 14, 16, 4, tzinfo=timezone.utc),
        finished_at=datetime(2026, 8, 14, 16, 5, tzinfo=timezone.utc),
    )
