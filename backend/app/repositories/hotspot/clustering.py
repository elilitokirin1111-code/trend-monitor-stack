"""Append-only persistence for Phase 5 clustering inputs, runs and evidence."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.domain.hotspot import ClusteringBatch, ClusterInputItem, Platform

from .migrations import HotspotMigrationRunner


class ClusteringDatabase(Protocol):
    db_type: str

    def get_connection(self): ...


class ClusteringRepository:
    def __init__(
        self,
        database: ClusteringDatabase,
        *,
        run_migrations: bool = True,
    ) -> None:
        self._database = database
        if run_migrations:
            HotspotMigrationRunner(database).apply()

    async def load_current_inputs(
        self,
        *,
        normalization_rule_version: str,
        normalization_config_hash: str,
        lookback_hours: int,
    ) -> tuple[ClusterInputItem, ...]:
        return await asyncio.to_thread(
            self._load_current_inputs,
            normalization_rule_version,
            normalization_config_hash,
            lookback_hours,
        )

    async def save_batch(self, batch: ClusteringBatch) -> bool:
        return await asyncio.to_thread(self._save_batch, batch)

    def _load_current_inputs(
        self,
        normalization_rule_version: str,
        normalization_config_hash: str,
        lookback_hours: int,
    ) -> tuple[ClusterInputItem, ...]:
        if not 1 <= lookback_hours <= 24 * 30:
            raise ValueError("lookback hours must be between 1 and 720")
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT MAX(s.observed_at) AS latest_observed_at
                       FROM hotspot_dedup_groups g
                       JOIN hotspot_normalization_runs r
                         ON r.normalization_run_id = g.normalization_run_id
                       JOIN hotspot_snapshots s ON s.snapshot_id = g.snapshot_id
                       WHERE r.rule_version = ? AND r.config_hash = ?"""
                ),
                (normalization_rule_version, normalization_config_hash),
            )
            row = cursor.fetchone()
            latest_value = _value(row, "latest_observed_at") if row else None
            if latest_value is None:
                return ()
            latest = _parse_dt(latest_value)
            cutoff = latest - timedelta(hours=lookback_hours)
            cursor.execute(
                self._sql(
                    """SELECT g.group_id, g.normalization_run_id, g.snapshot_id,
                              g.representative_normalized_item_id,
                              n.platform, n.provider_id, n.normalized_title,
                              n.title_fingerprint, n.canonical_url, n.rank_value,
                              n.published_at, s.observed_at
                       FROM hotspot_dedup_groups g
                       JOIN hotspot_normalization_runs r
                         ON r.normalization_run_id = g.normalization_run_id
                       JOIN hotspot_normalized_items n
                         ON n.normalized_item_id = g.representative_normalized_item_id
                       JOIN hotspot_snapshots s ON s.snapshot_id = g.snapshot_id
                       WHERE r.rule_version = ? AND r.config_hash = ?
                         AND s.observed_at >= ? AND s.observed_at <= ?
                       ORDER BY s.observed_at ASC, g.group_id ASC"""
                ),
                (
                    normalization_rule_version,
                    normalization_config_hash,
                    _iso(cutoff),
                    _iso(latest),
                ),
            )
            return tuple(
                ClusterInputItem(
                    group_id=_value(row, "group_id"),
                    normalization_run_id=_value(row, "normalization_run_id"),
                    normalized_item_id=_value(row, "representative_normalized_item_id"),
                    snapshot_id=_value(row, "snapshot_id"),
                    platform=Platform(_value(row, "platform")),
                    provider_id=_value(row, "provider_id"),
                    normalized_title=_value(row, "normalized_title"),
                    title_fingerprint=_value(row, "title_fingerprint"),
                    canonical_url=_value(row, "canonical_url"),
                    rank=_value(row, "rank_value"),
                    observed_at=_parse_dt(_value(row, "observed_at")),
                    published_at=_parse_dt(_value(row, "published_at")),
                )
                for row in cursor.fetchall()
            )

    def _save_batch(self, batch: ClusteringBatch) -> bool:
        created_at = _iso(datetime.now(timezone.utc))
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            if self._database.db_type == "sqlite":
                cursor.execute("PRAGMA foreign_keys = ON")
            insert = (
                "INSERT OR IGNORE INTO hotspot_clustering_runs "
                if self._database.db_type == "sqlite"
                else "INSERT IGNORE INTO hotspot_clustering_runs "
            )
            cursor.execute(
                self._sql(
                    insert
                    + """(
                        clustering_run_id, algorithm_version, config_hash,
                        config_json, normalization_rule_version,
                        normalization_config_hash, input_hash, window_start,
                        window_end, status, input_group_count,
                        candidate_pair_count, truncated_candidate_count,
                        semantic_call_count, event_count, started_at,
                        finished_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                ),
                (
                    batch.clustering_run_id,
                    batch.algorithm_version,
                    batch.config_hash,
                    batch.config_json,
                    batch.normalization_rule_version,
                    batch.normalization_config_hash,
                    batch.input_hash,
                    _iso(batch.window_start),
                    _iso(batch.window_end),
                    batch.status.value,
                    batch.input_group_count,
                    batch.candidate_pair_count,
                    batch.truncated_candidate_count,
                    batch.semantic_call_count,
                    len(batch.events),
                    _iso(batch.started_at),
                    _iso(batch.finished_at),
                    created_at,
                ),
            )
            if cursor.rowcount != 1:
                return False

            for candidate in batch.candidates:
                cursor.execute(
                    self._sql(
                        """INSERT INTO hotspot_cluster_candidates (
                            candidate_id, clustering_run_id, left_group_id,
                            right_group_id, recall_reasons_json, components_json,
                            deterministic_score, decision, semantic_status,
                            semantic_same_event, semantic_confidence,
                            semantic_reason, semantic_model_id, semantic_error,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                    ),
                    (
                        candidate.candidate_id,
                        candidate.clustering_run_id,
                        candidate.left_group_id,
                        candidate.right_group_id,
                        json.dumps(
                            list(candidate.recall_reasons),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        json.dumps(
                            dict(candidate.components),
                            ensure_ascii=False,
                            separators=(",", ":"),
                            sort_keys=True,
                        ),
                        str(candidate.deterministic_score),
                        candidate.decision.value,
                        candidate.semantic_status.value,
                        (
                            int(candidate.semantic_same_event)
                            if candidate.semantic_same_event is not None
                            else None
                        ),
                        (
                            str(candidate.semantic_confidence)
                            if candidate.semantic_confidence is not None
                            else None
                        ),
                        candidate.semantic_reason,
                        candidate.semantic_model_id,
                        candidate.semantic_error,
                        created_at,
                    ),
                )

            for event in batch.events:
                cursor.execute(
                    self._sql(
                        """INSERT INTO hotspot_events (
                            event_id, clustering_run_id, canonical_title,
                            representative_group_id,
                            representative_normalized_item_id, first_seen_at,
                            last_seen_at, platforms_json, platform_count,
                            member_count, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                    ),
                    (
                        event.event_id,
                        event.clustering_run_id,
                        event.canonical_title,
                        event.representative_group_id,
                        event.representative_normalized_item_id,
                        _iso(event.first_seen_at),
                        _iso(event.last_seen_at),
                        json.dumps(
                            [platform.value for platform in event.platforms],
                            separators=(",", ":"),
                        ),
                        len(event.platforms),
                        len(event.members),
                        created_at,
                    ),
                )
                for member in event.members:
                    cursor.execute(
                        self._sql(
                            """INSERT INTO hotspot_event_members (
                                event_id, group_id, normalized_item_id,
                                snapshot_id, platform, is_representative,
                                created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)"""
                        ),
                        (
                            event.event_id,
                            member.group_id,
                            member.normalized_item_id,
                            member.snapshot_id,
                            member.platform.value,
                            int(member.is_representative),
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


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _value(row, key: str):
    return row[key]
