"""Authenticated, read-only Phase 8 dashboard API."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.knowledge.weknora import WeKnoraConfig
from app.models.hotspot_v1 import (
    HotspotEventDetailResponse,
    HotspotEventListResponse,
    HotspotOverviewResponse,
    RawHotItemResponse,
)
from app.repositories.hotspot.annotations import AnnotationRepository
from app.repositories.hotspot.dashboard import HotspotDashboardRepository
from app.services.database import db

router = APIRouter()


@router.get("/overview", response_model=HotspotOverviewResponse)
async def get_overview():
    return HotspotDashboardRepository(db).get_overview()


@router.get("/events", response_model=HotspotEventListResponse)
async def list_events(
    q: str | None = Query(default=None, max_length=100),
    platform: Literal["douyin", "weibo", "bilibili", "xiaohongshu"] | None = None,
    lifecycle: Literal[
        "emerging", "rising", "peaking", "declining", "dormant", "recurring"
    ]
    | None = None,
    hospitality_relevance: Literal["relevant", "possibly_relevant", "irrelevant"]
    | None = None,
    data_quality: Literal["complete", "partial"] | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return HotspotDashboardRepository(db).list_events(
        q=q,
        platform=platform,
        lifecycle=lifecycle,
        hospitality_relevance=hospitality_relevance,
        data_quality=data_quality,
        limit=limit,
        offset=offset,
    )


@router.get("/events/{event_id}", response_model=HotspotEventDetailResponse)
async def get_event(event_id: str):
    item = HotspotDashboardRepository(db).get_event(event_id)
    if item is None:
        raise HTTPException(status_code=404, detail="热点事件不存在")
    annotations = AnnotationRepository(db)
    config = WeKnoraConfig.from_env()
    item["annotation"] = annotations.get_latest_for_event(event_id)
    item["knowledge_sync"] = annotations.latest_sync_for_event(event_id)
    item["knowledge_integration"] = {
        "provider": "weknora",
        "configured": config.configured,
        "base_url_configured": bool(config.base_url),
        "api_key_configured": bool(config.api_key),
        "knowledge_base_id_configured": bool(config.knowledge_base_id),
    }
    return item


@router.get("/raw-items/{raw_item_id}", response_model=RawHotItemResponse)
async def get_raw_item(raw_item_id: str):
    item = HotspotDashboardRepository(db).get_raw_item(raw_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="原始热点证据不存在")
    return item
