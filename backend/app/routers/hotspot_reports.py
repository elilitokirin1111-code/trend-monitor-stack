"""Authenticated V1 report API: list, inspect and regenerate reports."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.domain.hotspot import ReportType
from app.middleware.auth import require_admin, require_auth
from app.repositories.hotspot.reports import ReportRepository
from app.services.database import db
from app.services.hotspot_reports import HotspotReportService

router = APIRouter()


class ReportRegenerateRequest(BaseModel):
    period_start: datetime | None = None
    force: bool = False


class ReportRegenerateResponse(BaseModel):
    state: str
    report_run_id: str | None = None
    status: str | None = None
    data_quality: str | None = None
    item_count: int = 0
    error: str | None = None


@router.get("/reports", response_model=dict)
async def list_reports(
    report_type: Literal["daily", "weekly"] | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user=Depends(require_auth),
):
    report_type_enum = ReportType(report_type) if report_type else None
    return await ReportRepository(db).list_runs(
        report_type=report_type_enum, limit=limit, offset=offset
    )


@router.get("/reports/{report_run_id}", response_model=dict)
async def get_report(report_run_id: str, user=Depends(require_auth)):
    item = await ReportRepository(db).get_run(report_run_id)
    if item is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return item


@router.post(
    "/reports/{report_type}/regenerate",
    response_model=ReportRegenerateResponse,
)
async def regenerate_report(
    report_type: Literal["daily", "weekly"],
    payload: ReportRegenerateRequest | None = None,
    user=Depends(require_admin),
):
    payload = payload or ReportRegenerateRequest()
    if payload.period_start is not None and payload.period_start.tzinfo is None:
        raise HTTPException(
            status_code=422, detail="period_start 必须携带时区信息"
        )
    outcome = await HotspotReportService(db).generate(
        ReportType(report_type),
        period_start=payload.period_start,
        force=payload.force,
    )
    if outcome.state == "failed":
        raise HTTPException(
            status_code=500,
            detail=f"报告生成失败：{outcome.error or '未知错误'}",
        )
    return ReportRegenerateResponse(
        state=outcome.state,
        report_run_id=outcome.report_run_id,
        status=outcome.status,
        data_quality=outcome.data_quality,
        item_count=outcome.item_count,
        error=outcome.error,
    )
