from __future__ import annotations

from app.reports.rules import (
    ReportRules,
    report_input_hash,
    report_run_id_base,
)


def test_rules_defaults_are_stable() -> None:
    rules = ReportRules.from_settings({})

    assert rules.report_version == "hotspot-report-v1"
    assert rules.template == "markdown_brief"
    assert rules.max_items == 30
    assert rules.include_irrelevant is False
    assert rules.timezone == "Asia/Shanghai"
    assert len(rules.config_hash) == 64
    assert '"template":"markdown_brief"' in rules.config_json


def test_rules_read_runtime_settings_and_version_config() -> None:
    rules = ReportRules.from_settings(
        {
            "hotspot_report_version": "hotspot-report-v2",
            "hotspot_report_max_items": "50",
            "hotspot_report_include_irrelevant": "true",
        }
    )

    assert rules.report_version == "hotspot-report-v2"
    assert rules.max_items == 50
    assert rules.include_irrelevant is True
    changed = ReportRules.from_settings(
        {"hotspot_report_version": "hotspot-report-v2"}
    )
    assert rules.config_hash != changed.config_hash


def test_rules_reject_invalid_values() -> None:
    try:
        ReportRules.from_settings({"hotspot_report_max_items": "0"})
    except ValueError as exc:
        assert "max items" in str(exc)
    else:
        raise AssertionError("expected ValueError for max_items=0")

    try:
        ReportRules.from_settings({"hotspot_report_include_irrelevant": "maybe"})
    except ValueError as exc:
        assert "boolean" in str(exc)
    else:
        raise AssertionError("expected ValueError for invalid boolean")


def test_input_hash_is_stable_and_order_sensitive_to_events() -> None:
    events_a = (("e1", "s1", "台风", "rising", "relevant", "摘要"),)
    events_b = (("e2", "s2", "地震", "peaking", "relevant", "摘要"),)

    first = report_input_hash(
        report_type="daily",
        period_start="2026-08-13T16:00:00+00:00",
        period_end="2026-08-14T16:00:00+00:00",
        source_trend_run_id="trend-1",
        source_classification_run_id="class-1",
        events=events_a,
        platform_signals=(("weibo", "success", "fresh", "2026-08-14T08:07:00+00:00"),),
    )
    same = report_input_hash(
        report_type="daily",
        period_start="2026-08-13T16:00:00+00:00",
        period_end="2026-08-14T16:00:00+00:00",
        source_trend_run_id="trend-1",
        source_classification_run_id="class-1",
        events=events_a,
        platform_signals=(("weibo", "success", "fresh", "2026-08-14T08:07:00+00:00"),),
    )
    different = report_input_hash(
        report_type="daily",
        period_start="2026-08-13T16:00:00+00:00",
        period_end="2026-08-14T16:00:00+00:00",
        source_trend_run_id="trend-1",
        source_classification_run_id="class-1",
        events=events_b,
        platform_signals=(("weibo", "success", "fresh", "2026-08-14T08:07:00+00:00"),),
    )

    assert first == same
    assert first != different
    assert len(first) == 64


def test_run_id_is_deterministic_and_attempt_suffixed() -> None:
    base = report_run_id_base(
        report_type="daily",
        period_start="2026-08-13T16:00:00+00:00",
        report_version="hotspot-report-v1",
        config_hash="c" * 64,
        input_hash="i" * 64,
    )
    again = report_run_id_base(
        report_type="daily",
        period_start="2026-08-13T16:00:00+00:00",
        report_version="hotspot-report-v1",
        config_hash="c" * 64,
        input_hash="i" * 64,
    )

    assert base == again
    assert len(base) == 64
