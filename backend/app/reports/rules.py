"""Versioned configuration for the deterministic daily/weekly report engine."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReportRules:
    report_version: str = "hotspot-report-v1"
    template: str = "markdown_brief"
    max_items: int = 30
    include_irrelevant: bool = False
    timezone: str = "Asia/Shanghai"

    def __post_init__(self) -> None:
        if not str(self.report_version).strip():
            raise ValueError("report version cannot be empty")
        if len(self.report_version) > 64:
            raise ValueError("report version is too long")
        if not str(self.template).strip():
            raise ValueError("report template cannot be empty")
        if not 1 <= self.max_items <= 200:
            raise ValueError("report max items must be between 1 and 200")

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> ReportRules:
        return cls(
            report_version=settings.get(
                "hotspot_report_version", "hotspot-report-v1"
            ),
            template=settings.get("hotspot_report_template", "markdown_brief"),
            max_items=_integer(settings, "hotspot_report_max_items", 30),
            include_irrelevant=_boolean(
                settings.get("hotspot_report_include_irrelevant"), False
            ),
            timezone=settings.get("hotspot_report_timezone", "Asia/Shanghai"),
        )

    @property
    def config_json(self) -> str:
        return json.dumps(
            {
                "include_irrelevant": self.include_irrelevant,
                "max_items": self.max_items,
                "report_version": self.report_version,
                "template": self.template,
                "timezone": self.timezone,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.config_json.encode()).hexdigest()


def report_input_hash(
    *,
    report_type: str,
    period_start: str,
    period_end: str,
    source_trend_run_id: str,
    source_classification_run_id: str | None,
    events: tuple[tuple[str, str, str, str | None, str | None, str | None], ...],
    platform_signals: tuple[tuple[str, str, str, str | None], ...],
) -> str:
    """Stable input fingerprint for idempotent report generation."""
    payload = {
        "report_type": report_type,
        "period_start": period_start,
        "period_end": period_end,
        "source_trend_run_id": source_trend_run_id,
        "source_classification_run_id": source_classification_run_id,
        "events": sorted(events),
        "platform_signals": sorted(platform_signals),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def report_run_id_base(
    *,
    report_type: str,
    period_start: str,
    report_version: str,
    config_hash: str,
    input_hash: str,
) -> str:
    """Deterministic report run identifier (attempt 1)."""
    raw = "|".join(
        (report_type, period_start, report_version, config_hash, input_hash)
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def _boolean(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError("report include_irrelevant setting must be a boolean")


def _integer(settings: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(settings.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc
