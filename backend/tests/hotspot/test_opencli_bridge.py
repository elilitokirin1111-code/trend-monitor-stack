from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from tools import opencli_bridge


@pytest.mark.asyncio
async def test_bridge_requires_token_and_runs_only_fixed_read_command(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLI_BRIDGE_TOKEN", "bridge-secret")
    monkeypatch.setenv("OPENCLI_NODE_PATH", "C:/node.exe")
    monkeypatch.setenv("OPENCLI_NPX_CLI_PATH", "C:/npm/npx-cli.js")
    monkeypatch.setenv("OPENCLI_PACKAGE", "@jackwener/opencli@1.8.7")
    commands = []

    class Process:
        returncode = 0

        async def communicate(self):
            return (
                b'[{"id":"n1","title":"topic","url":"https://xhs/n1"}]',
                b"",
            )

    async def create_process(*command, **kwargs):
        commands.append(command)
        assert kwargs["stdout"] is asyncio.subprocess.PIPE
        assert kwargs["stderr"] is asyncio.subprocess.PIPE
        return Process()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", create_process)
    with pytest.raises(HTTPException) as unauthorized:
        await opencli_bridge.collect("xiaohongshu", 4, authorization=None)
    response = await opencli_bridge.collect(
        "xiaohongshu",
        4,
        authorization="Bearer bridge-secret",
    )

    assert unauthorized.value.status_code == 401
    assert response.status_code == 200
    assert commands == [
        (
            "C:/node.exe",
            "C:/npm/npx-cli.js",
            "-y",
            "@jackwener/opencli@1.8.7",
            "xiaohongshu",
            "feed",
            "--limit",
            "4",
            "--format",
            "json",
        )
    ]


@pytest.mark.asyncio
async def test_bridge_rejects_unknown_platform_before_starting_process(monkeypatch) -> None:
    monkeypatch.setenv("OPENCLI_BRIDGE_TOKEN", "bridge-secret")

    with pytest.raises(HTTPException) as error:
        await opencli_bridge.collect(
            "douyin",
            30,
            authorization="Bearer bridge-secret",
        )

    assert error.value.status_code == 404
