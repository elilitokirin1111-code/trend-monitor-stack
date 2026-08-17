"""Versioned configuration for report channel delivery (Feishu first)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FeishuDeliveryRules:
    webhook_url: str = ""
    secret: str = ""
    alert_webhook_url: str = ""
    timeout_seconds: float = 15
    max_retries: int = 2
    backoff_base_seconds: float = 1.0
    backoff_max_seconds: float = 30
    max_chunk_chars: int = 20000

    def __post_init__(self) -> None:
        if self.webhook_url and not self.webhook_url.startswith("https://"):
            raise ValueError("Feishu webhook URL must be HTTPS")
        if self.alert_webhook_url and not self.alert_webhook_url.startswith(
            "https://"
        ):
            raise ValueError("Feishu alert webhook URL must be HTTPS")
        if not 0.5 <= float(self.timeout_seconds) <= 120:
            raise ValueError("delivery timeout must be between 0.5 and 120 seconds")
        if not 0 <= self.max_retries <= 5:
            raise ValueError("delivery max retries must be between 0 and 5")
        if not 0.01 <= float(self.backoff_base_seconds) <= 60:
            raise ValueError("delivery backoff base must be between 0.01 and 60")
        if not 0.1 <= float(self.backoff_max_seconds) <= 600:
            raise ValueError("delivery backoff max must be between 0.1 and 600")
        if not 100 <= self.max_chunk_chars <= 200000:
            raise ValueError("delivery chunk size must be between 100 and 200000")

    @classmethod
    def from_settings(
        cls, settings: Mapping[str, str], *, defaults: Mapping[str, str] | None = None
    ) -> FeishuDeliveryRules:
        defaults = defaults or {}
        webhook = settings.get(
            "hotspot_feishu_webhook_url",
            defaults.get("feishu_webhook_url", ""),
        )
        secret = settings.get(
            "hotspot_feishu_secret",
            defaults.get("feishu_webhook_secret", ""),
        )
        return cls(
            webhook_url=str(webhook or "").strip(),
            secret=str(secret or "").strip(),
            alert_webhook_url=str(
                settings.get("hotspot_delivery_alert_webhook", "")
            ).strip(),
            timeout_seconds=_float(settings, "hotspot_delivery_timeout_seconds", 15),
            max_retries=_integer(settings, "hotspot_delivery_max_retries", 2),
            backoff_base_seconds=_float(
                settings, "hotspot_delivery_backoff_base_seconds", 1.0
            ),
            backoff_max_seconds=_float(
                settings, "hotspot_delivery_backoff_max_seconds", 30
            ),
            max_chunk_chars=_integer(
                settings, "hotspot_delivery_max_chunk_chars", 20000
            ),
        )

    @property
    def config_json(self) -> str:
        return json.dumps(
            {
                "alert_webhook_url": _mask(self.alert_webhook_url),
                "backoff_base_seconds": self.backoff_base_seconds,
                "backoff_max_seconds": self.backoff_max_seconds,
                "max_chunk_chars": self.max_chunk_chars,
                "max_retries": self.max_retries,
                "secret": "***" if self.secret else "",
                "timeout_seconds": self.timeout_seconds,
                "webhook_url": _mask(self.webhook_url),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.config_json.encode()).hexdigest()


def _mask(url: str) -> str:
    if not url:
        return ""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parts = urlsplit(url)
        if parts.query:
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "***", ""))
    except ValueError:
        pass
    return url


def _float(settings: Mapping[str, str], key: str, default: float) -> float:
    try:
        return float(settings.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric") from exc


def _integer(settings: Mapping[str, str], key: str, default: int) -> int:
    try:
        return int(settings.get(key, default))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc
