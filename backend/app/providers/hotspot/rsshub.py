"""RSSHub hotspot Provider adapter for the separately deployed RSS service."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from time import struct_time
from typing import Any
from urllib.parse import urljoin

import feedparser
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
    request_error,
    response_failure,
    text_or_none,
)


RSSHUB_ROUTES = {
    Platform.WEIBO: "weibo/search/hot",
    Platform.BILIBILI: "bilibili/hot-search",
}


class RssHubProvider:
    provider_id = "rsshub"
    supported_platforms = frozenset(RSSHUB_ROUTES)

    def __init__(
        self,
        *,
        base_url: str = "http://localhost:1200",
        max_age_minutes: int = 15,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if max_age_minutes < 1 or max_age_minutes > 180:
            raise ValueError("RSSHub max age must be between 1 and 180 minutes")
        self._base_url = base_url.rstrip("/") + "/"
        self._max_age = timedelta(minutes=max_age_minutes)
        self._client = client

    async def collect(self, request: CollectRequest) -> ProviderResult:
        route = RSSHUB_ROUTES.get(request.platform)
        if route is None:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=invalid_response_error(
                    f"RSSHub hot-list route is not configured for {request.platform.value}",
                    code="unsupported_platform",
                ),
            )

        fetched_at = utc_now()
        try:
            response = await self._get(route)
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
            "route": f"/{route}",
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

        parsed = feedparser.parse(response.content)
        items, invalid_count = self._parse_items(parsed.entries)
        parse_error = getattr(parsed, "bozo_exception", None)
        if parse_error is not None and not items:
            return response_failure(
                provider_id=self.provider_id,
                platform=request.platform,
                error=invalid_response_error(
                    f"invalid RSSHub feed: {type(parse_error).__name__}",
                    code="invalid_rss_feed",
                ),
                raw_payload=response.content,
                raw_content_type=content_type,
                metadata=metadata,
                at=fetched_at,
            )

        source_updated_at = self._parsed_time(parsed.feed.get("updated_parsed"))
        age = fetched_at - source_updated_at if source_updated_at else None
        freshness = (
            Freshness.FRESH
            if age is not None and timedelta(0) <= age <= self._max_age
            else Freshness.STALE
        )
        metadata.update(
            {
                "invalid_item_count": invalid_count,
                "feed_parse_warning": type(parse_error).__name__ if parse_error else None,
                "source_age_seconds": (
                    round(age.total_seconds(), 3) if age is not None else None
                ),
                "freshness_basis": (
                    "rsshub_last_build_date_within_max_age"
                    if freshness is Freshness.FRESH
                    else "rsshub_last_build_date_missing_or_old"
                ),
            }
        )
        if invalid_count or parse_error is not None:
            status = ProviderStatus.PARTIAL
            detail = f"RSSHub feed contained {invalid_count} invalid item(s)"
            if parse_error is not None:
                detail += f" and parse warning {type(parse_error).__name__}"
            error = invalid_response_error(detail, code="partial_invalid_items")
        else:
            status = ProviderStatus.SUCCESS
            error = None

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
            response = await self._get("")
        except httpx.RequestError as exc:
            return ProviderHealth(
                provider_id=self.provider_id,
                status=ProviderHealthStatus.UNAVAILABLE,
                checked_at=checked_at,
                detail=f"connection failed: {type(exc).__name__}",
            )
        status = (
            ProviderHealthStatus.HEALTHY
            if 200 <= response.status_code < 300
            else ProviderHealthStatus.UNAVAILABLE
        )
        return ProviderHealth(
            provider_id=self.provider_id,
            status=status,
            checked_at=checked_at,
            detail=f"HTTP {response.status_code}",
        )

    async def _get(self, path: str) -> httpx.Response:
        url = urljoin(self._base_url, path)
        if self._client is not None:
            return await self._client.get(url)
        async with httpx.AsyncClient(
            timeout=25,
            follow_redirects=True,
            headers={"User-Agent": "trend-monitor-stack/1.0"},
        ) as client:
            return await client.get(url)

    @staticmethod
    def _parse_items(raw_items: list[Any]) -> tuple[list[ProviderHotItem], int]:
        items: list[ProviderHotItem] = []
        invalid_count = 0
        for rank, raw in enumerate(raw_items, start=1):
            title = text_or_none(raw.get("title"))
            url = text_or_none(raw.get("link"))
            if not title or not url:
                invalid_count += 1
                continue
            items.append(
                ProviderHotItem(
                    title=title,
                    url=url,
                    external_id=text_or_none(raw.get("id")) or url,
                    rank=rank,
                    published_at=RssHubProvider._parsed_time(raw.get("published_parsed")),
                    raw_data={
                        "id": raw.get("id"),
                        "title": raw.get("title"),
                        "link": raw.get("link"),
                        "summary": raw.get("summary"),
                        "published": raw.get("published"),
                        "author": raw.get("author"),
                    },
                )
            )
        return items, invalid_count

    @staticmethod
    def _parsed_time(value: struct_time | None) -> datetime | None:
        if value is None:
            return None
        try:
            return datetime(*value[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError):
            return None
