import pytest

from app.domain.hotspot import Platform
from app.providers.hotspot import (
    DuplicateProviderError,
    ProviderNotSupportedError,
    ProviderRegistry,
)


class ProviderStub:
    def __init__(self, provider_id, platforms):
        self.provider_id = provider_id
        self.supported_platforms = frozenset(platforms)


def test_registry_preserves_configured_fallback_order():
    first = ProviderStub("first", {Platform.WEIBO})
    second = ProviderStub("second", {Platform.WEIBO})
    registry = ProviderRegistry((second, first))

    resolved = registry.resolve(Platform.WEIBO, ("first", "second"))

    assert resolved == (first, second)


def test_registry_rejects_duplicate_provider_ids():
    provider = ProviderStub("same", {Platform.WEIBO})
    with pytest.raises(DuplicateProviderError):
        ProviderRegistry((provider, provider))


def test_registry_rejects_provider_for_unsupported_platform():
    registry = ProviderRegistry((ProviderStub("weibo-only", {Platform.WEIBO}),))
    with pytest.raises(ProviderNotSupportedError):
        registry.resolve(Platform.DOUYIN, ("weibo-only",))
