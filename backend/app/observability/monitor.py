"""Database-aggregated pipeline monitoring.

Reads the append-only hotspot tables to answer operational questions:
provider success/latency/empty/stale/fallback, pipeline backlogs, AI
failures and report/delivery state. Never writes; never invents data.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol


class MonitorDatabase(Protocol):
    db_type: str

    def get_connection(self): ...

    def get_setting(self, key: str, default: str | None = None): ...


class PipelineMonitor:
    def __init__(self, database: MonitorDatabase, *, as_of: datetime | None = None) -> None:
        self._database = database
        self._as_of = as_of or datetime.now(timezone.utc)
        # 确保监控查询所需的表存在（幂等，只读场景也安全）
        from app.repositories.hotspot import HotspotMigrationRunner

        HotspotMigrationRunner(database).apply()

    async def provider_metrics(self, *, hours: int = 24) -> dict[str, Any]:
        return await asyncio.to_thread(self._provider_metrics, hours)

    async def collection_overview(self, *, hours: int = 24) -> dict[str, Any]:
        return await asyncio.to_thread(self._collection_overview, hours)

    async def pipeline_status(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._pipeline_status)

    async def summary(self, *, hours: int = 24) -> dict[str, Any]:
        provider = await self.provider_metrics(hours=hours)
        collection = await self.collection_overview(hours=hours)
        pipeline = await self.pipeline_status()
        return {
            "as_of": self._as_of.isoformat(),
            "window_hours": hours,
            "provider": provider,
            "collection": collection,
            "pipeline": pipeline,
        }

    # ------------------------------------------------------------------

    def _provider_metrics(self, hours: int) -> dict[str, Any]:
        since = self._as_of - timedelta(hours=hours)
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT cr.platform, pa.provider_id,
                              COUNT(*) AS attempts,
                              SUM(CASE WHEN pa.status = 'success'
                                       THEN 1 ELSE 0 END) AS success_count,
                              SUM(CASE WHEN pa.item_count = 0
                                       THEN 1 ELSE 0 END) AS empty_count,
                              SUM(CASE WHEN pa.attempt_number > 1
                                       THEN 1 ELSE 0 END) AS fallback_count,
                              AVG(
                                  (julianday(pa.finished_at)
                                   - julianday(pa.started_at)) * 86400.0
                              ) AS avg_latency_seconds
                       FROM hotspot_provider_attempts pa
                       JOIN hotspot_collection_runs cr
                         ON cr.run_id = pa.run_id
                       WHERE pa.finished_at >= ?
                       GROUP BY cr.platform, pa.provider_id
                       ORDER BY cr.platform, pa.provider_id"""
                    if self._database.db_type == "sqlite"
                    else """SELECT cr.platform, pa.provider_id,
                              COUNT(*) AS attempts,
                              SUM(CASE WHEN pa.status = 'success'
                                       THEN 1 ELSE 0 END) AS success_count,
                              SUM(CASE WHEN pa.item_count = 0
                                       THEN 1 ELSE 0 END) AS empty_count,
                              SUM(CASE WHEN pa.attempt_number > 1
                                       THEN 1 ELSE 0 END) AS fallback_count,
                              AVG(TIMESTAMPDIFF(
                                  SECOND, pa.started_at, pa.finished_at
                              )) AS avg_latency_seconds
                       FROM hotspot_provider_attempts pa
                       JOIN hotspot_collection_runs cr
                         ON cr.run_id = pa.run_id
                       WHERE pa.finished_at >= ?
                       GROUP BY cr.platform, pa.provider_id
                       ORDER BY cr.platform, pa.provider_id"""
                ),
                (since.isoformat(),),
            )
            rows = cursor.fetchall()
        items = []
        for row in rows:
            attempts = int(_value(row, "attempts") or 0)
            success = int(_value(row, "success_count") or 0)
            empty = int(_value(row, "empty_count") or 0)
            fallback = int(_value(row, "fallback_count") or 0)
            latency = _value(row, "avg_latency_seconds")
            items.append(
                {
                    "platform": _value(row, "platform"),
                    "provider_id": _value(row, "provider_id"),
                    "attempts": attempts,
                    "success_rate": success / attempts if attempts else None,
                    "empty_count": empty,
                    "fallback_attempts": fallback,
                    "fallback_ratio": fallback / attempts if attempts else None,
                    "avg_latency_seconds": round(float(latency), 3)
                    if latency is not None
                    else None,
                }
            )
        return {"items": items, "total_attempts": sum(i["attempts"] for i in items)}

    def _collection_overview(self, hours: int) -> dict[str, Any]:
        since = self._as_of - timedelta(hours=hours)
        now = self._as_of
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT platform, status, COUNT(*) AS count
                       FROM hotspot_collection_runs
                       WHERE finished_at >= ?
                       GROUP BY platform, status"""
                ),
                (since.isoformat(),),
            )
            runs = cursor.fetchall()
            cursor.execute(
                self._sql(
                    """SELECT platform, freshness,
                              MAX(observed_at) AS latest_observed_at
                       FROM hotspot_snapshots
                       WHERE created_at >= ?
                       GROUP BY platform, freshness"""
                ),
                (since.isoformat(),),
            )
            snapshots = cursor.fetchall()
        by_platform: dict[str, dict[str, int]] = {}
        for row in runs:
            platform = _value(row, "platform")
            bucket = by_platform.setdefault(
                platform, {"runs": 0, "failed": 0, "empty": 0, "stale": 0}
            )
            bucket["runs"] += int(_value(row, "count") or 0)
            if _value(row, "status") == "failed":
                bucket["failed"] += int(_value(row, "count") or 0)
        stale_age: dict[str, float | None] = {}
        for row in snapshots:
            platform = _value(row, "platform")
            if _value(row, "freshness") == "stale":
                observed = _parse_dt(_value(row, "latest_observed_at"))
                stale_age[platform] = (
                    (now - observed).total_seconds() / 60 if observed else None
                )
        return {
            "platforms": [
                {
                    "platform": platform,
                    **bucket,
                    "latest_stale_age_minutes": stale_age.get(platform),
                }
                for platform, bucket in sorted(by_platform.items())
            ],
            "runs": sum(b["runs"] for b in by_platform.values()),
            "failed_runs": sum(b["failed"] for b in by_platform.values()),
        }

    def _pipeline_status(self) -> dict[str, Any]:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            pending = self._scalar(
                cursor,
                """SELECT COUNT(*) AS count FROM hotspot_snapshots s
                   WHERE NOT EXISTS (
                       SELECT 1 FROM hotspot_normalization_runs nr
                       WHERE nr.snapshot_id = s.snapshot_id
                   )""",
            )
            last_clustering = self._latest(
                cursor,
                "hotspot_clustering_runs",
                "clustering_run_id, status, event_count, candidate_pair_count",
                "finished_at",
            )
            last_trend = self._latest(
                cursor,
                "hotspot_trend_runs",
                "trend_run_id, status, event_count",
                "finished_at",
            )
            last_classification = self._latest(
                cursor,
                "hotspot_classification_runs",
                "classification_run_id, status, event_count, failed_count",
                "finished_at",
            )
            last_report = self._latest(
                cursor,
                "hotspot_report_runs",
                "report_run_id, report_type, status, data_quality",
                "finished_at",
            )
            deliveries = self._scalar(
                cursor,
                """SELECT COUNT(*) AS count FROM hotspot_report_deliveries
                   WHERE status = 'failed'""",
            )
        return {
            "pending_normalization_snapshots": pending,
            "last_clustering": last_clustering,
            "last_trend": last_trend,
            "last_classification": last_classification,
            "last_report": last_report,
            "failed_deliveries_total": deliveries,
        }

    def _latest(self, cursor, table: str, columns: str, order_column: str):
        cursor.execute(
            self._sql(
                f"SELECT {columns} FROM {table}"
                f" ORDER BY {order_column} DESC, created_at DESC LIMIT 1"
            )
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return {key: _value(row, key) for key in _columns(columns)}

    def _scalar(self, cursor, statement: str) -> int:
        cursor.execute(self._sql(statement))
        row = cursor.fetchone()
        return int(_value(row, "count") or 0) if row is not None else 0

    def _sql(self, statement: str) -> str:
        return statement if self._database.db_type == "sqlite" else statement


def _columns(select: str) -> list[str]:
    return [part.strip().split(" ")[-1].strip() for part in select.split(",")]


def _value(row, key: str):
    return row[key]


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
