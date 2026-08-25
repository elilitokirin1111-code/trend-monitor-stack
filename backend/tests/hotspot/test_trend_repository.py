from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

from app.domain.hotspot import (
    CollectionStatus,
    Freshness,
    Platform,
    ProviderAttempt,
    ProviderError,
    ProviderErrorKind,
    ProviderResult,
    ProviderStatus,
    TrendLifecycleState,
)
from app.repositories.hotspot import HotspotRepository
from app.services.database import Database
from app.services.hotspot_clustering import HotspotClusteringService
from app.services.hotspot_trends import HotspotTrendService

from .test_clustering_repository import _prepare
from .test_hotspot_repository import AT


def _database(tmp_path: Path) -> Database:
    return Database(f"sqlite:///{tmp_path / 'trends.db'}")


def _prepare_clustering(database: Database) -> None:
    _prepare(database)
    outcome = asyncio.run(HotspotClusteringService(database).process_current())
    assert outcome.state == "processed"


def _failed_result(at):
    error = ProviderError(
        kind=ProviderErrorKind.CONNECTION,
        code="upstream_offline",
        message="upstream is unavailable",
        retryable=True,
    )
    provider = ProviderResult(
        provider_id="newsnow",
        platform=Platform.WEIBO,
        status=ProviderStatus.FAILED,
        freshness=Freshness.FRESH,
        fetched_at=at,
        observed_at=at,
        error=error,
        raw_payload=b"gateway unavailable",
        raw_content_type="text/plain",
    )
    from app.domain.hotspot import CollectorResult

    return CollectorResult(
        run_id="failed-watermark",
        platform=Platform.WEIBO,
        status=CollectionStatus.FAILED,
        freshness=Freshness.FRESH,
        started_at=at,
        finished_at=at + timedelta(seconds=1),
        items=(),
        attempts=(
            ProviderAttempt(
                "newsnow",
                1,
                at,
                at + timedelta(seconds=1),
                provider,
            ),
        ),
        error=error,
    )


def test_service_persists_features_state_and_lineage_evidence(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _prepare_clustering(database)

    outcome = asyncio.run(HotspotTrendService(database).process_current())

    assert outcome.state == "processed"
    assert outcome.event_count == 1
    assert outcome.status.value == "partial"
    with database.get_connection() as connection:
        run = connection.execute(
            """SELECT status, event_count, complete_count, partial_count,
                      length(config_hash), length(input_hash), evaluation_id
               FROM hotspot_trend_runs"""
        ).fetchone()
        state = connection.execute(
            """SELECT lifecycle_state, previous_state, trend_score,
                      data_quality, lineage_match_kind, lineage_overlap_count,
                      observation_count, fresh_observation_count,
                      fresh_platform_count, failed_platform_count,
                      missing_platform_count, velocity, acceleration,
                      features_json
               FROM hotspot_trend_states"""
        ).fetchone()
        raw_count = connection.execute(
            "SELECT COUNT(*) FROM hotspot_raw_items"
        ).fetchone()[0]

    assert tuple(run[:6]) == ("partial", 1, 0, 1, 64, 64)
    assert run["evaluation_id"] in {"weibo-run", "bili-run"}
    assert state["lifecycle_state"] == "emerging"
    assert state["previous_state"] is None
    assert state["data_quality"] == "partial"
    assert state["lineage_match_kind"] == "new"
    assert state["lineage_overlap_count"] == 0
    assert state["observation_count"] == 2
    assert state["fresh_observation_count"] == 2
    assert state["fresh_platform_count"] == 2
    assert state["failed_platform_count"] == 0
    assert state["missing_platform_count"] == 2
    assert "current_strength" in state["features_json"]
    assert raw_count == 3


def test_same_watermark_is_idempotent_and_config_change_appends(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _prepare_clustering(database)
    service = HotspotTrendService(database)

    first = asyncio.run(service.process_current())
    second = asyncio.run(service.process_current())
    database.set_setting("hotspot_trend_rising_velocity_threshold", "0.12")
    third = asyncio.run(service.process_current())

    assert first.state == "processed"
    assert second.state == "skipped_unchanged"
    assert third.state == "processed"
    with database.get_connection() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM hotspot_trend_runs").fetchone()[0]
            == 2
        )
        assert (
            connection.execute("SELECT COUNT(*) FROM hotspot_trend_states").fetchone()[
                0
            ]
            == 2
        )


def test_failed_collection_advances_watermark_to_dormant_without_new_snapshot(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    _prepare_clustering(database)
    service = HotspotTrendService(database)
    first = asyncio.run(service.process_current())
    assert first.lifecycle_counts[TrendLifecycleState.EMERGING] == 1

    asyncio.run(
        HotspotRepository(database).save_collection(
            _failed_result(AT + timedelta(hours=8))
        )
    )
    second = asyncio.run(service.process_current())

    assert second.state == "processed"
    assert second.lifecycle_counts[TrendLifecycleState.DORMANT] == 1
    with database.get_connection() as connection:
        latest = connection.execute(
            """SELECT s.lifecycle_state, s.previous_state,
                      s.failed_platform_count, s.missing_platform_count,
                      s.latest_fresh_age_hours, r.evaluation_id
               FROM hotspot_trend_states s
               JOIN hotspot_trend_runs r ON r.trend_run_id = s.trend_run_id
               ORDER BY r.evaluated_at DESC LIMIT 1"""
        ).fetchone()
        snapshot_count = connection.execute(
            "SELECT COUNT(*) FROM hotspot_snapshots"
        ).fetchone()[0]
    assert tuple(latest) == (
        "dormant",
        "emerging",
        1,
        3,
        "8.000278",
        "failed-watermark",
    )
    assert snapshot_count == 2


def test_no_phase5_events_returns_explicit_no_input(tmp_path: Path) -> None:
    database = _database(tmp_path)

    outcome = asyncio.run(HotspotTrendService(database).process_current())

    assert outcome.state == "no_input"
    assert outcome.trend_run_id is None


def test_replay_matches_previous_event_by_shared_groups(tmp_path: Path) -> None:
    database = _database(tmp_path)
    _prepare_clustering(database)
    service = HotspotTrendService(database)
    asyncio.run(service.process_current())

    # A new evaluation watermark reuses the unchanged Phase 5 event and must
    # carry the series through explicit shared-group lineage evidence.
    asyncio.run(
        HotspotRepository(database).save_collection(
            _failed_result(AT + timedelta(hours=1))
        )
    )
    second = asyncio.run(service.process_current())

    assert second.state == "processed"
    with database.get_connection() as connection:
        rows = connection.execute(
            """SELECT s.trend_series_id, s.lineage_match_kind,
                      s.lineage_overlap_count, s.predecessor_event_id
               FROM hotspot_trend_states s
               JOIN hotspot_trend_runs r ON r.trend_run_id = s.trend_run_id
               ORDER BY r.evaluated_at"""
        ).fetchall()
    assert rows[0]["trend_series_id"] == rows[1]["trend_series_id"]
    assert rows[1]["lineage_match_kind"] == "group_overlap"
    assert rows[1]["lineage_overlap_count"] == 2
    assert rows[1]["predecessor_event_id"] is not None
