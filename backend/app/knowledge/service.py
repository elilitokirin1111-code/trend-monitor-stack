"""Human-approved hotspot synchronization and retrieval for knowledge providers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from app.repositories.hotspot.annotations import AnnotationRepository
from app.repositories.hotspot.dashboard import HotspotDashboardRepository

from .weknora import WeKnoraClient, WeKnoraConfig, WeKnoraError


class KnowledgeConfigurationError(RuntimeError):
    pass


class AnnotationRequiredError(RuntimeError):
    pass


class KnowledgeSyncService:
    def __init__(
        self,
        database,
        *,
        config: WeKnoraConfig | None = None,
        client: WeKnoraClient | None = None,
    ) -> None:
        self._database = database
        self._config = config or WeKnoraConfig.from_env()
        self._client = client or WeKnoraClient(self._config)
        self._annotations = AnnotationRepository(database)
        self._dashboard = HotspotDashboardRepository(database)

    def status(self) -> dict[str, Any]:
        return {
            "provider": "weknora",
            "configured": self._config.configured,
            "base_url_configured": bool(self._config.base_url),
            "api_key_configured": bool(self._config.api_key),
            "knowledge_base_id_configured": bool(self._config.knowledge_base_id),
        }

    async def sync_event(self, event_id: str) -> tuple[dict[str, Any], bool]:
        event = self._dashboard.get_event(event_id)
        if event is None:
            raise LookupError("热点事件不存在")
        annotation = self._annotations.get_latest_for_event(event_id)
        if annotation is None:
            raise AnnotationRequiredError("请先保存人工标记，再同步到知识库")
        self._require_configuration()

        title, content = render_event_markdown(event, annotation)
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = self._annotations.find_successful_sync(
            annotation_id=annotation["annotation_id"],
            knowledge_base_id=self._config.knowledge_base_id,
            content_hash=content_hash,
        )
        if existing is not None:
            return existing, True

        latest = self._annotations.find_latest_knowledge_sync(
            trend_series_id=annotation["trend_series_id"],
            knowledge_base_id=self._config.knowledge_base_id,
        )
        operation = "update" if latest and latest.get("knowledge_id") else "create"
        started_at = datetime.now(timezone.utc)
        try:
            if operation == "update":
                response = await self._client.update_manual_knowledge(
                    knowledge_id=latest["knowledge_id"],
                    title=title,
                    content=content,
                )
            else:
                response = await self._client.create_manual_knowledge(
                    title=title,
                    content=content,
                )
            data = response.get("data") if isinstance(response.get("data"), dict) else {}
            knowledge_id = data.get("id") or (latest or {}).get("knowledge_id")
            if not knowledge_id:
                raise WeKnoraError(
                    "WeKnora did not return a knowledge ID",
                    kind="invalid_response",
                    response_data=response,
                )
            sync = self._annotations.record_sync(
                annotation=annotation,
                source_event_id=event_id,
                knowledge_base_id=self._config.knowledge_base_id,
                knowledge_id=knowledge_id,
                content_hash=content_hash,
                status="success",
                operation=operation,
                parse_status=data.get("parse_status"),
                error_kind=None,
                error_message=None,
                response_json=_json(response),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
            return sync, False
        except WeKnoraError as exc:
            self._annotations.record_sync(
                annotation=annotation,
                source_event_id=event_id,
                knowledge_base_id=self._config.knowledge_base_id,
                knowledge_id=(latest or {}).get("knowledge_id"),
                content_hash=content_hash,
                status="failed",
                operation=operation,
                parse_status=None,
                error_kind=exc.kind,
                error_message=str(exc)[:1000],
                response_json=(
                    _json(exc.response_data) if exc.response_data is not None else None
                ),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
            raise

    async def search_event(
        self,
        event_id: str,
        *,
        query: str | None,
        match_count: int,
    ) -> dict[str, Any]:
        self._require_configuration()
        event = self._dashboard.get_event(event_id)
        if event is None:
            raise LookupError("热点事件不存在")
        annotation = self._annotations.get_latest_for_event(event_id)
        effective_query = query or _default_query(event, annotation)
        items = await self._client.search(query=effective_query, match_count=match_count)
        return {
            "provider": "weknora",
            "query": effective_query,
            "knowledge_base_id": self._config.knowledge_base_id,
            "hits": [_search_hit(item) for item in items],
        }

    def _require_configuration(self) -> None:
        if not self._config.configured:
            raise KnowledgeConfigurationError(
                "WeKnora 未配置，请设置 WEKNORA_BASE_URL、WEKNORA_API_KEY 和 "
                "WEKNORA_KNOWLEDGE_BASE_ID"
            )


def render_event_markdown(
    event: dict[str, Any], annotation: dict[str, Any]
) -> tuple[str, str]:
    title = f"热点情报：{event['canonical_title']}"
    classification = event.get("classification") or {}
    lines = [
        f"# {title}",
        "",
        "## 人工研判",
        "",
        f"- 审核状态：{annotation['review_status']}",
        f"- 人工分类：{annotation.get('topic_category') or '未填写'}",
        f"- 决策通道：{annotation.get('decision_lane') or '未填写'}",
        f"- 酒旅相关性：{annotation.get('hospitality_relevance') or '未填写'}",
        f"- 标签：{', '.join(annotation.get('tags') or []) or '未填写'}",
        f"- 标记人：{annotation['updated_by']}",
        f"- 标记版本：{annotation['revision']}",
        "",
    ]
    if annotation.get("summary_override"):
        lines.extend(["### 人工摘要", "", annotation["summary_override"], ""])
    if annotation.get("notes"):
        lines.extend(["### 人工备注", "", annotation["notes"], ""])
    lines.extend(
        [
            "## 趋势事实",
            "",
            f"- 事件 ID：{event['event_id']}",
            f"- 趋势序列：{event['trend_series_id']}",
            f"- 生命周期：{event['lifecycle_state']}",
            f"- 趋势分：{event['trend_score']}",
            f"- 数据质量：{event['data_quality']}",
            f"- 覆盖平台：{', '.join(event.get('platforms') or [])}",
            f"- 首次发现：{event['first_seen_at']}",
            f"- 最近发现：{event['last_seen_at']}",
            "",
            "## AI 研判（未覆盖人工结论）",
            "",
            f"- AI 分类：{classification.get('topic_category') or '未提供'}",
            f"- AI 酒旅相关性：{classification.get('hospitality_relevance') or '未提供'}",
            f"- AI 摘要：{classification.get('summary') or '未提供'}",
            "",
            "## 原始证据",
            "",
        ]
    )
    evidence = event.get("evidence") or []
    if evidence:
        for item in evidence:
            rank = item.get("rank")
            rank_text = f"榜单 #{rank}" if rank is not None else "排名未提供"
            evidence_title = item["title"]
            if item.get("source_url"):
                evidence_title = f"[{evidence_title}]({item['source_url']})"
            lines.append(
                f"- {evidence_title} — "
                f"{item['platform']} / {item['provider_id']} / {rank_text} / "
                f"{item['freshness']} / 观测于 {item['observed_at']}"
            )
    else:
        lines.append("- 当前事件没有可用原始证据。")
    lines.extend(
        [
            "",
            "---",
            "本条知识由多平台热点情报中心同步；原始数据与人工标记分层保存。",
        ]
    )
    return title, "\n".join(lines)


def _default_query(event: dict[str, Any], annotation: dict[str, Any] | None) -> str:
    parts = [event["canonical_title"]]
    if annotation:
        parts.extend(annotation.get("tags") or [])
        if annotation.get("topic_category"):
            parts.append(annotation["topic_category"])
    return " ".join(dict.fromkeys(parts))


def _search_hit(item: dict[str, Any]) -> dict[str, Any]:
    score = item.get("score")
    return {
        "chunk_id": str(item.get("id") or ""),
        "content": str(item.get("content") or ""),
        "knowledge_id": str(item.get("knowledge_id") or ""),
        "knowledge_title": item.get("knowledge_title"),
        "score": float(score) if score is not None else None,
        "chunk_index": item.get("chunk_index"),
        "source": item.get("knowledge_source"),
        "metadata": item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
    }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
