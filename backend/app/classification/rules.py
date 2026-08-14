"""Versioned configuration for evidence-grounded AI classification."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class ClassificationRules:
    classifier_version: str = "hotspot-classifier-v1"
    prompt_version: str = "hotspot-classifier-prompt-v1"
    enabled: bool = False
    model: str = "gpt-4o-mini"
    api_key: str = field(default="", repr=False, compare=False)
    base_url: str = ""
    timeout_seconds: float = 30
    max_concurrency: int = 3
    max_summary_chars: int = 240
    max_rationale_chars: int = 500

    def __post_init__(self) -> None:
        for name in ("classifier_version", "prompt_version", "model"):
            if not str(getattr(self, name)).strip():
                raise ValueError(f"{name} cannot be empty")
        if len(self.classifier_version) > 64 or len(self.prompt_version) > 64:
            raise ValueError("AI classifier and prompt versions are too long")
        if len(self.model) > 191:
            raise ValueError("AI model name is too long")
        if self.base_url:
            parsed = urlsplit(self.base_url)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
            ):
                raise ValueError("AI base URL must be HTTP(S) without credentials")
        if not 0.01 <= float(self.timeout_seconds) <= 300:
            raise ValueError("AI timeout must be between 0.01 and 300 seconds")
        if not 1 <= self.max_concurrency <= 20:
            raise ValueError("AI max concurrency must be between 1 and 20")
        if not 80 <= self.max_summary_chars <= 2000:
            raise ValueError("AI summary limit must be between 80 and 2000")
        if not 100 <= self.max_rationale_chars <= 4000:
            raise ValueError("AI rationale limit must be between 100 and 4000")

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> ClassificationRules:
        legacy = _legacy_config(settings.get("ai_config"))
        return cls(
            classifier_version=settings.get(
                "hotspot_ai_classifier_version", "hotspot-classifier-v1"
            ),
            prompt_version=settings.get(
                "hotspot_ai_prompt_version", "hotspot-classifier-prompt-v1"
            ),
            enabled=_boolean(
                settings.get("hotspot_ai_classification_enabled"),
                False,
            ),
            model=settings.get(
                "hotspot_ai_model", str(legacy.get("model", "gpt-4o-mini"))
            ),
            api_key=settings.get("hotspot_ai_api_key", str(legacy.get("api_key", ""))),
            base_url=settings.get(
                "hotspot_ai_base_url", str(legacy.get("base_url", ""))
            ).rstrip("/"),
            timeout_seconds=_float(settings, "hotspot_ai_timeout_seconds", 30),
            max_concurrency=_integer(settings, "hotspot_ai_max_concurrency", 3),
            max_summary_chars=_integer(settings, "hotspot_ai_max_summary_chars", 240),
            max_rationale_chars=_integer(
                settings, "hotspot_ai_max_rationale_chars", 500
            ),
        )

    @property
    def config_json(self) -> str:
        return json.dumps(
            {
                "base_url": self.base_url,
                "classifier_version": self.classifier_version,
                "enabled": self.enabled,
                "max_concurrency": self.max_concurrency,
                "max_rationale_chars": self.max_rationale_chars,
                "max_summary_chars": self.max_summary_chars,
                "model": self.model,
                "prompt_version": self.prompt_version,
                "timeout_seconds": self.timeout_seconds,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.config_json.encode()).hexdigest()


def _legacy_config(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("ai_config must be valid JSON") from exc
    if not isinstance(value, dict):
        raise TypeError("ai_config must be a JSON object")
    return value


def _boolean(raw: str | None, default: bool) -> bool:
    if raw is None:
        return default
    normalized = str(raw).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError("AI enabled setting must be a boolean")


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
