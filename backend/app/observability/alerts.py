"""Configurable alert rules evaluated against the pipeline monitor snapshot.

Alerts are derived, read-only judgments: they never mutate pipeline data.
Notification state is tracked in the settings table so repeated checks do
not spam the configured webhook.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol


class AlertSeverity(str, Enum):
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class AlertRule:
    kind: str
    severity: AlertSeverity
    message: str
    platform: str | None = None
    observed_at: datetime = datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class AlertRulesConfig:
    enabled: bool = False
    max_stale_minutes: int = 180
    min_provider_success_rate: float = 0.5
    max_failed_runs: int = 3
    max_pending_snapshots: int = 12
    alert_webhook: str = ""

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> AlertRulesConfig:
        return cls(
            enabled=_boolean(settings.get("hotspot_alerts_enabled"), False),
            max_stale_minutes=_integer(
                settings, "hotspot_alert_max_stale_minutes", 180
            ),
            min_provider_success_rate=_float(
                settings, "hotspot_alert_min_provider_success_rate", 0.5
            ),
            max_failed_runs=_integer(
                settings, "hotspot_alert_max_failed_runs", 3
            ),
            max_pending_snapshots=_integer(
                settings, "hotspot_alert_max_pending_snapshots", 12
            ),
            alert_webhook=str(
                settings.get("hotspot_alert_webhook", "")
            ).strip(),
        )

    @property
    def config_hash(self) -> str:
        payload = json.dumps(
            {
                "alert_webhook": "***" if self.alert_webhook else "",
                "enabled": self.enabled,
                "max_failed_runs": self.max_failed_runs,
                "max_pending_snapshots": self.max_pending_snapshots,
                "max_stale_minutes": self.max_stale_minutes,
                "min_provider_success_rate": self.min_provider_success_rate,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode()).hexdigest()


class AlertEvaluator:
    def __init__(self, config: AlertRulesConfig) -> None:
        self._config = config

    def evaluate(self, summary: Mapping[str, Any]) -> tuple[AlertRule, ...]:
        if not self._config.enabled:
            return ()
        now = datetime.now(timezone.utc)
        alerts: list[AlertRule] = []

        for platform in summary.get("collection", {}).get("platforms", []):
            stale_age = platform.get("latest_stale_age_minutes")
            if stale_age is None:
                continue
            if stale_age > self._config.max_stale_minutes:
                alerts.append(
                    AlertRule(
                        kind="stale_platform",
                        severity=(
                            AlertSeverity.CRITICAL
                            if stale_age > self._config.max_stale_minutes * 3
                            else AlertSeverity.WARNING
                        ),
                        message=(
                            f"平台 {platform['platform']} 数据陈旧 "
                            f"{int(stale_age)} 分钟（阈值 "
                            f"{self._config.max_stale_minutes} 分钟）"
                        ),
                        platform=platform["platform"],
                        observed_at=now,
                    )
                )

        for item in summary.get("provider", {}).get("items", []):
            success_rate = item.get("success_rate")
            if success_rate is None or item.get("attempts", 0) < 3:
                continue
            if success_rate < self._config.min_provider_success_rate:
                alerts.append(
                    AlertRule(
                        kind="provider_success_rate",
                        severity=AlertSeverity.WARNING,
                        message=(
                            f"Provider {item['provider_id']}（"
                            f"{item['platform']}）成功率 "
                            f"{success_rate:.0%}（阈值 "
                            f"{self._config.min_provider_success_rate:.0%}）"
                        ),
                        platform=item["platform"],
                        observed_at=now,
                    )
                )

        failed_runs = summary.get("collection", {}).get("failed_runs", 0)
        if failed_runs > self._config.max_failed_runs:
            alerts.append(
                AlertRule(
                    kind="failed_runs",
                    severity=AlertSeverity.WARNING,
                    message=(
                        f"最近采集失败运行 {failed_runs} 次"
                        f"（阈值 {self._config.max_failed_runs} 次）"
                    ),
                    observed_at=now,
                )
            )

        pending = summary.get("pipeline", {}).get(
            "pending_normalization_snapshots", 0
        )
        if pending > self._config.max_pending_snapshots:
            alerts.append(
                AlertRule(
                    kind="pipeline_backlog",
                    severity=AlertSeverity.WARNING,
                    message=(
                        f"标准化积压快照 {pending} 个"
                        f"（阈值 {self._config.max_pending_snapshots} 个）"
                    ),
                    observed_at=now,
                )
            )

        failed_deliveries = summary.get("pipeline", {}).get(
            "failed_deliveries_total", 0
        )
        if failed_deliveries:
            alerts.append(
                AlertRule(
                    kind="delivery_failed",
                    severity=AlertSeverity.CRITICAL,
                    message=f"存在 {failed_deliveries} 条失败的报告投递记录",
                    observed_at=now,
                )
            )
        return tuple(alerts)


def alerts_fingerprint(alerts: tuple[AlertRule, ...]) -> str:
    payload = [
        (alert.kind, alert.severity.value, alert.message, alert.platform)
        for alert in alerts
    ]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def _boolean(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError("alerts enabled setting must be a boolean")


def _integer(settings: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(settings.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _float(settings: Mapping[str, str], key: str, default: float) -> float:
    try:
        return float(settings.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric") from exc
