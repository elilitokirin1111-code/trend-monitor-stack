"""Append-only persistence adapter for Phase 7 AI classifications."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Protocol

from app.domain.hotspot import (
    ClassificationBatch,
    ClassificationEvidence,
    ClassificationInput,
    ClassificationStatus,
    Platform,
    TrendDataQuality,
    TrendLifecycleState,
)

from .migrations import HotspotMigrationRunner


class ClassificationDatabase(Protocol):
    db_type: str

    def get_connection(self): ...


@dataclass(frozen=True, slots=True)
class ClassificationRepositoryInput:
    source_trend_run_id: str
    items: tuple[ClassificationInput, ...]


class ClassificationRepository:
    def __init__(
        self,
        database: ClassificationDatabase,
        *,
        run_migrations: bool = True,
    ) -> None:
        self._database = database
        if run_migrations:
            HotspotMigrationRunner(database).apply()

    async def load_current_input(self) -> ClassificationRepositoryInput | None:
        return await asyncio.to_thread(self._load_current_input)

    async def save_batch(self, batch: ClassificationBatch) -> bool:
        return await asyncio.to_thread(self._save_batch, batch)

    async def run_exists(self, classification_run_id: str) -> bool:
        return await asyncio.to_thread(self._run_exists, classification_run_id)

    def _run_exists(self, classification_run_id: str) -> bool:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT 1 FROM hotspot_classification_runs
                       WHERE classification_run_id = ? LIMIT 1"""
                ),
                (classification_run_id,),
            )
            return cursor.fetchone() is not None

    def _load_current_input(self) -> ClassificationRepositoryInput | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                """SELECT trend_run_id
                   FROM hotspot_trend_runs
                   ORDER BY evaluated_at DESC, finished_at DESC,
                            trend_run_id DESC LIMIT 1"""
            )
            run_row = cursor.fetchone()
            if run_row is None:
                return None
            trend_run_id = _value(run_row, "trend_run_id")
            cursor.execute(
                self._sql(
                    """SELECT ts.trend_state_id, ts.source_event_id,
                              ts.canonical_title, ts.lifecycle_state,
                              ts.trend_score, ts.data_quality, ts.evaluated_at,
                              m.normalized_item_id, m.platform,
                              n.normalized_title, n.rank_value,
                              n.hot_score_value, snap.observed_at
                       FROM hotspot_trend_states ts
                       JOIN hotspot_event_members m
                         ON m.event_id = ts.source_event_id
                       JOIN hotspot_normalized_items n
                         ON n.normalized_item_id = m.normalized_item_id
                       JOIN hotspot_snapshots snap
                         ON snap.snapshot_id = m.snapshot_id
                       WHERE ts.trend_run_id = ?
                       ORDER BY ts.trend_state_id ASC,
                                snap.observed_at ASC,
                                m.normalized_item_id ASC"""
                ),
                (trend_run_id,),
            )
            grouped: dict[str, list] = {}
            for row in cursor.fetchall():
                grouped.setdefault(_value(row, "trend_state_id"), []).append(row)
            items = []
            for trend_state_id, rows in grouped.items():
                first = rows[0]
                items.append(
                    ClassificationInput(
                        trend_state_id=trend_state_id,
                        source_event_id=_value(first, "source_event_id"),
                        canonical_title=_value(first, "canonical_title"),
                        lifecycle_state=TrendLifecycleState(
                            _value(first, "lifecycle_state")
                        ),
                        trend_score=Decimal(_value(first, "trend_score")),
                        data_quality=TrendDataQuality(_value(first, "data_quality")),
                        evaluated_at=_parse_dt(_value(first, "evaluated_at")),
                        evidence=tuple(
                            ClassificationEvidence(
                                evidence_id=_value(row, "normalized_item_id"),
                                platform=Platform(_value(row, "platform")),
                                title=_value(row, "normalized_title"),
                                observed_at=_parse_dt(_value(row, "observed_at")),
                                rank=_value(row, "rank_value"),
                                hot_score=(
                                    Decimal(_value(row, "hot_score_value"))
                                    if _value(row, "hot_score_value") is not None
                                    else None
                                ),
                            )
                            for row in rows
                        ),
                    )
                )
            return ClassificationRepositoryInput(trend_run_id, tuple(items))

    def _save_batch(self, batch: ClassificationBatch) -> bool:
        created_at = _iso(datetime.now(timezone.utc))
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            if self._database.db_type == "sqlite":
                cursor.execute("PRAGMA foreign_keys = ON")
            insert = (
                "INSERT OR IGNORE INTO hotspot_classification_runs "
                if self._database.db_type == "sqlite"
                else "INSERT IGNORE INTO hotspot_classification_runs "
            )
            success_count = sum(
                record.status is ClassificationStatus.SUCCESS
                for record in batch.records
            )
            failed_count = sum(
                record.status is ClassificationStatus.FAILED for record in batch.records
            )
            skipped_count = sum(
                record.status is ClassificationStatus.SKIPPED
                for record in batch.records
            )
            cursor.execute(
                self._sql(
                    insert
                    + """(
                        classification_run_id, source_trend_run_id,
                        classifier_version, prompt_version, model,
                        config_hash, config_json, input_hash, status,
                        event_count, success_count, failed_count, skipped_count,
                        started_at, finished_at, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                ),
                (
                    batch.classification_run_id,
                    batch.source_trend_run_id,
                    batch.classifier_version,
                    batch.prompt_version,
                    batch.model,
                    batch.config_hash,
                    batch.config_json,
                    batch.input_hash,
                    batch.status.value,
                    len(batch.records),
                    success_count,
                    failed_count,
                    skipped_count,
                    _iso(batch.started_at),
                    _iso(batch.finished_at),
                    created_at,
                ),
            )
            if cursor.rowcount != 1:
                return False
            for record in batch.records:
                decision = record.decision
                decision_json = (
                    json.dumps(
                        _decision_dict(decision),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    )
                    if decision
                    else None
                )
                cursor.execute(
                    self._sql(
                        """INSERT INTO hotspot_ai_classifications (
                            classification_id, classification_run_id,
                            trend_state_id, source_event_id, status, model,
                            prompt_version, request_hash, topic_category,
                            tags_json, hospitality_relevance,
                            hospitality_score, confidence, rationale, summary,
                            evidence_ids_json, decision_json, response_json,
                            response_hash, latency_ms, prompt_tokens,
                            completion_tokens, cost, error_kind, error_message,
                            created_at
                        ) VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?
                        )"""
                    ),
                    (
                        record.classification_id,
                        record.classification_run_id,
                        record.trend_state_id,
                        record.source_event_id,
                        record.status.value,
                        record.model,
                        record.prompt_version,
                        record.request_hash,
                        decision.category.value if decision else None,
                        _json_list(decision.tags) if decision else None,
                        (decision.hospitality_relevance.value if decision else None),
                        str(decision.hospitality_score) if decision else None,
                        str(decision.confidence) if decision else None,
                        decision.rationale if decision else None,
                        decision.summary if decision else None,
                        _json_list(decision.evidence_ids) if decision else None,
                        decision_json,
                        record.response_json,
                        record.response_hash,
                        record.latency_ms,
                        record.prompt_tokens,
                        record.completion_tokens,
                        str(record.cost) if record.cost is not None else None,
                        record.error_kind.value if record.error_kind else None,
                        record.error_message,
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


def _decision_dict(decision) -> dict[str, object]:
    return {
        "category": decision.category.value,
        "confidence": str(decision.confidence),
        "evidence_ids": list(decision.evidence_ids),
        "hospitality_relevance": decision.hospitality_relevance.value,
        "hospitality_score": str(decision.hospitality_score),
        "rationale": decision.rationale,
        "summary": decision.summary,
        "tags": list(decision.tags),
    }


def _json_list(values) -> str:
    return json.dumps(
        list(values), ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _value(row, key: str):
    return row[key]
