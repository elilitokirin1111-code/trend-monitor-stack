"""Hotspot provider interfaces and registry."""

from .base import HotspotProvider, RawCollectionWriter, StaleResultReader
from .dailyhot import DailyHotApiProvider
from .factory import (
    DEFAULT_PROVIDER_ORDER,
    ProviderRuntimeConfig,
    build_provider_registry,
    settings_with_default_provider_order,
)
from .newsnow import NewsNowProvider
from .opencli import CommandResult, OpenCliProvider
from .rsshub import RSSHUB_ROUTES, RssHubProvider
from .registry import (
    DuplicateProviderError,
    ProviderNotRegisteredError,
    ProviderNotSupportedError,
    ProviderRegistry,
)

__all__ = [
    "DEFAULT_PROVIDER_ORDER",
    "CommandResult",
    "DailyHotApiProvider",
    "DuplicateProviderError",
    "HotspotProvider",
    "NewsNowProvider",
    "OpenCliProvider",
    "ProviderNotRegisteredError",
    "ProviderNotSupportedError",
    "ProviderRegistry",
    "ProviderRuntimeConfig",
    "RSSHUB_ROUTES",
    "RawCollectionWriter",
    "RssHubProvider",
    "StaleResultReader",
    "build_provider_registry",
    "settings_with_default_provider_order",
]
