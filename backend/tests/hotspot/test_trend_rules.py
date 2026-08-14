from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.trends_v1 import TrendRules


def test_trend_rules_are_versioned_configurable_and_hash_stable() -> None:
    first = TrendRules.from_settings({})
    second = TrendRules.from_settings({})

    assert first.algorithm_version == "hotspot-trend-v1"
    assert first.bucket_minutes == 30
    assert first.recent_window_hours == 3
    assert first.dormant_after_hours == 6
    assert first.recurrent_gap_hours == 12
    assert first.config_json == second.config_json
    assert first.config_hash == second.config_hash
    assert len(first.config_hash) == 64

    configured = TrendRules.from_settings(
        {
            "hotspot_trend_algorithm_version": "hotspot-trend-v2",
            "hotspot_trend_bucket_minutes": "60",
            "hotspot_trend_recent_window_hours": "4",
            "hotspot_trend_dormant_after_hours": "8",
            "hotspot_trend_recurrent_gap_hours": "18",
            "hotspot_trend_rising_velocity_threshold": "0.12",
            "hotspot_trend_declining_velocity_threshold": "0.14",
            "hotspot_trend_peaking_score_threshold": "0.80",
            "hotspot_trend_weights": json.dumps(
                {
                    "strength": "0.40",
                    "coverage": "0.20",
                    "positive_velocity": "0.15",
                    "positive_acceleration": "0.10",
                    "persistence": "0.15",
                }
            ),
        }
    )

    assert configured.algorithm_version == "hotspot-trend-v2"
    assert configured.bucket_minutes == 60
    assert configured.recurrent_gap_hours == 18
    assert configured.rising_velocity_threshold == Decimal("0.12")
    assert configured.config_hash != first.config_hash


@pytest.mark.parametrize(
    "settings",
    [
        {"hotspot_trend_bucket_minutes": "0"},
        {
            "hotspot_trend_recent_window_hours": "8",
            "hotspot_trend_dormant_after_hours": "4",
        },
        {"hotspot_trend_recurrent_gap_hours": "4"},
        {"hotspot_trend_rank_ceiling": "1"},
        {"hotspot_trend_peaking_score_threshold": "1.1"},
        {"hotspot_trend_rising_velocity_threshold": "-0.1"},
        {"hotspot_trend_weights": '{"strength":"1"}'},
    ],
)
def test_invalid_trend_rules_fail_closed(settings: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        TrendRules.from_settings(settings)
