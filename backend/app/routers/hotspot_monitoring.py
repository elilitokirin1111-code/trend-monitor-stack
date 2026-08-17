"""V1 monitoring API: metrics, pipeline summary and alert evaluation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import PlainTextResponse

from app.middleware.auth import require_auth
from app.observability.metrics import registry
from app.services.database import db
from app.services.hotspot_monitoring import hotspot_monitoring_service

router = APIRouter()


@router.get("/monitoring/metrics", response_class=PlainTextResponse)
async def metrics_text():
    """Prometheus-style runtime metrics (public, no sensitive data)."""
    return registry.render_prometheus()


@router.get("/monitoring/summary", response_model=dict)
async def monitoring_summary(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    user=Depends(require_auth),
):
    return await hotspot_monitoring_service.summary(hours=hours)


@router.get("/monitoring/alerts", response_model=dict)
async def monitoring_alerts(
    hours: int = Query(default=24, ge=1, le=24 * 30),
    user=Depends(require_auth),
):
    outcome = await hotspot_monitoring_service.check_alerts(
        hours=hours, notify=False
    )
    return {
        "state": outcome.state,
        "alerts": list(outcome.alerts),
        "error": outcome.error,
    }


@router.get("/monitoring/health", response_model=dict)
async def hotspot_health(user=Depends(require_auth)):
    """Readiness-style view of the V1 pipeline for operators."""
    summary = await hotspot_monitoring_service.summary(hours=24)
    return {
        "database": "ok",
        "has_data": bool(summary["collection"]["runs"]),
        "collection_runs": summary["collection"]["runs"],
        "failed_runs": summary["collection"]["failed_runs"],
        "pending_normalization_snapshots": summary["pipeline"][
            "pending_normalization_snapshots"
        ],
        "last_report": summary["pipeline"]["last_report"],
    }
