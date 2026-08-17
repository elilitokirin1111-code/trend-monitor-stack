from __future__ import annotations

import asyncio

import pytest

from app.domain.hotspot import ReportType
from app.routers import hotspot_reports
from app.services.hotspot_reports import HotspotReportService

from .test_dashboard_repository import _classified_database


@pytest.mark.asyncio
async def test_report_list_is_protected(client) -> None:
    response = await client.get("/api/v1/hotspots/reports")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_report_api_contracts(client, admin_token, monkeypatch, tmp_path) -> None:
    database = await asyncio.to_thread(_classified_database, tmp_path)
    monkeypatch.setattr(hotspot_reports, "db", database)
    headers = {"Authorization": f"Bearer {admin_token}"}

    outcome = await HotspotReportService(database).generate(ReportType.DAILY)
    assert outcome.state == "processed"

    listing = await client.get("/api/v1/hotspots/reports", headers=headers)
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["total"] == 1
    report_run_id = payload["items"][0]["report_run_id"]

    detail = await client.get(
        f"/api/v1/hotspots/reports/{report_run_id}", headers=headers
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["report_type"] == "daily"
    assert body["content"].startswith("# 热点日报")
    assert body["source_trend_run_id"]

    filtered = await client.get(
        "/api/v1/hotspots/reports?report_type=weekly", headers=headers
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 0


@pytest.mark.asyncio
async def test_report_api_regenerate_requires_admin(
    client, user_token, admin_token, monkeypatch, tmp_path
) -> None:
    database = await asyncio.to_thread(_classified_database, tmp_path)
    monkeypatch.setattr(hotspot_reports, "db", database)

    user_headers = {"Authorization": f"Bearer {user_token}"}
    denied = await client.post(
        "/api/v1/hotspots/reports/daily/regenerate", headers=user_headers
    )
    assert denied.status_code in (401, 403)

    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    accepted = await client.post(
        "/api/v1/hotspots/reports/daily/regenerate",
        headers=admin_headers,
        json={"force": True},
    )
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["state"] == "processed"
    assert body["report_run_id"]

    empty = await client.post(
        "/api/v1/hotspots/reports/daily/regenerate",
        headers=admin_headers,
        json={"period_start": "2026-08-01T00:00:00+08:00"},
    )
    assert empty.status_code == 200
    assert empty.json()["state"] in ("processed", "no_input")


@pytest.mark.asyncio
async def test_report_api_returns_404_for_unknown_run(
    client, admin_token, monkeypatch, tmp_path
) -> None:
    database = await asyncio.to_thread(_classified_database, tmp_path)
    monkeypatch.setattr(hotspot_reports, "db", database)
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.get(
        "/api/v1/hotspots/reports/missing-report", headers=headers
    )
    assert response.status_code == 404
