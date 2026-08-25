from datetime import datetime, timedelta, timezone

import pytest

from app.domain.hotspot import Platform, snapshot_window_for


def test_default_window_floors_to_half_hour_in_utc() -> None:
    at = datetime(2026, 8, 14, 16, 47, 21, tzinfo=timezone(timedelta(hours=8)))

    window = snapshot_window_for(Platform.WEIBO, at)

    assert window.start == datetime(2026, 8, 14, 8, 30, tzinfo=timezone.utc)
    assert window.end == datetime(2026, 8, 14, 9, 0, tzinfo=timezone.utc)
    assert window.lock_key == "hotspot:weibo:30:20260814T083000Z"


@pytest.mark.parametrize("interval", [0, 1441])
def test_window_rejects_invalid_interval(interval: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 1440"):
        snapshot_window_for(Platform.DOUYIN, datetime.now(timezone.utc), interval)


def test_window_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        snapshot_window_for(
            Platform.BILIBILI,
            datetime(2026, 8, 14, 8, 0),  # noqa: DTZ001 - intentionally naive
        )
