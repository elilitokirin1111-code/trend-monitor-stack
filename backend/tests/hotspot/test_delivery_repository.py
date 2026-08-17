from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.hotspot import DeliveryErrorKind, DeliveryRecord, DeliveryStatus
from app.repositories.hotspot.deliveries import DeliveryRepository
from app.services.database import Database


def _record(
    *,
    delivery_id: str = "delivery-1",
    report_run_id: str = "report-run-1",
    content_version: str = "v" * 64,
    chunk_index: int = 0,
    status: DeliveryStatus = DeliveryStatus.SUCCESS,
    attempt: int = 1,
    created_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> DeliveryRecord:
    created = created_at or datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)
    finished = finished_at or created
    return DeliveryRecord(
        delivery_id=delivery_id,
        report_run_id=report_run_id,
        channel="feishu",
        content_version=content_version,
        chunk_index=chunk_index,
        total_chunks=2,
        status=status,
        attempt=attempt,
        latency_ms=120,
        error_kind=None if status is DeliveryStatus.SUCCESS else DeliveryErrorKind.HTTP_ERROR,
        error_message=None if status is DeliveryStatus.SUCCESS else "http 502",
        response_json='{"code": 0}' if status is DeliveryStatus.SUCCESS else None,
        created_at=created,
        finished_at=finished,
    )


def _database(tmp_path: Path) -> Database:
    return Database(f"sqlite:///{tmp_path / 'deliveries.db'}")


def test_save_and_find_by_idempotency_key(tmp_path: Path) -> None:
    database = _database(tmp_path)
    repository = DeliveryRepository(database)

    asyncio.run(repository.save(_record()))

    found = asyncio.run(
        repository.find(
            report_run_id="report-run-1",
            channel="feishu",
            content_version="v" * 64,
            chunk_index=0,
        )
    )
    assert found is not None
    assert found["delivery_id"] == "delivery-1"
    assert found["status"] == "success"
    assert found["response"] == '{"code": 0}'

    missing = asyncio.run(
        repository.find(
            report_run_id="report-run-1",
            channel="feishu",
            content_version="v" * 64,
            chunk_index=1,
        )
    )
    assert missing is None


def test_save_replaces_same_idempotency_key(tmp_path: Path) -> None:
    database = _database(tmp_path)
    repository = DeliveryRepository(database)

    asyncio.run(repository.save(_record(status=DeliveryStatus.FAILED)))
    asyncio.run(
        repository.save(
            _record(delivery_id="delivery-2", status=DeliveryStatus.SUCCESS)
        )
    )

    with database.get_connection() as connection:
        rows = connection.execute(
            "SELECT delivery_id, status FROM hotspot_report_deliveries"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["delivery_id"] == "delivery-2"
    assert rows[0]["status"] == "success"


def test_list_and_get_deliveries(tmp_path: Path) -> None:
    database = _database(tmp_path)
    repository = DeliveryRepository(database)

    asyncio.run(repository.save(_record(delivery_id="d1", chunk_index=0)))
    asyncio.run(repository.save(_record(delivery_id="d2", chunk_index=1)))
    asyncio.run(
        repository.save(
            _record(
                delivery_id="d3",
                report_run_id="report-run-2",
                chunk_index=0,
                status=DeliveryStatus.FAILED,
            )
        )
    )

    all_deliveries = asyncio.run(repository.list_deliveries(limit=10, offset=0))
    assert all_deliveries["total"] == 3

    filtered = asyncio.run(
        repository.list_deliveries(report_run_id="report-run-1", limit=10, offset=0)
    )
    assert filtered["total"] == 2

    failed = asyncio.run(
        repository.list_deliveries(status="failed", limit=10, offset=0)
    )
    assert failed["total"] == 1
    assert failed["items"][0]["delivery_id"] == "d3"

    detail = asyncio.run(repository.get_delivery("d3"))
    assert detail is not None
    assert detail["error_kind"] == "http_error"
    assert detail["error_message"] == "http 502"
    assert asyncio.run(repository.get_delivery("missing")) is None


def test_delivery_record_validates_chunk_and_time(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _record(chunk_index=2)  # >= total_chunks
    with pytest.raises(ValueError):
        _record(
            created_at=datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc),
            finished_at=datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc),
        )
