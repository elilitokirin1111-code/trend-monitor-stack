from __future__ import annotations

import asyncio

import pytest

from app.routers import hotspots_v1

from .test_dashboard_repository import _classified_database


@pytest.mark.asyncio
async def test_dashboard_v1_is_protected(client) -> None:
    response = await client.get("/api/v1/hotspots/overview")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_v1_contracts(
    client, admin_token, monkeypatch, tmp_path
) -> None:
    database = await asyncio.to_thread(_classified_database, tmp_path)
    monkeypatch.setattr(hotspots_v1, "db", database)
    headers = {"Authorization": f"Bearer {admin_token}"}

    overview = await client.get("/api/v1/hotspots/overview", headers=headers)
    events = await client.get(
        "/api/v1/hotspots/events?platform=weibo&limit=10", headers=headers
    )

    assert overview.status_code == 200
    assert len(overview.json()["platforms"]) == 4
    assert events.status_code == 200
    payload = events.json()
    assert payload["total"] == 1
    event_id = payload["items"][0]["event_id"]

    detail = await client.get(f"/api/v1/hotspots/events/{event_id}", headers=headers)
    assert detail.status_code == 200
    evidence = detail.json()["evidence"]
    raw = await client.get(evidence[0]["raw_item_url"], headers=headers)
    assert raw.status_code == 200
    assert raw.json()["raw_item_id"] == evidence[0]["raw_item_id"]
    openapi = (await client.get("/openapi.json")).json()
    assert "/api/v1/hotspots/events" in openapi["paths"]
    assert "HotspotEventListResponse" in openapi["components"]["schemas"]


@pytest.mark.asyncio
async def test_dashboard_v1_returns_404_for_unknown_evidence(
    client, admin_token, monkeypatch, tmp_path
) -> None:
    database = await asyncio.to_thread(_classified_database, tmp_path)
    monkeypatch.setattr(hotspots_v1, "db", database)
    headers = {"Authorization": f"Bearer {admin_token}"}

    event = await client.get("/api/v1/hotspots/events/missing-event", headers=headers)
    raw = await client.get("/api/v1/hotspots/raw-items/missing-raw", headers=headers)

    assert event.status_code == 404
    assert raw.status_code == 404
