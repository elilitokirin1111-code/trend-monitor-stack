from __future__ import annotations

from app.observability.alerts import (
    AlertEvaluator,
    AlertRulesConfig,
    AlertSeverity,
    alerts_fingerprint,
)


def _summary(**overrides):
    base = {
        "provider": {
            "items": [
                {
                    "platform": "weibo",
                    "provider_id": "newsnow",
                    "attempts": 10,
                    "success_rate": 0.9,
                }
            ]
        },
        "collection": {
            "platforms": [
                {
                    "platform": "weibo",
                    "runs": 10,
                    "failed": 0,
                    "empty": 0,
                    "stale": 0,
                    "latest_stale_age_minutes": 30,
                }
            ],
            "runs": 10,
            "failed_runs": 0,
        },
        "pipeline": {
            "pending_normalization_snapshots": 2,
            "failed_deliveries_total": 0,
        },
    }
    base.update(overrides)
    return base


def test_disabled_alerts_produce_nothing() -> None:
    evaluator = AlertEvaluator(
        AlertRulesConfig(enabled=False)
    )
    assert evaluator.evaluate(_summary()) == ()


def test_healthy_pipeline_has_no_alerts() -> None:
    evaluator = AlertEvaluator(
        AlertRulesConfig(enabled=True, max_stale_minutes=180)
    )
    assert evaluator.evaluate(_summary()) == ()


def test_stale_platform_triggers_warning_then_critical() -> None:
    evaluator = AlertEvaluator(
        AlertRulesConfig(enabled=True, max_stale_minutes=60)
    )
    summary = _summary()
    summary["collection"]["platforms"][0]["latest_stale_age_minutes"] = 120

    alerts = evaluator.evaluate(summary)

    assert len(alerts) == 1
    assert alerts[0].kind == "stale_platform"
    assert alerts[0].severity is AlertSeverity.WARNING
    assert "weibo" in alerts[0].message

    summary["collection"]["platforms"][0]["latest_stale_age_minutes"] = 400
    critical = evaluator.evaluate(summary)
    assert critical[0].severity is AlertSeverity.CRITICAL


def test_low_provider_success_rate_triggers_alert() -> None:
    evaluator = AlertEvaluator(
        AlertRulesConfig(enabled=True, min_provider_success_rate=0.8)
    )
    summary = _summary()
    summary["provider"]["items"][0]["success_rate"] = 0.4

    alerts = evaluator.evaluate(summary)

    assert any(alert.kind == "provider_success_rate" for alert in alerts)


def test_failed_runs_and_backlog_and_deliveries() -> None:
    evaluator = AlertEvaluator(
        AlertRulesConfig(
            enabled=True,
            max_failed_runs=3,
            max_pending_snapshots=12,
        )
    )
    summary = _summary()
    summary["collection"]["failed_runs"] = 5
    summary["pipeline"]["pending_normalization_snapshots"] = 20
    summary["pipeline"]["failed_deliveries_total"] = 2

    alerts = evaluator.evaluate(summary)
    kinds = {alert.kind for alert in alerts}

    assert {"failed_runs", "pipeline_backlog", "delivery_failed"} <= kinds
    delivery = next(
        alert for alert in alerts if alert.kind == "delivery_failed"
    )
    assert delivery.severity is AlertSeverity.CRITICAL


def test_small_sample_provider_is_not_alerted() -> None:
    evaluator = AlertEvaluator(
        AlertRulesConfig(enabled=True, min_provider_success_rate=0.8)
    )
    summary = _summary()
    summary["provider"]["items"][0]["attempts"] = 2
    summary["provider"]["items"][0]["success_rate"] = 0.0

    assert evaluator.evaluate(summary) == ()


def test_fingerprint_changes_with_alerts() -> None:
    empty = alerts_fingerprint(())
    alerts = AlertEvaluator(
        AlertRulesConfig(enabled=True, max_stale_minutes=10)
    ).evaluate(_summary())
    filled = alerts_fingerprint(alerts)

    assert empty != filled
    assert alerts_fingerprint(alerts) == filled


def test_rules_config_hash_masks_webhook() -> None:
    config = AlertRulesConfig(
        enabled=True, alert_webhook="https://open.feishu.cn/hook?token=xyz"
    )
    assert "xyz" not in config.config_hash
    assert len(config.config_hash) == 64
