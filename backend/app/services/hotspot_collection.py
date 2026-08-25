"""Phase 3 application service: one idempotent collection per platform/window."""

from __future__ import annotations

import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from app.collectors import CollectorPolicy, HotspotCollector
from app.config import settings
from app.domain.hotspot import (
    CollectionStatus,
    CollectRequest,
    Platform,
    SnapshotWindow,
    snapshot_window_for,
    utc_now,
)
from app.providers.hotspot import (
    ProviderRuntimeConfig,
    build_provider_registry,
    settings_with_default_provider_order,
)
from app.repositories.hotspot import HotspotMigrationRunner, HotspotRepository
from app.services.database import db


@dataclass(frozen=True, slots=True)
class WindowCollectionOutcome:
    platform: Platform
    window: SnapshotWindow
    state: str
    run_id: str | None = None
    error_code: str | None = None


class HotspotCollectionService:
    def __init__(
        self,
        database=db,
        *,
        clock: Callable[[], datetime] = utc_now,
        owner_id: str | None = None,
    ) -> None:
        self._database = database
        self._clock = clock
        self._owner_id = owner_id or f"{socket.gethostname()}:{uuid4()}"

    def initialize_storage(self) -> tuple[int, ...]:
        return HotspotMigrationRunner(self._database).apply()

    def get_interval_minutes(self) -> int:
        raw = self._database.get_setting("hotspot_collection_interval_minutes")
        if raw is None:
            return settings.hotspot_collection_interval_minutes
        try:
            interval = int(raw)
        except ValueError:
            return settings.hotspot_collection_interval_minutes
        if not 1 <= interval <= 1440:
            return settings.hotspot_collection_interval_minutes
        return interval

    async def collect_all(
        self,
        platforms: tuple[Platform, ...] = tuple(Platform),
    ) -> tuple[WindowCollectionOutcome, ...]:
        interval = self.get_interval_minutes()
        now = self._clock()
        repository = HotspotRepository(
            self._database,
            interval_minutes=interval,
        )
        runtime_settings = settings_with_default_provider_order(
            self._database.get_all_settings()
        )
        registry = build_provider_registry(
            ProviderRuntimeConfig.from_settings(runtime_settings)
        )
        policy = CollectorPolicy.from_settings(runtime_settings)
        outcomes = []
        for platform in platforms:
            window = snapshot_window_for(platform, now, interval)
            outcomes.append(
                await self._collect_window(
                    repository=repository,
                    registry=registry,
                    policy=policy,
                    window=window,
                    requested_at=now,
                )
            )
        return tuple(outcomes)

    async def _collect_window(
        self,
        *,
        repository: HotspotRepository,
        registry,
        policy: CollectorPolicy,
        window: SnapshotWindow,
        requested_at: datetime,
    ) -> WindowCollectionOutcome:
        if await repository.snapshot_exists(window):
            return WindowCollectionOutcome(window.platform, window, "skipped_existing")

        acquired = await repository.try_acquire_lock(
            window,
            self._owner_id,
            ttl_seconds=max(window.interval_minutes * 60, 300),
            now=requested_at,
        )
        if not acquired:
            return WindowCollectionOutcome(window.platform, window, "skipped_locked")

        try:
            if await repository.snapshot_exists(window):
                return WindowCollectionOutcome(
                    window.platform, window, "skipped_existing"
                )
            collector = HotspotCollector(
                registry=registry,
                policy=policy,
                writer=repository.writer_for(window),
                stale_reader=repository,
            )
            result = await collector.collect(
                CollectRequest(platform=window.platform, requested_at=requested_at)
            )
            return WindowCollectionOutcome(
                platform=window.platform,
                window=window,
                state=(
                    "failed"
                    if result.status is CollectionStatus.FAILED
                    else "collected"
                ),
                run_id=result.run_id,
                error_code=result.error.code if result.error else None,
            )
        finally:
            await repository.release_lock(window, self._owner_id)


hotspot_collection_service = HotspotCollectionService()
