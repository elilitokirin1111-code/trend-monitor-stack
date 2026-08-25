"""Append-only input and persistence adapter for Phase 6 trend lifecycles."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from app.domain.hotspot import (
    CollectionStatus,
    Freshness,
    Platform,
    PlatformSignal,
    PreviousTrendState,
    TrendBatch,
    TrendDataQuality,
    TrendEvaluationContext,
    TrendEventInput,
    TrendLifecycleState,
    TrendObservation,
)

from .migrations import HotspotMigrationRunner


class TrendDatabase(Protocol):
    db_type: str

    def get_connection(self): ...


@dataclass(frozen=True, slots=True)
class TrendRepositoryInput:
    events: tuple[TrendEventInput, ...]
    context: TrendEvaluationContext


@dataclass(frozen=True, slots=True)
class StoredPreviousTrend:
    state: PreviousTrendState
    representative_title_fingerprint: str
    group_ids: frozenset[str]


class TrendRepository:
    def __init__(
        self,
        database: TrendDatabase,
        *,
        run_migrations: bool = True,
    ) -> None:
        self._database = database
        if run_migrations:
            HotspotMigrationRunner(database).apply()

    async def load_current_input(self) -> TrendRepositoryInput | None:
        return await asyncio.to_thread(self._load_current_input)

    async def load_previous_trends(
        self,
        *,
        algorithm_version: str,
        config_hash: str,
        evaluated_before: datetime,
    ) -> tuple[StoredPreviousTrend, ...]:
        return await asyncio.to_thread(
            self._load_previous_trends,
            algorithm_version,
            config_hash,
            evaluated_before,
        )

    async def save_batch(self, batch: TrendBatch) -> bool:
        return await asyncio.to_thread(self._save_batch, batch)

    def _load_current_input(self) -> TrendRepositoryInput | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT clustering_run_id, window_start, window_end
                   FROM hotspot_clustering_runs
                   ORDER BY window_end DESC, finished_at DESC,
                            clustering_run_id DESC LIMIT 1"""
            )
            cluster_row = cursor.fetchone()
            if cluster_row is None:
                return None
            clustering_run_id = _value(cluster_row, "clustering_run_id")
            window_start = _parse_dt(_value(cluster_row, "window_start"))
            window_end = _parse_dt(_value(cluster_row, "window_end"))

            cursor.execute(
                """SELECT run_id, finished_at, window_start
                   FROM hotspot_collection_runs
                   ORDER BY finished_at DESC, run_id DESC LIMIT 1"""
            )
            evaluation_row = cursor.fetchone()
            if evaluation_row is None:
                return None
            evaluation_id = _value(evaluation_row, "run_id")
            evaluation_window = _value(evaluation_row, "window_start")
            evaluated_at = max(
                _parse_dt(_value(evaluation_row, "finished_at")), window_end
            )
            cursor.execute(
                self._sql(
                    """SELECT platform, status, freshness, finished_at
                       FROM hotspot_collection_runs
                       WHERE window_start = ?
                       ORDER BY platform ASC, finished_at DESC, run_id DESC"""
                ),
                (evaluation_window,),
            )
            signals_by_platform: dict[Platform, PlatformSignal] = {}
            for row in cursor.fetchall():
                platform = Platform(_value(row, "platform"))
                if platform in signals_by_platform:
                    continue
                signals_by_platform[platform] = PlatformSignal(
                    platform=platform,
                    status=CollectionStatus(_value(row, "status")),
                    freshness=Freshness(_value(row, "freshness")),
                    observed_at=_parse_dt(_value(row, "finished_at")),
                )
            context = TrendEvaluationContext(
                evaluation_id=evaluation_id,
                evaluated_at=evaluated_at,
                platform_signals=tuple(
                    signals_by_platform[platform]
                    for platform in Platform
                    if platform in signals_by_platform
                ),
            )

            cursor.execute(
                self._sql(
                    """SELECT e.event_id, e.canonical_title,
                              rep.title_fingerprint,
                              m.group_id, m.normalized_item_id, m.snapshot_id,
                              m.platform, n.rank_value, n.hot_score_value,
                              s.observed_at, s.freshness
                       FROM hotspot_events e
                       JOIN hotspot_normalized_items rep
                         ON rep.normalized_item_id =
                            e.representative_normalized_item_id
                       JOIN hotspot_event_members m ON m.event_id = e.event_id
                       JOIN hotspot_normalized_items n
                         ON n.normalized_item_id = m.normalized_item_id
                       JOIN hotspot_snapshots s ON s.snapshot_id = m.snapshot_id
                       WHERE e.clustering_run_id = ?
                       ORDER BY e.event_id ASC, s.observed_at ASC,
                                m.group_id ASC"""
                ),
                (clustering_run_id,),
            )
            event_rows: dict[str, list] = {}
            for row in cursor.fetchall():
                event_rows.setdefault(_value(row, "event_id"), []).append(row)
            events = []
            for event_id, rows in event_rows.items():
                first = rows[0]
                observations = tuple(
                    TrendObservation(
                        group_id=_value(row, "group_id"),
                        normalized_item_id=_value(row, "normalized_item_id"),
                        snapshot_id=_value(row, "snapshot_id"),
                        platform=Platform(_value(row, "platform")),
                        observed_at=_parse_dt(_value(row, "observed_at")),
                        freshness=Freshness(_value(row, "freshness")),
                        rank=_value(row, "rank_value"),
                        hot_score=(
                            Decimal(_value(row, "hot_score_value"))
                            if _value(row, "hot_score_value") is not None
                            else None
                        ),
                    )
                    for row in rows
                )
                events.append(
                    TrendEventInput(
                        event_id=event_id,
                        clustering_run_id=clustering_run_id,
                        canonical_title=_value(first, "canonical_title"),
                        representative_title_fingerprint=_value(
                            first, "title_fingerprint"
                        ),
                        window_start=window_start,
                        window_end=window_end,
                        observations=observations,
                    )
                )
            return TrendRepositoryInput(tuple(events), context)

    def _load_previous_trends(
        self,
        algorithm_version: str,
        config_hash: str,
        evaluated_before: datetime,
    ) -> tuple[StoredPreviousTrend, ...]:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT trend_run_id
                       FROM hotspot_trend_runs
                       WHERE algorithm_version = ? AND config_hash = ?
                         AND evaluated_at < ?
                       ORDER BY evaluated_at DESC, finished_at DESC LIMIT 1"""
                ),
                (algorithm_version, config_hash, _iso(evaluated_before)),
            )
            run = cursor.fetchone()
            if run is None:
                return ()
            trend_run_id = _value(run, "trend_run_id")
            cursor.execute(
                self._sql(
                    """SELECT ts.trend_series_id, ts.source_event_id,
                              ts.lifecycle_state, ts.last_fresh_seen_at,
                              ts.velocity, rep.title_fingerprint, em.group_id
                       FROM hotspot_trend_states ts
                       JOIN hotspot_events e ON e.event_id = ts.source_event_id
                       JOIN hotspot_normalized_items rep
                         ON rep.normalized_item_id =
                            e.representative_normalized_item_id
                       JOIN hotspot_event_members em
                         ON em.event_id = ts.source_event_id
                       WHERE ts.trend_run_id = ?
                       ORDER BY ts.source_event_id, em.group_id"""
                ),
                (trend_run_id,),
            )
            grouped: dict[str, list] = {}
            for row in cursor.fetchall():
                grouped.setdefault(_value(row, "source_event_id"), []).append(row)
            return tuple(
                StoredPreviousTrend(
                    state=PreviousTrendState(
                        trend_series_id=_value(rows[0], "trend_series_id"),
                        source_event_id=event_id,
                        state=TrendLifecycleState(_value(rows[0], "lifecycle_state")),
                        last_fresh_seen_at=_parse_dt(
                            _value(rows[0], "last_fresh_seen_at")
                        ),
                        velocity=Decimal(_value(rows[0], "velocity")),
                    ),
                    representative_title_fingerprint=_value(
                        rows[0], "title_fingerprint"
                    ),
                    group_ids=frozenset(_value(row, "group_id") for row in rows),
                )
                for event_id, rows in sorted(grouped.items())
            )

    def _save_batch(self, batch: TrendBatch) -> bool:
        created_at = _iso(datetime.now(timezone.utc))
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            if self._database.db_type == "sqlite":
                cursor.execute("PRAGMA foreign_keys = ON")
            insert = (
                "INSERT OR IGNORE INTO hotspot_trend_runs "
                if self._database.db_type == "sqlite"
                else "INSERT IGNORE INTO hotspot_trend_runs "
            )
            complete_count = sum(
                state.data_quality is TrendDataQuality.COMPLETE
                for state in batch.states
            )
            cursor.execute(
                self._sql(
                    insert
                    + """(
                        trend_run_id, source_clustering_run_id, evaluation_id,
                        algorithm_version, config_hash, config_json, input_hash,
                        evaluated_at, status, event_count, complete_count,
                        partial_count, started_at, finished_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                ),
                (
                    batch.trend_run_id,
                    batch.source_clustering_run_id,
                    batch.evaluation_id,
                    batch.algorithm_version,
                    batch.config_hash,
                    batch.config_json,
                    batch.input_hash,
                    _iso(batch.evaluated_at),
                    batch.status.value,
                    len(batch.states),
                    complete_count,
                    len(batch.states) - complete_count,
                    _iso(batch.started_at),
                    _iso(batch.finished_at),
                    created_at,
                ),
            )
            if cursor.rowcount != 1:
                return False
            for state in batch.states:
                features = state.features
                cursor.execute(
                    self._sql(
                        """INSERT INTO hotspot_trend_states (
                            trend_state_id, trend_run_id, trend_series_id,
                            source_event_id, predecessor_event_id,
                            lineage_match_kind, lineage_overlap_count,
                            canonical_title, lifecycle_state, previous_state,
                            trend_score, data_quality, evaluated_at,
                            observation_count, fresh_observation_count,
                            stale_observation_count, fresh_platform_count,
                            failed_platform_count, stale_platform_count,
                            missing_platform_count, data_completeness,
                            current_strength, previous_strength, earlier_strength,
                            velocity, acceleration, coverage_score,
                            persistence_score, active_duration_hours,
                            latest_fresh_age_hours, recurrence_gap_hours,
                            first_fresh_seen_at, last_fresh_seen_at,
                            features_json, created_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )"""
                    ),
                    (
                        state.trend_state_id,
                        state.trend_run_id,
                        state.trend_series_id,
                        state.source_event_id,
                        state.predecessor_event_id,
                        state.lineage_match_kind,
                        state.lineage_overlap_count,
                        state.canonical_title,
                        state.state.value,
                        state.previous_state.value if state.previous_state else None,
                        str(state.trend_score),
                        state.data_quality.value,
                        _iso(state.evaluated_at),
                        features.observation_count,
                        features.fresh_observation_count,
                        features.stale_observation_count,
                        features.fresh_platform_count,
                        features.failed_platform_count,
                        features.stale_platform_count,
                        features.missing_platform_count,
                        str(features.data_completeness),
                        str(features.current_strength),
                        str(features.previous_strength),
                        str(features.earlier_strength),
                        str(features.velocity),
                        str(features.acceleration),
                        str(features.coverage_score),
                        str(features.persistence_score),
                        str(features.active_duration_hours),
                        _decimal_text(features.latest_fresh_age_hours),
                        _decimal_text(features.recurrence_gap_hours),
                        _iso_optional(features.first_fresh_seen_at),
                        _iso_optional(features.last_fresh_seen_at),
                        json.dumps(
                            _features_dict(features),
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


def _features_dict(features) -> dict[str, object]:
    return {
        "acceleration": str(features.acceleration),
        "active_duration_hours": str(features.active_duration_hours),
        "coverage_score": str(features.coverage_score),
        "current_strength": str(features.current_strength),
        "data_completeness": str(features.data_completeness),
        "earlier_strength": str(features.earlier_strength),
        "failed_platform_count": features.failed_platform_count,
        "first_fresh_seen_at": _iso_optional(features.first_fresh_seen_at),
        "fresh_observation_count": features.fresh_observation_count,
        "fresh_platform_count": features.fresh_platform_count,
        "last_fresh_seen_at": _iso_optional(features.last_fresh_seen_at),
        "latest_fresh_age_hours": _decimal_text(features.latest_fresh_age_hours),
        "missing_platform_count": features.missing_platform_count,
        "observation_count": features.observation_count,
        "persistence_score": str(features.persistence_score),
        "previous_strength": str(features.previous_strength),
        "recurrence_gap_hours": _decimal_text(features.recurrence_gap_hours),
        "stale_observation_count": features.stale_observation_count,
        "stale_platform_count": features.stale_platform_count,
        "velocity": str(features.velocity),
    }


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _iso_optional(value: datetime | None) -> str | None:
    return _iso(value) if value else None


def _value(row, key: str):
    return row[key]
