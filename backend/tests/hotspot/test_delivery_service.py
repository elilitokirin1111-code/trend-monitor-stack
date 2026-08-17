from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from app.delivery.feishu import FeishuDeliveryAdapter
from app.delivery.rules import FeishuDeliveryRules
from app.domain.hotspot import ReportType
from app.services.hotspot_delivery import HotspotDeliveryService
from app.services.hotspot_reports import HotspotReportService

from .test_dashboard_repository import _classified_database


def _ok_response_handler():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    return handler


def _service(database, *, handler=None):
    transport = httpx.MockTransport(handler or _ok_response_handler())
    return HotspotDeliveryService(
        database,
        adapter_factory=lambda r: FeishuDeliveryAdapter(r, transport=transport),
    )


def _prepared_report(tmp_path: Path) -> tuple[object, str]:
    database = _classified_database(tmp_path)
    outcome = asyncio.run(HotspotReportService(database).generate(ReportType.DAILY))
    assert outcome.state == "processed"
    return database, outcome.report_run_id


def test_deliver_report_success_records_idempotent_delivery(tmp_path: Path) -> None:
    database, report_run_id = _prepared_report(tmp_path)
    database.set_setting(
        "hotspot_feishu_webhook_url",
        "https://open.feishu.cn/open-apis/bot/v2/hook/abc",
    )
    service = _service(database)

    first = asyncio.run(service.deliver_report(report_run_id))
    second = asyncio.run(service.deliver_report(report_run_id))

    assert first.state == "delivered"
    assert first.success_count == 1
    assert second.state == "skipped"
    assert second.skipped_count == 1
    with database.get_connection() as connection:
        rows = connection.execute(
            "SELECT status, attempt, chunk_index FROM hotspot_report_deliveries"
        ).fetchall()
    assert len(rows) == 1
    assert rows[0]["status"] == "success"
    assert rows[0]["attempt"] == 1


def test_deliver_report_force_redelivers(tmp_path: Path) -> None:
    database, report_run_id = _prepared_report(tmp_path)
    database.set_setting(
        "hotspot_feishu_webhook_url",
        "https://open.feishu.cn/open-apis/bot/v2/hook/abc",
    )
    service = _service(database)

    asyncio.run(service.deliver_report(report_run_id))
    forced = asyncio.run(
        service.deliver_report(report_run_id, force=True)
    )

    assert forced.state == "delivered"
    with database.get_connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM hotspot_report_deliveries"
            ).fetchone()[0]
            == 1
        )


def test_deliver_report_failure_triggers_alert_and_records_error(
    tmp_path: Path,
) -> None:
    alert_calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 9499, "msg": "invalid sign"})

    def alert_handler(request: httpx.Request) -> httpx.Response:
        alert_calls.append(str(request.url))
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    database, report_run_id = _prepared_report(tmp_path)
    database.set_setting(
        "hotspot_feishu_webhook_url",
        "https://open.feishu.cn/open-apis/bot/v2/hook/abc",
    )
    database.set_setting(
        "hotspot_delivery_alert_webhook",
        "https://open.feishu.cn/alert?token=x",
    )
    transport = httpx.MockTransport(handler)
    alert_transport = httpx.MockTransport(alert_handler)
    service = HotspotDeliveryService(
        database,
        adapter_factory=lambda r: FeishuDeliveryAdapter(
            r, transport=transport, alert_transport=alert_transport
        ),
    )

    outcome = asyncio.run(service.deliver_report(report_run_id))

    assert outcome.state == "partial"
    assert outcome.failed_count == 1
    assert alert_calls == ["https://open.feishu.cn/alert?token=x"]
    with database.get_connection() as connection:
        row = connection.execute(
            "SELECT status, error_kind, error_message FROM hotspot_report_deliveries"
        ).fetchone()
    assert row["status"] == "failed"
    assert row["error_kind"] == "business_error"
    assert "9499" in row["error_message"]


def test_deliver_report_not_configured(tmp_path: Path) -> None:
    database, report_run_id = _prepared_report(tmp_path)

    outcome = asyncio.run(_service(database).deliver_report(report_run_id))

    assert outcome.state == "not_configured"


def test_deliver_report_missing_report(tmp_path: Path) -> None:
    database = _classified_database(tmp_path)

    outcome = asyncio.run(
        _service(database).deliver_report("missing-report")
    )

    assert outcome.state == "no_report"


def test_replay_failed_delivery_recovers(tmp_path: Path) -> None:
    database, report_run_id = _prepared_report(tmp_path)
    database.set_setting(
        "hotspot_feishu_webhook_url",
        "https://open.feishu.cn/open-apis/bot/v2/hook/abc",
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"code": 9499, "msg": "boom"})
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    service = _service(database, handler=handler)
    failed = asyncio.run(service.deliver_report(report_run_id))
    assert failed.failed_count == 1
    with database.get_connection() as connection:
        delivery_id = connection.execute(
            "SELECT delivery_id FROM hotspot_report_deliveries"
        ).fetchone()["delivery_id"]

    replayed = asyncio.run(service.replay_delivery(delivery_id))

    assert replayed.state == "delivered"
    with database.get_connection() as connection:
        row = connection.execute(
            "SELECT status, attempt FROM hotspot_report_deliveries"
        ).fetchone()
    assert row["status"] == "success"
    assert row["attempt"] == 1


def test_replay_missing_delivery(tmp_path: Path) -> None:
    database = _classified_database(tmp_path)

    outcome = asyncio.run(_service(database).replay_delivery("missing"))

    assert outcome.state == "no_delivery"
