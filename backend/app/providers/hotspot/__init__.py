"""Hotspot provider interfaces and registry."""

from .base import HotspotProvider, RawCollectionWriter, StaleResultReader
from .registry import (
    DuplicateProviderError,
    ProviderNotRegisteredError,
    ProviderNotSupportedError,
    ProviderRegistry,
)

__all__ = [
    "DuplicateProviderError",
    "HotspotProvider",
    "ProviderNotRegisteredError",
    "ProviderNotSupportedError",
    "ProviderRegistry",
    "RawCollectionWriter",
    "StaleResultReader",
]
