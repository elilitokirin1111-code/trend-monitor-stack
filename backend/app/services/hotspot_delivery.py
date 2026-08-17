"""Phase 10 application service: idempotent, replayable report delivery."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from app.delivery.feishu import FeishuDeliveryAdapter, split_content
from app.delivery.rules import FeishuDeliveryRules
from app.domain.hotspot import DeliveryRecord, DeliveryStatus
from app.repositories.hotspot import ReportRepository
from app.repositories.hotspot.deliveries import DeliveryRepository
from app.config import settings as app_settings
from app.services.database import db


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    state: str
    delivery_id: str | None = None
    report_run_id: str | None = None
    chunk_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error: str | None = None


class HotspotDeliveryService:
    def __init__(
        self,
        database=db,
        *,
        adapter_factory=None,
    ) -> None:
        self._database = database
        self._adapter_factory = adapter_factory or FeishuDeliveryAdapter

    def _build_rules(self) -> FeishuDeliveryRules:
        return FeishuDeliveryRules.from_settings(
            self._database.get_all_settings(),
            defaults={
                "feishu_webhook_url": app_settings.feishu_webhook_url or "",
                "feishu_webhook_secret": app_settings.feishu_webhook_secret or "",
            },
        )

    async def deliver_report(
        self,
        report_run_id: str,
        *,
        channel: str = "feishu",
        force: bool = False,
    ) -> DeliveryOutcome:
        try:
            report = await ReportRepository(self._database).get_run(report_run_id)
            if report is None:
                return DeliveryOutcome(state="no_report", report_run_id=report_run_id)
            rules = self._build_rules()
            adapter = self._adapter_factory(rules)
            repository = DeliveryRepository(self._database)
            content = report["content"]
            content_version = hashlib.sha256(content.encode()).hexdigest()
            chunks = split_content(content, rules.max_chunk_chars)
            title = _report_title(report)
            success_count = 0
            failed_count = 0
            skipped_count = 0
            states: list[str] = []
            for chunk_index, chunk in enumerate(chunks):
                existing = await repository.find(
                    report_run_id=report_run_id,
                    channel=channel,
                    content_version=content_version,
                    chunk_index=chunk_index,
                )
                if existing is not None and not force:
                    if existing["status"] == DeliveryStatus.SUCCESS.value:
                        skipped_count += 1
                        states.append("skipped")
                        continue
                    # A previous failed attempt: re-deliver even without force,
                    # but keep the idempotency key (INSERT OR REPLACE).
                attempt = await adapter.send_text(chunk, title=title)
                if not rules.webhook_url:
                    return DeliveryOutcome(
                        state="not_configured",
                        report_run_id=report_run_id,
                        error="feishu webhook is not configured",
                    )
                record = DeliveryRecord(
                    delivery_id=str(uuid4()),
                    report_run_id=report_run_id,
                    channel=channel,
                    content_version=content_version,
                    chunk_index=chunk_index,
                    total_chunks=len(chunks),
                    status=(
                        DeliveryStatus.SUCCESS
                        if attempt.status == "success"
                        else DeliveryStatus.FAILED
                    ),
                    attempt=attempt.attempt,
                    latency_ms=attempt.latency_ms,
                    error_kind=attempt.error_kind,
                    error_message=attempt.error_message,
                    response_json=attempt.response,
                    created_at=datetime.now(timezone.utc),
                    finished_at=datetime.now(timezone.utc),
                )
                await repository.save(record)
                if attempt.status == "success":
                    success_count += 1
                    states.append("delivered")
                else:
                    failed_count += 1
                    states.append("failed")
                    await adapter.send_alert(
                        f"[HotPush 告警] 报告投递失败：{report_run_id} "
                        f"第 {chunk_index + 1}/{len(chunks)} 片 "
                        f"（{attempt.error_message}）"
                    )
            if failed_count:
                state = "partial"
            elif success_count and skipped_count:
                state = "delivered"
            elif skipped_count and not success_count:
                state = "skipped"
            else:
                state = "delivered"
            return DeliveryOutcome(
                state=state,
                report_run_id=report_run_id,
                chunk_count=len(chunks),
                success_count=success_count,
                failed_count=failed_count,
                skipped_count=skipped_count,
            )
        except Exception as exc:  # noqa: BLE001 - preserve scheduler progress
            return DeliveryOutcome(state="failed", error=str(exc))

    async def replay_delivery(self, delivery_id: str) -> DeliveryOutcome:
        """Re-deliver one recorded chunk (used for failed deliveries)."""
        try:
            repository = DeliveryRepository(self._database)
            delivery = await repository.get_delivery(delivery_id)
            if delivery is None:
                return DeliveryOutcome(state="no_delivery")
            report = await ReportRepository(self._database).get_run(
                delivery["report_run_id"]
            )
            if report is None:
                return DeliveryOutcome(state="no_report")
            rules = self._build_rules()
            adapter = self._adapter_factory(rules)
            chunks = split_content(report["content"], rules.max_chunk_chars)
            chunk_index = int(delivery["chunk_index"])
            if chunk_index >= len(chunks):
                return DeliveryOutcome(
                    state="failed", error="chunk index out of range"
                )
            attempt = await adapter.send_text(
                chunks[chunk_index], title=_report_title(report)
            )
            record = DeliveryRecord(
                delivery_id=delivery_id,
                report_run_id=delivery["report_run_id"],
                channel=delivery["channel"],
                content_version=delivery["content_version"],
                chunk_index=chunk_index,
                total_chunks=len(chunks),
                status=(
                    DeliveryStatus.SUCCESS
                    if attempt.status == "success"
                    else DeliveryStatus.FAILED
                ),
                attempt=attempt.attempt,
                latency_ms=attempt.latency_ms,
                error_kind=attempt.error_kind,
                error_message=attempt.error_message,
                response_json=attempt.response,
                created_at=datetime.fromisoformat(delivery["created_at"]),
                finished_at=datetime.now(timezone.utc),
            )
            await repository.save(record)
            return DeliveryOutcome(
                state="delivered" if attempt.status == "success" else "failed",
                delivery_id=delivery_id,
                report_run_id=delivery["report_run_id"],
            )
        except Exception as exc:  # noqa: BLE001 - preserve replay progress
            return DeliveryOutcome(state="failed", error=str(exc))


hotspot_delivery_service = HotspotDeliveryService()


def _report_title(report: dict) -> str:
    period = (report.get("period_start") or "")[:10]
    label = "周报" if report.get("report_type") == "weekly" else "日报"
    return f"[HotPush 热点{label} {period}]"
