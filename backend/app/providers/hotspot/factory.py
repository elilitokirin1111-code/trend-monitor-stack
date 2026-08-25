"""Provider construction and replaceable default chains."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from app.domain.hotspot import Platform

from .dailyhot import DailyHotApiProvider
from .newsnow import NewsNowProvider
from .opencli import OpenCliProvider
from .registry import ProviderRegistry
from .rsshub import RssHubProvider

DEFAULT_NEWSNOW_BASE_URL = "https://newsnow.busiyi.world"
DEFAULT_DAILYHOTAPI_BASE_URL = "https://api-hot.imsyy.top"
DEFAULT_RSSHUB_BASE_URL = "http://localhost:1200"
DEFAULT_RSSHUB_MAX_AGE_MINUTES = 15
DEFAULT_OPENCLI_EXECUTABLE = "opencli"
DEFAULT_OPENCLI_LIMIT = 30


DEFAULT_PROVIDER_ORDER = MappingProxyType(
    {
        Platform.DOUYIN: ("dailyhotapi", "newsnow"),
        Platform.WEIBO: ("rsshub", "dailyhotapi", "newsnow"),
        Platform.BILIBILI: ("rsshub", "dailyhotapi", "newsnow"),
        Platform.XIAOHONGSHU: ("opencli",),
    }
)


@dataclass(frozen=True, slots=True)
class ProviderRuntimeConfig:
    newsnow_base_url: str = DEFAULT_NEWSNOW_BASE_URL
    newsnow_trust_success_as_fresh: bool = False
    dailyhotapi_base_url: str = DEFAULT_DAILYHOTAPI_BASE_URL
    rsshub_base_url: str = DEFAULT_RSSHUB_BASE_URL
    rsshub_max_age_minutes: int = DEFAULT_RSSHUB_MAX_AGE_MINUTES
    opencli_executable: str = DEFAULT_OPENCLI_EXECUTABLE
    opencli_limit: int = DEFAULT_OPENCLI_LIMIT
    opencli_bridge_url: str | None = None
    opencli_bridge_token: str | None = None

    @classmethod
    def from_settings(
        cls,
        settings: Mapping[str, str],
        environ: Mapping[str, str] | None = None,
    ) -> ProviderRuntimeConfig:
        runtime_env = os.environ if environ is None else environ
        return cls(
            newsnow_base_url=settings.get(
                "hotspot_newsnow_base_url",
                runtime_env.get("HOTSPOT_NEWSNOW_BASE_URL", DEFAULT_NEWSNOW_BASE_URL),
            ),
            newsnow_trust_success_as_fresh=_parse_bool(
                settings.get("hotspot_newsnow_trust_success_as_fresh", "false"),
                "hotspot_newsnow_trust_success_as_fresh",
            ),
            dailyhotapi_base_url=settings.get(
                "hotspot_dailyhotapi_base_url",
                runtime_env.get(
                    "HOTSPOT_DAILYHOTAPI_BASE_URL", DEFAULT_DAILYHOTAPI_BASE_URL
                ),
            ),
            rsshub_base_url=settings.get(
                "hotspot_rsshub_base_url",
                runtime_env.get(
                    "HOTSPOT_RSSHUB_BASE_URL",
                    runtime_env.get("RSSHUB_URL", DEFAULT_RSSHUB_BASE_URL),
                ),
            ),
            rsshub_max_age_minutes=int(
                settings.get(
                    "hotspot_rsshub_max_age_minutes",
                    runtime_env.get(
                        "HOTSPOT_RSSHUB_MAX_AGE_MINUTES",
                        str(DEFAULT_RSSHUB_MAX_AGE_MINUTES),
                    ),
                )
            ),
            opencli_executable=settings.get(
                "hotspot_opencli_executable", DEFAULT_OPENCLI_EXECUTABLE
            ),
            opencli_limit=int(
                settings.get("hotspot_opencli_limit", str(DEFAULT_OPENCLI_LIMIT))
            ),
            opencli_bridge_url=(
                settings.get("hotspot_opencli_bridge_url")
                or runtime_env.get("HOTSPOT_OPENCLI_BRIDGE_URL")
                or None
            ),
            opencli_bridge_token=(
                settings.get("hotspot_opencli_bridge_token")
                or runtime_env.get("HOTSPOT_OPENCLI_BRIDGE_TOKEN")
                or None
            ),
        )


def build_provider_registry(config: ProviderRuntimeConfig) -> ProviderRegistry:
    return ProviderRegistry(
        (
            NewsNowProvider(
                base_url=config.newsnow_base_url,
                trust_success_as_fresh=config.newsnow_trust_success_as_fresh,
            ),
            DailyHotApiProvider(base_url=config.dailyhotapi_base_url),
            RssHubProvider(
                base_url=config.rsshub_base_url,
                max_age_minutes=config.rsshub_max_age_minutes,
            ),
            OpenCliProvider(
                executable=config.opencli_executable,
                limit=config.opencli_limit,
                bridge_url=config.opencli_bridge_url,
                bridge_token=config.opencli_bridge_token,
            ),
        )
    )


def settings_with_default_provider_order(
    settings: Mapping[str, str],
) -> dict[str, str]:
    """Fill only missing platform order keys; explicit admin values always win."""
    merged = dict(settings)
    for platform, provider_ids in DEFAULT_PROVIDER_ORDER.items():
        merged.setdefault(
            f"hotspot_provider_order_{platform.value}", ",".join(provider_ids)
        )
    return merged


def _parse_bool(value: str, key: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{key} must be a boolean")
