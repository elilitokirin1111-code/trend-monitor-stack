from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import app.trends_v1.engine as trend_engine_module
from app.domain.hotspot import CollectionStatus, Freshness, Platform
from app.domain.hotspot.trends import (
    PlatformSignal,
    PreviousTrendState,
    TrendDataQuality,
    TrendEvaluationContext,
    TrendEventInput,
    TrendLifecycleState,
    TrendObservation,
)
from app.trends_v1 import TrendLifecycleEngine, TrendRules

AT = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


def _observation(
    number: int,
    hours_ago: float,
    *,
    rank: int = 10,
    platform: Platform = Platform.WEIBO,
    freshness: Freshness = Freshness.FRESH,
    hot_score: Decimal | None = Decimal(10000),
) -> TrendObservation:
    return TrendObservation(
        group_id=f"group-{number}",
        normalized_item_id=f"normalized-{number}",
        snapshot_id=f"snapshot-{number}",
        platform=platform,
        observed_at=AT - timedelta(hours=hours_ago),
        freshness=freshness,
        rank=rank,
        hot_score=hot_score,
    )


def _event(
    observations: tuple[TrendObservation, ...],
    *,
    number: int = 1,
) -> TrendEventInput:
    return TrendEventInput(
        event_id=f"event-{number}",
        clustering_run_id="clustering-run-1",
        canonical_title=f"热点事件 {number}",
        representative_title_fingerprint=f"热点事件{number}",
        window_start=AT - timedelta(hours=48),
        window_end=AT,
        observations=observations,
    )


def _context(*signals: PlatformSignal) -> TrendEvaluationContext:
    return TrendEvaluationContext(
        evaluation_id="collection-watermark-1",
        evaluated_at=AT,
        platform_signals=signals,
    )


def _state(
    observations: tuple[TrendObservation, ...],
    *,
    previous: PreviousTrendState | None = None,
    context: TrendEvaluationContext | None = None,
):
    batch = TrendLifecycleEngine().analyze(
        (_event(observations),),
        context or _context(),
        previous_states={"event-1": previous} if previous else {},
    )
    return batch.states[0]


def test_single_recent_observation_is_emerging() -> None:
    state = _state((_observation(1, 0.5),))

    assert state.state is TrendLifecycleState.EMERGING
    assert state.features.fresh_observation_count == 1
    assert state.features.latest_fresh_age_hours == Decimal("0.500000")


def test_strength_velocity_and_acceleration_drive_rising_state() -> None:
    state = _state(
        (
            _observation(1, 8, rank=45),
            _observation(2, 5, rank=35),
            _observation(3, 2, rank=5, platform=Platform.DOUYIN),
            _observation(4, 0.5, rank=2, platform=Platform.BILIBILI),
        )
    )

    assert state.state is TrendLifecycleState.RISING
    assert state.features.velocity >= Decimal("0.10")
    assert state.features.acceleration > Decimal(0)
    assert state.features.fresh_platform_count == 3


def test_high_stable_strength_is_peaking() -> None:
    state = _state(
        tuple(
            _observation(
                number,
                hours_ago,
                rank=1,
                platform=(Platform.WEIBO if number % 2 else Platform.DOUYIN),
                hot_score=Decimal(100000000),
            )
            for number, hours_ago in enumerate((8, 6, 5, 3.5, 2, 0.5), start=1)
        )
    )

    assert state.state is TrendLifecycleState.PEAKING
    assert abs(state.features.velocity) <= Decimal("0.05")
    assert state.trend_score >= Decimal("0.70")


def test_falling_strength_is_declining() -> None:
    state = _state(
        (
            _observation(1, 8, rank=1, hot_score=Decimal(100000000)),
            _observation(2, 5, rank=2, hot_score=Decimal(100000000)),
            _observation(3, 2, rank=35, hot_score=Decimal(100)),
            _observation(4, 0.5, rank=48, hot_score=Decimal(10)),
        )
    )

    assert state.state is TrendLifecycleState.DECLINING
    assert state.features.velocity <= Decimal("-0.10")


def test_old_or_stale_only_activity_cannot_create_a_rising_signal() -> None:
    state = _state(
        (
            _observation(1, 8, rank=3),
            _observation(
                2,
                0.2,
                rank=1,
                freshness=Freshness.STALE,
                hot_score=Decimal(100000000),
            ),
        )
    )

    assert state.state is TrendLifecycleState.DORMANT
    assert state.features.stale_observation_count == 1
    assert state.features.latest_fresh_age_hours == Decimal("8.000000")
    assert state.features.current_strength == Decimal("0.000000")


def test_large_internal_gap_or_dormant_predecessor_is_recurrent() -> None:
    internal_gap = _state(
        (
            _observation(1, 20, rank=3),
            _observation(2, 1, rank=2),
        )
    )
    predecessor = PreviousTrendState(
        trend_series_id="series-existing",
        source_event_id="old-event",
        state=TrendLifecycleState.DORMANT,
        last_fresh_seen_at=AT - timedelta(hours=20),
        velocity=Decimal("-0.20"),
    )
    resumed = _state((_observation(3, 0.5, rank=2),), previous=predecessor)

    assert internal_gap.state is TrendLifecycleState.RECURRENT
    assert internal_gap.features.recurrence_gap_hours == Decimal("19.000000")
    assert resumed.state is TrendLifecycleState.RECURRENT
    assert resumed.trend_series_id == "series-existing"


def test_platform_failures_and_missing_platforms_lower_quality_not_raise_score() -> (
    None
):
    context = _context(
        PlatformSignal(
            platform=Platform.WEIBO,
            status=CollectionStatus.SUCCESS,
            freshness=Freshness.FRESH,
            observed_at=AT,
        ),
        PlatformSignal(
            platform=Platform.DOUYIN,
            status=CollectionStatus.FAILED,
            freshness=Freshness.FRESH,
            observed_at=AT,
        ),
    )

    state = _state((_observation(1, 0.5),), context=context)

    assert state.features.failed_platform_count == 1
    assert state.features.missing_platform_count == 2
    assert state.data_quality is TrendDataQuality.PARTIAL
    assert state.features.data_completeness == Decimal("0.250000")


def test_analysis_is_deterministic_and_linear_in_observation_count(monkeypatch) -> None:
    calls = 0
    original = trend_engine_module._observation_signal

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(trend_engine_module, "_observation_signal", counted)
    events = tuple(
        _event(
            tuple(
                _observation(
                    event_number * 100 + item_number,
                    hours_ago=(item_number % 48) + 0.1,
                    platform=tuple(Platform)[item_number % 4],
                )
                for item_number in range(100)
            ),
            number=event_number,
        )
        for event_number in range(1, 101)
    )
    engine = TrendLifecycleEngine(TrendRules())

    first = engine.analyze(events, _context())
    second = engine.analyze(tuple(reversed(events)), _context())

    assert calls == 20000
    assert first.trend_run_id == second.trend_run_id
    assert [state.trend_state_id for state in first.states] == [
        state.trend_state_id for state in second.states
    ]
    assert len(first.states) == 100
