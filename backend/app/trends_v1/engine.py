"""Deterministic feature extraction and hotspot lifecycle state machine."""

from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from itertools import pairwise

from app.domain.hotspot import (
    CollectionStatus,
    Freshness,
    Platform,
    PreviousTrendState,
    TrendBatch,
    TrendDataQuality,
    TrendEvaluationContext,
    TrendEventInput,
    TrendFeatures,
    TrendLifecycleState,
    TrendObservation,
    TrendStateRecord,
    utc_now,
)

from .rules import TrendRules

_QUANTUM = Decimal("0.000001")


class TrendLifecycleEngine:
    def __init__(self, rules: TrendRules | None = None) -> None:
        self.rules = rules or TrendRules()

    def analyze(
        self,
        input_events: tuple[TrendEventInput, ...],
        context: TrendEvaluationContext,
        *,
        previous_states: Mapping[str, PreviousTrendState] | None = None,
        lineage_evidence: Mapping[str, tuple[str, int]] | None = None,
    ) -> TrendBatch:
        if not input_events:
            raise ValueError("trend analysis requires at least one event")
        events = tuple(sorted(input_events, key=lambda event: event.event_id))
        run_ids = {event.clustering_run_id for event in events}
        if len(run_ids) != 1:
            raise ValueError("trend events must belong to one clustering run")
        if len({event.event_id for event in events}) != len(events):
            raise ValueError("trend input event identifiers must be unique")
        previous_states = previous_states or {}
        lineage_evidence = lineage_evidence or {}
        input_hash = _input_hash(
            events,
            context,
            previous_states,
            lineage_evidence,
        )
        source_run_id = next(iter(run_ids))
        run_id = _identifier(
            "trend-run",
            source_run_id,
            context.evaluation_id,
            self.rules.algorithm_version,
            self.rules.config_hash,
            input_hash,
        )
        started_at = utc_now()
        states = tuple(
            self._evaluate(
                event,
                context,
                run_id,
                previous_states.get(event.event_id),
                lineage_evidence.get(event.event_id),
            )
            for event in events
        )
        return TrendBatch(
            trend_run_id=run_id,
            source_clustering_run_id=source_run_id,
            evaluation_id=context.evaluation_id,
            algorithm_version=self.rules.algorithm_version,
            config_hash=self.rules.config_hash,
            config_json=self.rules.config_json,
            input_hash=input_hash,
            evaluated_at=context.evaluated_at,
            started_at=started_at,
            finished_at=utc_now(),
            states=states,
        )

    def _evaluate(
        self,
        event: TrendEventInput,
        context: TrendEvaluationContext,
        run_id: str,
        previous: PreviousTrendState | None,
        lineage: tuple[str, int] | None,
    ) -> TrendStateRecord:
        features = self._features(event, context)
        score = self._trend_score(features)
        proposed = self._proposed_state(features, score, previous, context)
        state = _transition(previous.state if previous else None, proposed)
        series_id = (
            previous.trend_series_id
            if previous
            else _identifier("trend-series", event.event_id)
        )
        match_kind, overlap_count = lineage or ("new", 0)
        quality = _data_quality(features)
        return TrendStateRecord(
            trend_state_id=_identifier("trend-state", run_id, event.event_id),
            trend_run_id=run_id,
            trend_series_id=series_id,
            source_event_id=event.event_id,
            predecessor_event_id=previous.source_event_id if previous else None,
            lineage_match_kind=match_kind,
            lineage_overlap_count=overlap_count,
            canonical_title=event.canonical_title,
            state=state,
            previous_state=previous.state if previous else None,
            trend_score=score,
            data_quality=quality,
            evaluated_at=context.evaluated_at,
            features=features,
        )

    def _features(
        self,
        event: TrendEventInput,
        context: TrendEvaluationContext,
    ) -> TrendFeatures:
        if context.evaluated_at < event.window_end:
            raise ValueError("trend evaluation cannot precede clustering window end")
        fresh = sorted(
            (item for item in event.observations if item.freshness is Freshness.FRESH),
            key=lambda item: (item.observed_at, item.group_id),
        )
        stale_count = len(event.observations) - len(fresh)
        buckets: dict[datetime, list[Decimal]] = defaultdict(list)
        for observation in fresh:
            buckets[
                _bucket_start(observation.observed_at, self.rules.bucket_minutes)
            ].append(_observation_signal(observation, self.rules))
        bucket_strength = {key: _mean(values) for key, values in buckets.items()}
        window = self.rules.recent_window_hours
        current = _window_mean(bucket_strength, context.evaluated_at, 0, window)
        previous = _window_mean(
            bucket_strength, context.evaluated_at, window, window * 2
        )
        earlier = _window_mean(
            bucket_strength, context.evaluated_at, window * 2, window * 3
        )
        velocity = _quantize(current - previous)
        acceleration = _quantize(velocity - (previous - earlier))
        fresh_platforms = {item.platform for item in fresh}
        coverage = _quantize(Decimal(len(fresh_platforms)) / Decimal(len(Platform)))
        first_seen = fresh[0].observed_at if fresh else None
        last_seen = fresh[-1].observed_at if fresh else None
        duration = (
            Decimal(str((last_seen - first_seen).total_seconds() / 3600))
            if first_seen and last_seen
            else Decimal(0)
        )
        persistence = _quantize(
            min(Decimal(1), duration / Decimal(self.rules.dormant_after_hours))
        )
        latest_age = (
            Decimal(str((context.evaluated_at - last_seen).total_seconds() / 3600))
            if last_seen
            else None
        )
        recurrence_gap = _maximum_gap_hours(fresh)
        failed, stale_platforms, missing, completeness = _platform_quality(context)
        return TrendFeatures(
            observation_count=len(event.observations),
            fresh_observation_count=len(fresh),
            stale_observation_count=stale_count,
            fresh_platform_count=len(fresh_platforms),
            failed_platform_count=failed,
            stale_platform_count=stale_platforms,
            missing_platform_count=missing,
            data_completeness=completeness,
            current_strength=current,
            previous_strength=previous,
            earlier_strength=earlier,
            velocity=velocity,
            acceleration=acceleration,
            coverage_score=coverage,
            persistence_score=persistence,
            active_duration_hours=_quantize(duration),
            latest_fresh_age_hours=(
                _quantize(max(Decimal(0), latest_age))
                if latest_age is not None
                else None
            ),
            recurrence_gap_hours=recurrence_gap,
            first_fresh_seen_at=first_seen,
            last_fresh_seen_at=last_seen,
        )

    def _trend_score(self, features: TrendFeatures) -> Decimal:
        values = {
            "strength": features.current_strength,
            "coverage": features.coverage_score,
            "positive_velocity": max(Decimal(0), features.velocity),
            "positive_acceleration": max(Decimal(0), features.acceleration),
            "persistence": features.persistence_score,
        }
        return _quantize(
            sum(
                (values[key] * self.rules.weights[key] for key in values),
                Decimal(0),
            )
        )

    def _proposed_state(
        self,
        features: TrendFeatures,
        score: Decimal,
        previous: PreviousTrendState | None,
        context: TrendEvaluationContext,
    ) -> TrendLifecycleState:
        age = features.latest_fresh_age_hours
        if age is None or age >= Decimal(self.rules.dormant_after_hours):
            return TrendLifecycleState.DORMANT
        if _is_recurrent(features, previous, self.rules):
            return TrendLifecycleState.RECURRENT
        minimum_duration = Decimal(self.rules.bucket_minutes) / Decimal(60)
        if (
            features.fresh_observation_count < self.rules.minimum_observations
            or features.active_duration_hours < minimum_duration
        ):
            return TrendLifecycleState.EMERGING
        if features.velocity >= self.rules.rising_velocity_threshold:
            return TrendLifecycleState.RISING
        if features.velocity <= -self.rules.declining_velocity_threshold:
            return TrendLifecycleState.DECLINING
        if (
            score >= self.rules.peaking_score_threshold
            and abs(features.velocity) <= self.rules.plateau_velocity_threshold
        ):
            return TrendLifecycleState.PEAKING
        return TrendLifecycleState.EMERGING


def _observation_signal(
    observation: TrendObservation,
    rules: TrendRules,
) -> Decimal:
    values: list[Decimal] = []
    if observation.rank is not None:
        rank = min(observation.rank, rules.rank_ceiling)
        values.append(Decimal(1) - Decimal(rank - 1) / Decimal(rules.rank_ceiling - 1))
    if observation.hot_score is not None:
        log_value = Decimal(str(math.log10(float(observation.hot_score) + 1)))
        values.append(min(Decimal(1), log_value / rules.hot_log_ceiling))
    return _quantize(_mean(values)) if values else Decimal(0)


def _bucket_start(value: datetime, minutes: int) -> datetime:
    utc = value.astimezone(timezone.utc)
    minute = utc.minute - (utc.minute % minutes) if minutes < 60 else 0
    if minutes < 60:
        return utc.replace(minute=minute, second=0, microsecond=0)
    epoch_minutes = int(utc.timestamp() // 60)
    floored = epoch_minutes - (epoch_minutes % minutes)
    return datetime.fromtimestamp(floored * 60, tz=timezone.utc)


def _window_mean(
    buckets: Mapping[datetime, Decimal],
    evaluated_at: datetime,
    minimum_age_hours: int,
    maximum_age_hours: int,
) -> Decimal:
    values = []
    for observed_at, strength in buckets.items():
        age = Decimal(str((evaluated_at - observed_at).total_seconds() / 3600))
        if Decimal(minimum_age_hours) <= age < Decimal(maximum_age_hours):
            values.append(strength)
    return _quantize(_mean(values)) if values else Decimal(0)


def _maximum_gap_hours(
    observations: list[TrendObservation],
) -> Decimal | None:
    if len(observations) < 2:
        return None
    gap = max(
        (
            right.observed_at - left.observed_at
            for left, right in pairwise(observations)
        ),
        key=lambda value: value.total_seconds(),
    )
    return _quantize(Decimal(str(gap.total_seconds() / 3600)))


def _platform_quality(
    context: TrendEvaluationContext,
) -> tuple[int, int, int, Decimal]:
    failed = sum(
        signal.status is CollectionStatus.FAILED for signal in context.platform_signals
    )
    stale = sum(
        signal.status is not CollectionStatus.FAILED
        and signal.freshness is Freshness.STALE
        for signal in context.platform_signals
    )
    missing = len(Platform) - len(context.platform_signals)
    usable = sum(
        signal.status is not CollectionStatus.FAILED
        and signal.freshness is Freshness.FRESH
        for signal in context.platform_signals
    )
    return failed, stale, missing, _quantize(Decimal(usable) / Decimal(len(Platform)))


def _data_quality(features: TrendFeatures) -> TrendDataQuality:
    if features.fresh_observation_count == 0:
        return (
            TrendDataQuality.STALE_ONLY
            if features.stale_observation_count
            else TrendDataQuality.NO_FRESH_DATA
        )
    if (
        features.stale_observation_count
        or features.failed_platform_count
        or features.stale_platform_count
        or features.missing_platform_count
    ):
        return TrendDataQuality.PARTIAL
    return TrendDataQuality.COMPLETE


def _is_recurrent(
    features: TrendFeatures,
    previous: PreviousTrendState | None,
    rules: TrendRules,
) -> bool:
    if (
        features.recurrence_gap_hours is not None
        and features.recurrence_gap_hours >= Decimal(rules.recurrent_gap_hours)
    ):
        return True
    if (
        previous
        and previous.state is TrendLifecycleState.DORMANT
        and previous.last_fresh_seen_at
        and features.last_fresh_seen_at
    ):
        gap = features.last_fresh_seen_at - previous.last_fresh_seen_at
        return (
            Decimal(str(gap.total_seconds() / 3600))
            >= Decimal(rules.recurrent_gap_hours)
            and features.latest_fresh_age_hours is not None
            and features.latest_fresh_age_hours < Decimal(rules.recent_window_hours)
        )
    return False


def _transition(
    previous: TrendLifecycleState | None,
    proposed: TrendLifecycleState,
) -> TrendLifecycleState:
    if previous is None or previous is proposed:
        return proposed
    allowed = {
        TrendLifecycleState.EMERGING: {
            TrendLifecycleState.RISING,
            TrendLifecycleState.PEAKING,
            TrendLifecycleState.DORMANT,
            TrendLifecycleState.RECURRENT,
        },
        TrendLifecycleState.RISING: {
            TrendLifecycleState.PEAKING,
            TrendLifecycleState.DECLINING,
            TrendLifecycleState.DORMANT,
            TrendLifecycleState.RECURRENT,
        },
        TrendLifecycleState.PEAKING: {
            TrendLifecycleState.DECLINING,
            TrendLifecycleState.DORMANT,
            TrendLifecycleState.RECURRENT,
        },
        TrendLifecycleState.DECLINING: {
            TrendLifecycleState.DORMANT,
            TrendLifecycleState.RECURRENT,
            TrendLifecycleState.RISING,
        },
        TrendLifecycleState.DORMANT: {
            TrendLifecycleState.RECURRENT,
            TrendLifecycleState.EMERGING,
        },
        TrendLifecycleState.RECURRENT: {
            TrendLifecycleState.RISING,
            TrendLifecycleState.PEAKING,
            TrendLifecycleState.DECLINING,
            TrendLifecycleState.DORMANT,
        },
    }
    return proposed if proposed in allowed[previous] else previous


def _input_hash(
    events: tuple[TrendEventInput, ...],
    context: TrendEvaluationContext,
    previous_states: Mapping[str, PreviousTrendState],
    lineage_evidence: Mapping[str, tuple[str, int]],
) -> str:
    body = json.dumps(
        {
            "context": {
                "evaluated_at": context.evaluated_at.isoformat(),
                "evaluation_id": context.evaluation_id,
                "platform_signals": [
                    {
                        "freshness": signal.freshness.value,
                        "observed_at": signal.observed_at.isoformat(),
                        "platform": signal.platform.value,
                        "status": signal.status.value,
                    }
                    for signal in sorted(
                        context.platform_signals,
                        key=lambda value: value.platform.value,
                    )
                ],
            },
            "events": [
                {
                    "canonical_title": event.canonical_title,
                    "event_id": event.event_id,
                    "fingerprint": event.representative_title_fingerprint,
                    "observations": [
                        {
                            "freshness": item.freshness.value,
                            "group_id": item.group_id,
                            "hot_score": (
                                str(item.hot_score)
                                if item.hot_score is not None
                                else None
                            ),
                            "observed_at": item.observed_at.isoformat(),
                            "platform": item.platform.value,
                            "rank": item.rank,
                        }
                        for item in sorted(
                            event.observations,
                            key=lambda value: value.group_id,
                        )
                    ],
                }
                for event in events
            ],
            "lineage": {
                event_id: {
                    "evidence": list(lineage_evidence.get(event_id, ("new", 0))),
                    "previous": (
                        {
                            "last_fresh_seen_at": (
                                previous_states[event_id].last_fresh_seen_at.isoformat()
                                if previous_states[event_id].last_fresh_seen_at
                                else None
                            ),
                            "source_event_id": previous_states[
                                event_id
                            ].source_event_id,
                            "state": previous_states[event_id].state.value,
                            "trend_series_id": previous_states[
                                event_id
                            ].trend_series_id,
                            "velocity": str(previous_states[event_id].velocity),
                        }
                        if event_id in previous_states
                        else None
                    ),
                }
                for event_id in sorted(event.event_id for event in events)
            },
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def _mean(values) -> Decimal:
    values = tuple(values)
    return sum(values, Decimal(0)) / Decimal(len(values)) if values else Decimal(0)


def _quantize(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_QUANTUM, rounding=ROUND_HALF_UP)


def _identifier(kind: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join((kind, *parts)).encode()).hexdigest()
    return f"{kind}-{digest}"
