"""Hotspot collection domain contracts."""

from .models import (
    CollectionStatus,
    CollectorResult,
    CollectRequest,
    Freshness,
    Platform,
    ProviderAttempt,
    ProviderError,
    ProviderErrorKind,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderHotItem,
    ProviderResult,
    ProviderStatus,
    RawHotItem,
    utc_now,
)

__all__ = [
    "CollectRequest",
    "CollectionStatus",
    "CollectorResult",
    "Freshness",
    "Platform",
    "ProviderAttempt",
    "ProviderError",
    "ProviderErrorKind",
    "ProviderHealth",
    "ProviderHealthStatus",
    "ProviderHotItem",
    "ProviderResult",
    "ProviderStatus",
    "RawHotItem",
    "utc_now",
]
