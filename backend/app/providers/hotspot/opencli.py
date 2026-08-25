"""Process-isolated OpenCLI Provider for browser-session data."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import httpx

from app.domain.hotspot import (
    CollectRequest,
    Freshness,
    Platform,
    ProviderError,
    ProviderErrorKind,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderHotItem,
    ProviderResult,
    ProviderStatus,
    utc_now,
)

from ._shared import (
    invalid_response_error,
    parse_json_array,
    response_failure,
    text_or_none,
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    return_code: int
    stdout: bytes
    stderr: bytes


CommandRunner = Callable[[tuple[str, ...]], Awaitable[CommandResult]]


class OpenCliProvider:
    provider_id = "opencli"
    supported_platforms = frozenset(
        {Platform.XIAOHONGSHU, Platform.WEIBO, Platform.BILIBILI}
    )
    commands = {
        Platform.XIAOHONGSHU: ("xiaohongshu", "feed"),
        Platform.WEIBO: ("weibo", "hot"),
        Platform.BILIBILI: ("bilibili", "hot"),
    }

    def __init__(
        self,
        *,
        executable: str = "opencli",
        limit: int = 30,
        runner: CommandRunner | None = None,
        bridge_url: str | None = None,
        bridge_token: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if limit < 1 or limit > 100:
            raise ValueError("OpenCLI limit must be between 1 and 100")
        self._executable = executable
        self._limit = limit
        self._runner = runner or self._run_command
        self._bridge_url = bridge_url.rstrip("/") + "/" if bridge_url else None
        self._bridge_token = bridge_token or None
        self._client = client

    async def collect(self, request: CollectRequest) -> ProviderResult:
        if request.platform not in self.supported_platforms:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=ProviderError(
                    kind=ProviderErrorKind.CONFIGURATION,
                    code="unsupported_platform",
                    message=f"OpenCLI command is not configured for {request.platform.value}",
                    retryable=False,
                ),
            )

        fetched_at = utc_now()
        site, action = self.commands[request.platform]
        command = (
            self._executable,
            site,
            action,
            "--limit",
            str(self._limit),
            "--format",
            "json",
        )
        try:
            command_result = (
                await self._run_bridge(request.platform)
                if self._bridge_url
                else await self._runner(command)
            )
        except httpx.RequestError as exc:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=ProviderError(
                    kind=ProviderErrorKind.CONNECTION,
                    code="opencli_bridge_connection_error",
                    message=f"OpenCLI host bridge connection failed: {type(exc).__name__}",
                    retryable=True,
                ),
                metadata={"execution_mode": "host_bridge"},
                at=fetched_at,
            )
        except FileNotFoundError:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=ProviderError(
                    kind=ProviderErrorKind.CONFIGURATION,
                    code="executable_not_found",
                    message="OpenCLI executable was not found",
                    retryable=False,
                ),
                metadata={"executable": executable_name(self._executable)},
                at=fetched_at,
            )
        except OSError as exc:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=ProviderError(
                    kind=ProviderErrorKind.CONNECTION,
                    code="process_start_failed",
                    message=f"OpenCLI process failed to start: {type(exc).__name__}",
                    retryable=True,
                ),
                metadata={"executable": executable_name(self._executable)},
                at=fetched_at,
            )

        metadata: dict[str, Any] = {
            "executable": executable_name(self._executable),
            "execution_mode": "host_bridge" if self._bridge_url else "local_process",
            "return_code": command_result.return_code,
            "stderr_present": bool(command_result.stderr),
        }
        if command_result.return_code != 0:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=self._command_error(command_result),
                raw_payload=command_result.stdout or command_result.stderr,
                raw_content_type="text/plain",
                metadata=metadata,
                at=fetched_at,
            )

        try:
            raw_items = parse_json_array(command_result.stdout)
        except (TypeError, ValueError) as exc:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=invalid_response_error(str(exc), code="invalid_cli_json"),
                raw_payload=command_result.stdout,
                raw_content_type="application/json",
                metadata=metadata,
                at=fetched_at,
            )

        items, invalid_count = self._parse_items(raw_items)
        metadata["invalid_item_count"] = invalid_count
        if invalid_count and not items:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=invalid_response_error("all OpenCLI items were invalid"),
                raw_payload=command_result.stdout,
                raw_content_type="application/json",
                metadata=metadata,
                at=fetched_at,
            )
        if invalid_count:
            status = ProviderStatus.PARTIAL
            error = invalid_response_error(
                f"ignored {invalid_count} invalid OpenCLI item(s)",
                code="partial_invalid_items",
            )
        else:
            status = ProviderStatus.SUCCESS
            error = None

        return ProviderResult(
            provider_id=self.provider_id,
            platform=request.platform,
            status=status,
            freshness=Freshness.FRESH,
            fetched_at=fetched_at,
            observed_at=fetched_at,
            items=tuple(items),
            raw_payload=command_result.stdout,
            raw_content_type="application/json",
            error=error,
            metadata=metadata,
        )

    async def health(self) -> ProviderHealth:
        checked_at = utc_now()
        try:
            result = (
                await self._bridge_health()
                if self._bridge_url
                else await self._runner((self._executable, "--version"))
            )
        except (FileNotFoundError, OSError, httpx.RequestError):
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                checked_at=checked_at,
                detail="OpenCLI executable is unavailable",
            )
        if result.return_code != 0:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                checked_at=checked_at,
                detail="OpenCLI version command failed",
            )
        return ProviderHealth(
            provider_id=self.provider_id,
            status=ProviderHealthStatus.DEGRADED,
            checked_at=checked_at,
            detail="executable available; browser session is verified during collection",
        )

    async def _run_bridge(self, platform: Platform) -> CommandResult:
        headers = self._bridge_headers()
        response = await self._bridge_get(
            f"v1/collect/{platform.value}",
            params={"limit": self._limit},
            headers=headers,
        )
        exit_code = int(response.headers.get("x-opencli-exit-code", "0"))
        return CommandResult(
            return_code=exit_code if exit_code else (0 if response.is_success else 1),
            stdout=response.content if response.is_success else b"",
            stderr=b"" if response.is_success else response.content,
        )

    async def _bridge_health(self) -> CommandResult:
        response = await self._bridge_get("health", headers=self._bridge_headers())
        return CommandResult(0 if response.is_success else 1, response.content, b"")

    async def _bridge_get(self, path: str, **kwargs) -> httpx.Response:
        url = urljoin(self._bridge_url or "", path)
        if self._client is not None:
            return await self._client.get(url, **kwargs)
        async with httpx.AsyncClient(timeout=90, follow_redirects=False) as client:
            return await client.get(url, **kwargs)

    def _bridge_headers(self) -> dict[str, str]:
        return (
            {"Authorization": f"Bearer {self._bridge_token}"}
            if self._bridge_token
            else {}
        )

    @staticmethod
    async def _run_command(command: tuple[str, ...]) -> CommandResult:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await process.communicate()
        except asyncio.CancelledError:
            if process.returncode is None:
                process.kill()
                await process.wait()
            raise
        return CommandResult(process.returncode or 0, stdout, stderr)

    @staticmethod
    def _command_error(result: CommandResult) -> ProviderError:
        detail = (
            (result.stderr or result.stdout).decode("utf-8", errors="replace").lower()
        )
        if any(token in detail for token in ("login", "cookie", "认证", "登录")):
            return ProviderError(
                kind=ProviderErrorKind.AUTHENTICATION,
                code="opencli_authentication_failed",
                message="OpenCLI browser session is not authenticated",
                retryable=False,
            )
        if "bridge authentication" in detail:
            return ProviderError(
                kind=ProviderErrorKind.CONFIGURATION,
                code="opencli_bridge_authentication_failed",
                message="OpenCLI host bridge authentication failed",
                retryable=False,
            )
        if any(
            token in detail
            for token in (
                "extension not connected",
                "extension is not connected",
                "chrome is not running",
                "daemon",
            )
        ):
            return ProviderError(
                kind=ProviderErrorKind.CONFIGURATION,
                code="opencli_bridge_unavailable",
                message="OpenCLI browser bridge is unavailable",
                retryable=False,
            )
        return ProviderError(
            kind=ProviderErrorKind.UPSTREAM,
            code="opencli_command_failed",
            message=f"OpenCLI command exited with code {result.return_code}",
            retryable=True,
        )

    @staticmethod
    def _parse_items(raw_items: list[Any]) -> tuple[list[ProviderHotItem], int]:
        items: list[ProviderHotItem] = []
        invalid_count = 0
        for rank, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict):
                invalid_count += 1
                continue
            title = text_or_none(raw.get("title"))
            url = text_or_none(raw.get("url") or raw.get("link"))
            if not title or not url:
                invalid_count += 1
                continue
            items.append(
                ProviderHotItem(
                    title=title,
                    url=url,
                    external_id=text_or_none(raw.get("id")),
                    rank=rank,
                    hot_score=text_or_none(
                        raw.get("likes") or raw.get("hot") or raw.get("score")
                    ),
                    raw_data=raw,
                )
            )
        return items, invalid_count


def executable_name(value: str) -> str:
    """Return a log-safe executable name without exposing local directories."""
    return value.replace("\\", "/").rsplit("/", 1)[-1]
