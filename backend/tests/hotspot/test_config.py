import pytest

from app.collectors import CollectorPolicy, ProviderPolicy
from app.domain.hotspot import Platform


def test_policy_loads_provider_order_from_existing_settings_shape():
    policy = CollectorPolicy.from_settings(
        {
            "hotspot_collector_timeout_seconds": "12.5",
            "hotspot_collector_max_retries_per_provider": "2",
            "hotspot_collector_allow_stale": "false",
            "hotspot_provider_order_weibo": "newsnow, dailyhotapi, opencli",
        }
    )

    weibo = policy.for_platform(Platform.WEIBO)
    assert weibo.provider_ids == ("newsnow", "dailyhotapi", "opencli")
    assert weibo.timeout_seconds == 12.5
    assert weibo.max_retries_per_provider == 2
    assert weibo.allow_stale is False
    assert policy.for_platform(Platform.DOUYIN).provider_ids == ()


def test_policy_rejects_duplicate_providers():
    with pytest.raises(ValueError, match="duplicates"):
        ProviderPolicy(provider_ids=("newsnow", "newsnow"))


def test_policy_rejects_unbounded_retries():
    with pytest.raises(ValueError, match="between 0 and 3"):
        ProviderPolicy(provider_ids=("newsnow",), max_retries_per_provider=4)


def test_policy_rejects_invalid_boolean_setting():
    with pytest.raises(ValueError, match="must be a boolean"):
        CollectorPolicy.from_settings({"hotspot_collector_allow_stale": "sometimes"})
