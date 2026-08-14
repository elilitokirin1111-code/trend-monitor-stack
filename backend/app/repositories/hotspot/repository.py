"""Append-only repository for collection evidence and historical snapshots."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

from app.domain.hotspot import (
    CollectionStatus,
    CollectorResult,
    Freshness,
    Platform,
    ProviderHotItem,
    ProviderResult,
    ProviderStatus,
    SnapshotWindow,
    snapshot_window_for,
)

from .migrations import HotspotMigrationRunner


class RepositoryDatabase(Protocol):
    db_type: str

    def get_connection(self): ...


class WindowedCollectionWriter:
    def __init__(self, repository: HotspotRepository, window: SnapshotWindow) -> None:
        self._repository = repository
        self._window = window

    async def save_collection(self, result: CollectorResult) -> None:
        await self._repository.save_collection_for_window(result, self._window)


class HotspotRepository:
    """Persists every Provider attempt while keeping snapshots immutable."""

    def __init__(
        self,
        database: RepositoryDatabase,
        *,
        interval_minutes: int = 30,
        run_migrations: bool = True,
    ) -> None:
        if not 1 <= interval_minutes <= 1440:
            raise ValueError("interval_minutes must be between 1 and 1440")
        self._database = database
        self._interval_minutes = interval_minutes
        if run_migrations:
            HotspotMigrationRunner(database).apply()

    def writer_for(self, window: SnapshotWindow) -> WindowedCollectionWriter:
        return WindowedCollectionWriter(self, window)

    async def save_collection(self, result: CollectorResult) -> None:
        window = snapshot_window_for(
            result.platform, result.started_at, self._interval_minutes
        )
        await self.save_collection_for_window(result, window)

    async def save_collection_for_window(
        self,
        result: CollectorResult,
        window: SnapshotWindow,
    ) -> None:
        if result.platform is not window.platform:
            raise ValueError("collection platform does not match snapshot window")
        await asyncio.to_thread(self._save_collection, result, window)

    async def get_latest(self, platform: Platform) -> ProviderResult | None:
        return await asyncio.to_thread(self._get_latest, platform)

    async def snapshot_exists(self, window: SnapshotWindow) -> bool:
        return await asyncio.to_thread(self._snapshot_exists, window)

    async def try_acquire_lock(
        self,
        window: SnapshotWindow,
        owner_id: str,
        *,
        ttl_seconds: int,
        now: datetime,
    ) -> bool:
        if not owner_id.strip():
            raise ValueError("owner_id cannot be empty")
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")
        return await asyncio.to_thread(
            self._try_acquire_lock, window.lock_key, owner_id, ttl_seconds, now
        )

    async def release_lock(self, window: SnapshotWindow, owner_id: str) -> None:
        await asyncio.to_thread(self._release_lock, window.lock_key, owner_id)

    def _save_collection(
        self,
        result: CollectorResult,
        window: SnapshotWindow,
    ) -> None:
        created_at = _iso(datetime.now(timezone.utc))
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            if self._database.db_type == "sqlite":
                cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute(
                self._sql(
                    "SELECT run_id FROM hotspot_collection_runs WHERE run_id = ?"
                ),
                (result.run_id,),
            )
            if cursor.fetchone() is not None:
                return

            error = result.error
            cursor.execute(
                self._sql(
                    """INSERT INTO hotspot_collection_runs (
                        run_id, platform, status, freshness, window_start, window_end,
                        started_at, finished_at, winning_provider_id, stale_reason,
                        error_kind, error_code, error_message, error_retryable,
                        error_upstream_status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                ),
                (
                    result.run_id,
                    result.platform.value,
                    result.status.value,
                    result.freshness.value,
                    _iso(window.start),
                    _iso(window.end),
                    _iso(result.started_at),
                    _iso(result.finished_at),
                    result.winning_provider_id,
                    result.stale_reason,
                    error.kind.value if error else None,
                    error.code if error else None,
                    error.message if error else None,
                    int(error.retryable) if error else None,
                    error.upstream_status if error else None,
                    created_at,
                ),
            )

            winning_attempt = self._find_winning_attempt(result)
            for attempt in result.attempts:
                provider_result = attempt.result
                payload_id = self._insert_payload(
                    cursor,
                    result.run_id,
                    attempt.attempt_number,
                    provider_result,
                    created_at,
                )
                self._insert_attempt(
                    cursor, result.run_id, attempt, payload_id, created_at
                )
                if (
                    result.freshness is Freshness.STALE
                    or attempt is not winning_attempt
                ):
                    self._insert_attempt_items(
                        cursor,
                        result.run_id,
                        attempt.attempt_number,
                        provider_result,
                        created_at,
                    )

            if result.freshness is Freshness.FRESH:
                winning_number = (
                    winning_attempt.attempt_number
                    if winning_attempt is not None
                    else None
                )
                for position, item in enumerate(result.items, start=1):
                    self._insert_raw_item(
                        cursor,
                        raw_item_id=item.raw_item_id,
                        run_id=result.run_id,
                        platform=item.platform,
                        provider_id=item.provider_id,
                        attempt_number=winning_number,
                        position=position,
                        selected=True,
                        freshness=result.freshness,
                        external_id=item.external_id,
                        title=item.title,
                        url=item.url,
                        rank=item.rank,
                        hot_score=item.hot_score,
                        published_at=item.published_at,
                        observed_at=item.observed_at,
                        fetched_at=item.fetched_at,
                        raw_data=item.raw_data,
                        raw_payload_sha256=item.raw_payload_sha256,
                        created_at=created_at,
                    )
                if result.status is not CollectionStatus.FAILED:
                    self._insert_snapshot(cursor, result, window, created_at)

    def _insert_payload(self, cursor, run_id, attempt_number, result, created_at):
        if result.raw_payload is None:
            return None
        payload_id = str(
            uuid5(
                NAMESPACE_URL,
                f"hotspot-payload:{run_id}:{result.provider_id}:{attempt_number}",
            )
        )
        cursor.execute(
            self._sql(
                """INSERT INTO hotspot_raw_payloads (
                    payload_id, run_id, provider_id, platform, attempt_number,
                    content_type, sha256, body, fetched_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            ),
            (
                payload_id,
                run_id,
                result.provider_id,
                result.platform.value,
                attempt_number,
                result.raw_content_type,
                hashlib.sha256(result.raw_payload).hexdigest(),
                result.raw_payload,
                _iso(result.fetched_at),
                created_at,
            ),
        )
        return payload_id

    def _insert_attempt(self, cursor, run_id, attempt, payload_id, created_at):
        result = attempt.result
        error = result.error
        cursor.execute(
            self._sql(
                """INSERT INTO hotspot_provider_attempts (
                    run_id, provider_id, attempt_number, started_at, finished_at,
                    status, freshness, item_count, observed_at, fetched_at,
                    source_updated_at, error_kind, error_code, error_message,
                    error_retryable, error_upstream_status, raw_payload_id, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            ),
            (
                run_id,
                attempt.provider_id,
                attempt.attempt_number,
                _iso(attempt.started_at),
                _iso(attempt.finished_at),
                result.status.value,
                result.freshness.value,
                len(result.items),
                _iso(result.observed_at),
                _iso(result.fetched_at),
                _iso(result.source_updated_at),
                error.kind.value if error else None,
                error.code if error else None,
                error.message if error else None,
                int(error.retryable) if error else None,
                error.upstream_status if error else None,
                payload_id,
                _json(result.metadata),
            ),
        )

    def _insert_attempt_items(
        self, cursor, run_id, attempt_number, result, created_at
    ) -> None:
        payload_hash = (
            hashlib.sha256(result.raw_payload).hexdigest()
            if result.raw_payload is not None
            else None
        )
        for position, item in enumerate(result.items, start=1):
            raw_item_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"hotspot-item:{run_id}:{result.provider_id}:{attempt_number}:{position}",
                )
            )
            self._insert_raw_item(
                cursor,
                raw_item_id=raw_item_id,
                run_id=run_id,
                platform=result.platform,
                provider_id=result.provider_id,
                attempt_number=attempt_number,
                position=position,
                selected=False,
                freshness=result.freshness,
                external_id=item.external_id,
                title=item.title,
                url=item.url,
                rank=item.rank,
                hot_score=item.hot_score,
                published_at=item.published_at,
                observed_at=result.observed_at,
                fetched_at=result.fetched_at,
                raw_data=item.raw_data,
                raw_payload_sha256=payload_hash,
                created_at=created_at,
            )

    def _insert_raw_item(self, cursor, **values) -> None:
        cursor.execute(
            self._sql(
                """INSERT INTO hotspot_raw_items (
                    raw_item_id, run_id, platform, provider_id,
                    provider_attempt_number, source_item_position, is_selected,
                    freshness, external_id, title, url, rank_value, hot_score,
                    published_at, observed_at, fetched_at, raw_data_json,
                    raw_payload_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            ),
            (
                values["raw_item_id"],
                values["run_id"],
                values["platform"].value,
                values["provider_id"],
                values["attempt_number"],
                values["position"],
                int(values["selected"]),
                values["freshness"].value,
                values["external_id"],
                values["title"],
                values["url"],
                values["rank"],
                values["hot_score"],
                _iso(values["published_at"]),
                _iso(values["observed_at"]),
                _iso(values["fetched_at"]),
                _json(values["raw_data"]),
                values["raw_payload_sha256"],
                values["created_at"],
            ),
        )

    def _insert_snapshot(self, cursor, result, window, created_at) -> None:
        if result.winning_provider_id is None:
            raise ValueError("fresh non-failed collection requires a winning provider")
        snapshot_id = str(
            uuid5(
                NAMESPACE_URL,
                f"hotspot-snapshot:{result.platform.value}:{_iso(window.start)}",
            )
        )
        statement = """INSERT {ignore} INTO hotspot_snapshots (
            snapshot_id, platform, window_start, window_end, collection_run_id,
            winning_provider_id, freshness, observed_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""".format(
            ignore="OR IGNORE" if self._database.db_type == "sqlite" else "IGNORE"
        )
        observed_at = (
            result.items[0].observed_at if result.items else result.finished_at
        )
        cursor.execute(
            self._sql(statement),
            (
                snapshot_id,
                result.platform.value,
                _iso(window.start),
                _iso(window.end),
                result.run_id,
                result.winning_provider_id,
                result.freshness.value,
                _iso(observed_at),
                created_at,
            ),
        )
        cursor.execute(
            self._sql(
                "SELECT collection_run_id FROM hotspot_snapshots WHERE snapshot_id = ?"
            ),
            (snapshot_id,),
        )
        row = cursor.fetchone()
        if row is None or _value(row, "collection_run_id") != result.run_id:
            return
        for position, item in enumerate(result.items, start=1):
            cursor.execute(
                self._sql(
                    "INSERT INTO hotspot_snapshot_members "
                    "(snapshot_id, raw_item_id, position) VALUES (?, ?, ?)"
                ),
                (snapshot_id, item.raw_item_id, position),
            )

    def _get_latest(self, platform: Platform) -> ProviderResult | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT s.snapshot_id, s.winning_provider_id, s.observed_at,
                              r.finished_at
                       FROM hotspot_snapshots s
                       JOIN hotspot_collection_runs r ON r.run_id = s.collection_run_id
                       WHERE s.platform = ?
                       ORDER BY s.window_start DESC LIMIT 1"""
                ),
                (platform.value,),
            )
            snapshot = cursor.fetchone()
            if snapshot is None:
                return None
            cursor.execute(
                self._sql(
                    """SELECT i.* FROM hotspot_snapshot_members m
                       JOIN hotspot_raw_items i ON i.raw_item_id = m.raw_item_id
                       WHERE m.snapshot_id = ? ORDER BY m.position"""
                ),
                (_value(snapshot, "snapshot_id"),),
            )
            rows = cursor.fetchall()
            if not rows:
                return None
            items = tuple(
                ProviderHotItem(
                    title=_value(row, "title"),
                    url=_value(row, "url"),
                    external_id=_value(row, "external_id"),
                    rank=_value(row, "rank_value"),
                    hot_score=_value(row, "hot_score"),
                    published_at=_parse_dt(_value(row, "published_at")),
                    raw_data=json.loads(_value(row, "raw_data_json")),
                )
                for row in rows
            )
            return ProviderResult(
                provider_id=_value(snapshot, "winning_provider_id"),
                platform=platform,
                status=ProviderStatus.SUCCESS,
                freshness=Freshness.STALE,
                fetched_at=_parse_dt(_value(snapshot, "finished_at")),
                observed_at=_parse_dt(_value(snapshot, "observed_at")),
                items=items,
                metadata={
                    "snapshot_id": _value(snapshot, "snapshot_id"),
                    "stale_source": "historical_snapshot",
                },
            )

    def _snapshot_exists(self, window: SnapshotWindow) -> bool:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT 1 FROM hotspot_snapshots WHERE platform = ? AND window_start = ?"
                ),
                (window.platform.value, _iso(window.start)),
            )
            return cursor.fetchone() is not None

    def _try_acquire_lock(
        self, lock_key: str, owner_id: str, ttl_seconds: int, now: datetime
    ) -> bool:
        expires_at = now + timedelta(seconds=ttl_seconds)
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "DELETE FROM hotspot_collection_locks WHERE lock_key = ? AND expires_at <= ?"
                ),
                (lock_key, _iso(now)),
            )
            insert = (
                "INSERT OR IGNORE INTO hotspot_collection_locks "
                if self._database.db_type == "sqlite"
                else "INSERT IGNORE INTO hotspot_collection_locks "
            )
            cursor.execute(
                self._sql(
                    insert
                    + "(lock_key, owner_id, acquired_at, expires_at) VALUES (?, ?, ?, ?)"
                ),
                (lock_key, owner_id, _iso(now), _iso(expires_at)),
            )
            return cursor.rowcount == 1

    def _release_lock(self, lock_key: str, owner_id: str) -> None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "DELETE FROM hotspot_collection_locks WHERE lock_key = ? AND owner_id = ?"
                ),
                (lock_key, owner_id),
            )

    @staticmethod
    def _find_winning_attempt(result: CollectorResult):
        if result.winning_provider_id is None:
            return None
        for attempt in reversed(result.attempts):
            if (
                attempt.provider_id == result.winning_provider_id
                and attempt.result.items
            ):
                return attempt
        return None

    def _sql(self, statement: str) -> str:
        return (
            statement
            if self._database.db_type == "sqlite"
            else statement.replace("?", "%s")
        )


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        dict(value), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _value(row, key: str):
    return row[key]
