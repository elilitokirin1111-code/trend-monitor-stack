"""Read-only projection used by the Phase 8 hotspot dashboard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol

from .migrations import HotspotMigrationRunner

PLATFORMS = ("douyin", "weibo", "bilibili", "xiaohongshu")


class DashboardDatabase(Protocol):
    db_type: str

    def get_connection(self): ...
    def get_setting(self, key: str, default: str | None = None): ...


class HotspotDashboardRepository:
    """Build a current, auditable read model without mutating source records."""

    def __init__(
        self, database: DashboardDatabase, *, run_migrations: bool = True
    ) -> None:
        self._database = database
        if run_migrations:
            HotspotMigrationRunner(database).apply()

    def get_overview(self, *, as_of: datetime | None = None) -> dict[str, Any]:
        now = _as_utc(as_of or datetime.now(timezone.utc))
        stale_after = self._stale_after_minutes()
        with self._database.get_connection() as connection:
            platforms = [
                self._platform_health(connection, platform, now, stale_after)
                for platform in PLATFORMS
            ]
            trend = self._latest_trend_run(connection)
        return {
            "generated_at": _iso(now),
            "has_data": any(item["snapshot_id"] for item in platforms),
            "event_count": int(_value(trend, "event_count") or 0) if trend else 0,
            "trend_run": self._trend_run_dict(trend),
            "platforms": platforms,
        }

    def list_events(
        self,
        *,
        q: str | None = None,
        platform: str | None = None,
        lifecycle: str | None = None,
        hospitality_relevance: str | None = None,
        data_quality: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        if offset < 0:
            raise ValueError("offset must not be negative")
        with self._database.get_connection() as connection:
            trend = self._latest_trend_run(connection)
            if trend is None:
                return self._empty_events(limit, offset)
            trend_run_id = _value(trend, "trend_run_id")
            classification = self._latest_classification_run(connection, trend_run_id)
            classification_run_id = (
                _value(classification, "classification_run_id")
                if classification
                else None
            )
            where, params = self._event_filters(
                trend_run_id=trend_run_id,
                classification_run_id=classification_run_id,
                q=q,
                platform=platform,
                lifecycle=lifecycle,
                hospitality_relevance=hospitality_relevance,
                data_quality=data_quality,
            )
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    self._event_select(classification_run_id, count=True) + where
                ),
                tuple(params),
            )
            total = int(_value(cursor.fetchone(), "total") or 0)
            score_cast = (
                "REAL" if self._database.db_type == "sqlite" else "DECIMAL(18,6)"
            )
            cursor.execute(
                self._sql(
                    self._event_select(classification_run_id)
                    + where
                    + f" ORDER BY CAST(s.trend_score AS {score_cast}) DESC, e.last_seen_at DESC"
                    + " LIMIT ? OFFSET ?"
                ),
                tuple(params + [limit, offset]),
            )
            items = [self._event_dict(row) for row in cursor.fetchall()]
        return {
            "trend_run_id": trend_run_id,
            "classification_run_id": classification_run_id,
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self._database.get_connection() as connection:
            trend = self._latest_trend_run(connection)
            if trend is None:
                return None
            trend_run_id = _value(trend, "trend_run_id")
            classification = self._latest_classification_run(connection, trend_run_id)
            classification_run_id = (
                _value(classification, "classification_run_id")
                if classification
                else None
            )
            where, params = self._event_filters(
                trend_run_id=trend_run_id,
                classification_run_id=classification_run_id,
                q=None,
                platform=None,
                lifecycle=None,
                hospitality_relevance=None,
                data_quality=None,
                event_id=event_id,
            )
            cursor = connection.cursor()
            cursor.execute(
                self._sql(self._event_select(classification_run_id) + where),
                tuple(params),
            )
            row = cursor.fetchone()
            if row is None:
                return None
            summary = self._event_dict(row)
            cursor.execute(
                self._sql(
                    """SELECT em.group_id, em.normalized_item_id, em.snapshot_id,
                              em.platform, em.is_representative,
                              n.normalized_title, n.canonical_url, n.rank_value,
                              n.hot_score_value, n.hot_score_unit
                       FROM hotspot_event_members em
                       JOIN hotspot_normalized_items n
                         ON n.normalized_item_id = em.normalized_item_id
                       WHERE em.event_id = ?
                       ORDER BY em.is_representative DESC, em.platform, em.group_id"""
                ),
                (event_id,),
            )
            members = [
                {
                    "group_id": _value(item, "group_id"),
                    "normalized_item_id": _value(item, "normalized_item_id"),
                    "snapshot_id": _value(item, "snapshot_id"),
                    "platform": _value(item, "platform"),
                    "is_representative": bool(_value(item, "is_representative")),
                    "title": _value(item, "normalized_title"),
                    "source_url": _value(item, "canonical_url"),
                    "rank": _value(item, "rank_value"),
                    "hot_score": _value(item, "hot_score_value"),
                    "hot_score_unit": _value(item, "hot_score_unit"),
                }
                for item in cursor.fetchall()
            ]
            cursor.execute(
                self._sql(
                    """SELECT em.group_id, n.normalized_item_id, r.raw_item_id,
                              r.platform, r.provider_id, r.title, r.url,
                              r.rank_value, r.hot_score, r.freshness,
                              r.observed_at, r.fetched_at, dm.match_kind,
                              dm.evidence_json
                       FROM hotspot_event_members em
                       JOIN hotspot_dedup_members dm ON dm.group_id = em.group_id
                       JOIN hotspot_normalized_items n
                         ON n.normalized_item_id = dm.normalized_item_id
                       JOIN hotspot_raw_items r ON r.raw_item_id = n.raw_item_id
                       WHERE em.event_id = ?
                       ORDER BY r.observed_at DESC, r.platform, r.source_item_position"""
                ),
                (event_id,),
            )
            evidence = [self._evidence_dict(item) for item in cursor.fetchall()]
        return {**summary, "members": members, "evidence": evidence}

    def get_raw_item(self, raw_item_id: str) -> dict[str, Any] | None:
        with self._database.get_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                self._sql(
                    """SELECT raw_item_id, run_id, platform, provider_id,
                              provider_attempt_number, source_item_position,
                              is_selected, freshness, external_id, title, url,
                              rank_value, hot_score, published_at, observed_at,
                              fetched_at, raw_data_json, raw_payload_sha256
                       FROM hotspot_raw_items WHERE raw_item_id = ?"""
                ),
                (raw_item_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "raw_item_id": _value(row, "raw_item_id"),
            "run_id": _value(row, "run_id"),
            "platform": _value(row, "platform"),
            "provider_id": _value(row, "provider_id"),
            "provider_attempt_number": _value(row, "provider_attempt_number"),
            "source_item_position": _value(row, "source_item_position"),
            "is_selected": bool(_value(row, "is_selected")),
            "freshness": _value(row, "freshness"),
            "external_id": _value(row, "external_id"),
            "title": _value(row, "title"),
            "url": _value(row, "url"),
            "rank": _value(row, "rank_value"),
            "hot_score": _value(row, "hot_score"),
            "published_at": _value(row, "published_at"),
            "observed_at": _value(row, "observed_at"),
            "fetched_at": _value(row, "fetched_at"),
            "raw_data": _json(_value(row, "raw_data_json"), {}),
            "raw_payload_sha256": _value(row, "raw_payload_sha256"),
        }

    def _platform_health(self, connection, platform, now, stale_after):
        cursor = connection.cursor()
        cursor.execute(
            self._sql(
                "SELECT * FROM hotspot_collection_runs WHERE platform = ? ORDER BY finished_at DESC, created_at DESC LIMIT 1"
            ),
            (platform,),
        )
        run = cursor.fetchone()
        if run is None:
            return {
                "platform": platform,
                "status": "unavailable",
                "freshness": "unknown",
                "data_age_minutes": None,
                "last_run_at": None,
                "snapshot_id": None,
                "snapshot_observed_at": None,
                "winning_provider_id": None,
                "fallback_used": False,
                "stale_reason": "no_collection_run",
                "error": None,
                "attempts": [],
            }
        cursor.execute(
            self._sql(
                "SELECT * FROM hotspot_snapshots WHERE platform = ? ORDER BY observed_at DESC, created_at DESC LIMIT 1"
            ),
            (platform,),
        )
        snapshot = cursor.fetchone()
        cursor.execute(
            self._sql(
                """SELECT provider_id, attempt_number, status, freshness,
                          item_count, error_code, error_message
                   FROM hotspot_provider_attempts WHERE run_id = ? ORDER BY attempt_number"""
            ),
            (_value(run, "run_id"),),
        )
        attempts = [
            {
                "provider_id": _value(item, "provider_id"),
                "attempt_number": _value(item, "attempt_number"),
                "status": _value(item, "status"),
                "freshness": _value(item, "freshness"),
                "item_count": _value(item, "item_count"),
                "error_code": _value(item, "error_code"),
                "error_message": _value(item, "error_message"),
            }
            for item in cursor.fetchall()
        ]
        observed = _parse_dt(_value(snapshot, "observed_at")) if snapshot else None
        age = max(0, int((now - observed).total_seconds() // 60)) if observed else None
        if _value(run, "status") == "failed":
            status, freshness, stale_reason = (
                "failed",
                "stale" if snapshot else "unknown",
                "latest_collection_failed",
            )
        elif _value(run, "freshness") == "stale" or (
            age is not None and age > stale_after
        ):
            status, freshness = "stale", "stale"
            stale_reason = _value(run, "stale_reason") or "snapshot_age_exceeded"
        else:
            status, freshness, stale_reason = "fresh", "fresh", None
        error = None
        if _value(run, "error_code") or _value(run, "error_message"):
            error = {
                "kind": _value(run, "error_kind"),
                "code": _value(run, "error_code"),
                "message": _value(run, "error_message"),
                "retryable": bool(_value(run, "error_retryable")),
                "upstream_status": _value(run, "error_upstream_status"),
            }
        winner = _value(run, "winning_provider_id")
        return {
            "platform": platform,
            "status": status,
            "freshness": freshness,
            "data_age_minutes": age,
            "last_run_at": _value(run, "finished_at"),
            "snapshot_id": _value(snapshot, "snapshot_id") if snapshot else None,
            "snapshot_observed_at": _value(snapshot, "observed_at")
            if snapshot
            else None,
            "winning_provider_id": winner,
            "fallback_used": len(attempts) > 1
            or (
                bool(attempts)
                and winner is not None
                and attempts[0]["provider_id"] != winner
            ),
            "stale_reason": stale_reason,
            "error": error,
            "attempts": attempts,
        }

    def _latest_trend_run(self, connection):
        cursor = connection.cursor()
        cursor.execute(
            "SELECT * FROM hotspot_trend_runs ORDER BY evaluated_at DESC, finished_at DESC LIMIT 1"
        )
        return cursor.fetchone()

    def _latest_classification_run(self, connection, trend_run_id):
        cursor = connection.cursor()
        cursor.execute(
            self._sql(
                "SELECT * FROM hotspot_classification_runs WHERE source_trend_run_id = ? ORDER BY finished_at DESC, created_at DESC LIMIT 1"
            ),
            (trend_run_id,),
        )
        return cursor.fetchone()

    def _event_select(self, classification_run_id, *, count=False):
        join = (
            " LEFT JOIN hotspot_ai_classifications c ON c.trend_state_id = s.trend_state_id AND c.classification_run_id = ?"
            if classification_run_id
            else " LEFT JOIN hotspot_ai_classifications c ON 1 = 0"
        )
        if count:
            return (
                "SELECT COUNT(*) AS total FROM hotspot_trend_states s JOIN hotspot_events e ON e.event_id = s.source_event_id"
                + join
            )
        return (
            """SELECT s.trend_state_id, s.trend_series_id, s.source_event_id AS event_id,
                      s.canonical_title, s.lifecycle_state, s.previous_state,
                      s.trend_score, s.data_quality, s.evaluated_at,
                      s.observation_count, s.fresh_observation_count,
                      s.stale_observation_count, s.fresh_platform_count,
                      s.failed_platform_count, s.stale_platform_count,
                      s.missing_platform_count, s.data_completeness,
                      s.velocity, s.acceleration, s.latest_fresh_age_hours,
                      e.first_seen_at, e.last_seen_at, e.platforms_json,
                      e.platform_count, e.member_count,
                      c.status AS classification_status, c.topic_category,
                      c.tags_json, c.hospitality_relevance, c.hospitality_score,
                      c.confidence, c.rationale, c.summary, c.evidence_ids_json
               FROM hotspot_trend_states s
               JOIN hotspot_events e ON e.event_id = s.source_event_id"""
            + join
        )

    def _event_filters(
        self,
        *,
        trend_run_id,
        classification_run_id,
        q,
        platform,
        lifecycle,
        hospitality_relevance,
        data_quality,
        event_id=None,
    ):
        clauses = ["s.trend_run_id = ?"]
        params: list[Any] = [classification_run_id] if classification_run_id else []
        params.append(trend_run_id)
        if event_id:
            clauses.append("e.event_id = ?")
            params.append(event_id)
        if q and q.strip():
            clauses.append("LOWER(e.canonical_title) LIKE ?")
            params.append(f"%{q.strip().lower()}%")
        if platform:
            clauses.append(
                "EXISTS (SELECT 1 FROM hotspot_event_members ep WHERE ep.event_id = e.event_id AND ep.platform = ?)"
            )
            params.append(platform)
        if lifecycle:
            clauses.append("s.lifecycle_state = ?")
            params.append(lifecycle)
        if hospitality_relevance:
            clauses.append("c.hospitality_relevance = ?")
            params.append(hospitality_relevance)
        if data_quality:
            clauses.append("s.data_quality = ?")
            params.append(data_quality)
        return " WHERE " + " AND ".join(clauses), params

    def _event_dict(self, row):
        classification = None
        if _value(row, "classification_status") is not None:
            classification = {
                "status": _value(row, "classification_status"),
                "topic_category": _value(row, "topic_category"),
                "tags": _json(_value(row, "tags_json"), []),
                "hospitality_relevance": _value(row, "hospitality_relevance"),
                "hospitality_score": _number(_value(row, "hospitality_score")),
                "confidence": _number(_value(row, "confidence")),
                "rationale": _value(row, "rationale"),
                "summary": _value(row, "summary"),
                "evidence_ids": _json(_value(row, "evidence_ids_json"), []),
            }
        event_id = _value(row, "event_id")
        return {
            "event_id": event_id,
            "trend_state_id": _value(row, "trend_state_id"),
            "trend_series_id": _value(row, "trend_series_id"),
            "canonical_title": _value(row, "canonical_title"),
            "lifecycle_state": _value(row, "lifecycle_state"),
            "previous_state": _value(row, "previous_state"),
            "trend_score": _number(_value(row, "trend_score")),
            "data_quality": _value(row, "data_quality"),
            "evaluated_at": _value(row, "evaluated_at"),
            "first_seen_at": _value(row, "first_seen_at"),
            "last_seen_at": _value(row, "last_seen_at"),
            "platforms": sorted(_json(_value(row, "platforms_json"), [])),
            "platform_count": _value(row, "platform_count"),
            "member_count": _value(row, "member_count"),
            "observation_count": _value(row, "observation_count"),
            "fresh_observation_count": _value(row, "fresh_observation_count"),
            "stale_observation_count": _value(row, "stale_observation_count"),
            "fresh_platform_count": _value(row, "fresh_platform_count"),
            "failed_platform_count": _value(row, "failed_platform_count"),
            "stale_platform_count": _value(row, "stale_platform_count"),
            "missing_platform_count": _value(row, "missing_platform_count"),
            "data_completeness": _number(_value(row, "data_completeness")),
            "velocity": _number(_value(row, "velocity")),
            "acceleration": _number(_value(row, "acceleration")),
            "latest_fresh_age_hours": _number(_value(row, "latest_fresh_age_hours")),
            "classification": classification,
            "detail_url": f"/api/v1/hotspots/events/{event_id}",
        }

    def _evidence_dict(self, row):
        raw_item_id = _value(row, "raw_item_id")
        return {
            "group_id": _value(row, "group_id"),
            "normalized_item_id": _value(row, "normalized_item_id"),
            "raw_item_id": raw_item_id,
            "raw_item_url": f"/api/v1/hotspots/raw-items/{raw_item_id}",
            "platform": _value(row, "platform"),
            "provider_id": _value(row, "provider_id"),
            "title": _value(row, "title"),
            "source_url": _value(row, "url"),
            "rank": _value(row, "rank_value"),
            "hot_score": _value(row, "hot_score"),
            "freshness": _value(row, "freshness"),
            "observed_at": _value(row, "observed_at"),
            "fetched_at": _value(row, "fetched_at"),
            "match_kind": _value(row, "match_kind"),
            "dedup_evidence": _json(_value(row, "evidence_json"), {}),
        }

    def _trend_run_dict(self, row):
        if row is None:
            return None
        return {
            "trend_run_id": _value(row, "trend_run_id"),
            "evaluated_at": _value(row, "evaluated_at"),
            "status": _value(row, "status"),
            "event_count": _value(row, "event_count"),
            "complete_count": _value(row, "complete_count"),
            "partial_count": _value(row, "partial_count"),
            "algorithm_version": _value(row, "algorithm_version"),
        }

    def _empty_events(self, limit, offset):
        return {
            "trend_run_id": None,
            "classification_run_id": None,
            "total": 0,
            "limit": limit,
            "offset": offset,
            "items": [],
        }

    def _stale_after_minutes(self) -> int:
        try:
            value = self._database.get_setting("hotspot_dashboard_stale_after_minutes")
            return max(1, int(value or 60))
        except (AttributeError, TypeError, ValueError):
            return 60

    def _sql(self, statement):
        return (
            statement
            if self._database.db_type == "sqlite"
            else statement.replace("?", "%s")
        )


def _value(row, key):
    if row is None:
        return None
    try:
        return row[key]
    except (KeyError, TypeError, IndexError):
        return None


def _json(value, default):
    try:
        return json.loads(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _number(value):
    return float(value) if value is not None else None


def _parse_dt(value):
    return _as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))


def _as_utc(value):
    if value.tzinfo is None:
        raise ValueError("dashboard timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value):
    return _as_utc(value).isoformat()
