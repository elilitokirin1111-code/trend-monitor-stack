from __future__ import annotations

import asyncio

from app.services import scheduler as scheduler_module


class _FakeDatabase:
    @staticmethod
    def get_setting(key: str):
        return None


class _FakeHotspotService:
    def __init__(self) -> None:
        self.initialized = False
        self.calls = 0

    @staticmethod
    def get_interval_minutes() -> int:
        return 30

    def initialize_storage(self) -> tuple[int, ...]:
        self.initialized = True
        return (1,)

    async def collect_all(self):
        self.calls += 1
        return ()


class _FakeNormalizationService:
    def __init__(self) -> None:
        self.calls = 0

    async def process_pending(self):
        self.calls += 1
        return ()


def test_scheduler_registers_single_instance_thirty_minute_job(monkeypatch) -> None:
    fake_hotspot = _FakeHotspotService()
    fake_normalization = _FakeNormalizationService()
    monkeypatch.setattr(scheduler_module, "db", _FakeDatabase())
    monkeypatch.setattr(scheduler_module, "hotspot_collection_service", fake_hotspot)
    monkeypatch.setattr(
        scheduler_module,
        "hotspot_normalization_service",
        fake_normalization,
    )
    service = scheduler_module.SchedulerService()

    async def exercise() -> None:
        service.start()
        job = service.scheduler.get_job("hotspot_collect_v2")
        assert job is not None
        assert job.max_instances == 1
        assert job.coalesce is True
        assert job.misfire_grace_time == 1800
        assert job.trigger.interval.total_seconds() == 1800
        service.stop()

    asyncio.run(exercise())
    assert fake_hotspot.initialized is True


def test_manual_trigger_uses_same_hotspot_job(monkeypatch) -> None:
    fake_hotspot = _FakeHotspotService()
    fake_normalization = _FakeNormalizationService()
    monkeypatch.setattr(scheduler_module, "hotspot_collection_service", fake_hotspot)
    monkeypatch.setattr(
        scheduler_module,
        "hotspot_normalization_service",
        fake_normalization,
    )
    service = scheduler_module.SchedulerService()

    assert asyncio.run(service.trigger_hotspot_collection()) == ()
    assert fake_hotspot.calls == 1
    assert fake_normalization.calls == 1
