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
from .window import SnapshotWindow, snapshot_window_for

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
    "SnapshotWindow",
    "snapshot_window_for",
    "utc_now",
]
