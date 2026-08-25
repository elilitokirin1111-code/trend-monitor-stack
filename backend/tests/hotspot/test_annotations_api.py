from __future__ import annotations

import asyncio

import pytest

from app.routers import hotspot_annotations, hotspots_v1
from app.repositories.hotspot.dashboard import HotspotDashboardRepository

from .test_dashboard_repository import _classified_database


@pytest.mark.asyncio
async def test_annotation_write_requires_auth(client) -> None:
    response = await client.put(
        "/api/v1/hotspots/events/missing/annotation",
        json={"review_status": "reviewed"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_annotation_is_visible_in_detail_and_sync_fails_closed_without_config(
    client, admin_token, monkeypatch, tmp_path
) -> None:
    database = await asyncio.to_thread(_classified_database, tmp_path)
    monkeypatch.setattr(hotspot_annotations, "db", database)
    monkeypatch.setattr(hotspots_v1, "db", database)
    for name in (
        "WEKNORA_BASE_URL",
        "WEKNORA_API_KEY",
        "WEKNORA_KNOWLEDGE_BASE_ID",
    ):
        monkeypatch.delenv(name, raising=False)

    event_id = HotspotDashboardRepository(database).list_events(limit=1, offset=0)[
        "items"
    ][0]["event_id"]
    headers = {"Authorization": f"Bearer {admin_token}"}
    saved = await client.put(
        f"/api/v1/hotspots/events/{event_id}/annotation",
        headers=headers,
        json={
            "review_status": "reviewed",
            "topic_category": "酒旅风险",
            "tags": ["台风", "酒店运营"],
            "hospitality_relevance": "relevant",
            "decision_lane": "risk_watch",
            "notes": "关注退改与住客安全。",
        },
    )
    detail = await client.get(
        f"/api/v1/hotspots/events/{event_id}", headers=headers
    )
    sync = await client.post(
        f"/api/v1/hotspots/events/{event_id}/knowledge/sync", headers=headers
    )

    assert saved.status_code == 200
    assert saved.json()["revision"] == 1
    assert saved.json()["updated_by"] == "admin"
    assert detail.status_code == 200
    assert detail.json()["annotation"]["topic_category"] == "酒旅风险"
    assert detail.json()["knowledge_integration"]["configured"] is False
    assert sync.status_code == 503
    assert "WeKnora 未配置" in sync.json()["detail"]


@pytest.mark.asyncio
async def test_knowledge_sync_requires_a_human_annotation(
    client, admin_token, monkeypatch, tmp_path
) -> None:
    database = await asyncio.to_thread(_classified_database, tmp_path)
    monkeypatch.setattr(hotspot_annotations, "db", database)
    monkeypatch.setenv("WEKNORA_BASE_URL", "https://weknora.example")
    monkeypatch.setenv("WEKNORA_API_KEY", "secret-test-key")
    monkeypatch.setenv("WEKNORA_KNOWLEDGE_BASE_ID", "kb-1")
    event_id = HotspotDashboardRepository(database).list_events(limit=1, offset=0)[
        "items"
    ][0]["event_id"]

    response = await client.post(
        f"/api/v1/hotspots/events/{event_id}/knowledge/sync",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert response.status_code == 409
    assert "先保存人工标记" in response.json()["detail"]
