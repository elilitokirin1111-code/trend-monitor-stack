import asyncio
import json

import httpx
import pytest

from app.domain.hotspot import (
    CollectRequest,
    Platform,
    ProviderErrorKind,
    ProviderHealthStatus,
    ProviderStatus,
)
from app.providers.hotspot.opencli import CommandResult, OpenCliProvider


@pytest.mark.asyncio
async def test_opencli_maps_xiaohongshu_json_and_never_uses_a_shell():
    commands = []

    async def runner(command):
        commands.append(command)
        return CommandResult(
            0,
            json.dumps(
                [
                    {
                        "id": "note-1",
                        "title": "真实推荐内容",
                        "author": "作者",
                        "likes": "1234",
                        "type": "normal",
                        "url": "https://www.xiaohongshu.com/explore/note-1",
                    }
                ]
            ).encode(),
            b"",
        )

    provider = OpenCliProvider(executable="opencli", limit=5, runner=runner)
    result = await provider.collect(CollectRequest(platform=Platform.XIAOHONGSHU))

    assert commands == [
        (
            "opencli",
            "xiaohongshu",
            "feed",
            "--limit",
            "5",
            "--format",
            "json",
        )
    ]
    assert result.status is ProviderStatus.SUCCESS
    assert result.items[0].external_id == "note-1"
    assert result.items[0].hot_score == "1234"
    assert result.raw_payload is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "site"),
    ((Platform.WEIBO, "weibo"), (Platform.BILIBILI, "bilibili")),
)
async def test_opencli_can_be_configured_as_logged_in_hot_list_fallback(
    platform: Platform, site: str
) -> None:
    commands = []

    async def runner(command):
        commands.append(command)
        return CommandResult(
            0,
            json.dumps(
                [{"id": "hot-1", "title": "热点", "hot": 987, "url": "https://x/1"}]
            ).encode(),
            b"",
        )

    result = await OpenCliProvider(limit=8, runner=runner).collect(
        CollectRequest(platform=platform)
    )

    assert commands == [("opencli", site, "hot", "--limit", "8", "--format", "json")]
    assert result.status is ProviderStatus.SUCCESS
    assert result.items[0].hot_score == "987"


@pytest.mark.asyncio
async def test_opencli_host_bridge_returns_raw_xiaohongshu_items() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/collect/xiaohongshu"
        assert request.url.params["limit"] == "6"
        assert request.headers["authorization"] == "Bearer local-secret"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "note-bridge",
                    "title": "登录态推荐",
                    "likes": 321,
                    "url": "https://www.xiaohongshu.com/explore/note-bridge",
                }
            ],
            headers={"X-OpenCLI-Exit-Code": "0"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenCliProvider(
            limit=6,
            bridge_url="http://host.docker.internal:19826",
            bridge_token="local-secret",
            client=client,
        )
        result = await provider.collect(
            CollectRequest(platform=Platform.XIAOHONGSHU)
        )

    assert result.status is ProviderStatus.SUCCESS
    assert result.items[0].external_id == "note-bridge"
    assert result.metadata["execution_mode"] == "host_bridge"


@pytest.mark.asyncio
async def test_opencli_host_bridge_auth_failure_is_not_live_data() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            text="OpenCLI bridge authentication failed",
            headers={"X-OpenCLI-Exit-Code": "78"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenCliProvider(
            bridge_url="http://host.docker.internal:19826",
            bridge_token="wrong",
            client=client,
        )
        result = await provider.collect(
            CollectRequest(platform=Platform.XIAOHONGSHU)
        )

    assert result.status is ProviderStatus.FAILED
    assert result.error.kind is ProviderErrorKind.CONFIGURATION
    assert result.error.code == "opencli_bridge_authentication_failed"
    assert result.items == ()


@pytest.mark.asyncio
async def test_opencli_bridge_failure_is_explicit_configuration_failure():
    async def runner(command):
        return CommandResult(1, b"", b"Chrome extension not connected")

    provider = OpenCliProvider(runner=runner)
    result = await provider.collect(CollectRequest(platform=Platform.XIAOHONGSHU))

    assert result.status is ProviderStatus.FAILED
    assert result.error.kind is ProviderErrorKind.CONFIGURATION
    assert result.error.code == "opencli_bridge_unavailable"
    assert result.raw_payload == b"Chrome extension not connected"


@pytest.mark.asyncio
async def test_opencli_login_failure_is_authentication_not_live_data():
    async def runner(command):
        return CommandResult(1, b"", "请先登录".encode())

    provider = OpenCliProvider(runner=runner)
    result = await provider.collect(CollectRequest(platform=Platform.XIAOHONGSHU))

    assert result.status is ProviderStatus.FAILED
    assert result.error.kind is ProviderErrorKind.AUTHENTICATION
    assert result.items == ()


@pytest.mark.asyncio
async def test_opencli_invalid_json_is_failed_with_raw_evidence():
    async def runner(command):
        return CommandResult(0, b"not-json", b"")

    provider = OpenCliProvider(runner=runner)
    result = await provider.collect(CollectRequest(platform=Platform.XIAOHONGSHU))

    assert result.status is ProviderStatus.FAILED
    assert result.error.kind is ProviderErrorKind.INVALID_RESPONSE
    assert result.raw_payload == b"not-json"


@pytest.mark.asyncio
async def test_opencli_reports_executable_health_without_claiming_browser_health():
    async def runner(command):
        return CommandResult(0, b"opencli 1.8.6", b"")

    provider = OpenCliProvider(runner=runner)
    health = await provider.health()

    assert health.status is ProviderHealthStatus.DEGRADED
    assert "browser session" in health.detail


@pytest.mark.asyncio
async def test_default_runner_kills_child_process_when_collector_timeout_cancels(
    monkeypatch,
):
    class Process:
        returncode = None
        killed = False
        waited = False

        async def communicate(self):
            await asyncio.Future()

        def kill(self):
            self.killed = True
            self.returncode = -9

        async def wait(self):
            self.waited = True

    process = Process()

    async def create_process(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    task = asyncio.create_task(OpenCliProvider._run_command(("opencli", "--version")))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert process.killed is True
    assert process.waited is True
