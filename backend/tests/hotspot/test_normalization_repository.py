from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from app.domain.hotspot import ProviderHotItem
from app.repositories.hotspot import HotspotRepository, NormalizationRepository
from app.services.database import Database
from app.services.hotspot_normalization import HotspotNormalizationService

from .test_hotspot_repository import _result


def _database(tmp_path: Path) -> Database:
    return Database(f"sqlite:///{tmp_path / 'normalization.db'}")


def _duplicate_result():
    base = _result()
    first = replace(
        base.items[0],
        title="酒店暑期套餐",
        url="https://example.test/topic?utm_source=first",
        external_id="topic-1",
        rank=2,
        raw_data={"time": "30分钟前"},
    )
    second = replace(
        base.items[0],
        raw_item_id="run-1:2",
        title="酒店暑期套餐！",
        url="https://example.test/topic?utm_source=second",
        external_id="topic-1",
        rank=1,
        raw_data={"time": "30分钟前"},
    )
    provider_result = replace(
        base.attempts[0].result,
        items=(
            ProviderHotItem(
                title=first.title,
                url=first.url,
                external_id=first.external_id,
                rank=first.rank,
                hot_score=first.hot_score,
                raw_data=first.raw_data,
            ),
            ProviderHotItem(
                title=second.title,
                url=second.url,
                external_id=second.external_id,
                rank=second.rank,
                hot_score=second.hot_score,
                raw_data=second.raw_data,
            ),
        ),
    )
    attempt = replace(base.attempts[0], result=provider_result)
    return replace(base, items=(first, second), attempts=(attempt,))


def _snapshot_id(database: Database) -> str:
    with database.get_connection() as connection:
        return connection.execute(
            "SELECT snapshot_id FROM hotspot_snapshots"
        ).fetchone()[0]


def test_repository_loads_only_snapshot_members_in_source_order(tmp_path: Path) -> None:
    database = _database(tmp_path)
    asyncio.run(HotspotRepository(database).save_collection(_duplicate_result()))
    snapshot_id = _snapshot_id(database)
    repository = NormalizationRepository(database)

    pending = asyncio.run(
        repository.list_pending_snapshots(
            rule_version="hotspot-normalize-v1",
            config_hash="a" * 64,
        )
    )
    raw_items = asyncio.run(repository.load_snapshot(snapshot_id))

    assert pending == (snapshot_id,)
    assert [item.raw_item_id for item in raw_items] == ["run-1:1", "run-1:2"]
    assert [item.position for item in raw_items] == [1, 2]
    assert raw_items[0].raw_data["time"] == "30分钟前"


def test_service_persists_versioned_normalization_and_dedup_evidence(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    asyncio.run(HotspotRepository(database).save_collection(_duplicate_result()))
    service = HotspotNormalizationService(database)

    outcomes = asyncio.run(service.process_pending())

    assert len(outcomes) == 1
    assert outcomes[0].state == "processed"
    assert outcomes[0].total_count == 2
    assert outcomes[0].group_count == 1
    with database.get_connection() as connection:
        run = connection.execute(
            """SELECT status, total_count, success_count, partial_count,
                      failed_count, length(config_hash)
               FROM hotspot_normalization_runs"""
        ).fetchone()
        normalized = connection.execute(
            """SELECT normalized_title, title_fingerprint, canonical_url,
                      hot_score_value, published_at_precision, status
               FROM hotspot_normalized_items ORDER BY source_position"""
        ).fetchall()
        group = connection.execute(
            """SELECT member_count, representative_normalized_item_id
               FROM hotspot_dedup_groups"""
        ).fetchone()
        members = connection.execute(
            """SELECT normalized_item_id, is_representative, match_kind,
                      evidence_json
               FROM hotspot_dedup_members ORDER BY is_representative DESC"""
        ).fetchall()
        raw_titles = connection.execute(
            "SELECT title FROM hotspot_raw_items ORDER BY source_item_position"
        ).fetchall()

    assert tuple(run) == ("success", 2, 2, 0, 0, 64)
    assert [row["title_fingerprint"] for row in normalized] == [
        "酒店暑期套餐",
        "酒店暑期套餐",
    ]
    assert {row["canonical_url"] for row in normalized} == {
        "https://example.test/topic"
    }
    assert {row["hot_score_value"] for row in normalized} == {"999"}
    assert group["member_count"] == 2
    representative = next(row for row in members if row["is_representative"])
    assert (
        representative["normalized_item_id"]
        == group["representative_normalized_item_id"]
    )
    assert {row["match_kind"] for row in members} == {
        "representative",
        "external_id",
    }
    assert "value_sha256" in next(
        row["evidence_json"] for row in members if not row["is_representative"]
    )
    assert [row["title"] for row in raw_titles] == [
        "酒店暑期套餐",
        "酒店暑期套餐！",
    ]


def test_same_rules_are_idempotent_but_new_version_is_append_only(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    asyncio.run(HotspotRepository(database).save_collection(_duplicate_result()))
    service = HotspotNormalizationService(database)

    assert len(asyncio.run(service.process_pending())) == 1
    assert asyncio.run(service.process_pending()) == ()
    database.set_setting("hotspot_normalization_rule_version", "hotspot-normalize-v2")
    assert len(asyncio.run(service.process_pending())) == 1

    with database.get_connection() as connection:
        run_count = connection.execute(
            "SELECT COUNT(*) FROM hotspot_normalization_runs"
        ).fetchone()[0]
        item_count = connection.execute(
            "SELECT COUNT(*) FROM hotspot_normalized_items"
        ).fetchone()[0]
        raw_count = connection.execute(
            "SELECT COUNT(*) FROM hotspot_raw_items"
        ).fetchone()[0]
    assert (run_count, item_count, raw_count) == (2, 4, 2)


def test_real_empty_snapshot_produces_successful_zero_item_batch(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    base = _result()
    provider_result = replace(base.attempts[0].result, items=())
    empty = replace(
        base,
        items=(),
        attempts=(replace(base.attempts[0], result=provider_result),),
    )
    asyncio.run(HotspotRepository(database).save_collection(empty))

    outcomes = asyncio.run(HotspotNormalizationService(database).process_pending())

    assert len(outcomes) == 1
    assert outcomes[0].state == "processed"
    assert outcomes[0].total_count == 0
    assert outcomes[0].group_count == 0
    with database.get_connection() as connection:
        run = connection.execute(
            "SELECT status, total_count FROM hotspot_normalization_runs"
        ).fetchone()
    assert tuple(run) == ("success", 0)


def test_pending_limit_is_validated(tmp_path: Path) -> None:
    repository = NormalizationRepository(_database(tmp_path))

    try:
        asyncio.run(
            repository.list_pending_snapshots(
                rule_version="v1",
                config_hash="a" * 64,
                limit=0,
            )
        )
    except ValueError as exc:
        assert "between 1 and 1000" in str(exc)
    else:
        raise AssertionError("invalid replay limit must fail")


def test_failed_normalization_is_persisted_without_a_dedup_group(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    base = _result()
    raw_item = replace(base.items[0], title="\u200b")
    provider_item = ProviderHotItem(
        title="\u200b",
        url=raw_item.url,
        external_id=raw_item.external_id,
        rank=raw_item.rank,
        hot_score=raw_item.hot_score,
        raw_data=raw_item.raw_data,
    )
    provider_result = replace(base.attempts[0].result, items=(provider_item,))
    result = replace(
        base,
        items=(raw_item,),
        attempts=(replace(base.attempts[0], result=provider_result),),
    )
    asyncio.run(HotspotRepository(database).save_collection(result))

    outcomes = asyncio.run(HotspotNormalizationService(database).process_pending())

    assert outcomes[0].status.value == "failed"
    assert outcomes[0].group_count == 0
    with database.get_connection() as connection:
        normalized = connection.execute(
            "SELECT status, error_code FROM hotspot_normalized_items"
        ).fetchone()
        group_count = connection.execute(
            "SELECT COUNT(*) FROM hotspot_dedup_groups"
        ).fetchone()[0]
        raw_title = connection.execute(
            "SELECT title FROM hotspot_raw_items"
        ).fetchone()[0]
    assert tuple(normalized) == ("failed", "empty_title")
    assert group_count == 0
    assert raw_title == "\u200b"
