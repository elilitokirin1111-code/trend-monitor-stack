from datetime import datetime, timezone

import pytest

from app.domain.hotspot import (
    Freshness,
    Platform,
    ProviderError,
    ProviderErrorKind,
    ProviderHotItem,
    ProviderResult,
    ProviderStatus,
)

NOW = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)


def test_successful_empty_result_is_valid_real_empty_board():
    result = ProviderResult(
        provider_id="provider-a",
        platform=Platform.WEIBO,
        status=ProviderStatus.SUCCESS,
        freshness=Freshness.FRESH,
        fetched_at=NOW,
        observed_at=NOW,
        items=(),
    )

    assert result.items == ()


def test_failed_result_cannot_contain_items():
    with pytest.raises(ValueError, match="cannot contain items"):
        ProviderResult(
            provider_id="provider-a",
            platform=Platform.WEIBO,
            status=ProviderStatus.FAILED,
            freshness=Freshness.FRESH,
            fetched_at=NOW,
            observed_at=NOW,
            items=(ProviderHotItem(title="topic", url="https://example.com"),),
            error=ProviderError(
                kind=ProviderErrorKind.UPSTREAM,
                code="failed",
                message="failed",
                retryable=True,
            ),
        )


def test_domain_timestamps_must_be_timezone_aware():
    with pytest.raises(ValueError, match="timezone-aware"):
        ProviderResult(
            provider_id="provider-a",
            platform=Platform.WEIBO,
            status=ProviderStatus.SUCCESS,
            freshness=Freshness.FRESH,
            fetched_at=datetime(2026, 8, 14, 8, 0),  # noqa: DTZ001 - invalid by design
            observed_at=NOW,
        )
