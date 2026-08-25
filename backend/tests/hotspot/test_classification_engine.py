from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal

from app.classification import (
    ClassificationEngine,
    ClassificationProviderError,
    ClassificationProviderResult,
    ClassificationRules,
)
from app.domain.hotspot import (
    ClassificationErrorKind,
    ClassificationEvidence,
    ClassificationInput,
    ClassificationStatus,
    HospitalityRelevance,
    Platform,
    TopicCategory,
    TrendDataQuality,
    TrendLifecycleState,
)

AT = datetime(2026, 8, 14, 8, tzinfo=timezone.utc)


def _input(identifier: str = "state-1") -> ClassificationInput:
    return ClassificationInput(
        trend_state_id=identifier,
        source_event_id=f"event-{identifier}",
        canonical_title="上海暑期酒店预订热度上升",
        lifecycle_state=TrendLifecycleState.RISING,
        trend_score=Decimal("0.81"),
        data_quality=TrendDataQuality.COMPLETE,
        evaluated_at=AT,
        evidence=(
            ClassificationEvidence(
                evidence_id="item-1",
                platform=Platform.WEIBO,
                title="上海暑期酒店预订热度上升",
                observed_at=AT,
                rank=3,
            ),
        ),
    )


def _content(**overrides) -> str:
    body = {
        "category": "hotel_travel",
        "tags": ["酒店", "暑期出行"],
        "hospitality_relevance": "high",
        "hospitality_score": 0.94,
        "confidence": 0.91,
        "rationale": "标题直接涉及酒店预订需求。",
        "summary": "上海暑期酒店预订关注度上升。",
        "evidence_ids": ["item-1"],
    }
    body.update(overrides)
    return json.dumps(body, ensure_ascii=False)


class _Provider:
    def __init__(self, content: str = "", *, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.calls = 0

    async def classify(self, request):
        self.calls += 1
        if self.error:
            raise self.error
        return ClassificationProviderResult(
            content=self.content,
            model=request.model,
            latency_ms=25,
            prompt_tokens=100,
            completion_tokens=40,
            cost=Decimal("0.0012"),
        )


def _rules(**overrides) -> ClassificationRules:
    return ClassificationRules(enabled=True, api_key="test-key", **overrides)


def test_strict_structured_output_is_classified_and_grounded() -> None:
    provider = _Provider(_content())
    batch = asyncio.run(
        ClassificationEngine(_rules(), provider).classify(
            (_input(),), source_trend_run_id="trend-run-1"
        )
    )

    record = batch.records[0]
    assert record.status is ClassificationStatus.SUCCESS
    assert record.decision.category is TopicCategory.HOTEL_TRAVEL
    assert record.decision.hospitality_relevance is HospitalityRelevance.HIGH
    assert record.decision.evidence_ids == ("item-1",)
    assert record.response_hash and len(record.response_hash) == 64
    assert record.prompt_tokens == 100
    assert provider.calls == 1


def test_unknown_evidence_id_is_rejected_without_fabricated_decision() -> None:
    batch = asyncio.run(
        ClassificationEngine(
            _rules(), _Provider(_content(evidence_ids=["invented-item"]))
        ).classify((_input(),), source_trend_run_id="trend-run-1")
    )

    record = batch.records[0]
    assert record.status is ClassificationStatus.FAILED
    assert record.error_kind is ClassificationErrorKind.INVALID_SCHEMA
    assert record.decision is None


def test_invalid_json_and_provider_error_are_explicit_failures() -> None:
    invalid = asyncio.run(
        ClassificationEngine(_rules(), _Provider("```json\n{}\n```")).classify(
            (_input("invalid"),), source_trend_run_id="trend-run-1"
        )
    )
    failed = asyncio.run(
        ClassificationEngine(
            _rules(), _Provider(error=RuntimeError("offline"))
        ).classify((_input("offline"),), source_trend_run_id="trend-run-1")
    )

    assert invalid.records[0].error_kind is ClassificationErrorKind.INVALID_JSON
    assert failed.records[0].error_kind is ClassificationErrorKind.PROVIDER_ERROR
    assert failed.records[0].error_message == "offline"


def test_rate_limit_is_preserved_as_a_distinct_failure() -> None:
    batch = asyncio.run(
        ClassificationEngine(
            _rules(),
            _Provider(
                error=ClassificationProviderError(
                    ClassificationErrorKind.RATE_LIMITED, "quota exceeded"
                )
            ),
        ).classify((_input(),), source_trend_run_id="trend-run-1")
    )

    assert batch.records[0].error_kind is ClassificationErrorKind.RATE_LIMITED


def test_provider_error_cannot_persist_the_configured_api_key() -> None:
    batch = asyncio.run(
        ClassificationEngine(
            _rules(), _Provider(error=RuntimeError("bad credential test-key"))
        ).classify((_input(),), source_trend_run_id="trend-run-1")
    )

    assert batch.records[0].error_message == "bad credential ***"


def test_disabled_and_missing_key_never_call_provider() -> None:
    provider = _Provider(_content())
    disabled = asyncio.run(
        ClassificationEngine(ClassificationRules(), provider).classify(
            (_input("disabled"),), source_trend_run_id="trend-run-1"
        )
    )
    missing = asyncio.run(
        ClassificationEngine(ClassificationRules(enabled=True), provider).classify(
            (_input("missing"),), source_trend_run_id="trend-run-1"
        )
    )

    assert disabled.records[0].status is ClassificationStatus.SKIPPED
    assert disabled.records[0].error_kind is ClassificationErrorKind.DISABLED
    assert missing.records[0].status is ClassificationStatus.FAILED
    assert missing.records[0].error_kind is ClassificationErrorKind.MISSING_API_KEY
    assert provider.calls == 0


def test_timeout_is_bounded_and_recorded() -> None:
    class _SlowProvider:
        async def classify(self, request):
            await asyncio.sleep(0.05)
            return ClassificationProviderResult(content=_content(), model=request.model)

    batch = asyncio.run(
        ClassificationEngine(_rules(timeout_seconds=0.01), _SlowProvider()).classify(
            (_input(),), source_trend_run_id="trend-run-1"
        )
    )

    assert batch.records[0].error_kind is ClassificationErrorKind.TIMEOUT


def test_classification_replay_is_deterministic_except_runtime_evidence() -> None:
    first = asyncio.run(
        ClassificationEngine(_rules(), _Provider(_content())).classify(
            (_input(),), source_trend_run_id="trend-run-1"
        )
    )
    second = asyncio.run(
        ClassificationEngine(_rules(), _Provider(_content())).classify(
            (_input(),), source_trend_run_id="trend-run-1"
        )
    )

    assert first.classification_run_id == second.classification_run_id
    assert first.input_hash == second.input_hash
    assert first.records[0].classification_id == second.records[0].classification_id


def test_configured_concurrency_bounds_one_call_per_event() -> None:
    class _ConcurrentProvider:
        def __init__(self) -> None:
            self.active = 0
            self.maximum = 0
            self.calls = 0

        async def classify(self, request):
            self.active += 1
            self.calls += 1
            self.maximum = max(self.maximum, self.active)
            await asyncio.sleep(0)
            self.active -= 1
            return ClassificationProviderResult(content=_content(), model=request.model)

    provider = _ConcurrentProvider()
    items = tuple(_input(f"state-{index}") for index in range(50))

    batch = asyncio.run(
        ClassificationEngine(_rules(max_concurrency=3), provider).classify(
            items, source_trend_run_id="trend-run-scale"
        )
    )

    assert len(batch.records) == 50
    assert provider.calls == 50
    assert provider.maximum == 3
