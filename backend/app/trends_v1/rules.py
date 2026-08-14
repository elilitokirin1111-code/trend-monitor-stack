"""Versioned and configurable rules for the Phase 6 lifecycle engine."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

DEFAULT_TREND_WEIGHTS = {
    "strength": Decimal("0.50"),
    "coverage": Decimal("0.15"),
    "positive_velocity": Decimal("0.15"),
    "positive_acceleration": Decimal("0.05"),
    "persistence": Decimal("0.15"),
}


@dataclass(frozen=True, slots=True)
class TrendRules:
    algorithm_version: str = "hotspot-trend-v1"
    bucket_minutes: int = 30
    recent_window_hours: int = 3
    dormant_after_hours: int = 6
    recurrent_gap_hours: int = 12
    rank_ceiling: int = 50
    hot_log_ceiling: Decimal = Decimal(8)
    minimum_observations: int = 2
    rising_velocity_threshold: Decimal = Decimal("0.10")
    declining_velocity_threshold: Decimal = Decimal("0.10")
    plateau_velocity_threshold: Decimal = Decimal("0.05")
    peaking_score_threshold: Decimal = Decimal("0.70")
    weights: Mapping[str, Decimal] = field(
        default_factory=lambda: MappingProxyType(dict(DEFAULT_TREND_WEIGHTS))
    )

    def __post_init__(self) -> None:
        if not self.algorithm_version.strip():
            raise ValueError("trend algorithm version cannot be empty")
        if not 5 <= self.bucket_minutes <= 1440:
            raise ValueError("trend bucket minutes must be between 5 and 1440")
        if not 1 <= self.recent_window_hours <= 24:
            raise ValueError("recent window hours must be between 1 and 24")
        if not self.recent_window_hours < self.dormant_after_hours <= 24 * 30:
            raise ValueError("dormant threshold must exceed the recent window")
        if not self.dormant_after_hours < self.recurrent_gap_hours <= 24 * 30:
            raise ValueError("recurrence gap must exceed the dormant threshold")
        if not 2 <= self.rank_ceiling <= 10000:
            raise ValueError("rank ceiling must be between 2 and 10000")
        if not 1 <= self.minimum_observations <= 1000:
            raise ValueError("minimum observations must be between 1 and 1000")

        decimals = {
            "hot_log_ceiling": _decimal(self.hot_log_ceiling, "hot log ceiling"),
            "rising_velocity_threshold": _decimal(
                self.rising_velocity_threshold, "rising velocity threshold"
            ),
            "declining_velocity_threshold": _decimal(
                self.declining_velocity_threshold, "declining velocity threshold"
            ),
            "plateau_velocity_threshold": _decimal(
                self.plateau_velocity_threshold, "plateau velocity threshold"
            ),
            "peaking_score_threshold": _decimal(
                self.peaking_score_threshold, "peaking score threshold"
            ),
        }
        if decimals["hot_log_ceiling"] <= 0:
            raise ValueError("hot log ceiling must be positive")
        for key in (
            "rising_velocity_threshold",
            "declining_velocity_threshold",
            "plateau_velocity_threshold",
            "peaking_score_threshold",
        ):
            if not Decimal(0) <= decimals[key] <= Decimal(1):
                raise ValueError(f"{key} must be between zero and one")
        for key, value in decimals.items():
            object.__setattr__(self, key, value)

        expected = set(DEFAULT_TREND_WEIGHTS)
        weights = {
            str(key): _decimal(value, f"weight {key}")
            for key, value in self.weights.items()
        }
        if set(weights) != expected:
            raise ValueError(f"trend weights must contain exactly {sorted(expected)}")
        if any(value < 0 for value in weights.values()) or sum(
            weights.values(), Decimal(0)
        ) != Decimal(1):
            raise ValueError("trend weights must be non-negative and sum to one")
        object.__setattr__(self, "weights", MappingProxyType(weights))

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> TrendRules:
        weights: Mapping[str, Decimal] = DEFAULT_TREND_WEIGHTS
        raw_weights = settings.get("hotspot_trend_weights")
        if raw_weights:
            try:
                value = json.loads(raw_weights)
            except json.JSONDecodeError as exc:
                raise ValueError("hotspot_trend_weights must be valid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError("hotspot_trend_weights must be a JSON object")
            weights = value
        return cls(
            algorithm_version=settings.get(
                "hotspot_trend_algorithm_version", "hotspot-trend-v1"
            ),
            bucket_minutes=_integer(settings, "hotspot_trend_bucket_minutes", 30),
            recent_window_hours=_integer(
                settings, "hotspot_trend_recent_window_hours", 3
            ),
            dormant_after_hours=_integer(
                settings, "hotspot_trend_dormant_after_hours", 6
            ),
            recurrent_gap_hours=_integer(
                settings, "hotspot_trend_recurrent_gap_hours", 12
            ),
            rank_ceiling=_integer(settings, "hotspot_trend_rank_ceiling", 50),
            hot_log_ceiling=_decimal_setting(
                settings, "hotspot_trend_hot_log_ceiling", "8"
            ),
            minimum_observations=_integer(
                settings, "hotspot_trend_minimum_observations", 2
            ),
            rising_velocity_threshold=_decimal_setting(
                settings, "hotspot_trend_rising_velocity_threshold", "0.10"
            ),
            declining_velocity_threshold=_decimal_setting(
                settings, "hotspot_trend_declining_velocity_threshold", "0.10"
            ),
            plateau_velocity_threshold=_decimal_setting(
                settings, "hotspot_trend_plateau_velocity_threshold", "0.05"
            ),
            peaking_score_threshold=_decimal_setting(
                settings, "hotspot_trend_peaking_score_threshold", "0.70"
            ),
            weights=weights,
        )

    @property
    def config_json(self) -> str:
        return json.dumps(
            {
                "algorithm_version": self.algorithm_version,
                "bucket_minutes": self.bucket_minutes,
                "declining_velocity_threshold": str(self.declining_velocity_threshold),
                "dormant_after_hours": self.dormant_after_hours,
                "hot_log_ceiling": str(self.hot_log_ceiling),
                "minimum_observations": self.minimum_observations,
                "peaking_score_threshold": str(self.peaking_score_threshold),
                "plateau_velocity_threshold": str(self.plateau_velocity_threshold),
                "rank_ceiling": self.rank_ceiling,
                "recent_window_hours": self.recent_window_hours,
                "recurrent_gap_hours": self.recurrent_gap_hours,
                "rising_velocity_threshold": str(self.rising_velocity_threshold),
                "weights": {
                    key: str(value) for key, value in sorted(self.weights.items())
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(self.config_json.encode()).hexdigest()


def _integer(settings: Mapping[str, str], key: str, default: int) -> int:
    raw = settings.get(key)
    try:
        return default if raw is None else int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _decimal_setting(settings: Mapping[str, str], key: str, default: str) -> Decimal:
    return _decimal(settings.get(key, default), key)


def _decimal(value, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed
