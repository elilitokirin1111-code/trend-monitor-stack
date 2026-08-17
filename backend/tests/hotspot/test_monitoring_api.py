from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest

from app.routers import hotspot_monitoring
from app.services.hotspot_monitoring import HotspotMonitoringService

from .test_dashboard_repository import _classified_database
from .test_hotspot_repository import AT


@pytest.mark.asyncio
async def test_metrics_endpoint_is_public_and_prometheus_style(client) -> None:
    response = await client.get("/api/v1/hotspots/monitoring/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert isinstance(response.text, str)


@pytest.mark.asyncio
async def test_summary_and_alerts_require_auth(client) -> None:
    summary = await client.get("/api/v1/hotspots/monitoring/summary")
    alerts = await client.get("/api/v1/hotspots/monitoring/alerts")
    health = await client.get("/api/v1/hotspots/monitoring/health")

    assert summary.status_code == 401
    assert alerts.status_code == 401
    assert health.status_code == 401


@pytest.mark.asyncio
async def test_monitoring_api_contracts(
    client, admin_token, monkeypatch, tmp_path
) -> None:
    database = await asyncio.to_thread(_classified_database, tmp_path)
    monkeypatch.setattr(
        hotspot_monitoring,
        "hotspot_monitoring_service",
        HotspotMonitoringService(database, as_of=AT + timedelta(hours=6)),
    )
    headers = {"Authorization": f"Bearer {admin_token}"}

    summary = await client.get(
        "/api/v1/hotspots/monitoring/summary", headers=headers
    )
    assert summary.status_code == 200
    body = summary.json()
    assert set(body) == {"as_of", "window_hours", "provider", "collection", "pipeline"}
    assert body["provider"]["items"]

    alerts = await client.get(
        "/api/v1/hotspots/monitoring/alerts", headers=headers
    )
    assert alerts.status_code == 200
    assert alerts.json()["state"] == "checked"

    health = await client.get(
        "/api/v1/hotspots/monitoring/health", headers=headers
    )
    assert health.status_code == 200
    assert health.json()["database"] == "ok"
    assert health.json()["has_data"] is True


@pytest.mark.asyncio
async def test_monitoring_alerts_respect_thresholds(
    client, admin_token, monkeypatch, tmp_path
) -> None:
    database = await asyncio.to_thread(_classified_database, tmp_path)
    # 提高 stale 阈值使现有数据不再触发告警
    database.set_setting("hotspot_alerts_enabled", "true")
    database.set_setting("hotspot_alert_max_stale_minutes", "100000")
    monkeypatch.setattr(
        hotspot_monitoring,
        "hotspot_monitoring_service",
        HotspotMonitoringService(database, as_of=AT + timedelta(hours=6)),
    )
    headers = {"Authorization": f"Bearer {admin_token}"}

    response = await client.get(
        "/api/v1/hotspots/monitoring/alerts", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["state"] == "checked"
