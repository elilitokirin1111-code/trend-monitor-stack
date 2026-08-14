import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone

import pytest

from app.collectors import CollectorPolicy, HotspotCollector, ProviderPolicy
from app.domain.hotspot import (
    CollectionStatus,
    CollectRequest,
    Freshness,
    Platform,
    ProviderError,
    ProviderErrorKind,
    ProviderHotItem,
    ProviderResult,
    ProviderStatus,
)
from app.providers.hotspot import ProviderRegistry

NOW = datetime(2026, 8, 14, 8, 0, tzinfo=timezone.utc)


def item(title="topic", external_id="1"):
    return ProviderHotItem(
        title=title,
        url=f"https://example.com/{external_id}",
        external_id=external_id,
        rank=1,
        raw_data={"title": title, "id": external_id},
    )


def success(
    provider_id, *, items=(None,), freshness=Freshness.FRESH, platform=Platform.WEIBO
):
    resolved_items = (
        ()
        if items == ()
        else tuple(item() if value is None else value for value in items)
    )
    return ProviderResult(
        provider_id=provider_id,
        platform=platform,
        status=ProviderStatus.SUCCESS,
        freshness=freshness,
        fetched_at=NOW,
        observed_at=NOW,
        items=resolved_items,
        raw_payload=b'{"data":[]}',
        raw_content_type="application/json",
    )


def failed(provider_id, *, retryable, platform=Platform.WEIBO):
    return ProviderResult.failure(
        provider_id=provider_id,
        platform=platform,
        at=NOW,
        error=ProviderError(
            kind=ProviderErrorKind.UPSTREAM,
            code="upstream_failed",
            message="upstream failed",
            retryable=retryable,
        ),
    )


def partial(provider_id, *, count=1):
    return ProviderResult(
        provider_id=provider_id,
        platform=Platform.WEIBO,
        status=ProviderStatus.PARTIAL,
        freshness=Freshness.FRESH,
        fetched_at=NOW,
        observed_at=NOW,
        items=tuple(item(f"topic-{index}", str(index)) for index in range(count)),
        error=ProviderError(
            kind=ProviderErrorKind.UPSTREAM,
            code="partial_response",
            message="response was incomplete",
            retryable=True,
        ),
    )


class ScriptedProvider:
    def __init__(self, provider_id, responses, platforms=(Platform.WEIBO,)):
        self.provider_id = provider_id
        self.supported_platforms = frozenset(platforms)
        self.responses = deque(responses)
        self.calls = 0

    async def collect(self, request):
        self.calls += 1
        response = self.responses.popleft()
        if isinstance(response, BaseException):
            raise response
        if callable(response):
            return await response(request)
        return response


class RecordingWriter:
    def __init__(self):
        self.results = []

    async def save_collection(self, result):
        self.results.append(result)


class FailingWriter:
    async def save_collection(self, result):
        raise RuntimeError("database unavailable")


class StaticStaleReader:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def get_latest(self, platform):
        self.calls += 1
        return self.result


def collector(*providers, retries=0, timeout=0.1, stale_reader=None, allow_stale=True):
    writer = RecordingWriter()
    policy = CollectorPolicy(
        platforms={
            Platform.WEIBO: ProviderPolicy(
                provider_ids=tuple(provider.provider_id for provider in providers),
                timeout_seconds=timeout,
                max_retries_per_provider=retries,
                allow_stale=allow_stale,
            )
        }
    )
    instance = HotspotCollector(
        registry=ProviderRegistry(providers),
        policy=policy,
        writer=writer,
        stale_reader=stale_reader,
        clock=lambda: NOW,
        run_id_factory=lambda: "run-1",
    )
    return instance, writer


@pytest.mark.asyncio
async def test_first_fresh_success_stops_fallback_and_persists_raw_evidence():
    primary = ScriptedProvider("primary", [success("primary")])
    fallback = ScriptedProvider("fallback", [success("fallback")])
    instance, writer = collector(primary, fallback)

    result = await instance.collect(
        CollectRequest(platform=Platform.WEIBO, requested_at=NOW)
    )

    assert result.status is CollectionStatus.SUCCESS
    assert result.freshness is Freshness.FRESH
    assert result.winning_provider_id == "primary"
    assert primary.calls == 1
    assert fallback.calls == 0
    assert result.items[0].raw_data["title"] == "topic"
    assert result.items[0].raw_payload_sha256 is not None
    assert writer.results == [result]


@pytest.mark.asyncio
async def test_retryable_failure_is_retried_before_fallback():
    primary = ScriptedProvider(
        "primary", [failed("primary", retryable=True), success("primary")]
    )
    fallback = ScriptedProvider("fallback", [success("fallback")])
    instance, _ = collector(primary, fallback, retries=1)

    result = await instance.collect(
        CollectRequest(platform=Platform.WEIBO, requested_at=NOW)
    )

    assert result.winning_provider_id == "primary"
    assert primary.calls == 2
    assert [attempt.attempt_number for attempt in result.attempts] == [1, 2]
    assert fallback.calls == 0


@pytest.mark.asyncio
async def test_non_retryable_failure_moves_directly_to_fallback():
    primary = ScriptedProvider("primary", [failed("primary", retryable=False)])
    fallback = ScriptedProvider("fallback", [success("fallback")])
    instance, _ = collector(primary, fallback, retries=2)

    result = await instance.collect(
        CollectRequest(platform=Platform.WEIBO, requested_at=NOW)
    )

    assert result.winning_provider_id == "fallback"
    assert primary.calls == 1
    assert fallback.calls == 1


@pytest.mark.asyncio
async def test_timeout_is_recorded_and_falls_back():
    async def slow(_request):
        await asyncio.sleep(0.05)
        return success("primary")

    primary = ScriptedProvider("primary", [slow])
    fallback = ScriptedProvider("fallback", [success("fallback")])
    instance, _ = collector(primary, fallback, timeout=0.001)

    result = await instance.collect(
        CollectRequest(platform=Platform.WEIBO, requested_at=NOW)
    )

    assert result.winning_provider_id == "fallback"
    assert result.attempts[0].result.error.kind is ProviderErrorKind.TIMEOUT


@pytest.mark.asyncio
async def test_fresh_partial_is_used_only_when_no_provider_succeeds():
    primary = ScriptedProvider("primary", [partial("primary", count=2)])
    fallback = ScriptedProvider("fallback", [failed("fallback", retryable=False)])
    instance, _ = collector(primary, fallback)

    result = await instance.collect(
        CollectRequest(platform=Platform.WEIBO, requested_at=NOW)
    )

    assert result.status is CollectionStatus.PARTIAL
    assert result.freshness is Freshness.FRESH
    assert result.winning_provider_id == "primary"
    assert len(result.items) == 2


@pytest.mark.asyncio
async def test_fresh_success_replaces_an_earlier_partial_result():
    primary = ScriptedProvider("primary", [partial("primary", count=2)])
    fallback = ScriptedProvider("fallback", [success("fallback")])
    instance, _ = collector(primary, fallback)

    result = await instance.collect(
        CollectRequest(platform=Platform.WEIBO, requested_at=NOW)
    )

    assert result.status is CollectionStatus.SUCCESS
    assert result.winning_provider_id == "fallback"
    assert len(result.attempts) == 2


@pytest.mark.asyncio
async def test_true_empty_success_does_not_fallback_or_serve_stale():
    primary = ScriptedProvider("primary", [success("primary", items=())])
    fallback = ScriptedProvider("fallback", [success("fallback")])
    stale = success("cache", freshness=Freshness.STALE)
    stale_reader = StaticStaleReader(stale)
    instance, _ = collector(primary, fallback, stale_reader=stale_reader)

    result = await instance.collect(
        CollectRequest(platform=Platform.WEIBO, requested_at=NOW)
    )

    assert result.status is CollectionStatus.SUCCESS
    assert result.items == ()
    assert fallback.calls == 0
    assert stale_reader.calls == 0


@pytest.mark.asyncio
async def test_all_failures_can_serve_explicitly_stale_data():
    live = ScriptedProvider("live", [failed("live", retryable=False)])
    stale_result = ProviderResult(
        provider_id="cache",
        platform=Platform.WEIBO,
        status=ProviderStatus.SUCCESS,
        freshness=Freshness.STALE,
        fetched_at=NOW - timedelta(hours=1),
        observed_at=NOW - timedelta(hours=1),
        items=(item("old topic", "old"),),
    )
    stale_reader = StaticStaleReader(stale_result)
    instance, writer = collector(live, stale_reader=stale_reader)

    result = await instance.collect(
        CollectRequest(platform=Platform.WEIBO, requested_at=NOW)
    )

    assert result.status is CollectionStatus.PARTIAL
    assert result.freshness is Freshness.STALE
    assert result.stale_reason == "all_providers_failed"
    assert result.items[0].observed_at == NOW - timedelta(hours=1)
    assert writer.results == [result]


@pytest.mark.asyncio
async def test_stale_can_be_disabled_per_request():
    live = ScriptedProvider("live", [failed("live", retryable=False)])
    stale_reader = StaticStaleReader(success("cache", freshness=Freshness.STALE))
    instance, _ = collector(live, stale_reader=stale_reader)

    result = await instance.collect(
        CollectRequest(platform=Platform.WEIBO, requested_at=NOW, allow_stale=False)
    )

    assert result.status is CollectionStatus.FAILED
    assert result.items == ()
    assert stale_reader.calls == 0


@pytest.mark.asyncio
async def test_missing_provider_configuration_returns_persisted_failure():
    writer = RecordingWriter()
    instance = HotspotCollector(
        registry=ProviderRegistry(),
        policy=CollectorPolicy(platforms={}),
        writer=writer,
        clock=lambda: NOW,
        run_id_factory=lambda: "run-1",
    )

    result = await instance.collect(
        CollectRequest(platform=Platform.WEIBO, requested_at=NOW)
    )

    assert result.status is CollectionStatus.FAILED
    assert result.error.kind is ProviderErrorKind.CONFIGURATION
    assert writer.results == [result]


@pytest.mark.asyncio
async def test_mismatched_provider_identity_is_not_accepted_as_live_data():
    invalid = ScriptedProvider(
        "primary",
        [success("somebody-else")],
    )
    fallback = ScriptedProvider("fallback", [success("fallback")])
    instance, _ = collector(invalid, fallback)

    result = await instance.collect(
        CollectRequest(platform=Platform.WEIBO, requested_at=NOW)
    )

    assert result.winning_provider_id == "fallback"
    assert result.attempts[0].result.error.kind is ProviderErrorKind.INVALID_RESPONSE


@pytest.mark.asyncio
async def test_persistence_failure_is_not_reported_as_collection_success():
    provider = ScriptedProvider("primary", [success("primary")])
    instance = HotspotCollector(
        registry=ProviderRegistry((provider,)),
        policy=CollectorPolicy(
            platforms={Platform.WEIBO: ProviderPolicy(provider_ids=("primary",))}
        ),
        writer=FailingWriter(),
        clock=lambda: NOW,
        run_id_factory=lambda: "run-1",
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        await instance.collect(
            CollectRequest(platform=Platform.WEIBO, requested_at=NOW)
        )
