"""Authenticated human-review and WeKnora integration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.knowledge.service import (
    AnnotationRequiredError,
    KnowledgeConfigurationError,
    KnowledgeSyncService,
)
from app.knowledge.weknora import WeKnoraError
from app.middleware.auth import require_auth
from app.models.hotspot_annotations import (
    AnnotationUpdateRequest,
    EventAnnotationView,
    KnowledgeIntegrationStatus,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSyncResponse,
)
from app.repositories.hotspot.annotations import AnnotationRepository
from app.services.database import db


router = APIRouter()


@router.put(
    "/events/{event_id}/annotation",
    response_model=EventAnnotationView,
)
async def update_annotation(
    event_id: str,
    request: AnnotationUpdateRequest,
    user: dict = Depends(require_auth),
):
    updated_by = str(user.get("username") or user.get("user_id") or "local-admin")
    annotation = AnnotationRepository(db).save_annotation(
        event_id=event_id,
        updated_by=updated_by,
        **request.model_dump(),
    )
    if annotation is None:
        raise HTTPException(status_code=404, detail="热点事件不存在")
    return annotation


@router.get("/knowledge/status", response_model=KnowledgeIntegrationStatus)
async def knowledge_status(user: dict = Depends(require_auth)):
    del user
    return KnowledgeSyncService(db).status()


@router.post(
    "/events/{event_id}/knowledge/sync",
    response_model=KnowledgeSyncResponse,
)
async def sync_event_to_knowledge(
    event_id: str,
    user: dict = Depends(require_auth),
):
    del user
    try:
        sync, skipped = await KnowledgeSyncService(db).sync_event(event_id)
        return {"sync": sync, "skipped_existing": skipped}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AnnotationRequiredError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KnowledgeConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WeKnoraError as exc:
        status = 503 if exc.kind == "connection" else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc


@router.post(
    "/events/{event_id}/knowledge/search",
    response_model=KnowledgeSearchResponse,
)
async def search_event_knowledge(
    event_id: str,
    request: KnowledgeSearchRequest,
    user: dict = Depends(require_auth),
):
    del user
    try:
        return await KnowledgeSyncService(db).search_event(
            event_id,
            query=request.query,
            match_count=request.match_count,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except KnowledgeConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except WeKnoraError as exc:
        status = 503 if exc.kind == "connection" else 502
        raise HTTPException(status_code=status, detail=str(exc)) from exc
