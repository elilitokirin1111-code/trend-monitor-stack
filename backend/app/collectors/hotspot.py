"""Collector V2 orchestration with bounded retries and Provider fallback."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from app.domain.hotspot import (
    CollectionStatus,
    CollectorResult,
    CollectRequest,
    Freshness,
    ProviderAttempt,
    ProviderError,
    ProviderErrorKind,
    ProviderResult,
    ProviderStatus,
    RawHotItem,
    utc_now,
)
from app.providers.hotspot import (
    ProviderRegistry,
    RawCollectionWriter,
    StaleResultReader,
)
from app.providers.hotspot.registry import ProviderRegistryError

from .config import CollectorPolicy, ProviderPolicy


@dataclass(slots=True)
class _ProviderRun:
    attempts: list[ProviderAttempt] = field(default_factory=list)
    fresh_success: ProviderResult | None = None
    best_partial: ProviderResult | None = None
    stale_candidate: ProviderResult | None = None
    terminal_error: ProviderError | None = None


class HotspotCollector:
    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        policy: CollectorPolicy,
        writer: RawCollectionWriter,
        stale_reader: StaleResultReader | None = None,
        clock: Callable[[], datetime] = utc_now,
        run_id_factory: Callable[[], str] = lambda: str(uuid4()),
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._writer = writer
        self._stale_reader = stale_reader
        self._clock = clock
        self._run_id_factory = run_id_factory

    async def collect(self, request: CollectRequest) -> CollectorResult:
        run_id = self._run_id_factory()
        started_at = self._clock()
        provider_policy = self._policy.for_platform(request.platform)
        attempts: list[ProviderAttempt] = []

        try:
            providers = self._registry.resolve(
                request.platform,
                provider_policy.provider_ids,
            )
            if not providers:
                raise ProviderRegistryError(
                    f"no providers configured for {request.platform.value}"
                )
        except ProviderRegistryError as exc:
            result = self._failed_result(
                run_id=run_id,
                request=request,
                started_at=started_at,
                attempts=attempts,
                error=ProviderError(
                    kind=ProviderErrorKind.CONFIGURATION,
                    code="provider_configuration_invalid",
                    message=str(exc),
                    retryable=False,
                ),
            )
            await self._writer.save_collection(result)
            return result

        best_partial: ProviderResult | None = None
        stale_candidate: ProviderResult | None = None
        terminal_error: ProviderError | None = None

        for provider in providers:
            provider_run = await self._run_provider(
                provider=provider,
                request=request,
                policy=provider_policy,
            )
            attempts.extend(provider_run.attempts)
            best_partial = self._choose_more_complete(
                best_partial,
                provider_run.best_partial,
            )
            stale_candidate = self._choose_more_complete(
                stale_candidate,
                provider_run.stale_candidate,
            )
            terminal_error = provider_run.terminal_error or terminal_error

            if provider_run.fresh_success is not None:
                result = self._selected_result(
                    run_id=run_id,
                    request=request,
                    started_at=started_at,
                    attempts=attempts,
                    selected=provider_run.fresh_success,
                )
                await self._writer.save_collection(result)
                return result

        if best_partial is not None:
            result = self._selected_result(
                run_id=run_id,
                request=request,
                started_at=started_at,
                attempts=attempts,
                selected=best_partial,
            )
            await self._writer.save_collection(result)
            return result

        allow_stale = (
            provider_policy.allow_stale
            if request.allow_stale is None
            else request.allow_stale
        )
        if allow_stale:
            if stale_candidate is None:
                stale_candidate = await self._load_stale(request)
            if stale_candidate is not None:
                result = self._selected_result(
                    run_id=run_id,
                    request=request,
                    started_at=started_at,
                    attempts=attempts,
                    selected=stale_candidate,
                    stale_reason="all_providers_failed",
                )
                await self._writer.save_collection(result)
                return result

        error = terminal_error or ProviderError(
            kind=ProviderErrorKind.UPSTREAM,
            code="all_providers_failed",
            message=f"all providers failed for {request.platform.value}",
            retryable=True,
        )
        result = self._failed_result(
            run_id=run_id,
            request=request,
            started_at=started_at,
            attempts=attempts,
            error=error,
        )
        await self._writer.save_collection(result)
        return result

    async def _run_provider(
        self,
        *,
        provider,
        request: CollectRequest,
        policy: ProviderPolicy,
    ) -> _ProviderRun:
        run = _ProviderRun()
        for attempt_number in range(1, policy.max_retries_per_provider + 2):
            attempt_started = self._clock()
            result = await self._call_provider(
                provider=provider,
                request=request,
                timeout_seconds=policy.timeout_seconds,
            )
            run.attempts.append(
                ProviderAttempt(
                    provider_id=provider.provider_id,
                    attempt_number=attempt_number,
                    started_at=attempt_started,
                    finished_at=self._clock(),
                    result=result,
                )
            )

            if (
                result.status is ProviderStatus.SUCCESS
                and result.freshness is Freshness.FRESH
            ):
                run.fresh_success = result
                break
            if result.items and result.freshness is Freshness.STALE:
                run.stale_candidate = self._choose_more_complete(
                    run.stale_candidate,
                    result,
                )
            elif result.items:
                run.best_partial = self._choose_more_complete(
                    run.best_partial,
                    result,
                )
            if result.error is not None:
                run.terminal_error = result.error

            should_retry = (
                result.error is not None
                and result.error.retryable
                and attempt_number <= policy.max_retries_per_provider
            )
            if not should_retry:
                break
        return run

    async def _call_provider(
        self,
        *,
        provider,
        request: CollectRequest,
        timeout_seconds: float,
    ) -> ProviderResult:
        try:
            result = await asyncio.wait_for(
                provider.collect(request),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            return self._provider_failure(
                provider.provider_id,
                request,
                kind=ProviderErrorKind.TIMEOUT,
                code="provider_timeout",
                message=f"provider {provider.provider_id} timed out",
                retryable=True,
            )
        except (ConnectionError, OSError) as exc:
            return self._provider_failure(
                provider.provider_id,
                request,
                kind=ProviderErrorKind.CONNECTION,
                code="provider_connection_error",
                message=(
                    f"provider {provider.provider_id} connection failed "
                    f"({type(exc).__name__})"
                ),
                retryable=True,
            )
        except Exception as exc:  # noqa: BLE001 - isolate third-party Provider failures
            return self._provider_failure(
                provider.provider_id,
                request,
                kind=ProviderErrorKind.UNKNOWN,
                code="provider_unexpected_error",
                message=f"provider {provider.provider_id} failed ({type(exc).__name__})",
                retryable=False,
            )

        if not isinstance(result, ProviderResult):
            return self._provider_failure(
                provider.provider_id,
                request,
                kind=ProviderErrorKind.INVALID_RESPONSE,
                code="provider_result_type_invalid",
                message=f"provider {provider.provider_id} returned an invalid result type",
                retryable=False,
            )
        if (
            result.provider_id != provider.provider_id
            or result.platform is not request.platform
        ):
            return self._provider_failure(
                provider.provider_id,
                request,
                kind=ProviderErrorKind.INVALID_RESPONSE,
                code="provider_result_identity_mismatch",
                message=f"provider {provider.provider_id} returned mismatched identity",
                retryable=False,
            )
        return result

    def _provider_failure(
        self,
        provider_id: str,
        request: CollectRequest,
        *,
        kind: ProviderErrorKind,
        code: str,
        message: str,
        retryable: bool,
    ) -> ProviderResult:
        return ProviderResult.failure(
            provider_id=provider_id,
            platform=request.platform,
            at=self._clock(),
            error=ProviderError(
                kind=kind,
                code=code,
                message=message,
                retryable=retryable,
            ),
        )

    async def _load_stale(self, request: CollectRequest) -> ProviderResult | None:
        if self._stale_reader is None:
            return None
        try:
            result = await self._stale_reader.get_latest(request.platform)
        except Exception:  # noqa: BLE001 - stale storage must not hide live failure
            return None
        if result is None:
            return None
        if (
            result.platform is not request.platform
            or result.freshness is not Freshness.STALE
            or result.status is ProviderStatus.FAILED
        ):
            return None
        return result

    @staticmethod
    def _choose_more_complete(
        current: ProviderResult | None,
        candidate: ProviderResult | None,
    ) -> ProviderResult | None:
        if candidate is None:
            return current
        if current is None or len(candidate.items) > len(current.items):
            return candidate
        return current

    def _selected_result(
        self,
        *,
        run_id: str,
        request: CollectRequest,
        started_at: datetime,
        attempts: list[ProviderAttempt],
        selected: ProviderResult,
        stale_reason: str | None = None,
    ) -> CollectorResult:
        payload_hash = (
            hashlib.sha256(selected.raw_payload).hexdigest()
            if selected.raw_payload is not None
            else None
        )
        raw_items = tuple(
            RawHotItem(
                raw_item_id=f"{run_id}:{index}",
                run_id=run_id,
                platform=request.platform,
                provider_id=selected.provider_id,
                title=item.title,
                url=item.url,
                external_id=item.external_id,
                rank=item.rank,
                hot_score=item.hot_score,
                published_at=item.published_at,
                observed_at=selected.observed_at,
                fetched_at=selected.fetched_at,
                raw_data=item.raw_data,
                raw_payload_sha256=payload_hash,
            )
            for index, item in enumerate(selected.items, start=1)
        )
        freshness = selected.freshness
        collection_status = (
            CollectionStatus.SUCCESS
            if selected.status is ProviderStatus.SUCCESS
            and freshness is Freshness.FRESH
            else CollectionStatus.PARTIAL
        )
        return CollectorResult(
            run_id=run_id,
            platform=request.platform,
            status=collection_status,
            freshness=freshness,
            started_at=started_at,
            finished_at=self._clock(),
            items=raw_items,
            attempts=tuple(attempts),
            winning_provider_id=selected.provider_id,
            stale_reason=stale_reason,
        )

    def _failed_result(
        self,
        *,
        run_id: str,
        request: CollectRequest,
        started_at: datetime,
        attempts: list[ProviderAttempt],
        error: ProviderError,
    ) -> CollectorResult:
        return CollectorResult(
            run_id=run_id,
            platform=request.platform,
            status=CollectionStatus.FAILED,
            freshness=Freshness.FRESH,
            started_at=started_at,
            finished_at=self._clock(),
            items=(),
            attempts=tuple(attempts),
            error=error,
        )
