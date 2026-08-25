from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.domain.hotspot import (
    CollectionStatus,
    CollectorResult,
    Freshness,
    Platform,
    ProviderAttempt,
    ProviderError,
    ProviderErrorKind,
    ProviderHotItem,
    ProviderResult,
    ProviderStatus,
    RawHotItem,
    snapshot_window_for,
)
from app.repositories.hotspot import (
    HotspotMigrationRunner,
    HotspotRepository,
    MigrationDriftError,
)
from app.services.database import Database

AT = datetime(2026, 8, 14, 8, 7, tzinfo=timezone.utc)


def _database(tmp_path: Path) -> Database:
    return Database(f"sqlite:///{tmp_path / 'hotspot.db'}")


def _result(
    run_id: str = "run-1",
    *,
    freshness: Freshness = Freshness.FRESH,
    status: CollectionStatus = CollectionStatus.SUCCESS,
    at: datetime = AT,
) -> CollectorResult:
    item = ProviderHotItem(
        title="真实热点",
        url="https://example.test/hot/1",
        external_id="source-1",
        rank=1,
        hot_score="999",
        raw_data={"title": "真实热点", "rank": 1},
    )
    provider_result = ProviderResult(
        provider_id="newsnow",
        platform=Platform.WEIBO,
        status=ProviderStatus.SUCCESS,
        freshness=freshness,
        fetched_at=at,
        observed_at=at,
        items=(item,),
        raw_payload=b'{"items":[{"title":"real"}]}',
        raw_content_type="application/json",
        metadata={"upstream": "newsnow"},
    )
    attempt = ProviderAttempt(
        provider_id="newsnow",
        attempt_number=1,
        started_at=at,
        finished_at=at + timedelta(seconds=1),
        result=provider_result,
    )
    raw_item = RawHotItem(
        raw_item_id=f"{run_id}:1",
        run_id=run_id,
        platform=Platform.WEIBO,
        provider_id="newsnow",
        title=item.title,
        url=item.url,
        external_id=item.external_id,
        rank=item.rank,
        hot_score=item.hot_score,
        published_at=None,
        observed_at=at,
        fetched_at=at,
        raw_data=item.raw_data,
        raw_payload_sha256=None,
    )
    return CollectorResult(
        run_id=run_id,
        platform=Platform.WEIBO,
        status=status,
        freshness=freshness,
        started_at=at,
        finished_at=at + timedelta(seconds=2),
        items=(raw_item,),
        attempts=(attempt,),
        winning_provider_id="newsnow",
        stale_reason="all_providers_failed" if freshness is Freshness.STALE else None,
    )


def _counts(database: Database) -> dict[str, int]:
    tables = (
        "hotspot_collection_runs",
        "hotspot_provider_attempts",
        "hotspot_raw_payloads",
        "hotspot_raw_items",
        "hotspot_snapshots",
        "hotspot_snapshot_members",
    )
    with database.get_connection() as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }


def test_migration_is_versioned_and_idempotent(tmp_path: Path) -> None:
    database = _database(tmp_path)
    runner = HotspotMigrationRunner(database)

    assert runner.apply() == (1, 2, 3, 4, 5, 6, 7, 8)
    assert runner.apply() == ()

    with database.get_connection() as connection:
        rows = connection.execute(
            "SELECT version, name, length(checksum) FROM hotspot_schema_migrations"
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        (1, "initial", 64),
        (2, "normalization", 64),
        (3, "event_clustering", 64),
        (4, "trend_lifecycle", 64),
        (5, "ai_classification", 64),
        (6, "reports", 64),
        (7, "deliveries", 64),
        (8, "annotations_knowledge", 64),
    ]


def test_fresh_collection_persists_evidence_and_one_snapshot(tmp_path: Path) -> None:
    database = _database(tmp_path)
    repository = HotspotRepository(database)

    asyncio.run(repository.save_collection(_result()))

    assert _counts(database) == {
        "hotspot_collection_runs": 1,
        "hotspot_provider_attempts": 1,
        "hotspot_raw_payloads": 1,
        "hotspot_raw_items": 1,
        "hotspot_snapshots": 1,
        "hotspot_snapshot_members": 1,
    }
    with database.get_connection() as connection:
        payload = connection.execute(
            "SELECT body, sha256 FROM hotspot_raw_payloads"
        ).fetchone()
    assert bytes(payload["body"]) == b'{"items":[{"title":"real"}]}'
    assert len(payload["sha256"]) == 64


def test_same_run_and_same_window_are_idempotent_without_losing_raw_runs(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    repository = HotspotRepository(database)

    asyncio.run(repository.save_collection(_result("run-1")))
    asyncio.run(repository.save_collection(_result("run-1")))
    asyncio.run(repository.save_collection(_result("run-2")))

    counts = _counts(database)
    assert counts["hotspot_collection_runs"] == 2
    assert counts["hotspot_raw_items"] == 2
    assert counts["hotspot_snapshots"] == 1
    assert counts["hotspot_snapshot_members"] == 1


def test_stale_replay_never_creates_a_new_snapshot(tmp_path: Path) -> None:
    database = _database(tmp_path)
    repository = HotspotRepository(database)

    asyncio.run(repository.save_collection(_result(freshness=Freshness.STALE)))

    counts = _counts(database)
    assert counts["hotspot_collection_runs"] == 1
    assert counts["hotspot_provider_attempts"] == 1
    assert counts["hotspot_raw_payloads"] == 1
    assert counts["hotspot_raw_items"] == 1
    assert counts["hotspot_snapshots"] == 0
    assert counts["hotspot_snapshot_members"] == 0


def test_failed_collection_preserves_error_without_snapshot(tmp_path: Path) -> None:
    database = _database(tmp_path)
    repository = HotspotRepository(database)
    error = ProviderError(
        kind=ProviderErrorKind.CONNECTION,
        code="upstream_offline",
        message="upstream is unavailable",
        retryable=True,
    )
    provider_result = ProviderResult(
        provider_id="newsnow",
        platform=Platform.WEIBO,
        status=ProviderStatus.FAILED,
        freshness=Freshness.FRESH,
        fetched_at=AT,
        observed_at=AT,
        error=error,
        raw_payload=b"gateway unavailable",
        raw_content_type="text/plain",
    )
    result = CollectorResult(
        run_id="failed-run",
        platform=Platform.WEIBO,
        status=CollectionStatus.FAILED,
        freshness=Freshness.FRESH,
        started_at=AT,
        finished_at=AT + timedelta(seconds=1),
        items=(),
        attempts=(
            ProviderAttempt(
                "newsnow", 1, AT, AT + timedelta(seconds=1), provider_result
            ),
        ),
        error=error,
    )

    asyncio.run(repository.save_collection(result))

    counts = _counts(database)
    assert counts["hotspot_collection_runs"] == 1
    assert counts["hotspot_raw_payloads"] == 1
    assert counts["hotspot_snapshots"] == 0
    with database.get_connection() as connection:
        row = connection.execute(
            "SELECT error_code, error_retryable FROM hotspot_collection_runs"
        ).fetchone()
    assert tuple(row) == ("upstream_offline", 1)


def test_latest_snapshot_is_explicitly_returned_as_stale(tmp_path: Path) -> None:
    repository = HotspotRepository(_database(tmp_path))
    asyncio.run(repository.save_collection(_result()))

    latest = asyncio.run(repository.get_latest(Platform.WEIBO))

    assert latest is not None
    assert latest.freshness is Freshness.STALE
    assert latest.items[0].title == "真实热点"
    assert latest.metadata["stale_source"] == "historical_snapshot"


def test_database_lock_is_owned_and_expired_locks_can_be_recovered(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    first_repository = HotspotRepository(database)
    second_repository = HotspotRepository(database)
    window = snapshot_window_for(Platform.DOUYIN, AT)

    async def compete() -> list[bool]:
        return list(
            await asyncio.gather(
                first_repository.try_acquire_lock(
                    window, "worker-a", ttl_seconds=30, now=AT
                ),
                second_repository.try_acquire_lock(
                    window, "worker-b", ttl_seconds=30, now=AT
                ),
            )
        )

    winners = asyncio.run(compete())
    assert sum(winners) == 1
    winner = "worker-a" if winners[0] else "worker-b"
    loser = "worker-b" if winners[0] else "worker-a"

    asyncio.run(first_repository.release_lock(window, loser))
    assert not asyncio.run(
        second_repository.try_acquire_lock(window, loser, ttl_seconds=30, now=AT)
    )
    assert asyncio.run(
        second_repository.try_acquire_lock(
            window,
            loser,
            ttl_seconds=30,
            now=AT + timedelta(seconds=31),
        )
    )
    asyncio.run(second_repository.release_lock(window, loser))
    asyncio.run(first_repository.release_lock(window, winner))


def test_migration_failure_does_not_mark_version_as_applied(tmp_path: Path) -> None:
    database = _database(tmp_path)
    root = tmp_path / "migrations"
    sqlite_dir = root / "sqlite"
    sqlite_dir.mkdir(parents=True)
    migration = sqlite_dir / "001_broken.sql"
    migration.write_text("CREATE TABL this_is_invalid", encoding="utf-8")

    try:
        HotspotMigrationRunner(database, root).apply()
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError("invalid migration must fail")

    migration.write_text(
        "CREATE TABLE recovered (id INTEGER PRIMARY KEY)", encoding="utf-8"
    )
    assert HotspotMigrationRunner(database, root).apply() == (1,)
    migration.write_text(
        "CREATE TABLE recovered (id INTEGER PRIMARY KEY, changed TEXT)",
        encoding="utf-8",
    )
    try:
        HotspotMigrationRunner(database, root).apply()
    except MigrationDriftError:
        pass
    else:
        raise AssertionError("edited applied migration must be rejected")
