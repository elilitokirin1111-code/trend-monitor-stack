from __future__ import annotations

from app.repositories.hotspot.annotations import AnnotationRepository
from app.repositories.hotspot.dashboard import HotspotDashboardRepository

from .test_dashboard_repository import _classified_database


def _event_id(database) -> str:
    return HotspotDashboardRepository(database).list_events(limit=10, offset=0)[
        "items"
    ][0]["event_id"]


def test_manual_annotations_are_append_only_and_latest_revision_wins(tmp_path) -> None:
    database = _classified_database(tmp_path)
    repository = AnnotationRepository(database)
    event_id = _event_id(database)

    first = repository.save_annotation(
        event_id=event_id,
        review_status="watch",
        topic_category="目的地天气",
        tags=["台风", "广东"],
        hospitality_relevance="possibly_relevant",
        decision_lane="risk_watch",
        notes="关注退改与住客安全。",
        summary_override=None,
        updated_by="reviewer-a",
    )
    second = repository.save_annotation(
        event_id=event_id,
        review_status="reviewed",
        topic_category="酒旅风险",
        tags=["台风", "酒店运营"],
        hospitality_relevance="relevant",
        decision_lane="risk_watch",
        notes="已确认影响广东门店。",
        summary_override="台风可能影响广东门店入住与交通。",
        updated_by="reviewer-b",
    )

    assert first is not None and first["revision"] == 1
    assert second is not None and second["revision"] == 2
    latest = repository.get_latest_for_event(event_id)
    assert latest == second
    assert latest["updated_by"] == "reviewer-b"
    assert repository.get_annotation(first["annotation_id"]) == first


def test_annotation_rejects_unknown_event_without_creating_data(tmp_path) -> None:
    database = _classified_database(tmp_path)
    repository = AnnotationRepository(database)

    result = repository.save_annotation(
        event_id="missing-event",
        review_status="reviewed",
        topic_category=None,
        tags=[],
        hospitality_relevance=None,
        decision_lane=None,
        notes=None,
        summary_override=None,
        updated_by="reviewer",
    )

    assert result is None
