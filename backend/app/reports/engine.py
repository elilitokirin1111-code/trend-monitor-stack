"""Deterministic report rendering.

The engine consumes only already-versioned trend states, events and AI
classifications (``ReportInput``); it never touches Provider responses or
live collection state. Output is plain Markdown plus the audit trail needed
to trace every derived statement back to its source run and input hash.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
from app.reports.rules import ReportRules

_RELEVANCE_LABELS = {
    "relevant": "相关",
    "possibly_relevant": "可能相关",
    "irrelevant": "不相关",
}


class ReportEngine:
    def __init__(self, rules: ReportRules) -> None:
        self._rules = rules

    def render(
        self,
        source: ReportInput,
        *,
        report_run_id: str,
        attempt: int = 1,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> ReportBatch:
        if finished_at is not None and started_at is not None:
            if finished_at < started_at:
                raise ValueError("report cannot finish before it starts")
        now = finished_at or datetime.now(timezone.utc)
        begin = started_at or now

        items = [
            item
            for item in source.events
            if self._rules.include_irrelevant
            or item.hospitality_relevance != "irrelevant"
        ]
        items.sort(
            key=lambda item: (
                -float(item.trend_score),
                -len(item.platforms),
                item.canonical_title,
            )
        )
        items = items[: self._rules.max_items]

        stale = sorted(
            signal.platform.value
            for signal in source.platform_signals
            if signal.freshness is Freshness.STALE
        )
        missing = sorted(
            platform.value
            for platform in (
                set(Platform)
                - {signal.platform for signal in source.platform_signals}
            )
        )
        data_quality = _data_quality(source.platform_signals)
        status = (
            ReportStatus.SUCCESS
            if data_quality is ReportDataQuality.COMPLETE
            else ReportStatus.PARTIAL
        )

        content = _render_markdown(
            source=source,
            rules=self._rules,
            items=items,
            stale=stale,
            missing=missing,
            data_quality=data_quality,
            finished_at=now,
        )
        return ReportBatch(
            report_run_id=report_run_id,
            report_type=source.report_type,
            period_start=source.period_start,
            period_end=source.period_end,
            report_version=self._rules.report_version,
            config_hash=self._rules.config_hash,
            config_json=self._rules.config_json,
            input_hash=_input_hash(source),
            status=status,
            data_quality=data_quality,
            stale_platforms=tuple(stale),
            missing_platforms=tuple(missing),
            content=content,
            template=self._rules.template,
            source_trend_run_id=source.source_trend_run_id,
            source_classification_run_id=source.source_classification_run_id,
            attempt=attempt,
            started_at=begin,
            finished_at=now,
        )


def _data_quality(
    signals: tuple[ReportPlatformSignal, ...],
) -> ReportDataQuality:
    if not signals:
        return ReportDataQuality.NO_FRESH_DATA
    if not any(signal.freshness is Freshness.FRESH for signal in signals):
        return ReportDataQuality.STALE_ONLY
    expected = {platform.value for platform in Platform}
    observed = {signal.platform.value for signal in signals}
    incomplete = {
        signal.platform.value
        for signal in signals
        if signal.status is CollectionStatus.FAILED
        or signal.freshness is not Freshness.FRESH
    } | (expected - observed)
    if incomplete:
        return ReportDataQuality.PARTIAL
    return ReportDataQuality.COMPLETE


def _input_hash(source: ReportInput) -> str:
    from app.reports.rules import report_input_hash

    events = tuple(
        (
            item.event_id,
            item.trend_series_id,
            item.canonical_title,
            item.trend_state,
            item.hospitality_relevance,
            item.summary,
        )
        for item in source.events
    )
    signals = tuple(
        (
            signal.platform.value,
            signal.status.value,
            signal.freshness.value,
            signal.observed_at.isoformat() if signal.observed_at else None,
        )
        for signal in source.platform_signals
    )
    return report_input_hash(
        report_type=source.report_type.value,
        period_start=source.period_start.isoformat(),
        period_end=source.period_end.isoformat(),
        source_trend_run_id=source.source_trend_run_id,
        source_classification_run_id=source.source_classification_run_id,
        events=events,
        platform_signals=signals,
    )


def _render_markdown(
    *,
    source: ReportInput,
    rules: ReportRules,
    items: list[ReportEventItem],
    stale: list[str],
    missing: list[str],
    data_quality: ReportDataQuality,
    finished_at: datetime,
) -> str:
    period_label = (
        "日报" if source.report_type is ReportType.DAILY else "周报"
    )
    lines: list[str] = []
    lines.append(f"# 热点{period_label} {source.period_start:%Y-%m-%d} ~ {source.period_end:%Y-%m-%d}")
    lines.append("")
    lines.append(f"- 生成时间：{finished_at.astimezone(timezone.utc).isoformat()}")
    lines.append(f"- 报告版本：{rules.report_version}（模板：{rules.template}）")
    lines.append(f"- 数据质量：{data_quality.value}")
    lines.append(f"- 事件数量：{len(items)}（共 {len(source.events)} 个事件）")
    lines.append("")

    lines.append("## 平台健康")
    lines.append("")
    if not source.platform_signals:
        lines.append("- 无任何平台采集记录")
    else:
        for signal in source.platform_signals:
            observed = (
                signal.observed_at.astimezone(timezone.utc).isoformat()
                if signal.observed_at
                else "无"
            )
            lines.append(
                f"- {signal.platform.value}：{_platform_state(signal)}"
                f"（观测 {observed}）"
            )
    lines.append("")

    lines.append("## 热点事件")
    lines.append("")
    if not items:
        lines.append("（该时间窗内没有可报告的事件）")
    for index, item in enumerate(items, start=1):
        relevance = _RELEVANCE_LABELS.get(
            item.hospitality_relevance, item.hospitality_relevance or "未分类"
        )
        score = float(item.trend_score)
        lines.append(f"{index}. **{item.canonical_title}**")
        lines.append(
            f"   - 趋势：{item.trend_state}（评分 {score:.3f}）｜"
            f"数据质量：{item.data_quality}"
        )
        lines.append(f"   - 平台覆盖：{', '.join(item.platforms) or '无'}")
        lines.append(f"   - 酒旅相关性：{relevance}")
        if item.summary:
            lines.append(f"   - 摘要：{item.summary}")
        lines.append("")

    lines.append("## 数据质量警告")
    lines.append("")
    if not stale and not missing and data_quality is ReportDataQuality.COMPLETE:
        lines.append("- 无：全部平台均有 fresh 观测。")
    if stale:
        lines.append(f"- 陈旧数据平台：{', '.join(stale)}（结果非实时，仅供参考）")
    if missing:
        lines.append(f"- 缺失平台：{', '.join(missing)}（本期无采集记录）")
    if data_quality is ReportDataQuality.STALE_ONLY:
        lines.append("- 本报告没有任何 fresh 证据，全部内容来自陈旧缓存。")
    if data_quality is ReportDataQuality.NO_FRESH_DATA:
        lines.append("- 本报告没有任何平台观测，数据不完整。")
    lines.append("")

    lines.append("## 审计来源")
    lines.append("")
    lines.append(f"- 源趋势运行：`{source.source_trend_run_id}`")
    if source.source_classification_run_id:
        lines.append(f"- 源 AI 分类运行：`{source.source_classification_run_id}`")
    lines.append(f"- 输入哈希：`{_input_hash(source)}`")
    lines.append(f"- 配置哈希：`{rules.config_hash}`")
    lines.append("")
    lines.append("> 本报告由版本化事件与趋势数据确定性生成，未直接读取 Provider 响应。")
    return "\n".join(lines)


def _platform_state(signal: ReportPlatformSignal) -> str:
    if signal.status is CollectionStatus.FAILED:
        return "采集失败"
    if signal.freshness is Freshness.FRESH:
        return "实时"
    if signal.freshness is Freshness.STALE:
        return "陈旧"
    return signal.status.value
