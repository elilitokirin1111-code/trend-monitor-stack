"""Append-only persistence for report channel deliveries."""

from __future__ import annotations

import asyncio
from typing import Any, Protocol

from app.domain.hotspot import DeliveryRecord

from .migrations import HotspotMigrationRunner


class DeliveryDatabase(Protocol):
    db_type: str

    def get_connection(self): ...


class DeliveryRepository:
    def __init__(
        self,
        database: DeliveryDatabase,
        *,
        run_migrations: bool = True,
    ) -> None:
        self._database = database
        if run_migrations:
            HotspotMigrationRunner(database).apply()

    async def find(
        self,
        *,
        report_run_id: str,
        channel: str,
        content_version: str,
        chunk_index: int,
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(
            self._find, report_run_id, channel, content_version, chunk_index
        )

    async def save(self, record: DeliveryRecord) -> None:
        await asyncio.to_thread(self._save, record)

    async def list_deliveries(
        self,
        *,
        report_run_id: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._list_deliveries, report_run_id, status, limit, offset
        )

    async def get_delivery(self, delivery_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_delivery, delivery_id)

    # ------------------------------------------------------------------

    def _find(
        self,
        report_run_id: str,
        channel: str,
        content_version: str,
        chunk_index: int,
    ) -> dict[str, Any] | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT * FROM hotspot_report_deliveries
                       WHERE report_run_id = ? AND channel = ?
                         AND content_version = ? AND chunk_index = ?"""
                ),
                (report_run_id, channel, content_version, chunk_index),
            )
            row = cursor.fetchone()
        return self._delivery_dict(row) if row is not None else None

    def _save(self, record: DeliveryRecord) -> None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """INSERT OR REPLACE INTO hotspot_report_deliveries (
                        delivery_id, report_run_id, channel, content_version,
                        chunk_index, total_chunks, status, attempt, latency_ms,
                        error_kind, error_message, response_json,
                        created_at, finished_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
                ),
                (
                    record.delivery_id,
                    record.report_run_id,
                    record.channel,
                    record.content_version,
                    record.chunk_index,
                    record.total_chunks,
                    record.status.value,
                    record.attempt,
                    record.latency_ms,
                    record.error_kind.value if record.error_kind else None,
                    record.error_message,
                    record.response_json,
                    record.created_at.isoformat(),
                    record.finished_at.isoformat(),
                ),
            )

    def _list_deliveries(
        self,
        report_run_id: str | None,
        status: str | None,
        limit: int,
        offset: int,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must not be negative")
        where = []
        params: list[Any] = []
        if report_run_id:
            where.append("report_run_id = ?")
            params.append(report_run_id)
        if status:
            where.append("status = ?")
            params.append(status)
        clause = f" WHERE {' AND '.join(where)}" if where else ""
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT COUNT(*) AS total FROM hotspot_report_deliveries"
                    + clause
                ),
                tuple(params),
            )
            total = int(_value(cursor.fetchone(), "total") or 0)
            cursor.execute(
                self._sql(
                    "SELECT * FROM hotspot_report_deliveries"
                    + clause
                    + " ORDER BY finished_at DESC, chunk_index ASC,"
                    "   delivery_id DESC LIMIT ? OFFSET ?"
                ),
                tuple(params + [limit, offset]),
            )
            items = [self._delivery_dict(row) for row in cursor.fetchall()]
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def _get_delivery(self, delivery_id: str) -> dict[str, Any] | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    "SELECT * FROM hotspot_report_deliveries"
                    " WHERE delivery_id = ?"
                ),
                (delivery_id,),
            )
            row = cursor.fetchone()
        return self._delivery_dict(row) if row is not None else None

    def _delivery_dict(self, row) -> dict[str, Any]:
        return {
            "delivery_id": _value(row, "delivery_id"),
            "report_run_id": _value(row, "report_run_id"),
            "channel": _value(row, "channel"),
            "content_version": _value(row, "content_version"),
            "chunk_index": _value(row, "chunk_index"),
            "total_chunks": _value(row, "total_chunks"),
            "status": _value(row, "status"),
            "attempt": _value(row, "attempt"),
            "latency_ms": _value(row, "latency_ms"),
            "error_kind": _value(row, "error_kind"),
            "error_message": _value(row, "error_message"),
            "response": _value(row, "response_json"),
            "created_at": _value(row, "created_at"),
            "finished_at": _value(row, "finished_at"),
        }

    def _sql(self, statement: str) -> str:
        if self._database.db_type == "sqlite":
            return statement
        return statement.replace("?", "%s")


def _value(row, key: str):
    return row[key]
