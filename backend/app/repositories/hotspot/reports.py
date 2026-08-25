"""Append-only input and persistence adapter for versioned hotspot reports.

The report repository reads only versioned derived data (trend states, events,
AI classifications) plus collection-run freshness signals. It never reads
Provider payloads and never rewrites historical report runs.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

from app.domain.hotspot import (
    CollectionStatus,
    Freshness,
    Platform,
    ReportBatch,
    ReportEventItem,
    ReportInput,
    ReportPlatformSignal,
    ReportType,
)
from app.reports.rules import report_input_hash, report_run_id_base

from .migrations import HotspotMigrationRunner


class ReportDatabase(Protocol):
    db_type: str

    def get_connection(self): ...


@dataclass(frozen=True, slots=True)
class StoredReportRun:
    report_run_id: str
    report_type: str
    period_start: str
    period_end: str
    report_version: str
    config_hash: str
    input_hash: str
    status: str
    data_quality: str
    template: str
    attempt: int
    started_at: str
    finished_at: str
    created_at: str


class ReportRepository:
    def __init__(
        self,
        database: ReportDatabase,
        *,
        run_migrations: bool = True,
    ) -> None:
        self._database = database
        if run_migrations:
            HotspotMigrationRunner(database).apply()

    async def load_current_input(
        self,
        report_type: ReportType,
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> ReportInput | None:
        return await asyncio.to_thread(
            self._load_current_input,
            report_type,
            period_start=period_start,
            period_end=period_end,
        )

    async def run_exists(self, report_run_id: str) -> bool:
        return await asyncio.to_thread(self._run_exists, report_run_id)

    async def next_attempt(self, report_run_id_base: str) -> int:
        return await asyncio.to_thread(self._next_attempt, report_run_id_base)

    async def save_batch(self, batch: ReportBatch) -> bool:
        return await asyncio.to_thread(self._save_batch, batch)

    async def list_runs(
        self,
        *,
        report_type: ReportType | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._list_runs, report_type, limit, offset
        )

    async def get_run(self, report_run_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_run, report_run_id)

    # ------------------------------------------------------------------

    def _load_current_input(
        self,
        report_type: ReportType,
        *,
        period_start: datetime,
        period_end: datetime,
    ) -> ReportInput | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT trend_run_id, evaluated_at
                       FROM hotspot_trend_runs
                       ORDER BY evaluated_at DESC, finished_at DESC,
                                trend_run_id DESC LIMIT 1"""
                )
            )
            trend_row = cursor.fetchone()
            if trend_row is None:
                return None
            source_trend_run_id = _value(trend_row, "trend_run_id")

            cursor.execute(
                self._sql(
                    """SELECT classification_run_id
                       FROM hotspot_classification_runs
                       WHERE source_trend_run_id = ?
                       ORDER BY finished_at DESC, created_at DESC LIMIT 1"""
                ),
                (source_trend_run_id,),
            )
            classification_row = cursor.fetchone()
            source_classification_run_id = (
                _value(classification_row, "classification_run_id")
                if classification_row
                else None
            )

            cursor.execute(
                self._sql(
                    """SELECT ts.trend_state_id, ts.source_event_id,
                              ts.trend_series_id, ts.canonical_title,
                              ts.lifecycle_state, ts.trend_score,
                              ts.data_quality
                       FROM hotspot_trend_states ts
                       WHERE ts.trend_run_id = ?
                       ORDER BY ts.evaluated_at ASC"""
                ),
                (source_trend_run_id,),
            )
            trend_rows = cursor.fetchall()
            if not trend_rows:
                return None

            platform_cover: dict[str, tuple[str, ...]] = {}
            for row in trend_rows:
                event_id = _value(row, "source_event_id")
                cursor.execute(
                    self._sql(
                        """SELECT platform FROM hotspot_event_members
                           WHERE event_id = ?"""
                    ),
                    (event_id,),
                )
                platform_cover[event_id] = tuple(
                    sorted({_value(item, "platform") for item in cursor.fetchall()})
                )

            classification_by_state: dict[str, dict[str, Any]] = {}
            if source_classification_run_id:
                cursor.execute(
                    self._sql(
                        """SELECT trend_state_id, hospitality_relevance,
                                  hospitality_score, confidence, summary, status
                           FROM hotspot_ai_classifications
                           WHERE classification_run_id = ?"""
                    ),
                    (source_classification_run_id,),
                )
                for row in cursor.fetchall():
                    classification_by_state[_value(row, "trend_state_id")] = {
                        "relevance": _value(row, "hospitality_relevance"),
                        "score": _value(row, "hospitality_score"),
                        "summary": _value(row, "summary"),
                        "status": _value(row, "status"),
                    }

            events = []
            for row in trend_rows:
                classification = classification_by_state.get(
                    _value(row, "trend_state_id"), {}
                )
                classification_status = classification.get("status")
                summary = classification.get("summary")
                if (
                    classification_status is not None
                    and classification_status != "success"
                ):
                    summary = None
                events.append(
                    ReportEventItem(
                        event_id=_value(row, "source_event_id"),
                        trend_series_id=_value(row, "trend_series_id"),
                        canonical_title=_value(row, "canonical_title"),
                        trend_state=_value(row, "lifecycle_state"),
                        trend_score=Decimal(
                            str(_value(row, "trend_score") or "0")
                        ),
                        data_quality=_value(row, "data_quality"),
                        platforms=platform_cover.get(
                            _value(row, "source_event_id"), ()
                        ),
                        hospitality_relevance=classification.get("relevance"),
                        hospitality_score=(
                            Decimal(str(classification["score"]))
                            if classification.get("score") is not None
                            else None
                        ),
                        summary=summary,
                    )
                )

            cursor.execute(
                self._sql(
                    """SELECT platform, status, freshness, finished_at
                       FROM hotspot_collection_runs
                       WHERE window_start >= ? AND window_start < ?
                       ORDER BY platform ASC, finished_at DESC, run_id DESC"""
                ),
                (period_start.isoformat(), period_end.isoformat()),
            )
            latest_by_platform: dict[str, tuple[Any, ...]] = {}
            for row in cursor.fetchall():
                platform = _value(row, "platform")
                if platform not in latest_by_platform:
                    latest_by_platform[platform] = row
            signals = []
            for platform, row in sorted(latest_by_platform.items()):
                signals.append(
                    ReportPlatformSignal(
                        platform=Platform(platform),
                        status=CollectionStatus(_value(row, "status")),
                        freshness=Freshness(_value(row, "freshness")),
                        observed_at=_parse_dt(_value(row, "finished_at")),
                    )
                )
        return ReportInput(
            report_type=report_type,
            period_start=period_start,
            period_end=period_end,
            source_trend_run_id=source_trend_run_id,
            source_classification_run_id=source_classification_run_id,
            events=tuple(events),
            platform_signals=tuple(signals),
        )

    def _run_exists(self, report_run_id: str) -> bool:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT 1 FROM hotspot_report_runs WHERE report_run_id = ?"
                ),
                (report_run_id,),
            )
            return cursor.fetchone() is not None

    def _next_attempt(self, base: str) -> int:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT COALESCE(MAX(attempt), 0) + 1 AS next_attempt
                       FROM hotspot_report_runs
                       WHERE report_run_id_base = ?"""
                ),
                (base,),
            )
            return int(_value(cursor.fetchone(), "next_attempt") or 1)

    def _save_batch(self, batch: ReportBatch) -> bool:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """INSERT OR IGNORE INTO hotspot_report_runs (
                        report_run_id, report_run_id_base, report_type,
                        period_start, period_end, report_version,
                        config_hash, config_json, input_hash, status,
                        data_quality, stale_platforms_json,
                        missing_platforms_json, content, template,
                        source_trend_run_id, source_classification_run_id,
                        attempt, started_at, finished_at, created_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                 ?, ?, ?, ?, ?, ?)"""
                ),
                (
                    batch.report_run_id,
                    batch.report_run_id.split("#")[0],
                    batch.report_type.value,
                    batch.period_start.isoformat(),
                    batch.period_end.isoformat(),
                    batch.report_version,
                    batch.config_hash,
                    batch.config_json,
                    batch.input_hash,
                    batch.status.value,
                    batch.data_quality.value,
                    json.dumps(batch.stale_platforms, ensure_ascii=False),
                    json.dumps(batch.missing_platforms, ensure_ascii=False),
                    batch.content,
                    batch.template,
                    batch.source_trend_run_id,
                    batch.source_classification_run_id,
                    batch.attempt,
                    batch.started_at.isoformat(),
                    batch.finished_at.isoformat(),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            return cursor.rowcount > 0

    def _list_runs(
        self,
        report_type: ReportType | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must not be negative")
        where = " WHERE report_type = ?" if report_type else ""
        params: list[Any] = [report_type.value] if report_type else []
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT COUNT(*) AS total FROM hotspot_report_runs" + where
                ),
                tuple(params),
            )
            total = int(_value(cursor.fetchone(), "total") or 0)
            cursor.execute(
                self._sql(
                    "SELECT * FROM hotspot_report_runs"
                    + where
                    + " ORDER BY period_start DESC, finished_at DESC,"
                    "   report_run_id DESC LIMIT ? OFFSET ?"
                ),
                tuple(params + [limit, offset]),
            )
            items = [self._run_dict(row) for row in cursor.fetchall()]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def _get_run(self, report_run_id: str) -> dict[str, Any] | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT * FROM hotspot_report_runs WHERE report_run_id = ?"
                ),
                (report_run_id,),
            )
            row = cursor.fetchone()
        return self._run_dict(row) if row is not None else None

    def _run_dict(self, row) -> dict[str, Any]:
        return {
            "report_run_id": _value(row, "report_run_id"),
            "report_type": _value(row, "report_type"),
            "period_start": _value(row, "period_start"),
            "period_end": _value(row, "period_end"),
            "report_version": _value(row, "report_version"),
            "config_hash": _value(row, "config_hash"),
            "input_hash": _value(row, "input_hash"),
            "status": _value(row, "status"),
            "data_quality": _value(row, "data_quality"),
            "stale_platforms": _json(_value(row, "stale_platforms_json"), []),
            "missing_platforms": _json(_value(row, "missing_platforms_json"), []),
            "content": _value(row, "content"),
            "template": _value(row, "template"),
            "source_trend_run_id": _value(row, "source_trend_run_id"),
            "source_classification_run_id": _value(
                row, "source_classification_run_id"
            ),
            "attempt": _value(row, "attempt"),
            "started_at": _value(row, "started_at"),
            "finished_at": _value(row, "finished_at"),
            "created_at": _value(row, "created_at"),
        }

    def _sql(self, statement: str) -> str:
        if self._database.db_type == "sqlite":
            return statement
        return (
            statement.replace("?", "%s")
            .replace("INSERT OR IGNORE INTO", "INSERT IGNORE INTO")
        )


def report_id_for(
    *,
    report_type: ReportType,
    period_start: datetime,
    rules,
    input_hash: str,
    attempt: int = 1,
) -> str:
    base = report_run_id_base(
        report_type=report_type.value,
        period_start=period_start.astimezone(timezone.utc).isoformat(),
        report_version=rules.report_version,
        config_hash=rules.config_hash,
        input_hash=input_hash,
    )
    return f"{base}#a{attempt}" if attempt > 1 else base


def _value(row, key: str):
    return row[key]


def _json(value, default):
    if value is None:
        return default
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return default
    return parsed if isinstance(parsed, list) else default


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)
