"""Phase 7 application service for auditable AI classification."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from app.classification import (
    ClassificationEngine,
    ClassificationProvider,
    ClassificationRules,
    LiteLLMClassificationProvider,
    classification_input_hash,
    classification_run_id,
)
from app.domain.hotspot import ClassificationRunStatus, ClassificationStatus
from app.repositories.hotspot import ClassificationRepository
from app.services.database import db


@dataclass(frozen=True, slots=True)
class ClassificationOutcome:
    state: str
    classification_run_id: str | None = None
    status: ClassificationRunStatus | None = None
    event_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error: str | None = None


class HotspotClassificationService:
    def __init__(self, database=db, *, provider: ClassificationProvider | None = None):
        self._database = database
        self._provider = provider

    async def process_current(self) -> ClassificationOutcome:
        try:
            rules = ClassificationRules.from_settings(self._database.get_all_settings())
            repository = ClassificationRepository(self._database)
            source = await repository.load_current_input()
            if source is None or not source.items:
                return ClassificationOutcome(state="no_input")
            input_hash = classification_input_hash(source.items)
            run_id = classification_run_id(
                source.source_trend_run_id, rules, input_hash
            )
            if await repository.run_exists(run_id):
                return ClassificationOutcome(
                    state="skipped_unchanged", classification_run_id=run_id
                )
            provider = self._provider
            if provider is None and rules.enabled and rules.api_key:
                provider = LiteLLMClassificationProvider(
                    api_key=rules.api_key,
                    base_url=rules.base_url,
                )
            batch = await ClassificationEngine(rules, provider).classify(
                source.items,
                source_trend_run_id=source.source_trend_run_id,
            )
            saved = await repository.save_batch(batch)
            counts = Counter(record.status for record in batch.records)
            return ClassificationOutcome(
                state="processed" if saved else "skipped_unchanged",
                classification_run_id=batch.classification_run_id,
                status=batch.status,
                event_count=len(batch.records),
                success_count=counts[ClassificationStatus.SUCCESS],
                failed_count=counts[ClassificationStatus.FAILED],
                skipped_count=counts[ClassificationStatus.SKIPPED],
            )
        except Exception as exc:  # noqa: BLE001 - preserve scheduler progress
            return ClassificationOutcome(state="failed", error=str(exc))


hotspot_classification_service = HotspotClassificationService()
