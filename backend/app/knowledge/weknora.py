"""Original REST adapter for a separately deployed WeKnora knowledge service."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass(frozen=True)
class WeKnoraConfig:
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    knowledge_base_id: str = ""
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> WeKnoraConfig:
        runtime = os.environ if environ is None else environ
        return cls(
            base_url=runtime.get("WEKNORA_BASE_URL", "").strip(),
            api_key=runtime.get("WEKNORA_API_KEY", "").strip(),
            knowledge_base_id=runtime.get("WEKNORA_KNOWLEDGE_BASE_ID", "").strip(),
            timeout_seconds=_timeout(runtime.get("WEKNORA_TIMEOUT_SECONDS", "30")),
        )

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.knowledge_base_id)

    @property
    def api_root(self) -> str:
        root = self.base_url.rstrip("/")
        return root if root.endswith("/api/v1") else f"{root}/api/v1"


class WeKnoraError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        kind: str,
        status_code: int | None = None,
        retryable: bool = False,
        response_data: Any = None,
    ) -> None:
        super().__init__(message)
        self.kind = kind
        self.status_code = status_code
        self.retryable = retryable
        self.response_data = response_data


class WeKnoraClient:
    def __init__(
        self,
        config: WeKnoraConfig,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        self._client = client

    async def create_manual_knowledge(self, *, title: str, content: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"knowledge-bases/{self.config.knowledge_base_id}/knowledge/manual",
            json={
                "title": title,
                "content": content,
                "status": "published",
                "channel": "api",
            },
        )

    async def update_manual_knowledge(
        self,
        *,
        knowledge_id: str,
        title: str,
        content: str,
    ) -> dict[str, Any]:
        return await self._request(
            "PUT",
            f"knowledge/manual/{knowledge_id}",
            json={"title": title, "content": content, "status": "published"},
        )

    async def search(self, *, query: str, match_count: int) -> list[dict[str, Any]]:
        payload = await self._request(
            "POST",
            f"knowledge-bases/{self.config.knowledge_base_id}/hybrid-search",
            json={
                "query_text": query,
                "match_count": match_count,
            },
        )
        data = payload.get("data")
        if not isinstance(data, list):
            raise WeKnoraError(
                "WeKnora knowledge search returned an invalid data field",
                kind="invalid_response",
                response_data=payload,
            )
        return [item for item in data if isinstance(item, dict)]

    async def _request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        if not self.config.configured:
            raise WeKnoraError("WeKnora integration is not configured", kind="configuration")
        headers = {
            "X-API-Key": self.config.api_key,
            "Accept": "application/json",
        }
        try:
            if self._client is not None:
                response = await self._client.request(method, path, headers=headers, **kwargs)
            else:
                async with httpx.AsyncClient(
                    base_url=self.config.api_root.rstrip("/") + "/",
                    timeout=self.config.timeout_seconds,
                    follow_redirects=False,
                ) as client:
                    response = await client.request(method, path, headers=headers, **kwargs)
        except httpx.RequestError as exc:
            raise WeKnoraError(
                f"WeKnora connection failed: {type(exc).__name__}",
                kind="connection",
                retryable=True,
            ) from exc

        try:
            payload = response.json()
        except ValueError:
            payload = {"message": response.text[:1000]}
        if not response.is_success:
            message = _error_message(payload) or f"WeKnora HTTP {response.status_code}"
            raise WeKnoraError(
                message,
                kind="authentication" if response.status_code in {401, 403} else "upstream",
                status_code=response.status_code,
                retryable=response.status_code >= 500,
                response_data=payload,
            )
        if not isinstance(payload, dict) or payload.get("success") is False:
            raise WeKnoraError(
                _error_message(payload) or "WeKnora returned an unsuccessful response",
                kind="invalid_response",
                response_data=payload,
            )
        return payload


def _error_message(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    detail = payload.get("detail") or payload.get("message") or payload.get("error")
    return detail if isinstance(detail, str) else None


def _timeout(value: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 30.0
    return parsed if parsed > 0 else 30.0
