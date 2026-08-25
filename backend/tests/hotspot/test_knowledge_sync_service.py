from __future__ import annotations

import asyncio

import pytest

from app.knowledge.service import (
    AnnotationRequiredError,
    KnowledgeSyncService,
    render_event_markdown,
)
from app.knowledge.weknora import WeKnoraConfig, WeKnoraError
from app.repositories.hotspot.annotations import AnnotationRepository
from app.repositories.hotspot.dashboard import HotspotDashboardRepository

from .test_dashboard_repository import _classified_database


class _Client:
    def __init__(self) -> None:
        self.created = []
        self.updated = []
        self.searches = []

    async def create_manual_knowledge(self, *, title, content):
        self.created.append((title, content))
        return {
            "success": True,
            "data": {"id": "knowledge-1", "parse_status": "processing"},
        }

    async def update_manual_knowledge(self, *, knowledge_id, title, content):
        self.updated.append((knowledge_id, title, content))
        return {
            "success": True,
            "data": {"id": knowledge_id, "parse_status": "processing"},
        }

    async def search(self, *, query, match_count):
        self.searches.append((query, match_count))
        return [
            {
                "id": "chunk-1",
                "content": "门店应提前检查退改政策。",
                "knowledge_id": "knowledge-old",
                "knowledge_title": "台风应急预案",
                "score": 0.88,
                "chunk_index": 2,
                "knowledge_source": "manual",
                "metadata": {"owner": "operations"},
            }
        ]


class _MissingIdClient(_Client):
    async def create_manual_knowledge(self, *, title, content):
        self.created.append((title, content))
        return {"success": True, "data": {"parse_status": "processing"}}


def _config() -> WeKnoraConfig:
    return WeKnoraConfig(
        base_url="http://weknora.local",
        api_key="key",
        knowledge_base_id="kb-1",
    )


def _event_id(database) -> str:
    return HotspotDashboardRepository(database).list_events(limit=10, offset=0)[
        "items"
    ][0]["event_id"]


def _annotate(database, event_id: str, *, summary: str):
    return AnnotationRepository(database).save_annotation(
        event_id=event_id,
        review_status="reviewed",
        topic_category="酒旅风险",
        tags=["台风", "酒店运营"],
        hospitality_relevance="relevant",
        decision_lane="risk_watch",
        notes="检查门店预案。",
        summary_override=summary,
        updated_by="reviewer",
    )


def test_only_annotated_event_syncs_and_same_revision_is_idempotent(tmp_path) -> None:
    database = _classified_database(tmp_path)
    event_id = _event_id(database)
    client = _Client()
    service = KnowledgeSyncService(database, config=_config(), client=client)

    with pytest.raises(AnnotationRequiredError):
        asyncio.run(service.sync_event(event_id))

    _annotate(database, event_id, summary="台风影响酒旅门店。")
    first, first_skipped = asyncio.run(service.sync_event(event_id))
    second, second_skipped = asyncio.run(service.sync_event(event_id))

    assert first["status"] == "success"
    assert first["operation"] == "create"
    assert first_skipped is False
    assert second == first
    assert second_skipped is True
    assert len(client.created) == 1
    assert "## 原始证据" in client.created[0][1]
    assert "https://" in client.created[0][1]


def test_create_without_remote_knowledge_id_is_recorded_as_failed(tmp_path) -> None:
    database = _classified_database(tmp_path)
    event_id = _event_id(database)
    _annotate(database, event_id, summary="人工确认摘要")
    service = KnowledgeSyncService(
        database, config=_config(), client=_MissingIdClient()
    )

    with pytest.raises(WeKnoraError, match="knowledge ID"):
        asyncio.run(service.sync_event(event_id))

    latest = AnnotationRepository(database).latest_sync_for_event(event_id)
    assert latest is not None
    assert latest["status"] == "failed"
    assert latest["error_kind"] == "invalid_response"


def test_new_annotation_updates_existing_knowledge_and_can_search_it(tmp_path) -> None:
    database = _classified_database(tmp_path)
    event_id = _event_id(database)
    client = _Client()
    service = KnowledgeSyncService(database, config=_config(), client=client)
    _annotate(database, event_id, summary="第一版")
    asyncio.run(service.sync_event(event_id))
    _annotate(database, event_id, summary="第二版")

    sync, skipped = asyncio.run(service.sync_event(event_id))
    result = asyncio.run(service.search_event(event_id, query=None, match_count=4))

    assert skipped is False
    assert sync["operation"] == "update"
    assert client.updated[0][0] == "knowledge-1"
    assert "第二版" in client.updated[0][2]
    assert result["hits"][0]["knowledge_title"] == "台风应急预案"
    assert result["hits"][0]["score"] == 0.88
    assert client.searches == [("台风登陆广东 台风 酒店运营 酒旅风险", 4)]


def test_markdown_keeps_ai_and_human_judgement_separate(tmp_path) -> None:
    database = _classified_database(tmp_path)
    event_id = _event_id(database)
    annotation = _annotate(database, event_id, summary="人工确认摘要")
    event = HotspotDashboardRepository(database).get_event(event_id)

    title, content = render_event_markdown(event, annotation)

    assert title.startswith("热点情报：")
    assert "## 人工研判" in content
    assert "## AI 研判（未覆盖人工结论）" in content
    assert "人工确认摘要" in content
