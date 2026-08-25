"""Phase 11 application service: pipeline monitoring and alert checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.delivery.feishu import FeishuDeliveryAdapter
from app.delivery.rules import FeishuDeliveryRules
from app.observability.alerts import (
    AlertEvaluator,
    AlertRule,
    AlertRulesConfig,
    alerts_fingerprint,
)
from app.observability.monitor import PipelineMonitor
from app.services.database import db


@dataclass(frozen=True, slots=True)
class AlertCheckOutcome:
    state: str
    alerts: tuple[dict[str, Any], ...] = ()
    changed: bool = False
    error: str | None = None


class HotspotMonitoringService:
    def __init__(self, database=db, *, as_of=None) -> None:
        self._database = database
        self._as_of = as_of

    async def summary(self, *, hours: int = 24) -> dict[str, Any]:
        return await PipelineMonitor(
            self._database, as_of=self._as_of
        ).summary(hours=hours)

    async def check_alerts(
        self, *, hours: int = 24, notify: bool = True
    ) -> AlertCheckOutcome:
        try:
            config = AlertRulesConfig.from_settings(
                self._database.get_all_settings()
            )
            summary = await self.summary(hours=hours)
            alerts = AlertEvaluator(config).evaluate(summary)
            rendered = [_alert_dict(alert) for alert in alerts]
            fingerprint = alerts_fingerprint(alerts)
            last = self._database.get_setting("hotspot_alert_last_fingerprint")
            changed = fingerprint != last
            if changed:
                self._database.set_setting(
                    "hotspot_alert_last_fingerprint", fingerprint
                )
            if changed and notify and config.alert_webhook and alerts:
                await self._notify(config.alert_webhook, alerts)
            return AlertCheckOutcome(
                state="checked",
                alerts=tuple(rendered),
                changed=changed,
            )
        except Exception as exc:  # noqa: BLE001 - monitoring must not break pipeline
            return AlertCheckOutcome(state="failed", error=str(exc))

    async def _notify(self, webhook_url: str, alerts: tuple[AlertRule, ...]) -> None:
        rules = FeishuDeliveryRules(
            webhook_url=webhook_url,
            timeout_seconds=10,
            max_retries=0,
        )
        lines = ["[HotPush 告警]", ""]
        lines.extend(
            f"- [{alert.severity.value}] {alert.message}"
            for alert in alerts
        )
        adapter = FeishuDeliveryAdapter(rules)
        await adapter.send_alert("\n".join(lines))


hotspot_monitoring_service = HotspotMonitoringService()


def _alert_dict(alert: AlertRule) -> dict[str, Any]:
    return {
        "kind": alert.kind,
        "severity": alert.severity.value,
        "message": alert.message,
        "platform": alert.platform,
        "observed_at": alert.observed_at.isoformat(),
    }
