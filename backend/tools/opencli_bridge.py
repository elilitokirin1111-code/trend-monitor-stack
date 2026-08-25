"""Authenticated read-only host bridge for OpenCLI browser-session collection."""

from __future__ import annotations

import asyncio
import hmac
import os

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import Response


app = FastAPI(title="Trend Monitor OpenCLI Bridge", docs_url=None, redoc_url=None)

COMMANDS = {
    "xiaohongshu": ("xiaohongshu", "feed"),
    "weibo": ("weibo", "hot"),
    "bilibili": ("bilibili", "hot"),
}


def _authorize(authorization: str | None) -> None:
    expected = os.getenv("OPENCLI_BRIDGE_TOKEN", "")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="OpenCLI bridge authentication failed")


def _command(platform: str, limit: int) -> tuple[str, ...]:
    node = os.getenv("OPENCLI_NODE_PATH", "node")
    npx_cli = os.getenv("OPENCLI_NPX_CLI_PATH")
    package = os.getenv("OPENCLI_PACKAGE", "@jackwener/opencli@1.8.7")
    site, action = COMMANDS[platform]
    if npx_cli:
        prefix = (node, npx_cli, "-y", package)
    else:
        prefix = ("npx", "-y", package)
    return (*prefix, site, action, "--limit", str(limit), "--format", "json")


@app.get("/health")
async def health(authorization: str | None = Header(default=None)) -> dict[str, str]:
    _authorize(authorization)
    return {"status": "ok"}


@app.get("/v1/collect/{platform}")
async def collect(
    platform: str,
    limit: int = Query(default=30, ge=1, le=100),
    authorization: str | None = Header(default=None),
) -> Response:
    _authorize(authorization)
    if platform not in COMMANDS:
        raise HTTPException(status_code=404, detail="unsupported platform")

    process = await asyncio.create_subprocess_exec(
        *_command(platform, limit),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=90)
    except TimeoutError:
        process.kill()
        await process.wait()
        return Response(
            content=b"OpenCLI command timed out",
            status_code=504,
            media_type="text/plain",
            headers={"X-OpenCLI-Exit-Code": "124"},
        )

    exit_code = process.returncode or 0
    payload = stdout if exit_code == 0 else (stderr or stdout)
    return Response(
        content=payload,
        status_code=200 if exit_code == 0 else 503,
        media_type="application/json" if exit_code == 0 else "text/plain",
        headers={"X-OpenCLI-Exit-Code": str(exit_code)},
    )
