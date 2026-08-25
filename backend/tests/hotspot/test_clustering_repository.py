from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

from app.domain.hotspot import Platform, ProviderHotItem
from app.repositories.hotspot import HotspotRepository
from app.services.database import Database
from app.services.hotspot_clustering import HotspotClusteringService
from app.services.hotspot_normalization import HotspotNormalizationService

from .test_hotspot_repository import _result


def _database(tmp_path: Path) -> Database:
    return Database(f"sqlite:///{tmp_path / 'clustering.db'}")


def _platform_result(run_id: str, platform: Platform, title: str):
    base = _result(run_id)
    provider_item = replace(
        base.attempts[0].result.items[0],
        title=title,
        external_id=f"{platform.value}-topic",
        url=f"https://{platform.value}.example.test/topic",
    )
    provider_result = replace(
        base.attempts[0].result,
        platform=platform,
        items=(provider_item,),
    )
    attempt = replace(base.attempts[0], result=provider_result)
    raw_item = replace(
        base.items[0],
        raw_item_id=f"{run_id}:1",
        run_id=run_id,
        platform=platform,
        title=title,
        external_id=provider_item.external_id,
        url=provider_item.url,
    )
    return replace(
        base,
        run_id=run_id,
        platform=platform,
        items=(raw_item,),
        attempts=(attempt,),
    )


def _duplicate_weibo_result():
    base = _platform_result("weibo-run", Platform.WEIBO, "台风登陆广东")
    first = base.items[0]
    second = replace(
        first,
        raw_item_id="weibo-run:2",
        rank=2,
        title="台风登陆广东！",
    )
    provider_items = (
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
    )
    result = replace(base.attempts[0].result, items=provider_items)
    return replace(
        base,
        items=(first, second),
        attempts=(replace(base.attempts[0], result=result),),
    )


def _prepare(database: Database) -> None:
    repository = HotspotRepository(database)
    asyncio.run(repository.save_collection(_duplicate_weibo_result()))
    asyncio.run(
        repository.save_collection(
            _platform_result("bili-run", Platform.BILIBILI, "台风登陆广东")
        )
    )
    normalization = asyncio.run(HotspotNormalizationService(database).process_pending())
    assert len(normalization) == 2


def test_service_clusters_only_phase4_representatives_and_persists_evidence(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    _prepare(database)

    outcome = asyncio.run(HotspotClusteringService(database).process_current())

    assert outcome.state == "processed"
    assert outcome.input_group_count == 2
    assert outcome.event_count == 1
    assert outcome.candidate_pair_count == 1
    assert outcome.status.value == "success"
    with database.get_connection() as connection:
        run = connection.execute(
            """SELECT status, input_group_count, candidate_pair_count,
                      event_count, semantic_call_count, length(config_hash),
                      length(input_hash)
               FROM hotspot_clustering_runs"""
        ).fetchone()
        event = connection.execute(
            """SELECT canonical_title, member_count, platform_count
               FROM hotspot_events"""
        ).fetchone()
        members = connection.execute(
            """SELECT platform, is_representative
               FROM hotspot_event_members ORDER BY platform"""
        ).fetchall()
        candidate = connection.execute(
            """SELECT deterministic_score, decision, semantic_status,
                      recall_reasons_json, components_json
               FROM hotspot_cluster_candidates"""
        ).fetchone()
        raw_count = connection.execute(
            "SELECT COUNT(*) FROM hotspot_raw_items"
        ).fetchone()[0]

    assert tuple(run) == ("success", 2, 1, 1, 0, 64, 64)
    assert tuple(event) == ("台风登陆广东", 2, 2)
    assert {row["platform"] for row in members} == {"weibo", "bilibili"}
    assert sum(row["is_representative"] for row in members) == 1
    assert candidate["decision"] == "accepted"
    assert candidate["semantic_status"] == "not_requested"
    assert "exact_title" in candidate["recall_reasons_json"]
    assert "sequence" in candidate["components_json"]
    assert raw_count == 3


def test_same_input_is_idempotent_and_config_change_appends_new_run(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    _prepare(database)
    service = HotspotClusteringService(database)

    first = asyncio.run(service.process_current())
    second = asyncio.run(service.process_current())
    database.set_setting("hotspot_clustering_accept_threshold", "0.90")
    third = asyncio.run(service.process_current())

    assert first.state == "processed"
    assert second.state == "skipped_unchanged"
    assert third.state == "processed"
    with database.get_connection() as connection:
        counts = tuple(
            connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in (
                "hotspot_clustering_runs",
                "hotspot_events",
                "hotspot_event_members",
            )
        )
    assert counts == (2, 2, 4)


def test_no_normalized_groups_returns_explicit_no_input(tmp_path: Path) -> None:
    database = _database(tmp_path)

    outcome = asyncio.run(HotspotClusteringService(database).process_current())

    assert outcome.state == "no_input"
    assert outcome.clustering_run_id is None
    with database.get_connection() as connection:
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM hotspot_clustering_runs"
            ).fetchone()[0]
            == 0
        )


def test_historical_replay_anchors_lookback_to_latest_input_not_wall_clock(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    _prepare(database)

    outcome = asyncio.run(HotspotClusteringService(database).process_current())

    assert outcome.state == "processed"
    assert outcome.input_group_count == 2
