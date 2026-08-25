from __future__ import annotations

import json

import pytest

from app.classification import ClassificationRules


def test_rules_are_disabled_by_default_and_do_not_hash_secrets() -> None:
    rules = ClassificationRules.from_settings({})

    assert rules.enabled is False
    assert rules.model == "gpt-4o-mini"
    assert rules.api_key == ""
    assert "api_key" not in rules.config_json
    assert len(rules.config_hash) == 64


def test_rules_reuse_legacy_ai_connection_without_exposing_key() -> None:
    rules = ClassificationRules.from_settings(
        {
            "ai_config": json.dumps(
                {
                    "enabled": True,
                    "model": "openai/test-model",
                    "api_key": "secret-value",
                    "base_url": "https://llm.example/v1",
                }
            ),
            "hotspot_ai_timeout_seconds": "12",
            "hotspot_ai_max_concurrency": "2",
            "hotspot_ai_classification_enabled": "true",
        }
    )

    assert rules.enabled is True
    assert rules.api_key == "secret-value"
    assert rules.timeout_seconds == 12
    assert rules.max_concurrency == 2
    assert "secret-value" not in rules.config_json


@pytest.mark.parametrize(
    ("key", "value"),
    (
        ("hotspot_ai_timeout_seconds", "0"),
        ("hotspot_ai_max_concurrency", "0"),
        ("hotspot_ai_max_summary_chars", "20"),
        ("hotspot_ai_classifier_version", ""),
        ("hotspot_ai_base_url", "https://user:secret@llm.example/v1"),
    ),
)
def test_invalid_rules_fail_closed(key: str, value: str) -> None:
    with pytest.raises(ValueError):
        ClassificationRules.from_settings({key: value})
