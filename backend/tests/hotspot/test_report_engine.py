from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.hotspot import (
    CollectionStatus,
    Freshness,
    Platform,
    ReportBatch,
    ReportDataQuality,
    ReportEventItem,
    ReportInput,
    ReportPlatformSignal,
    ReportStatus,
    ReportType,
)
from app.reports.engine import ReportEngine
from app.reports.rules import ReportRules

PERIOD_START = datetime(2026, 8, 13, 16, 0, tzinfo=timezone.utc)
PERIOD_END = datetime(2026, 8, 14, 16, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 8, 14, 16, 5, tzinfo=timezone.utc)


def _event(
    *,
    event_id: str = "evt-1",
    title: str = "台风登陆广东",
    trend_state: str = "rising",
    score: str = "0.72",
    quality: str = "complete",
    platforms: tuple[str, ...] = ("weibo", "bilibili"),
    relevance: str | None = "relevant",
    summary: str | None = "酒旅相关热点事件。",
) -> ReportEventItem:
    return ReportEventItem(
        event_id=event_id,
        trend_series_id=f"series-{event_id}",
        canonical_title=title,
        trend_state=trend_state,
        trend_score=Decimal(score),
        data_quality=quality,
        platforms=platforms,
        hospitality_relevance=relevance,
        hospitality_score=Decimal("0.82"),
        summary=summary,
    )


def _input(
    *,
    events: tuple[ReportEventItem, ...] = (_event(),),
    signals: tuple[ReportPlatformSignal, ...] = tuple(
        ReportPlatformSignal(
            platform=platform,
            status=CollectionStatus.SUCCESS,
            freshness=Freshness.FRESH,
            observed_at=datetime(2026, 8, 14, 8, 7, tzinfo=timezone.utc),
        )
        for platform in (Platform.WEIBO, Platform.BILIBILI, Platform.DOUYIN, Platform.XIAOHONGSHU)
    ),
) -> ReportInput:
    return ReportInput(
        report_type=ReportType.DAILY,
        period_start=PERIOD_START,
        period_end=PERIOD_END,
        source_trend_run_id="trend-run-1",
        source_classification_run_id="class-run-1",
        events=events,
        platform_signals=signals,
    )


def _render(source: ReportInput, **kwargs) -> ReportBatch:
    return ReportEngine(ReportRules.from_settings({})).render(
        source,
        report_run_id="report-run-1",
        started_at=NOW - timedelta(seconds=2),
        finished_at=NOW,
        **kwargs,
    )


def test_render_produces_audited_markdown_without_provider_data() -> None:
    batch = _render(_input())

    assert isinstance(batch, ReportBatch)
    assert batch.status is ReportStatus.SUCCESS
    assert batch.data_quality is ReportDataQuality.COMPLETE
    assert batch.report_type is ReportType.DAILY
    assert batch.source_trend_run_id == "trend-run-1"
    assert batch.source_classification_run_id == "class-run-1"
    assert batch.attempt == 1
    assert "热点日报" in batch.content
    assert "台风登陆广东" in batch.content
    assert "trend-run-1" in batch.content
    assert "class-run-1" in batch.content
    assert "未直接读取 Provider 响应" in batch.content
    assert "weibo：实时" in batch.content
    assert "无：全部平台均有 fresh 观测" in batch.content
    assert batch.input_hash
    assert batch.config_hash


def test_render_marks_stale_and_missing_platforms() -> None:
    source = _input(
        signals=(
            ReportPlatformSignal(
                platform=Platform.WEIBO,
                status=CollectionStatus.SUCCESS,
                freshness=Freshness.STALE,
                observed_at=datetime(2026, 8, 14, 8, 7, tzinfo=timezone.utc),
            ),
            ReportPlatformSignal(
                platform=Platform.DOUYIN,
                status=CollectionStatus.FAILED,
                freshness=Freshness.STALE,
                observed_at=datetime(2026, 8, 14, 8, 7, tzinfo=timezone.utc),
            ),
        )
    )

    batch = _render(source)

    assert batch.status is ReportStatus.PARTIAL
    assert batch.data_quality is ReportDataQuality.STALE_ONLY
    assert batch.stale_platforms == ("douyin", "weibo")
    assert batch.missing_platforms == ("bilibili", "xiaohongshu")
    assert "陈旧数据平台：douyin, weibo" in batch.content
    assert "缺失平台：bilibili, xiaohongshu" in batch.content
    assert "本报告没有任何 fresh 证据" in batch.content


def test_render_without_any_signal_is_no_fresh_data() -> None:
    batch = _render(_input(signals=()))

    assert batch.data_quality is ReportDataQuality.NO_FRESH_DATA
    assert batch.status is ReportStatus.PARTIAL
    assert "无任何平台采集记录" in batch.content
    assert "本报告没有任何平台观测" in batch.content


def test_render_filters_irrelevant_and_orders_by_score() -> None:
    source = _input(
        events=(
            _event(event_id="evt-low", title="低分事件", score="0.3"),
            _event(
                event_id="evt-irrelevant",
                title="无关事件",
                score="0.9",
                relevance="irrelevant",
            ),
            _event(event_id="evt-high", title="高分事件", score="0.95"),
        )
    )

    batch = _render(source)

    assert "无关事件" not in batch.content
    assert batch.content.index("高分事件") < batch.content.index("低分事件")


def test_render_include_irrelevant_setting() -> None:
    rules = ReportRules.from_settings({"hotspot_report_include_irrelevant": "true"})
    source = _input(
        events=(
            _event(event_id="evt-a", title="无关事件", relevance="irrelevant"),
        )
    )

    batch = ReportEngine(rules).render(
        source, report_run_id="r", finished_at=NOW
    )

    assert "无关事件" in batch.content


def test_render_max_items_truncates() -> None:
    rules = ReportRules.from_settings({"hotspot_report_max_items": "1"})
    source = _input(
        events=(
            _event(event_id="evt-1", title="第一个", score="0.8"),
            _event(event_id="evt-2", title="第二个", score="0.7"),
        )
    )

    batch = ReportEngine(rules).render(source, report_run_id="r", finished_at=NOW)

    assert "第二个" not in batch.content
    assert "共 2 个事件" in batch.content


def test_render_weekly_uses_weekly_label() -> None:
    source = _input()
    object.__setattr__(source, "report_type", ReportType.WEEKLY)

    batch = _render(source)

    assert "热点周报" in batch.content


def test_render_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        ReportInput(
            report_type=ReportType.DAILY,
            period_start=PERIOD_END,
            period_end=PERIOD_START,
            source_trend_run_id="trend-run-1",
            source_classification_run_id=None,
            events=(_event(),),
            platform_signals=(),
        )
