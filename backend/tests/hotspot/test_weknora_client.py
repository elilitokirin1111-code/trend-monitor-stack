from __future__ import annotations

import httpx
import pytest

from app.knowledge.weknora import WeKnoraClient, WeKnoraConfig, WeKnoraError


def _config() -> WeKnoraConfig:
    return WeKnoraConfig(
        base_url="http://weknora.local",
        api_key="secret-key",
        knowledge_base_id="kb-1",
    )


@pytest.mark.asyncio
async def test_weknora_adapter_creates_updates_and_searches_manual_knowledge() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["x-api-key"] == "secret-key"
        if request.url.path.endswith("/hybrid-search"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "data": [
                        {
                            "id": "chunk-1",
                            "knowledge_id": "knowledge-1",
                            "content": "历史台风处置方案",
                            "score": 0.91,
                        }
                    ],
                },
            )
        return httpx.Response(
            201 if request.method == "POST" else 200,
            json={
                "success": True,
                "data": {"id": "knowledge-1", "parse_status": "processing"},
            },
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://weknora.local/api/v1/",
    ) as http_client:
        client = WeKnoraClient(_config(), client=http_client)
        created = await client.create_manual_knowledge(title="热点", content="# 热点")
        updated = await client.update_manual_knowledge(
            knowledge_id="knowledge-1", title="热点 V2", content="# 热点 V2"
        )
        hits = await client.search(query="台风 酒店", match_count=6)

    assert created["data"]["id"] == "knowledge-1"
    assert updated["success"] is True
    assert hits[0]["content"] == "历史台风处置方案"
    assert [request.url.path for request in requests] == [
        "/api/v1/knowledge-bases/kb-1/knowledge/manual",
        "/api/v1/knowledge/manual/knowledge-1",
        "/api/v1/knowledge-bases/kb-1/hybrid-search",
    ]


@pytest.mark.asyncio
async def test_weknora_adapter_classifies_auth_failure_without_leaking_key() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "invalid api key"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="http://weknora.local/api/v1/",
    ) as http_client:
        client = WeKnoraClient(_config(), client=http_client)
        with pytest.raises(WeKnoraError) as error:
            await client.search(query="测试", match_count=3)

    assert error.value.kind == "authentication"
    assert error.value.status_code == 401
    assert "secret-key" not in str(error.value)


def test_weknora_timeout_configuration_falls_back_safely() -> None:
    invalid = WeKnoraConfig.from_env({"WEKNORA_TIMEOUT_SECONDS": "invalid"})
    non_positive = WeKnoraConfig.from_env({"WEKNORA_TIMEOUT_SECONDS": "0"})

    assert invalid.timeout_seconds == 30.0
    assert non_positive.timeout_seconds == 30.0
