"""Run non-fabricated Provider probes and print redacted evidence as JSON.

Only response metadata, counts, hashes, and classified errors are printed. Raw
payloads remain in ProviderResult and are never dumped by this tool.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from datetime import datetime
from typing import Any

from app.domain.hotspot import CollectRequest, Platform, ProviderResult
from app.providers.hotspot import (
    DEFAULT_PROVIDER_ORDER,
    ProviderRuntimeConfig,
    build_provider_registry,
)


def iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def evidence_record(result: ProviderResult) -> dict[str, Any]:
    raw_payload = result.raw_payload
    return {
        "provider": result.provider_id,
        "platform": result.platform.value,
        "status": result.status.value,
        "freshness": result.freshness.value,
        "fetched_at": iso(result.fetched_at),
        "source_updated_at": iso(result.source_updated_at),
        "item_count": len(result.items),
        "raw_payload_bytes": len(raw_payload) if raw_payload is not None else 0,
        "raw_payload_sha256": (
            hashlib.sha256(raw_payload).hexdigest() if raw_payload is not None else None
        ),
        "raw_content_type": result.raw_content_type,
        "error_kind": result.error.kind.value if result.error else None,
        "error_code": result.error.code if result.error else None,
        "error_retryable": result.error.retryable if result.error else None,
        "upstream_status": result.error.upstream_status if result.error else None,
    }


async def run(
    *,
    provider_filter: frozenset[str] = frozenset(),
    platform_filter: frozenset[Platform] = frozenset(),
) -> list[dict[str, Any]]:
    defaults = ProviderRuntimeConfig()
    config = ProviderRuntimeConfig(
        newsnow_base_url=os.getenv(
            "HOTSPOT_NEWSNOW_BASE_URL", defaults.newsnow_base_url
        ),
        newsnow_trust_success_as_fresh=os.getenv(
            "HOTSPOT_NEWSNOW_TRUST_SUCCESS_AS_FRESH", "false"
        ).lower()
        in {"1", "true", "yes", "on"},
        dailyhotapi_base_url=os.getenv(
            "HOTSPOT_DAILYHOTAPI_BASE_URL", defaults.dailyhotapi_base_url
        ),
        opencli_executable=os.getenv(
            "HOTSPOT_OPENCLI_EXECUTABLE", defaults.opencli_executable
        ),
        opencli_limit=int(os.getenv("HOTSPOT_OPENCLI_LIMIT", "10")),
    )
    registry = build_provider_registry(config)
    evidence = []
    for platform, provider_ids in DEFAULT_PROVIDER_ORDER.items():
        if platform_filter and platform not in platform_filter:
            continue
        for provider_id in provider_ids:
            if provider_filter and provider_id not in provider_filter:
                continue
            provider = registry.get(provider_id)
            result = await provider.collect(CollectRequest(platform=platform))
            evidence.append(evidence_record(result))
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", action="append", default=[])
    parser.add_argument(
        "--platform", action="append", choices=[platform.value for platform in Platform]
    )
    args = parser.parse_args()
    print(
        json.dumps(
            asyncio.run(
                run(
                    provider_filter=frozenset(args.provider),
                    platform_filter=frozenset(
                        Platform(value) for value in (args.platform or [])
                    ),
                )
            ),
            ensure_ascii=False,
            indent=2,
        )
    )
