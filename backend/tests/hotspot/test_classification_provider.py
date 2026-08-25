from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.classification import (
    ClassificationProviderError,
    ClassificationRequest,
    LiteLLMClassificationProvider,
)
from app.domain.hotspot import ClassificationErrorKind


def _request() -> ClassificationRequest:
    return ClassificationRequest(
        input_id="state-1",
        model="openai/test-model",
        prompt="classify this evidence",
        evidence_json="[]",
    )


def test_litellm_adapter_requests_json_and_records_usage(monkeypatch) -> None:
    captured = {}

    async def acompletion(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            model="test-model-202608",
            choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))],
            usage={"prompt_tokens": 12, "completion_tokens": 6},
            _hidden_params={"response_cost": 0.002},
        )

    monkeypatch.setitem(
        sys.modules, "litellm", SimpleNamespace(acompletion=acompletion)
    )
    provider = LiteLLMClassificationProvider(
        api_key="test-key", base_url="https://llm.example"
    )

    result = asyncio.run(provider.classify(_request()))

    assert captured["api_base"] == "https://llm.example/v1"
    assert captured["temperature"] == 0
    assert captured["response_format"] == {"type": "json_object"}
    assert result.model == "test-model-202608"
    assert (result.prompt_tokens, result.completion_tokens) == (12, 6)
    assert result.cost == Decimal("0.002")


def test_litellm_rate_limit_maps_to_explicit_error(monkeypatch) -> None:
    class RateLimitError(RuntimeError):
        pass

    async def acompletion(**kwargs):
        raise RateLimitError("quota")

    monkeypatch.setitem(
        sys.modules, "litellm", SimpleNamespace(acompletion=acompletion)
    )
    provider = LiteLLMClassificationProvider(api_key="test-key")

    with pytest.raises(ClassificationProviderError) as captured:
        asyncio.run(provider.classify(_request()))

    assert captured.value.kind is ClassificationErrorKind.RATE_LIMITED
