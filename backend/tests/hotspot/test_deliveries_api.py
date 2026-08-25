from __future__ import annotations

import asyncio

import httpx
import pytest

from app.delivery.feishu import FeishuDeliveryAdapter
from app.delivery.rules import FeishuDeliveryRules
from app.domain.hotspot import ReportType
from app.routers import hotspot_deliveries, hotspot_reports
from app.services.hotspot_delivery import HotspotDeliveryService
from app.services.hotspot_reports import HotspotReportService

from .test_dashboard_repository import _classified_database


async def _prepared(tmp_path) -> tuple[object, str]:
    database = await asyncio.to_thread(_classified_database, tmp_path)
    database.set_setting(
        "hotspot_feishu_webhook_url",
        "https://open.feishu.cn/open-apis/bot/v2/hook/abc",
    )
    outcome = await HotspotReportService(database).generate(ReportType.DAILY)
    assert outcome.state == "processed"
    return database, outcome.report_run_id


def _mock_transport_service(
    monkeypatch, database, *, handler=None
) -> HotspotDeliveryService:
    monkeypatch.setattr(hotspot_deliveries, "db", database)

    def handler_default(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    transport = httpx.MockTransport(handler or handler_default)
    service = HotspotDeliveryService(
        database,
        adapter_factory=lambda rules: FeishuDeliveryAdapter(
            rules, transport=transport
        ),
    )
    monkeypatch.setattr(
        hotspot_deliveries, "HotspotDeliveryService", lambda db: service
    )
    return service


@pytest.mark.asyncio
async def test_delivery_list_is_protected(client) -> None:
    response = await client.get("/api/v1/hotspots/deliveries")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delivery_api_contracts(client, admin_token, monkeypatch, tmp_path) -> None:
    database, report_run_id = await _prepared(tmp_path)
    monkeypatch.setattr(hotspot_deliveries, "db", database)
    monkeypatch.setattr(hotspot_reports, "db", database)
    _mock_transport_service(monkeypatch, database)
    headers = {"Authorization": f"Bearer {admin_token}"}

    delivered = await client.post(
        f"/api/v1/hotspots/reports/{report_run_id}/deliver",
        headers=headers,
        json={"channel": "feishu"},
    )
    assert delivered.status_code == 200
    body = delivered.json()
    assert body["state"] == "delivered"
    assert body["success_count"] == 1

    listing = await client.get("/api/v1/hotspots/deliveries", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    delivery_id = listing.json()["items"][0]["delivery_id"]

    detail = await client.get(
        f"/api/v1/hotspots/deliveries/{delivery_id}", headers=headers
    )
    assert detail.status_code == 200
    assert detail.json()["status"] == "success"
    assert detail.json()["report_run_id"] == report_run_id

    filtered = await client.get(
        "/api/v1/hotspots/deliveries?status=failed", headers=headers
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 0


@pytest.mark.asyncio
async def test_delivery_actions_require_admin(
    client, user_token, admin_token, monkeypatch, tmp_path
) -> None:
    database, report_run_id = await _prepared(tmp_path)
    monkeypatch.setattr(hotspot_deliveries, "db", database)
    user_headers = {"Authorization": f"Bearer {user_token}"}
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    denied = await client.post(
        f"/api/v1/hotspots/reports/{report_run_id}/deliver",
        headers=user_headers,
        json={},
    )
    assert denied.status_code in (401, 403)

    missing = await client.post(
        "/api/v1/hotspots/reports/missing-report/deliver",
        headers=admin_headers,
        json={},
    )
    assert missing.status_code == 404

    replay_missing = await client.post(
        "/api/v1/hotspots/deliveries/missing/replay", headers=admin_headers
    )
    assert replay_missing.status_code == 404


@pytest.mark.asyncio
async def test_delivery_api_with_mocked_transport(
    client, admin_token, monkeypatch, tmp_path
) -> None:
    """Simulate a failing Feishu upstream through the API and replay it."""
    database, report_run_id = await _prepared(tmp_path)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, json={"code": 9499, "msg": "boom"})
        return httpx.Response(200, json={"code": 0, "msg": "success"})

    _mock_transport_service(monkeypatch, database, handler=handler)
    headers = {"Authorization": f"Bearer {admin_token}"}

    failed = await client.post(
        f"/api/v1/hotspots/reports/{report_run_id}/deliver",
        headers=headers,
        json={},
    )
    assert failed.status_code == 200
    assert failed.json()["state"] == "partial"

    listing = await client.get(
        f"/api/v1/hotspots/deliveries?report_run_id={report_run_id}",
        headers=headers,
    )
    delivery_id = listing.json()["items"][0]["delivery_id"]

    replayed = await client.post(
        f"/api/v1/hotspots/deliveries/{delivery_id}/replay", headers=headers
    )
    assert replayed.status_code == 200
    assert replayed.json()["state"] == "delivered"
