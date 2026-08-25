"""Replaceable provider boundary for Phase 7 classification calls."""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.domain.hotspot import ClassificationErrorKind


@dataclass(frozen=True, slots=True)
class ClassificationRequest:
    input_id: str
    model: str
    prompt: str
    evidence_json: str


@dataclass(frozen=True, slots=True)
class ClassificationProviderResult:
    content: str
    model: str
    latency_ms: int | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not self.model.strip():
            raise ValueError("classification provider content and model are required")
        for name in ("latency_ms", "prompt_tokens", "completion_tokens"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} cannot be negative")
        if self.cost is not None:
            value = Decimal(str(self.cost))
            if not value.is_finite() or value < 0:
                raise ValueError("classification provider cost must be non-negative")
            object.__setattr__(self, "cost", value)


class ClassificationProviderError(RuntimeError):
    def __init__(self, kind: ClassificationErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class ClassificationProvider(Protocol):
    async def classify(
        self, request: ClassificationRequest
    ) -> ClassificationProviderResult: ...


class LiteLLMClassificationProvider:
    def __init__(self, *, api_key: str, base_url: str = "") -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")

    async def classify(
        self, request: ClassificationRequest
    ) -> ClassificationProviderResult:
        try:
            import litellm
        except ImportError as exc:
            raise ClassificationProviderError(
                ClassificationErrorKind.PROVIDER_ERROR, "litellm is not installed"
            ) from exc

        model, base_url = _compatible_endpoint(request.model, self._base_url)
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": request.prompt}],
            "api_key": self._api_key,
            "temperature": 0,
            "max_tokens": 900,
            "response_format": {"type": "json_object"},
        }
        if base_url:
            kwargs["api_base"] = base_url
        started = time.perf_counter()
        try:
            response = await litellm.acompletion(**kwargs)
        except Exception as exc:
            name = type(exc).__name__.lower()
            kind = (
                ClassificationErrorKind.RATE_LIMITED
                if "rate" in name or "429" in str(exc)
                else ClassificationErrorKind.PROVIDER_ERROR
            )
            raise ClassificationProviderError(kind, str(exc)) from exc
        latency_ms = round((time.perf_counter() - started) * 1000)
        content = response.choices[0].message.content
        usage = getattr(response, "usage", None)
        hidden = getattr(response, "_hidden_params", {}) or {}
        cost = hidden.get("response_cost")
        return ClassificationProviderResult(
            content=str(content or ""),
            model=str(getattr(response, "model", None) or request.model),
            latency_ms=latency_ms,
            prompt_tokens=_usage_value(usage, "prompt_tokens"),
            completion_tokens=_usage_value(usage, "completion_tokens"),
            cost=Decimal(str(cost)) if cost is not None else None,
        )


def _usage_value(usage, name: str) -> int | None:
    if usage is None:
        return None
    value = getattr(usage, name, None)
    if value is None and isinstance(usage, dict):
        value = usage.get(name)
    return int(value) if value is not None else None


def _compatible_endpoint(model: str, base_url: str) -> tuple[str, str]:
    if not base_url:
        return model, base_url
    if model.startswith("openai/"):
        return model, base_url if base_url.endswith("/v1") else f"{base_url}/v1"
    if model.startswith(("gpt-", "deepseek/", "moonshot/")):
        endpoint = base_url if base_url.endswith("/v1") else f"{base_url}/v1"
        return f"openai/{model}", endpoint
    if model.startswith("claude") and base_url.endswith("/v1"):
        return model, base_url[:-3]
    return model, base_url
