"""Validated Collector V2 configuration compatible with the settings API."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.domain.hotspot import Platform


def _parse_bool(value: str, key: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be a boolean")


@dataclass(frozen=True, slots=True)
class ProviderPolicy:
    provider_ids: tuple[str, ...]
    timeout_seconds: float = 20.0
    max_retries_per_provider: int = 1
    allow_stale: bool = True

    def __post_init__(self) -> None:
        normalized = tuple(provider_id.strip() for provider_id in self.provider_ids)
        if any(not provider_id for provider_id in normalized):
            raise ValueError("provider_ids cannot contain empty values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("provider_ids cannot contain duplicates")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 0 <= self.max_retries_per_provider <= 3:
            raise ValueError("max_retries_per_provider must be between 0 and 3")
        object.__setattr__(self, "provider_ids", normalized)


@dataclass(frozen=True, slots=True)
class CollectorPolicy:
    platforms: Mapping[Platform, ProviderPolicy]

    def __post_init__(self) -> None:
        object.__setattr__(self, "platforms", MappingProxyType(dict(self.platforms)))

    def for_platform(self, platform: Platform) -> ProviderPolicy:
        return self.platforms.get(platform, ProviderPolicy(provider_ids=()))

    @classmethod
    def from_settings(cls, settings: Mapping[str, str]) -> CollectorPolicy:
        """Build policy from values accepted by the existing generic settings API.

        Keys:
        - hotspot_collector_timeout_seconds
        - hotspot_collector_max_retries_per_provider
        - hotspot_collector_allow_stale
        - hotspot_provider_order_<platform> (comma-separated Provider ids)
        """
        timeout_key = "hotspot_collector_timeout_seconds"
        retries_key = "hotspot_collector_max_retries_per_provider"
        stale_key = "hotspot_collector_allow_stale"

        timeout = float(settings.get(timeout_key, "20"))
        retries = int(settings.get(retries_key, "1"))
        allow_stale = _parse_bool(settings.get(stale_key, "true"), stale_key)

        policies = {}
        for platform in Platform:
            order_key = f"hotspot_provider_order_{platform.value}"
            provider_ids = tuple(
                value.strip()
                for value in settings.get(order_key, "").split(",")
                if value.strip()
            )
            policies[platform] = ProviderPolicy(
                provider_ids=provider_ids,
                timeout_seconds=timeout,
                max_retries_per_provider=retries,
                allow_stale=allow_stale,
            )
        return cls(platforms=policies)
