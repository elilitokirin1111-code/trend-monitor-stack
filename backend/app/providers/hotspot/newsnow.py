"""NewsNow hotspot Provider adapter.

This module implements the public response contract; it does not copy NewsNow
collector source code.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from app.domain.hotspot import (
    CollectRequest,
    Freshness,
    Platform,
    ProviderHealth,
    ProviderHealthStatus,
    ProviderHotItem,
    ProviderResult,
    ProviderStatus,
    utc_now,
)

from ._shared import (
    http_status_error,
    invalid_response_error,
    parse_datetime,
    parse_json_object,
    request_error,
    response_failure,
    text_or_none,
)


class NewsNowProvider:
    provider_id = "newsnow"
    supported_platforms = frozenset(
        {Platform.DOUYIN, Platform.WEIBO, Platform.BILIBILI}
    )

    def __init__(
        self,
        *,
        base_url: str = "https://newsnow.busiyi.world",
        trust_success_as_fresh: bool = False,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/") + "/"
        self._trust_success_as_fresh = trust_success_as_fresh
        self._client = client

    async def collect(self, request: CollectRequest) -> ProviderResult:
        if request.platform not in self.supported_platforms:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=invalid_response_error(
                    f"NewsNow does not expose {request.platform.value}",
                    code="unsupported_platform",
                ),
            )

        fetched_at = utc_now()
        try:
            response = await self._get("api/s", params={"id": request.platform.value})
        except httpx.RequestError as exc:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=request_error(exc),
                at=fetched_at,
            )

        content_type = response.headers.get("content-type")
        metadata: dict[str, Any] = {
            "http_status": response.status_code,
        }
        if not 200 <= response.status_code < 300:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=http_status_error(response.status_code),
                raw_payload=response.content,
                raw_content_type=content_type,
                metadata=metadata,
                at=fetched_at,
            )

        try:
            payload = parse_json_object(response.content)
            raw_items = payload["items"]
            if not isinstance(raw_items, list):
                raise TypeError("NewsNow items must be an array")
            source_status = payload.get("status")
            if source_status not in {"success", "cache"}:
                raise ValueError("NewsNow status must be success or cache")
        except (KeyError, TypeError, ValueError) as exc:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=invalid_response_error(str(exc)),
                raw_payload=response.content,
                raw_content_type=content_type,
                metadata=metadata,
                at=fetched_at,
            )

        items, invalid_count = self._parse_items(raw_items)
        source_updated_at = parse_datetime(payload.get("updatedTime"))
        freshness = (
            Freshness.FRESH
            if source_status == "success" and self._trust_success_as_fresh
            else Freshness.STALE
        )
        metadata.update(
            {
                "source_status": source_status,
                "freshness_basis": (
                    "operator_asserted_cache_disabled"
                    if freshness is Freshness.FRESH
                    else "newsnow_success_may_include_interval_cache"
                ),
                "invalid_item_count": invalid_count,
            }
        )

        if invalid_count and not items:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=invalid_response_error("all NewsNow items were invalid"),
                raw_payload=response.content,
                raw_content_type=content_type,
                metadata=metadata,
                at=fetched_at,
            )
        if invalid_count:
            error = invalid_response_error(
                f"ignored {invalid_count} invalid NewsNow item(s)",
                code="partial_invalid_items",
            )
            status = ProviderStatus.PARTIAL
        else:
            error = None
            status = ProviderStatus.SUCCESS

        return ProviderResult(
            provider_id=self.provider_id,
            platform=request.platform,
            status=status,
            freshness=freshness,
            fetched_at=fetched_at,
            observed_at=fetched_at,
            source_updated_at=source_updated_at,
            items=tuple(items),
            raw_payload=response.content,
            raw_content_type=content_type,
            error=error,
            metadata=metadata,
        )

    async def health(self) -> ProviderHealth:
        checked_at = utc_now()
        try:
            response = await self._get("api/s", params={"id": "bilibili"})
        except httpx.RequestError as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                checked_at=checked_at,
                detail=f"connection failed: {type(exc).__name__}",
            )
        if 200 <= response.status_code < 300:
            status = ProviderHealthStatus.HEALTHY
        elif response.status_code in {401, 403, 429} or response.status_code >= 500:
            status = ProviderHealthStatus.DEGRADED
        else:
            status = ProviderHealthStatus.UNAVAILABLE
        return ProviderHealth(
            provider_id=self.provider_id,
            status=status,
            checked_at=checked_at,
            detail=f"HTTP {response.status_code}",
        )

    async def _get(self, path: str, **kwargs: Any) -> httpx.Response:
        url = urljoin(self._base_url, path)
        if self._client is not None:
            return await self._client.get(url, **kwargs)
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "trend-monitor-stack/1.0"},
        ) as client:
            return await client.get(url, **kwargs)

    @staticmethod
    def _parse_items(raw_items: list[Any]) -> tuple[list[ProviderHotItem], int]:
        items: list[ProviderHotItem] = []
        invalid_count = 0
        for rank, raw in enumerate(raw_items, start=1):
            if not isinstance(raw, dict):
                invalid_count += 1
                continue
            title = text_or_none(raw.get("title"))
            url = text_or_none(raw.get("url") or raw.get("mobileUrl"))
            if not title or not url:
                invalid_count += 1
                continue
            items.append(
                ProviderHotItem(
                    title=title,
                    url=url,
                    external_id=text_or_none(raw.get("id")),
                    rank=rank,
                    hot_score=text_or_none(raw.get("hot")),
                    published_at=parse_datetime(raw.get("pubDate")),
                    raw_data=raw,
                )
            )
        return items, invalid_count
