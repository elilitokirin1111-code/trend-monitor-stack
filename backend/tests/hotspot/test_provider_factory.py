from app.collectors.config import CollectorPolicy
from app.domain.hotspot import Platform
from app.providers.hotspot.factory import (
    ProviderRuntimeConfig,
    build_provider_registry,
    settings_with_default_provider_order,
)


def test_factory_registers_only_real_declared_capabilities():
    registry = build_provider_registry(ProviderRuntimeConfig())

    assert registry.provider_ids() == ("newsnow", "dailyhotapi", "rsshub", "opencli")
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
        "dailyhotapi",
        "newsnow",
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
            "hotspot_rsshub_base_url": "http://rsshub.internal:1200",
            "hotspot_rsshub_max_age_minutes": "12",
            "hotspot_opencli_executable": "C:/tools/opencli.exe",
            "hotspot_opencli_limit": "20",
            "hotspot_opencli_bridge_url": "http://host.docker.internal:19826",
            "hotspot_opencli_bridge_token": "bridge-secret",
        }
    )

    assert config.newsnow_base_url == "https://newsnow.internal"
    assert config.newsnow_trust_success_as_fresh is True
    assert config.dailyhotapi_base_url == "https://dailyhot.internal"
    assert config.rsshub_base_url == "http://rsshub.internal:1200"
    assert config.rsshub_max_age_minutes == 12
    assert config.opencli_executable == "C:/tools/opencli.exe"
    assert config.opencli_limit == 20
    assert config.opencli_bridge_url == "http://host.docker.internal:19826"
    assert config.opencli_bridge_token == "bridge-secret"


def test_runtime_config_empty_settings_uses_documented_defaults():
    assert ProviderRuntimeConfig.from_settings({}, {}) == ProviderRuntimeConfig()


def test_runtime_config_uses_compose_environment_but_database_settings_win():
    environment = {
        "HOTSPOT_DAILYHOTAPI_BASE_URL": "http://dailyhotapi:6688",
        "HOTSPOT_RSSHUB_BASE_URL": "http://rsshub:1200",
    }

    from_environment = ProviderRuntimeConfig.from_settings({}, environment)
    overridden = ProviderRuntimeConfig.from_settings(
        {"hotspot_dailyhotapi_base_url": "https://operator.example"}, environment
    )

    assert from_environment.dailyhotapi_base_url == "http://dailyhotapi:6688"
    assert from_environment.rsshub_base_url == "http://rsshub:1200"
    assert overridden.dailyhotapi_base_url == "https://operator.example"
