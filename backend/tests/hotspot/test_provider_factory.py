from app.collectors.config import CollectorPolicy
from app.domain.hotspot import Platform
from app.providers.hotspot.factory import (
    ProviderRuntimeConfig,
    build_provider_registry,
    settings_with_default_provider_order,
)


def test_factory_registers_only_real_declared_capabilities():
    registry = build_provider_registry(ProviderRuntimeConfig())

    assert registry.provider_ids() == ("newsnow", "dailyhotapi", "opencli")
    assert [
        provider.provider_id
        for provider in registry.resolve(
            Platform.XIAOHONGSHU,
            ("opencli",),
        )
    ] == ["opencli"]


def test_default_provider_order_is_replaceable_through_existing_settings_shape():
    settings = settings_with_default_provider_order(
        {"hotspot_provider_order_weibo": "dailyhotapi,newsnow"}
    )
    policy = CollectorPolicy.from_settings(settings)

    assert policy.for_platform(Platform.DOUYIN).provider_ids == (
        "newsnow",
        "dailyhotapi",
    )
    assert policy.for_platform(Platform.WEIBO).provider_ids == (
        "dailyhotapi",
        "newsnow",
    )
    assert policy.for_platform(Platform.XIAOHONGSHU).provider_ids == ("opencli",)


def test_runtime_config_reads_provider_specific_settings():
    config = ProviderRuntimeConfig.from_settings(
        {
            "hotspot_newsnow_base_url": "https://newsnow.internal",
            "hotspot_newsnow_trust_success_as_fresh": "true",
            "hotspot_dailyhotapi_base_url": "https://dailyhot.internal",
            "hotspot_opencli_executable": "C:/tools/opencli.exe",
            "hotspot_opencli_limit": "20",
        }
    )

    assert config.newsnow_base_url == "https://newsnow.internal"
    assert config.newsnow_trust_success_as_fresh is True
    assert config.dailyhotapi_base_url == "https://dailyhot.internal"
    assert config.opencli_executable == "C:/tools/opencli.exe"
    assert config.opencli_limit == 20


def test_runtime_config_empty_settings_uses_documented_defaults():
    assert ProviderRuntimeConfig.from_settings({}) == ProviderRuntimeConfig()
