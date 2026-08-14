from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path

from app.classification import ClassificationProviderResult
from app.services.database import Database
from app.services.hotspot_classification import HotspotClassificationService
from app.services.hotspot_trends import HotspotTrendService

from .test_trend_repository import _prepare_clustering


class _Provider:
    def __init__(self) -> None:
        self.calls = 0

    async def classify(self, request):
        self.calls += 1
        evidence_id = json.loads(request.evidence_json)[0]["evidence_id"]
        return ClassificationProviderResult(
            content=json.dumps(
                {
                    "category": "hotel_travel",
                    "tags": ["酒旅"],
                    "hospitality_relevance": "relevant",
                    "hospitality_score": 0.82,
                    "confidence": 0.88,
                    "rationale": "事件证据涉及出行消费。",
                    "summary": "酒旅相关热点事件。",
                    "evidence_ids": [evidence_id],
                },
                ensure_ascii=False,
            ),
            model=request.model,
            latency_ms=18,
            prompt_tokens=80,
            completion_tokens=30,
            cost=Decimal("0.0008"),
        )


def _database(tmp_path: Path) -> Database:
    database = Database(f"sqlite:///{tmp_path / 'classification.db'}")
    _prepare_clustering(database)
    trend = asyncio.run(HotspotTrendService(database).process_current())
    assert trend.state == "processed"
    database.set_setting("hotspot_ai_classification_enabled", "true")
    database.set_setting("hotspot_ai_api_key", "test-key")
    return database


def test_service_persists_versioned_classification_and_raw_response(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    provider = _Provider()

    outcome = asyncio.run(
        HotspotClassificationService(database, provider=provider).process_current()
    )

    assert outcome.state == "processed"
    assert outcome.success_count == 1
    with database.get_connection() as connection:
        run = connection.execute(
            """SELECT status, event_count, success_count, failed_count,
                      length(config_hash), length(input_hash)
               FROM hotspot_classification_runs"""
        ).fetchone()
        record = connection.execute(
            """SELECT status, topic_category, hospitality_relevance,
                      evidence_ids_json, response_json, response_hash,
                      prompt_tokens, completion_tokens, cost
               FROM hotspot_ai_classifications"""
        ).fetchone()
        raw_count = connection.execute(
            "SELECT COUNT(*) FROM hotspot_raw_items"
        ).fetchone()[0]

    assert tuple(run) == ("success", 1, 1, 0, 64, 64)
    assert record["status"] == "success"
    assert record["topic_category"] == "hotel_travel"
    assert record["hospitality_relevance"] == "relevant"
    assert json.loads(record["evidence_ids_json"])
    assert json.loads(record["response_json"])["category"] == "hotel_travel"
    assert len(record["response_hash"]) == 64
    assert (
        record["prompt_tokens"],
        record["completion_tokens"],
        record["cost"],
    ) == (80, 30, "0.0008")
    assert raw_count == 3


def test_same_input_is_idempotent_and_prompt_change_appends(tmp_path: Path) -> None:
    database = _database(tmp_path)
    provider = _Provider()
    service = HotspotClassificationService(database, provider=provider)

    first = asyncio.run(service.process_current())
    second = asyncio.run(service.process_current())
    database.set_setting("hotspot_ai_prompt_version", "hotspot-classifier-prompt-v2")
    third = asyncio.run(service.process_current())

    assert first.state == "processed"
    assert second.state == "skipped_unchanged"
    assert third.state == "processed"
    assert provider.calls == 2
    with database.get_connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM hotspot_classification_runs"
            ).fetchone()[0]
            == 2
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM hotspot_ai_classifications"
            ).fetchone()[0]
            == 2
        )


def test_disabled_classification_is_audited_without_provider_call(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    database.set_setting("hotspot_ai_classification_enabled", "false")
    provider = _Provider()

    outcome = asyncio.run(
        HotspotClassificationService(database, provider=provider).process_current()
    )

    assert outcome.state == "processed"
    assert outcome.skipped_count == 1
    assert provider.calls == 0
    with database.get_connection() as connection:
        row = connection.execute(
            "SELECT status, error_kind FROM hotspot_ai_classifications"
        ).fetchone()
    assert tuple(row) == ("skipped", "disabled")
