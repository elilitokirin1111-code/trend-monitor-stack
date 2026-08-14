"""Persistence adapter for versioned normalization and dedup batches."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Protocol

from app.domain.hotspot import (
    NormalizationBatch,
    NormalizationStatus,
    Platform,
    SnapshotRawItem,
)

from .migrations import HotspotMigrationRunner


class NormalizationDatabase(Protocol):
    db_type: str

    def get_connection(self): ...


class NormalizationRepository:
    def __init__(
        self,
        database: NormalizationDatabase,
        *,
        run_migrations: bool = True,
    ) -> None:
        self._database = database
        if run_migrations:
            HotspotMigrationRunner(database).apply()

    async def list_pending_snapshots(
        self,
        *,
        rule_version: str,
        config_hash: str,
        limit: int = 100,
    ) -> tuple[str, ...]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        return await asyncio.to_thread(
            self._list_pending_snapshots,
            rule_version,
            config_hash,
            limit,
        )

    async def load_snapshot(self, snapshot_id: str) -> tuple[SnapshotRawItem, ...]:
        return await asyncio.to_thread(self._load_snapshot, snapshot_id)

    async def save_batch(self, batch: NormalizationBatch) -> bool:
        return await asyncio.to_thread(self._save_batch, batch)

    def _list_pending_snapshots(
        self,
        rule_version: str,
        config_hash: str,
        limit: int,
    ) -> tuple[str, ...]:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT s.snapshot_id
                       FROM hotspot_snapshots s
                       WHERE NOT EXISTS (
                           SELECT 1 FROM hotspot_normalization_runs n
                           WHERE n.snapshot_id = s.snapshot_id
                             AND n.rule_version = ?
                             AND n.config_hash = ?
                       )
                       ORDER BY s.window_start ASC, s.platform ASC
                       LIMIT ?"""
                ),
                (rule_version, config_hash, limit),
            )
            return tuple(_value(row, "snapshot_id") for row in cursor.fetchall())

    def _load_snapshot(self, snapshot_id: str) -> tuple[SnapshotRawItem, ...]:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT m.position, i.raw_item_id, i.platform, i.provider_id,
                              i.external_id, i.title, i.url, i.rank_value,
                              i.hot_score, i.published_at, i.observed_at,
                              i.raw_data_json
                       FROM hotspot_snapshot_members m
                       JOIN hotspot_raw_items i ON i.raw_item_id = m.raw_item_id
                       WHERE m.snapshot_id = ?
                       ORDER BY m.position ASC"""
                ),
                (snapshot_id,),
            )
            return tuple(
                SnapshotRawItem(
                    snapshot_id=snapshot_id,
                    raw_item_id=_value(row, "raw_item_id"),
                    position=int(_value(row, "position")),
                    platform=Platform(_value(row, "platform")),
                    provider_id=_value(row, "provider_id"),
                    title=_value(row, "title"),
                    url=_value(row, "url"),
                    external_id=_value(row, "external_id"),
                    rank=_value(row, "rank_value"),
                    hot_score=_value(row, "hot_score"),
                    published_at=_parse_dt(_value(row, "published_at")),
                    observed_at=_parse_dt(_value(row, "observed_at")),
                    raw_data=json.loads(_value(row, "raw_data_json")),
                )
                for row in cursor.fetchall()
            )

    def _save_batch(self, batch: NormalizationBatch) -> bool:
        created_at = _iso(datetime.now(timezone.utc))
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            if self._database.db_type == "sqlite":
                cursor.execute("PRAGMA foreign_keys = ON")
            counts = {
                status: sum(item.status is status for item in batch.items)
                for status in NormalizationStatus
            }
            insert = (
                "INSERT OR IGNORE INTO hotspot_normalization_runs "
                if self._database.db_type == "sqlite"
                else "INSERT IGNORE INTO hotspot_normalization_runs "
            )
            cursor.execute(
                self._sql(
                    insert
                    + """(
                        normalization_run_id, snapshot_id, rule_version,
                        config_hash, config_json, algorithm_version, status,
                        total_count, success_count, partial_count, failed_count,
                        started_at, finished_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                ),
                (
                    batch.normalization_run_id,
                    batch.snapshot_id,
                    batch.rule_version,
                    batch.config_hash,
                    batch.config_json,
                    batch.algorithm_version,
                    batch.status.value,
                    len(batch.items),
                    counts[NormalizationStatus.SUCCESS],
                    counts[NormalizationStatus.PARTIAL],
                    counts[NormalizationStatus.FAILED],
                    _iso(batch.started_at),
                    _iso(batch.finished_at),
                    created_at,
                ),
            )
            if cursor.rowcount != 1:
                return False

            for item in batch.items:
                cursor.execute(
                    self._sql(
                        """INSERT INTO hotspot_normalized_items (
                            normalized_item_id, normalization_run_id, snapshot_id,
                            raw_item_id, source_position, platform, provider_id,
                            rank_value, external_id_normalized, normalized_title,
                            title_fingerprint, canonical_url, hot_score_value,
                            hot_score_unit, published_at, published_at_precision,
                            status, warnings_json, error_code, rule_version, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                    ),
                    (
                        item.normalized_item_id,
                        item.normalization_run_id,
                        item.snapshot_id,
                        item.raw_item_id,
                        item.position,
                        item.platform.value,
                        item.provider_id,
                        item.rank,
                        item.external_id_normalized,
                        item.normalized_title,
                        item.title_fingerprint,
                        item.canonical_url,
                        item.hot_score_value,
                        item.hot_score_unit,
                        _iso(item.published_at),
                        item.published_at_precision.value,
                        item.status.value,
                        json.dumps(
                            list(item.warnings),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        item.error_code,
                        item.rule_version,
                        created_at,
                    ),
                )

            for group in batch.groups:
                cursor.execute(
                    self._sql(
                        """INSERT INTO hotspot_dedup_groups (
                            group_id, normalization_run_id, snapshot_id,
                            algorithm_version, representative_normalized_item_id,
                            member_count, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)"""
                    ),
                    (
                        group.group_id,
                        group.normalization_run_id,
                        group.snapshot_id,
                        group.algorithm_version,
                        group.representative_normalized_item_id,
                        len(group.members),
                        created_at,
                    ),
                )
                for member in group.members:
                    cursor.execute(
                        self._sql(
                            """INSERT INTO hotspot_dedup_members (
                                group_id, normalized_item_id, is_representative,
                                match_kind, evidence_json, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?)"""
                        ),
                        (
                            group.group_id,
                            member.normalized_item_id,
                            int(member.is_representative),
                            member.match_kind,
                            json.dumps(
                                [dict(evidence) for evidence in member.evidence],
                                ensure_ascii=False,
                                separators=(",", ":"),
                                sort_keys=True,
                            ),
                            created_at,
                        ),
                    )
        return True

    def _sql(self, statement: str) -> str:
        return (
            statement
            if self._database.db_type == "sqlite"
            else statement.replace("?", "%s")
        )


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def _value(row, key: str):
    return row[key]
