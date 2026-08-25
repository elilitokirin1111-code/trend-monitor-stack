"""Append-only manual annotations and knowledge synchronization audit records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from .migrations import HotspotMigrationRunner


class AnnotationDatabase(Protocol):
    db_type: str

    def get_connection(self): ...


class AnnotationRepository:
    def __init__(
        self,
        database: AnnotationDatabase,
        *,
        run_migrations: bool = True,
    ) -> None:
        self._database = database
        if run_migrations:
            HotspotMigrationRunner(database).apply()

    def save_annotation(
        self,
        *,
        event_id: str,
        review_status: str,
        topic_category: str | None,
        tags: list[str],
        hospitality_relevance: str | None,
        decision_lane: str | None,
        notes: str | None,
        summary_override: str | None,
        updated_by: str,
    ) -> dict[str, Any] | None:
        created_at = _iso(datetime.now(timezone.utc))
        annotation_id = f"annotation-{uuid4()}"
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            context = self._event_context(cursor, event_id)
            if context is None:
                return None
            trend_series_id = _value(context, "trend_series_id")
            cursor.execute(
                self._sql(
                    "SELECT COALESCE(MAX(revision), 0) AS revision "
                    "FROM hotspot_event_annotations WHERE trend_series_id = ?"
                ),
                (trend_series_id,),
            )
            revision = int(_value(cursor.fetchone(), "revision") or 0) + 1
            cursor.execute(
                self._sql(
                    """INSERT INTO hotspot_event_annotations (
                        annotation_id, trend_series_id, source_event_id, revision,
                        review_status, topic_category, tags_json,
                        hospitality_relevance, decision_lane, notes,
                        summary_override, updated_by, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                ),
                (
                    annotation_id,
                    trend_series_id,
                    event_id,
                    revision,
                    review_status,
                    topic_category,
                    _json(tags),
                    hospitality_relevance,
                    decision_lane,
                    notes,
                    summary_override,
                    updated_by,
                    created_at,
                ),
            )
        return self.get_annotation(annotation_id)

    def get_annotation(self, annotation_id: str) -> dict[str, Any] | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT * FROM hotspot_event_annotations WHERE annotation_id = ?"
                ),
                (annotation_id,),
            )
            row = cursor.fetchone()
        return _annotation_dict(row) if row is not None else None

    def get_latest_for_event(self, event_id: str) -> dict[str, Any] | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            context = self._event_context(cursor, event_id)
            if context is None:
                return None
            cursor.execute(
                self._sql(
                    """SELECT * FROM hotspot_event_annotations
                       WHERE trend_series_id = ?
                       ORDER BY revision DESC LIMIT 1"""
                ),
                (_value(context, "trend_series_id"),),
            )
            row = cursor.fetchone()
        return _annotation_dict(row) if row is not None else None

    def find_successful_sync(
        self,
        *,
        annotation_id: str,
        knowledge_base_id: str,
        content_hash: str,
    ) -> dict[str, Any] | None:
        return self._find_sync(
            """annotation_id = ? AND knowledge_base_id = ?
               AND content_hash = ? AND status = 'success'""",
            (annotation_id, knowledge_base_id, content_hash),
        )

    def find_latest_knowledge_sync(
        self,
        *,
        trend_series_id: str,
        knowledge_base_id: str,
    ) -> dict[str, Any] | None:
        return self._find_sync(
            """trend_series_id = ? AND knowledge_base_id = ?
               AND status = 'success' AND knowledge_id IS NOT NULL""",
            (trend_series_id, knowledge_base_id),
        )

    def latest_sync_for_event(self, event_id: str) -> dict[str, Any] | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            context = self._event_context(cursor, event_id)
            if context is None:
                return None
            cursor.execute(
                self._sql(
                    """SELECT * FROM hotspot_knowledge_syncs
                       WHERE trend_series_id = ?
                       ORDER BY finished_at DESC LIMIT 1"""
                ),
                (_value(context, "trend_series_id"),),
            )
            row = cursor.fetchone()
        return _sync_dict(row) if row is not None else None

    def record_sync(
        self,
        *,
        annotation: Mapping[str, Any],
        source_event_id: str,
        knowledge_base_id: str,
        knowledge_id: str | None,
        content_hash: str,
        status: str,
        operation: str,
        parse_status: str | None,
        error_kind: str | None,
        error_message: str | None,
        response_json: str | None,
        started_at: datetime,
        finished_at: datetime,
    ) -> dict[str, Any]:
        sync_id = f"knowledge-sync-{uuid4()}"
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """INSERT INTO hotspot_knowledge_syncs (
                        sync_id, annotation_id, trend_series_id, source_event_id,
                        provider, knowledge_base_id, knowledge_id, content_hash,
                        status, operation, parse_status, error_kind,
                        error_message, response_json, started_at, finished_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                ),
                (
                    sync_id,
                    annotation["annotation_id"],
                    annotation["trend_series_id"],
                    source_event_id,
                    "weknora",
                    knowledge_base_id,
                    knowledge_id,
                    content_hash,
                    status,
                    operation,
                    parse_status,
                    error_kind,
                    error_message,
                    response_json,
                    _iso(started_at),
                    _iso(finished_at),
                ),
            )
        result = self._find_sync("sync_id = ?", (sync_id,))
        if result is None:  # pragma: no cover - database contract violation
            raise RuntimeError("knowledge sync record was not persisted")
        return result

    def _find_sync(self, where: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    f"SELECT * FROM hotspot_knowledge_syncs WHERE {where} "
                    "ORDER BY finished_at DESC LIMIT 1"
                ),
                params,
            )
            row = cursor.fetchone()
        return _sync_dict(row) if row is not None else None

    def _event_context(self, cursor, event_id: str):
        cursor.execute(
            self._sql(
                """SELECT trend_series_id, source_event_id
                   FROM hotspot_trend_states
                   WHERE source_event_id = ?
                   ORDER BY evaluated_at DESC LIMIT 1"""
            ),
            (event_id,),
        )
        return cursor.fetchone()

    def _sql(self, statement: str) -> str:
        if self._database.db_type == "mysql":
            return statement.replace("?", "%s")
        return statement


def _annotation_dict(row) -> dict[str, Any]:
    return {
        "annotation_id": _value(row, "annotation_id"),
        "trend_series_id": _value(row, "trend_series_id"),
        "source_event_id": _value(row, "source_event_id"),
        "revision": int(_value(row, "revision")),
        "review_status": _value(row, "review_status"),
        "topic_category": _value(row, "topic_category"),
        "tags": _json_value(_value(row, "tags_json"), []),
        "hospitality_relevance": _value(row, "hospitality_relevance"),
        "decision_lane": _value(row, "decision_lane"),
        "notes": _value(row, "notes"),
        "summary_override": _value(row, "summary_override"),
        "updated_by": _value(row, "updated_by"),
        "created_at": _value(row, "created_at"),
    }


def _sync_dict(row) -> dict[str, Any]:
    return {
        "sync_id": _value(row, "sync_id"),
        "annotation_id": _value(row, "annotation_id"),
        "trend_series_id": _value(row, "trend_series_id"),
        "source_event_id": _value(row, "source_event_id"),
        "provider": _value(row, "provider"),
        "knowledge_base_id": _value(row, "knowledge_base_id"),
        "knowledge_id": _value(row, "knowledge_id"),
        "content_hash": _value(row, "content_hash"),
        "status": _value(row, "status"),
        "operation": _value(row, "operation"),
        "parse_status": _value(row, "parse_status"),
        "error_kind": _value(row, "error_kind"),
        "error_message": _value(row, "error_message"),
        "started_at": _value(row, "started_at"),
        "finished_at": _value(row, "finished_at"),
    }


def _value(row, key: str):
    if isinstance(row, Mapping):
        return row.get(key)
    return row[key]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_value(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value) if value else default
    except (TypeError, json.JSONDecodeError):
        return default


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()
