"""Replaceable hotspot Provider registry."""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.hotspot import Platform

from .base import HotspotProvider


class ProviderRegistryError(ValueError):
    """Base class for invalid registry configuration."""


class DuplicateProviderError(ProviderRegistryError):
    pass


class ProviderNotRegisteredError(ProviderRegistryError):
    pass


class ProviderNotSupportedError(ProviderRegistryError):
    pass


class ProviderRegistry:
    def __init__(self, providers: Iterable[HotspotProvider] = ()) -> None:
        self._providers: dict[str, HotspotProvider] = {}
        for provider in providers:
            self.register(provider)

    def register(self, provider: HotspotProvider) -> None:
        provider_id = provider.provider_id.strip()
        if not provider_id:
            raise ValueError("provider_id cannot be empty")
        if provider_id in self._providers:
            raise DuplicateProviderError(f"provider already registered: {provider_id}")
        if not provider.supported_platforms:
            raise ValueError(f"provider supports no platforms: {provider_id}")
        self._providers[provider_id] = provider

    def get(self, provider_id: str) -> HotspotProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ProviderNotRegisteredError(
                f"provider is not registered: {provider_id}"
            ) from exc

    def resolve(
        self,
        platform: Platform,
        provider_ids: tuple[str, ...],
    ) -> tuple[HotspotProvider, ...]:
        providers = []
        for provider_id in provider_ids:
            provider = self.get(provider_id)
            if platform not in provider.supported_platforms:
                raise ProviderNotSupportedError(
                    f"provider {provider_id} does not support {platform.value}"
                )
            providers.append(provider)
        return tuple(providers)

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(self._providers)
