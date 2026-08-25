"""Phase 5 application service for replayable cross-platform clustering."""

from __future__ import annotations

from dataclasses import dataclass

from app.clustering import (
    ClusteringRules,
    HotspotEventClusterer,
    SemanticBoundaryJudge,
)
from app.domain.hotspot import ClusteringStatus
from app.normalization import NormalizationRules
from app.repositories.hotspot import ClusteringRepository
from app.services.database import db


@dataclass(frozen=True, slots=True)
class ClusteringOutcome:
    state: str
    clustering_run_id: str | None = None
    status: ClusteringStatus | None = None
    input_group_count: int = 0
    candidate_pair_count: int = 0
    event_count: int = 0
    semantic_call_count: int = 0
    error: str | None = None


class HotspotClusteringService:
    def __init__(
        self,
        database=db,
        semantic_judge: SemanticBoundaryJudge | None = None,
    ) -> None:
        self._database = database
        self._semantic_judge = semantic_judge

    async def process_current(self) -> ClusteringOutcome:
        try:
            settings = self._database.get_all_settings()
            normalization_rules = NormalizationRules.from_settings(settings)
            rules = ClusteringRules.from_settings(settings)
            repository = ClusteringRepository(self._database)
            inputs = await repository.load_current_inputs(
                normalization_rule_version=normalization_rules.version,
                normalization_config_hash=normalization_rules.config_hash,
                lookback_hours=rules.lookback_hours,
            )
            if not inputs:
                return ClusteringOutcome(state="no_input")
            batch = await HotspotEventClusterer(
                rules,
                self._semantic_judge,
            ).cluster(
                inputs,
                normalization_config_hash=normalization_rules.config_hash,
            )
            saved = await repository.save_batch(batch)
            return ClusteringOutcome(
                state="processed" if saved else "skipped_unchanged",
                clustering_run_id=batch.clustering_run_id,
                status=batch.status,
                input_group_count=batch.input_group_count,
                candidate_pair_count=batch.candidate_pair_count,
                event_count=len(batch.events),
                semantic_call_count=batch.semantic_call_count,
            )
        except Exception as exc:  # noqa: BLE001 - keep collection scheduler alive
            return ClusteringOutcome(state="failed", error=str(exc))


hotspot_clustering_service = HotspotClusteringService()
