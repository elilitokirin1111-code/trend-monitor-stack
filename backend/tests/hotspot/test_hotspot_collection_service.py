from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from app.domain.hotspot import Platform
from app.repositories.hotspot import HotspotRepository
from app.services.database import Database
from app.services.hotspot_collection import HotspotCollectionService

from .test_hotspot_repository import _result


def test_collection_service_skips_an_existing_window_without_live_call(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'service.db'}")
    repository = HotspotRepository(database)
    asyncio.run(repository.save_collection(_result()))
    service = HotspotCollectionService(
        database,
        clock=lambda: datetime(2026, 8, 14, 8, 9, tzinfo=timezone.utc),
        owner_id="test-worker",
    )

    outcomes = asyncio.run(service.collect_all((Platform.WEIBO,)))

    assert len(outcomes) == 1
    assert outcomes[0].state == "skipped_existing"
    assert outcomes[0].run_id is None


def test_invalid_database_interval_falls_back_to_config_default(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'settings.db'}")
    database.set_setting("hotspot_collection_interval_minutes", "invalid")

    service = HotspotCollectionService(database)

    assert service.get_interval_minutes() == 30
