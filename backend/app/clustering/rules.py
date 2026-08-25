"""Configuration contract for bounded deterministic event clustering."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from types import MappingProxyType

DEFAULT_WEIGHTS = {
    "sequence": Decimal("0.45"),
    "ngram": Decimal("0.35"),
    "keyword": Decimal("0.15"),
    "time": Decimal("0.05"),
}


@dataclass(frozen=True, slots=True)
class ClusteringRules:
    algorithm_version: str = "hotspot-cluster-v1"
    normalization_rule_version: str = "hotspot-normalize-v1"
    lookback_hours: int = 48
    candidate_window_hours: int = 36
    ngram_size: int = 2
    min_shared_ngrams: int = 2
    max_candidates_per_item: int = 20
    max_postings_per_key: int = 200
    semantic_lower_threshold: Decimal = Decimal("0.68")
    accept_threshold: Decimal = Decimal("0.82")
    semantic_enabled: bool = False
    max_semantic_calls: int = 50
    weights: Mapping[str, Decimal] = field(
        default_factory=lambda: MappingProxyType(dict(DEFAULT_WEIGHTS))
    )

    def __post_init__(self) -> None:
        if (
            not self.algorithm_version.strip()
            or not self.normalization_rule_version.strip()
        ):
            raise ValueError("clustering and normalization versions cannot be empty")
        if not 1 <= self.lookback_hours <= 24 * 30:
            raise ValueError("lookback hours must be between 1 and 720")
        if not 1 <= self.candidate_window_hours <= self.lookback_hours:
            raise ValueError("candidate window must fit inside lookback window")
        if not 2 <= self.ngram_size <= 4:
            raise ValueError("ngram size must be between 2 and 4")
        if not 1 <= self.min_shared_ngrams <= 50:
            raise ValueError("minimum shared ngrams must be between 1 and 50")
        if not 1 <= self.max_candidates_per_item <= 100:
            raise ValueError("max candidates per item must be between 1 and 100")
        if not 5 <= self.max_postings_per_key <= 1000:
            raise ValueError("max postings per key must be between 5 and 1000")
        if not 0 <= self.max_semantic_calls <= 1000:
            raise ValueError("max semantic calls must be between 0 and 1000")

        lower = _decimal(self.semantic_lower_threshold, "semantic lower threshold")
        accept = _decimal(self.accept_threshold, "accept threshold")
        if not Decimal(0) <= lower < accept <= Decimal(1):
            raise ValueError(
                "clustering thresholds must satisfy 0 <= lower < accept <= 1"
            )
        object.__setattr__(self, "semantic_lower_threshold", lower)
        object.__setattr__(self, "accept_threshold", accept)

        expected = set(DEFAULT_WEIGHTS)
        parsed_weights = {
            str(key): _decimal(value, f"weight {key}")
            for key, value in self.weights.items()
        }
        if set(parsed_weights) != expected:
            raise ValueError(f"weights must contain exactly {sorted(expected)}")
        if any(value < 0 for value in parsed_weights.values()) or sum(
            parsed_weights.values(), Decimal(0)
        ) != Decimal(1):
            raise ValueError("clustering weights must be non-negative and sum to one")
        object.__setattr__(self, "weights", MappingProxyType(parsed_weights))

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> ClusteringRules:
        weights: Mapping[str, Decimal] = DEFAULT_WEIGHTS
        raw_weights = settings.get("hotspot_clustering_weights")
        if raw_weights:
            try:
                value = json.loads(raw_weights)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    "hotspot_clustering_weights must be valid JSON"
                ) from exc
            if not isinstance(value, dict):
                raise ValueError("hotspot_clustering_weights must be a JSON object")
            weights = value

        return cls(
            algorithm_version=settings.get(
                "hotspot_clustering_algorithm_version", "hotspot-cluster-v1"
            ),
            normalization_rule_version=settings.get(
                "hotspot_normalization_rule_version", "hotspot-normalize-v1"
            ),
            lookback_hours=_integer_setting(
                settings, "hotspot_clustering_lookback_hours", 48
            ),
            candidate_window_hours=_integer_setting(
                settings, "hotspot_clustering_candidate_window_hours", 36
            ),
            ngram_size=_integer_setting(settings, "hotspot_clustering_ngram_size", 2),
            min_shared_ngrams=_integer_setting(
                settings, "hotspot_clustering_min_shared_ngrams", 2
            ),
            max_candidates_per_item=_integer_setting(
                settings, "hotspot_clustering_max_candidates_per_item", 20
            ),
            max_postings_per_key=_integer_setting(
                settings, "hotspot_clustering_max_postings_per_key", 200
            ),
            semantic_lower_threshold=_decimal_setting(
                settings, "hotspot_clustering_semantic_lower_threshold", "0.68"
            ),
            accept_threshold=_decimal_setting(
                settings, "hotspot_clustering_accept_threshold", "0.82"
            ),
            semantic_enabled=_boolean_setting(
                settings, "hotspot_clustering_semantic_enabled", False
            ),
            max_semantic_calls=_integer_setting(
                settings, "hotspot_clustering_max_semantic_calls", 50
            ),
            weights=weights,
        )

    @property
    def config_json(self) -> str:
        return json.dumps(
            {
                "accept_threshold": str(self.accept_threshold),
                "algorithm_version": self.algorithm_version,
                "candidate_window_hours": self.candidate_window_hours,
                "lookback_hours": self.lookback_hours,
                "max_candidates_per_item": self.max_candidates_per_item,
                "max_postings_per_key": self.max_postings_per_key,
                "max_semantic_calls": self.max_semantic_calls,
                "min_shared_ngrams": self.min_shared_ngrams,
                "ngram_size": self.ngram_size,
                "normalization_rule_version": self.normalization_rule_version,
                "semantic_enabled": self.semantic_enabled,
                "semantic_lower_threshold": str(self.semantic_lower_threshold),
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


def _integer_setting(settings: Mapping[str, str], key: str, default: int) -> int:
    raw = settings.get(key)
    try:
        return default if raw is None else int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


def _decimal_setting(settings: Mapping[str, str], key: str, default: str) -> Decimal:
    return _decimal(settings.get(key, default), key)


def _boolean_setting(settings: Mapping[str, str], key: str, default: bool) -> bool:
    raw = settings.get(key)
    if raw is None:
        return default
    normalized = raw.strip().casefold()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be a boolean")


def _decimal(value, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{field_name} must be a decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed
