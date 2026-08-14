from __future__ import annotations

from app.services import ai_service as ai_module
from app.services import config_service as config_module


class _Database:
    @staticmethod
    def get_setting(key: str):
        assert key == "ai_config"
        return '{"enabled":true,"model":"test","api_key":"live-secret"}'


def test_public_ai_config_never_returns_the_api_key(monkeypatch) -> None:
    monkeypatch.setattr(ai_module, "db", _Database())

    private = ai_module.AIService().get_config()
    public = ai_module.AIService().get_public_config()

    assert private["api_key"] == "live-secret"
    assert public["api_key"].endswith("****")
    assert "live-secret" not in str(public)


def test_generic_settings_response_redacts_both_ai_key_shapes(monkeypatch) -> None:
    class _SettingsDatabase:
        @staticmethod
        def get_all_settings():
            return {
                "ai_config": '{"model":"test","api_key":"legacy-secret"}',
                "hotspot_ai_api_key": "phase-seven-secret",
                "ordinary_setting": "visible",
            }

    monkeypatch.setattr(config_module, "db", _SettingsDatabase())

    public = config_module.ConfigService().get_public_settings()

    assert public["ordinary_setting"] == "visible"
    assert public["hotspot_ai_api_key"].endswith("****")
    assert "legacy-secret" not in public["ai_config"]
    assert "phase-seven-secret" not in str(public)
