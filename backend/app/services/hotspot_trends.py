"""Phase 6 service for replayable, versioned hotspot lifecycle evaluation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from app.domain.hotspot import TrendLifecycleState, TrendRunStatus
from app.repositories.hotspot import StoredPreviousTrend, TrendRepository
from app.services.database import db
from app.trends_v1 import TrendLifecycleEngine, TrendRules


@dataclass(frozen=True, slots=True)
class TrendOutcome:
    state: str
    trend_run_id: str | None = None
    status: TrendRunStatus | None = None
    event_count: int = 0
    lifecycle_counts: dict[TrendLifecycleState, int] = field(default_factory=dict)
    error: str | None = None


class HotspotTrendService:
    def __init__(self, database=db) -> None:
        self._database = database

    async def process_current(self) -> TrendOutcome:
        try:
            rules = TrendRules.from_settings(self._database.get_all_settings())
            repository = TrendRepository(self._database)
            source = await repository.load_current_input()
            if source is None or not source.events:
                return TrendOutcome(state="no_input")
            previous = await repository.load_previous_trends(
                algorithm_version=rules.algorithm_version,
                config_hash=rules.config_hash,
                evaluated_before=source.context.evaluated_at,
            )
            previous_states, evidence = _match_lineage(source.events, previous)
            batch = TrendLifecycleEngine(rules).analyze(
                source.events,
                source.context,
                previous_states=previous_states,
                lineage_evidence=evidence,
            )
            saved = await repository.save_batch(batch)
            return TrendOutcome(
                state="processed" if saved else "skipped_unchanged",
                trend_run_id=batch.trend_run_id,
                status=batch.status,
                event_count=len(batch.states),
                lifecycle_counts=dict(Counter(item.state for item in batch.states)),
            )
        except Exception as exc:  # noqa: BLE001 - preserve scheduler progress
            return TrendOutcome(state="failed", error=str(exc))


def _match_lineage(events, previous: tuple[StoredPreviousTrend, ...]):
    previous_states = {}
    evidence = {}
    used_previous: set[str] = set()
    event_groups = {
        event.event_id: {item.group_id for item in event.observations}
        for event in events
    }
    overlap_candidates = []
    for event in events:
        for stored in previous:
            overlap = len(event_groups[event.event_id] & stored.group_ids)
            if overlap:
                overlap_candidates.append(
                    (-overlap, event.event_id, stored.state.source_event_id, stored)
                )
    matched_events: set[str] = set()
    for negative_overlap, event_id, previous_event_id, stored in sorted(
        overlap_candidates,
        key=lambda value: (value[0], value[1], value[2]),
    ):
        if event_id in matched_events or previous_event_id in used_previous:
            continue
        previous_states[event_id] = stored.state
        evidence[event_id] = ("group_overlap", -negative_overlap)
        matched_events.add(event_id)
        used_previous.add(previous_event_id)

    unmatched_previous_by_fingerprint = {}
    for stored in previous:
        if stored.state.source_event_id in used_previous:
            continue
        unmatched_previous_by_fingerprint.setdefault(
            stored.representative_title_fingerprint, []
        ).append(stored)
    for event in sorted(events, key=lambda value: value.event_id):
        if event.event_id in matched_events:
            continue
        matches = unmatched_previous_by_fingerprint.get(
            event.representative_title_fingerprint, []
        )
        matches = [
            stored
            for stored in matches
            if stored.state.source_event_id not in used_previous
        ]
        if len(matches) != 1:
            continue
        stored = matches[0]
        previous_states[event.event_id] = stored.state
        evidence[event.event_id] = ("exact_fingerprint", 0)
        used_previous.add(stored.state.source_event_id)
    return previous_states, evidence


hotspot_trend_service = HotspotTrendService()
