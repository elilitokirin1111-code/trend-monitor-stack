"""Authenticated V1 delivery API: inspect, deliver and replay reports."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.middleware.auth import require_admin, require_auth
from app.repositories.hotspot.deliveries import DeliveryRepository
from app.services.database import db
from app.services.hotspot_delivery import HotspotDeliveryService

router = APIRouter()


class DeliverRequest(BaseModel):
    channel: str = "feishu"
    force: bool = False


class DeliveryActionResponse(BaseModel):
    state: str
    delivery_id: str | None = None
    report_run_id: str | None = None
    chunk_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    error: str | None = None


@router.get("/deliveries", response_model=dict)
async def list_deliveries(
    report_run_id: str | None = Query(default=None, max_length=200),
    status: Literal["success", "failed", "pending"] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(require_auth),
):
    return await DeliveryRepository(db).list_deliveries(
        report_run_id=report_run_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.get("/deliveries/{delivery_id}", response_model=dict)
async def get_delivery(delivery_id: str, user=Depends(require_auth)):
    item = await DeliveryRepository(db).get_delivery(delivery_id)
    if item is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    return item


@router.post(
    "/reports/{report_run_id}/deliver",
    response_model=DeliveryActionResponse,
)
async def deliver_report(
    report_run_id: str,
    payload: DeliverRequest | None = None,
    user=Depends(require_admin),
):
    payload = payload or DeliverRequest()
    outcome = await HotspotDeliveryService(db).deliver_report(
        report_run_id,
        channel=payload.channel,
        force=payload.force,
    )
    if outcome.state in {"no_report"}:
        raise HTTPException(status_code=404, detail="报告不存在")
    return DeliveryActionResponse(
        state=outcome.state,
        report_run_id=outcome.report_run_id,
        chunk_count=outcome.chunk_count,
        success_count=outcome.success_count,
        failed_count=outcome.failed_count,
        skipped_count=outcome.skipped_count,
        error=outcome.error,
    )


@router.post(
    "/deliveries/{delivery_id}/replay",
    response_model=DeliveryActionResponse,
)
async def replay_delivery(delivery_id: str, user=Depends(require_admin)):
    outcome = await HotspotDeliveryService(db).replay_delivery(delivery_id)
    if outcome.state == "no_delivery":
        raise HTTPException(status_code=404, detail="投递记录不存在")
    return DeliveryActionResponse(
        state=outcome.state,
        delivery_id=outcome.delivery_id,
        report_run_id=outcome.report_run_id,
        error=outcome.error,
    )
