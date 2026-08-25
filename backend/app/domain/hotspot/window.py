"""Time-window primitives for immutable hotspot snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .models import Platform


@dataclass(frozen=True, slots=True)
class SnapshotWindow:
    """A half-open UTC collection window: ``[start, end)``."""

    platform: Platform
    start: datetime
    end: datetime
    interval_minutes: int

    def __post_init__(self) -> None:
        if not 1 <= self.interval_minutes <= 1440:
            raise ValueError("interval_minutes must be between 1 and 1440")
        for name, value in (("start", self.start), ("end", self.end)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            if value.utcoffset() != timedelta(0):
                raise ValueError(f"{name} must be UTC")
        if self.end - self.start != timedelta(minutes=self.interval_minutes):
            raise ValueError("snapshot window length does not match interval")

    @property
    def lock_key(self) -> str:
        start = self.start.strftime("%Y%m%dT%H%M%SZ")
        return f"hotspot:{self.platform.value}:{self.interval_minutes}:{start}"


def snapshot_window_for(
    platform: Platform,
    at: datetime,
    interval_minutes: int = 30,
) -> SnapshotWindow:
    """Floor a timestamp into a deterministic UTC snapshot window."""
    if not 1 <= interval_minutes <= 1440:
        raise ValueError("interval_minutes must be between 1 and 1440")
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("at must be timezone-aware")

    utc_at = at.astimezone(timezone.utc)
    interval_seconds = interval_minutes * 60
    start_epoch = int(utc_at.timestamp()) // interval_seconds * interval_seconds
    start = datetime.fromtimestamp(start_epoch, tz=timezone.utc)
    return SnapshotWindow(
        platform=platform,
        start=start,
        end=start + timedelta(minutes=interval_minutes),
        interval_minutes=interval_minutes,
    )
