"""Authenticated, read-only Phase 8 dashboard API."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.models.hotspot_v1 import (
    HotspotEventDetailResponse,
    HotspotEventListResponse,
    HotspotOverviewResponse,
    RawHotItemResponse,
)
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
    return item


@router.get("/raw-items/{raw_item_id}", response_model=RawHotItemResponse)
async def get_raw_item(raw_item_id: str):
    item = HotspotDashboardRepository(db).get_raw_item(raw_item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="原始热点证据不存在")
    return item
