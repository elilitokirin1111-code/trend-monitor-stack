"""Phase 4 application service for replayable normalization and basic dedup."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.hotspot import NormalizationStatus
from app.normalization import HotspotNormalizer, NormalizationRules
from app.repositories.hotspot import NormalizationRepository
from app.services.database import db


@dataclass(frozen=True, slots=True)
class NormalizationOutcome:
    snapshot_id: str
    state: str
    normalization_run_id: str | None = None
    status: NormalizationStatus | None = None
    total_count: int = 0
    group_count: int = 0
    error: str | None = None


class HotspotNormalizationService:
    def __init__(self, database=db) -> None:
        self._database = database

    async def process_pending(
        self, *, limit: int = 100
    ) -> tuple[NormalizationOutcome, ...]:
        rules = NormalizationRules.from_settings(self._database.get_all_settings())
        repository = NormalizationRepository(self._database)
        snapshot_ids = await repository.list_pending_snapshots(
            rule_version=rules.version,
            config_hash=rules.config_hash,
            limit=limit,
        )
        outcomes = []
        for snapshot_id in snapshot_ids:
            try:
                raw_items = await repository.load_snapshot(snapshot_id)
                batch = HotspotNormalizer(rules).normalize_snapshot(
                    snapshot_id,
                    raw_items,
                )
                saved = await repository.save_batch(batch)
                outcomes.append(
                    NormalizationOutcome(
                        snapshot_id=snapshot_id,
                        state="processed" if saved else "skipped_concurrent",
                        normalization_run_id=(
                            batch.normalization_run_id if saved else None
                        ),
                        status=batch.status if saved else None,
                        total_count=len(batch.items) if saved else 0,
                        group_count=len(batch.groups) if saved else 0,
                    )
                )
            except Exception as exc:  # noqa: BLE001 - isolate one replayable snapshot
                outcomes.append(
                    NormalizationOutcome(
                        snapshot_id=snapshot_id,
                        state="failed",
                        error=str(exc),
                    )
                )
        return tuple(outcomes)


hotspot_normalization_service = HotspotNormalizationService()
