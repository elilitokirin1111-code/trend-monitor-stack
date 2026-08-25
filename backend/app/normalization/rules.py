"""Versioned, configurable rules for Phase 4 deterministic processing."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

DEFAULT_TRACKING_PARAMETERS = frozenset(
    {
        "fbclid",
        "gclid",
        "spm",
        "from",
        "source",
        "share_source",
        "share_medium",
    }
)
DEFAULT_HOT_SCORE_MULTIPLIERS = {
    "": Decimal(1),
    "k": Decimal(1000),
    "m": Decimal(1000000),
    "w": Decimal(10000),
    "万": Decimal(10000),
    "亿": Decimal(100000000),
}
DEFAULT_PUBLISHED_AT_FIELDS = (
    "published_at",
    "pubDate",
    "timestamp",
    "created_at",
    "create_time",
    "time",
    "date",
)


@dataclass(frozen=True, slots=True)
class NormalizationRules:
    version: str = "hotspot-normalize-v1"
    dedup_algorithm_version: str = "hotspot-dedup-v1"
    tracking_parameters: frozenset[str] = DEFAULT_TRACKING_PARAMETERS
    hot_score_multipliers: Mapping[str, Decimal] = field(
        default_factory=lambda: MappingProxyType(dict(DEFAULT_HOT_SCORE_MULTIPLIERS))
    )
    published_at_fields: tuple[str, ...] = DEFAULT_PUBLISHED_AT_FIELDS

    def __post_init__(self) -> None:
        if not self.version.strip() or not self.dedup_algorithm_version.strip():
            raise ValueError("normalization and dedup versions cannot be empty")
        if not self.published_at_fields:
            raise ValueError("published_at_fields cannot be empty")
        multipliers = {
            _normalized_unit(key): Decimal(value)
            for key, value in self.hot_score_multipliers.items()
        }
        if "" not in multipliers or any(value <= 0 for value in multipliers.values()):
            raise ValueError(
                "hot score multipliers must be positive and include empty unit"
            )
        object.__setattr__(self, "hot_score_multipliers", MappingProxyType(multipliers))
        object.__setattr__(
            self,
            "tracking_parameters",
            frozenset(value.strip().casefold() for value in self.tracking_parameters),
        )
        object.__setattr__(
            self,
            "published_at_fields",
            tuple(value.strip() for value in self.published_at_fields if value.strip()),
        )

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> NormalizationRules:
        multipliers = dict(DEFAULT_HOT_SCORE_MULTIPLIERS)
        raw_multipliers = settings.get("hotspot_normalization_hot_score_units")
        if raw_multipliers:
            try:
                parsed = json.loads(raw_multipliers)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "hotspot_normalization_hot_score_units must be valid JSON"
                ) from exc
            if not isinstance(parsed, dict):
                raise ValueError(
                    "hotspot_normalization_hot_score_units must be a JSON object"
                )
            try:
                multipliers.update(
                    {str(key): Decimal(str(value)) for key, value in parsed.items()}
                )
            except InvalidOperation as exc:
                raise ValueError(
                    "hot score unit multipliers must be decimal values"
                ) from exc

        tracking = _csv_setting(
            settings.get("hotspot_normalization_tracking_params"),
            DEFAULT_TRACKING_PARAMETERS,
        )
        published_fields = _csv_setting(
            settings.get("hotspot_normalization_published_at_fields"),
            DEFAULT_PUBLISHED_AT_FIELDS,
        )
        return cls(
            version=settings.get(
                "hotspot_normalization_rule_version", "hotspot-normalize-v1"
            ),
            dedup_algorithm_version=settings.get(
                "hotspot_dedup_algorithm_version", "hotspot-dedup-v1"
            ),
            tracking_parameters=frozenset(tracking),
            hot_score_multipliers=multipliers,
            published_at_fields=tuple(published_fields),
        )

    @property
    def config_json(self) -> str:
        return json.dumps(
            {
                "dedup_algorithm_version": self.dedup_algorithm_version,
                "hot_score_multipliers": {
                    key: str(value)
                    for key, value in sorted(self.hot_score_multipliers.items())
                },
                "published_at_fields": list(self.published_at_fields),
                "tracking_parameters": sorted(self.tracking_parameters),
                "version": self.version,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.config_json.encode()).hexdigest()


def _csv_setting(value: str | None, default) -> tuple[str, ...]:
    if value is None:
        return tuple(default)
    parsed = tuple(part.strip() for part in value.split(",") if part.strip())
    if not parsed:
        raise ValueError("comma-separated normalization setting cannot be empty")
    return parsed


def _normalized_unit(value: str) -> str:
    stripped = value.strip()
    return stripped.casefold() if stripped.isascii() else stripped
