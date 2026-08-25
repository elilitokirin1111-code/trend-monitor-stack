"""Strict, evidence-grounded classification orchestration."""

from __future__ import annotations

import asyncio
import hashlib
import json
from decimal import Decimal, InvalidOperation

from app.domain.hotspot import (
    ClassificationBatch,
    ClassificationDecision,
    ClassificationErrorKind,
    ClassificationInput,
    ClassificationRecord,
    ClassificationStatus,
    HospitalityRelevance,
    TopicCategory,
    utc_now,
)

from .provider import (
    ClassificationProvider,
    ClassificationProviderError,
    ClassificationProviderResult,
    ClassificationRequest,
)
from .rules import ClassificationRules

_OUTPUT_KEYS = {
    "category",
    "tags",
    "hospitality_relevance",
    "hospitality_score",
    "confidence",
    "rationale",
    "summary",
    "evidence_ids",
}


class ClassificationEngine:
    def __init__(
        self,
        rules: ClassificationRules | None = None,
        provider: ClassificationProvider | None = None,
    ) -> None:
        self.rules = rules or ClassificationRules()
        self.provider = provider

    async def classify(
        self,
        inputs: tuple[ClassificationInput, ...],
        *,
        source_trend_run_id: str,
    ) -> ClassificationBatch:
        if not source_trend_run_id or not inputs:
            raise ValueError("classification requires a trend run and inputs")
        items = tuple(sorted(inputs, key=lambda item: item.trend_state_id))
        if len({item.trend_state_id for item in items}) != len(items):
            raise ValueError("classification input identifiers must be unique")
        input_hash = classification_input_hash(items)
        run_id = classification_run_id(source_trend_run_id, self.rules, input_hash)
        started_at = utc_now()
        semaphore = asyncio.Semaphore(self.rules.max_concurrency)

        async def execute(item: ClassificationInput) -> ClassificationRecord:
            async with semaphore:
                return await self._classify_one(item, run_id)

        records = tuple(await asyncio.gather(*(execute(item) for item in items)))
        return ClassificationBatch(
            classification_run_id=run_id,
            source_trend_run_id=source_trend_run_id,
            classifier_version=self.rules.classifier_version,
            prompt_version=self.rules.prompt_version,
            model=self.rules.model,
            config_hash=self.rules.config_hash,
            config_json=self.rules.config_json,
            input_hash=input_hash,
            started_at=started_at,
            finished_at=utc_now(),
            records=records,
        )

    async def _classify_one(
        self,
        item: ClassificationInput,
        run_id: str,
    ) -> ClassificationRecord:
        evidence_json = _evidence_json(item)
        prompt = _prompt(item, evidence_json, self.rules)
        request_hash = hashlib.sha256(prompt.encode()).hexdigest()
        record_id = _identifier("classification", run_id, item.trend_state_id)
        base = {
            "classification_id": record_id,
            "classification_run_id": run_id,
            "trend_state_id": item.trend_state_id,
            "source_event_id": item.source_event_id,
            "model": self.rules.model,
            "prompt_version": self.rules.prompt_version,
            "request_hash": request_hash,
        }
        if not self.rules.enabled:
            return _failure(
                base,
                ClassificationStatus.SKIPPED,
                ClassificationErrorKind.DISABLED,
                "classification is disabled",
            )
        if not self.rules.api_key:
            return _failure(
                base,
                ClassificationStatus.FAILED,
                ClassificationErrorKind.MISSING_API_KEY,
                "classification API key is not configured",
            )
        if self.provider is None:
            return _failure(
                base,
                ClassificationStatus.FAILED,
                ClassificationErrorKind.PROVIDER_ERROR,
                "classification provider is unavailable",
            )

        request = ClassificationRequest(
            input_id=item.trend_state_id,
            model=self.rules.model,
            prompt=prompt,
            evidence_json=evidence_json,
        )
        try:
            result = await asyncio.wait_for(
                self.provider.classify(request),
                timeout=self.rules.timeout_seconds,
            )
        except TimeoutError:
            return _failure(
                base,
                ClassificationStatus.FAILED,
                ClassificationErrorKind.TIMEOUT,
                "classification provider timed out",
            )
        except ClassificationProviderError as exc:
            return _failure(
                base,
                ClassificationStatus.FAILED,
                exc.kind,
                _safe_error(str(exc), self.rules.api_key),
            )
        except Exception as exc:  # noqa: BLE001 - provider isolation boundary
            return _failure(
                base,
                ClassificationStatus.FAILED,
                ClassificationErrorKind.PROVIDER_ERROR,
                _safe_error(str(exc), self.rules.api_key),
            )
        return _record_from_result(base, item, result, self.rules)


def _record_from_result(
    base: dict,
    item: ClassificationInput,
    result: ClassificationProviderResult,
    rules: ClassificationRules,
) -> ClassificationRecord:
    base = {**base, "model": result.model}
    response_hash = hashlib.sha256(result.content.encode()).hexdigest()
    runtime = {
        "response_json": result.content,
        "response_hash": response_hash,
        "latency_ms": result.latency_ms,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "cost": result.cost,
    }
    try:
        value = json.loads(result.content)
    except json.JSONDecodeError:
        return _failure(
            base,
            ClassificationStatus.FAILED,
            ClassificationErrorKind.INVALID_JSON,
            "classification response is not strict JSON",
            **runtime,
        )
    try:
        decision = _decision(value, item, rules)
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        return _failure(
            base,
            ClassificationStatus.FAILED,
            ClassificationErrorKind.INVALID_SCHEMA,
            str(exc),
            **runtime,
        )
    return ClassificationRecord(
        **base,
        status=ClassificationStatus.SUCCESS,
        decision=decision,
        error_kind=None,
        error_message=None,
        **runtime,
    )


def _decision(
    value,
    item: ClassificationInput,
    rules: ClassificationRules,
) -> ClassificationDecision:
    if not isinstance(value, dict) or set(value) != _OUTPUT_KEYS:
        raise ValueError("classification response keys do not match the schema")
    tags = value["tags"]
    evidence_ids = value["evidence_ids"]
    if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
        raise TypeError("tags must be a string array")
    if not isinstance(evidence_ids, list) or not all(
        isinstance(identifier, str) for identifier in evidence_ids
    ):
        raise TypeError("evidence_ids must be a string array")
    allowed_evidence = {evidence.evidence_id for evidence in item.evidence}
    if not set(evidence_ids).issubset(allowed_evidence):
        raise ValueError("classification cited evidence outside the source event")
    rationale = value["rationale"]
    summary = value["summary"]
    if not isinstance(rationale, str) or len(rationale) > rules.max_rationale_chars:
        raise ValueError("classification rationale exceeds its schema limit")
    if not isinstance(summary, str) or len(summary) > rules.max_summary_chars:
        raise ValueError("classification summary exceeds its schema limit")
    return ClassificationDecision(
        category=TopicCategory(value["category"]),
        tags=tuple(tags),
        hospitality_relevance=HospitalityRelevance(value["hospitality_relevance"]),
        hospitality_score=Decimal(str(value["hospitality_score"])),
        confidence=Decimal(str(value["confidence"])),
        rationale=rationale,
        summary=summary,
        evidence_ids=tuple(evidence_ids),
    )


def _failure(
    base: dict,
    status: ClassificationStatus,
    kind: ClassificationErrorKind,
    message: str,
    *,
    response_json: str | None = None,
    response_hash: str | None = None,
    latency_ms: int | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    cost: Decimal | None = None,
) -> ClassificationRecord:
    return ClassificationRecord(
        **base,
        status=status,
        response_json=response_json,
        response_hash=response_hash,
        decision=None,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost=cost,
        error_kind=kind,
        error_message=message[:1000],
    )


def _prompt(
    item: ClassificationInput,
    evidence_json: str,
    rules: ClassificationRules,
) -> str:
    categories = ", ".join(value.value for value in TopicCategory)
    relevance = ", ".join(value.value for value in HospitalityRelevance)
    return (
        f"你是热点情报分类器。提示词版本：{rules.prompt_version}。"
        "只能依据给定证据，不得补充外部事实、热度或趋势。"
        "只返回一个 JSON 对象，不要 Markdown。"
        f"category 只能是：{categories}；hospitality_relevance 只能是：{relevance}。"
        "字段必须且只能包含 category,tags,hospitality_relevance,"
        "hospitality_score,confidence,rationale,summary,evidence_ids。"
        "hospitality_score 与 confidence 必须为 0 到 1；tags 为 1-5 个短标签；"
        "evidence_ids 必须引用下方 evidence_id。"
        f"summary 不超过 {rules.max_summary_chars} 字，rationale 不超过 "
        f"{rules.max_rationale_chars} 字。\n"
        f"事件标题：{item.canonical_title}\n"
        f"生命周期：{item.lifecycle_state.value}\n"
        f"趋势分数：{item.trend_score}\n"
        f"数据质量：{item.data_quality.value}\n"
        f"证据：{evidence_json}"
    )


def _evidence_json(item: ClassificationInput) -> str:
    return json.dumps(
        [
            {
                "evidence_id": evidence.evidence_id,
                "hot_score": (
                    str(evidence.hot_score) if evidence.hot_score is not None else None
                ),
                "observed_at": evidence.observed_at.isoformat(),
                "platform": evidence.platform.value,
                "rank": evidence.rank,
                "title": evidence.title,
            }
            for evidence in sorted(item.evidence, key=lambda value: value.evidence_id)
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def classification_input_hash(items: tuple[ClassificationInput, ...]) -> str:
    body = json.dumps(
        [
            {
                "canonical_title": item.canonical_title,
                "data_quality": item.data_quality.value,
                "evaluated_at": item.evaluated_at.isoformat(),
                "evidence": json.loads(_evidence_json(item)),
                "lifecycle_state": item.lifecycle_state.value,
                "source_event_id": item.source_event_id,
                "trend_score": str(item.trend_score),
                "trend_state_id": item.trend_state_id,
            }
            for item in items
        ],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(body.encode()).hexdigest()


def classification_run_id(
    source_trend_run_id: str,
    rules: ClassificationRules,
    input_hash: str,
) -> str:
    return _identifier(
        "classification-run",
        source_trend_run_id,
        rules.classifier_version,
        rules.prompt_version,
        rules.model,
        rules.config_hash,
        input_hash,
    )


def _identifier(kind: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join((kind, *parts)).encode()).hexdigest()
    return f"{kind}-{digest}"


def _safe_error(message: str, api_key: str) -> str:
    return message.replace(api_key, "***") if api_key else message
