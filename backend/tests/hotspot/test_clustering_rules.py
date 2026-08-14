from __future__ import annotations

import json
from decimal import Decimal

import pytest

from app.clustering import ClusteringRules


def test_rules_are_versioned_configurable_and_hash_stable() -> None:
    first = ClusteringRules.from_settings({})
    second = ClusteringRules.from_settings({})

    assert first.algorithm_version == "hotspot-cluster-v1"
    assert first.lookback_hours == 48
    assert first.candidate_window_hours == 36
    assert first.max_candidates_per_item == 20
    assert first.semantic_enabled is False
    assert first.config_json == second.config_json
    assert first.config_hash == second.config_hash
    assert len(first.config_hash) == 64

    configured = ClusteringRules.from_settings(
        {
            "hotspot_clustering_algorithm_version": "hotspot-cluster-v2",
            "hotspot_clustering_lookback_hours": "72",
            "hotspot_clustering_candidate_window_hours": "24",
            "hotspot_clustering_max_candidates_per_item": "12",
            "hotspot_clustering_min_shared_ngrams": "3",
            "hotspot_clustering_accept_threshold": "0.90",
            "hotspot_clustering_semantic_lower_threshold": "0.70",
            "hotspot_clustering_semantic_enabled": "true",
            "hotspot_clustering_max_semantic_calls": "8",
            "hotspot_clustering_weights": json.dumps(
                {
                    "sequence": "0.50",
                    "ngram": "0.30",
                    "keyword": "0.10",
                    "time": "0.10",
                }
            ),
        }
    )

    assert configured.algorithm_version == "hotspot-cluster-v2"
    assert configured.lookback_hours == 72
    assert configured.candidate_window_hours == 24
    assert configured.max_candidates_per_item == 12
    assert configured.accept_threshold == Decimal("0.90")
    assert configured.semantic_lower_threshold == Decimal("0.70")
    assert configured.semantic_enabled is True
    assert configured.max_semantic_calls == 8
    assert configured.config_hash != first.config_hash


@pytest.mark.parametrize(
    "settings",
    [
        {"hotspot_clustering_lookback_hours": "0"},
        {
            "hotspot_clustering_lookback_hours": "12",
            "hotspot_clustering_candidate_window_hours": "24",
        },
        {"hotspot_clustering_max_candidates_per_item": "0"},
        {"hotspot_clustering_semantic_enabled": "perhaps"},
        {
            "hotspot_clustering_accept_threshold": "0.5",
            "hotspot_clustering_semantic_lower_threshold": "0.5",
        },
        {"hotspot_clustering_weights": '{"sequence":"1","ngram":"1"}'},
    ],
)
def test_invalid_rule_settings_fail_closed(settings: dict[str, str]) -> None:
    with pytest.raises(ValueError):
        ClusteringRules.from_settings(settings)
