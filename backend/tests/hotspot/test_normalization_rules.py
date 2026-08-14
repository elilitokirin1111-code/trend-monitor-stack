from decimal import Decimal

import pytest

from app.normalization import NormalizationRules


def test_rules_have_stable_config_hash_independent_of_mapping_order() -> None:
    first = NormalizationRules(hot_score_multipliers={"": 1, "万": 10000})
    second = NormalizationRules(hot_score_multipliers={"万": 10000, "": 1})

    assert first.config_json == second.config_json
    assert first.config_hash == second.config_hash
    assert len(first.config_hash) == 64


def test_rules_load_versioned_overrides_from_existing_settings_shape() -> None:
    rules = NormalizationRules.from_settings(
        {
            "hotspot_normalization_rule_version": "normalize-v2",
            "hotspot_dedup_algorithm_version": "dedup-v2",
            "hotspot_normalization_tracking_params": "campaign, ref",
            "hotspot_normalization_published_at_fields": "when,created",
            "hotspot_normalization_hot_score_units": '{"千":"1000"}',
        }
    )

    assert rules.version == "normalize-v2"
    assert rules.dedup_algorithm_version == "dedup-v2"
    assert rules.tracking_parameters == frozenset({"campaign", "ref"})
    assert rules.published_at_fields == ("when", "created")
    assert rules.hot_score_multipliers["千"] == Decimal(1000)
    assert rules.hot_score_multipliers["万"] == Decimal(10000)


@pytest.mark.parametrize(
    "settings, message",
    [
        (
            {"hotspot_normalization_hot_score_units": "not-json"},
            "must be valid JSON",
        ),
        (
            {"hotspot_normalization_hot_score_units": "[]"},
            "must be a JSON object",
        ),
        (
            {"hotspot_normalization_tracking_params": " , "},
            "cannot be empty",
        ),
    ],
)
def test_rules_reject_invalid_admin_configuration(settings, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        NormalizationRules.from_settings(settings)
