"""Phase 9 application service for idempotent daily/weekly report generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from app.domain.hotspot import ReportType, utc_now
from app.reports.engine import ReportEngine
from app.reports.rules import ReportRules
from app.repositories.hotspot import ReportRepository
from app.repositories.hotspot.reports import report_id_for
from app.services.database import db


@dataclass(frozen=True, slots=True)
class ReportOutcome:
    state: str
    report_run_id: str | None = None
    status: str | None = None
    data_quality: str | None = None
    item_count: int = 0
    error: str | None = None


class HotspotReportService:
    def __init__(
        self,
        database=db,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._database = database
        self._clock = clock

    async def generate(
        self,
        report_type: ReportType,
        *,
        period_start: datetime | None = None,
        force: bool = False,
    ) -> ReportOutcome:
        try:
            rules = ReportRules.from_settings(self._database.get_all_settings())
            window = self._resolve_window(report_type, period_start)
            repository = ReportRepository(self._database)
            source = await repository.load_current_input(
                report_type,
                period_start=window["start"],
                period_end=window["end"],
            )
            if source is None or not source.events:
                return ReportOutcome(state="no_input")
            batch = ReportEngine(rules).render(source, report_run_id="pending")
            input_hash = batch.input_hash
            run_id = report_id_for(
                report_type=report_type,
                period_start=window["start"],
                rules=rules,
                input_hash=input_hash,
            )
            if not force and await repository.run_exists(run_id):
                return ReportOutcome(
                    state="skipped_unchanged",
                    report_run_id=run_id,
                    status=batch.status.value,
                    data_quality=batch.data_quality.value,
                    item_count=len(source.events),
                )
            attempt = await repository.next_attempt(run_id) if force else 1
            run_id = report_id_for(
                report_type=report_type,
                period_start=window["start"],
                rules=rules,
                input_hash=input_hash,
                attempt=attempt,
            )
            started_at = self._clock()
            batch = ReportEngine(rules).render(
                source,
                report_run_id=run_id,
                attempt=attempt,
                started_at=started_at,
            )
            saved = await repository.save_batch(batch)
            return ReportOutcome(
                state=(
                    "processed"
                    if saved
                    else f"skipped_duplicate_attempt_{attempt}"
                ),
                report_run_id=run_id,
                status=batch.status.value,
                data_quality=batch.data_quality.value,
                item_count=len(source.events),
            )
        except Exception as exc:  # noqa: BLE001 - preserve scheduler progress
            return ReportOutcome(state="failed", error=str(exc))

    def _resolve_window(
        self,
        report_type: ReportType,
        period_start: datetime | None,
    ) -> dict[str, datetime]:
        tz = ZoneInfo("Asia/Shanghai")
        now = self._clock().astimezone(tz)
        if period_start is None:
            today = now.replace(hour=0, minute=0, second=0, microsecond=0)
            start_local = today - timedelta(days=1 if report_type is ReportType.DAILY else 7)
        else:
            start_local = period_start.astimezone(tz).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            days = 1 if report_type is ReportType.DAILY else 7
            if start_local > now:
                raise ValueError("报告时间窗不能在当前时间之后")
        end_local = start_local + timedelta(days=1 if report_type is ReportType.DAILY else 7)
        return {
            "start": start_local.astimezone(timezone.utc),
            "end": end_local.astimezone(timezone.utc),
        }


hotspot_report_service = HotspotReportService()
