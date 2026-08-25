"""Ports that keep collection infrastructure independent from business logic."""

from __future__ import annotations

from typing import Protocol

from app.domain.hotspot import (
    CollectorResult,
    CollectRequest,
    Platform,
    ProviderHealth,
    ProviderResult,
)


class HotspotProvider(Protocol):
    provider_id: str
    supported_platforms: frozenset[Platform]

    async def collect(self, request: CollectRequest) -> ProviderResult:
        """Collect one platform without invoking business analysis."""

    async def health(self) -> ProviderHealth:
        """Return provider-specific availability without fabricating data."""


class RawCollectionWriter(Protocol):
    async def save_collection(self, result: CollectorResult) -> None:
        """Persist the complete run, attempts, raw payloads and raw items."""


class StaleResultReader(Protocol):
    async def get_latest(self, platform: Platform) -> ProviderResult | None:
        """Load the last persisted result, explicitly marked stale."""
