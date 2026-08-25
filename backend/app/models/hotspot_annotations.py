"""Contracts for human review and knowledge-base integration."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AnnotationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnnotationUpdateRequest(AnnotationModel):
    review_status: Literal["reviewed", "watch", "ignored"] = "reviewed"
    topic_category: str | None = Field(default=None, max_length=80)
    tags: list[str] = Field(default_factory=list, max_length=20)
    hospitality_relevance: Literal[
        "relevant", "possibly_relevant", "irrelevant"
    ] | None = None
    decision_lane: Literal[
        "opportunity",
        "context_signal",
        "risk_watch",
        "reference_material",
        "background",
    ] | None = None
    notes: str | None = Field(default=None, max_length=4000)
    summary_override: str | None = Field(default=None, max_length=2000)

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            tag = value.strip()
            if not tag:
                continue
            if len(tag) > 32:
                raise ValueError("单个标签不能超过 32 个字符")
            if tag not in normalized:
                normalized.append(tag)
        return normalized

    @field_validator("topic_category", "notes", "summary_override")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class EventAnnotationView(AnnotationModel):
    annotation_id: str
    trend_series_id: str
    source_event_id: str
    revision: int
    review_status: str
    topic_category: str | None = None
    tags: list[str]
    hospitality_relevance: str | None = None
    decision_lane: str | None = None
    notes: str | None = None
    summary_override: str | None = None
    updated_by: str
    created_at: str


class KnowledgeSyncView(AnnotationModel):
    sync_id: str
    annotation_id: str
    trend_series_id: str
    source_event_id: str
    provider: str
    knowledge_base_id: str
    knowledge_id: str | None = None
    content_hash: str
    status: str
    operation: str
    parse_status: str | None = None
    error_kind: str | None = None
    error_message: str | None = None
    started_at: str
    finished_at: str


class KnowledgeSyncResponse(AnnotationModel):
    sync: KnowledgeSyncView
    skipped_existing: bool = False


class KnowledgeSearchRequest(AnnotationModel):
    query: str | None = Field(default=None, max_length=300)
    match_count: int = Field(default=5, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None


class KnowledgeSearchHit(AnnotationModel):
    chunk_id: str
    content: str
    knowledge_id: str
    knowledge_title: str | None = None
    score: float | None = None
    chunk_index: int | None = None
    source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchResponse(AnnotationModel):
    provider: str
    query: str
    knowledge_base_id: str
    hits: list[KnowledgeSearchHit]


class KnowledgeIntegrationStatus(AnnotationModel):
    provider: Literal["weknora"] = "weknora"
    configured: bool
    base_url_configured: bool
    api_key_configured: bool
    knowledge_base_id_configured: bool
