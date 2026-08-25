"""Immutable Phase 4 normalization and deterministic dedup contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any

from .models import Platform


class NormalizationStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class PublishedAtPrecision(str, Enum):
    EXACT = "exact"
    MINUTE = "minute"
    DAY = "day"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SnapshotRawItem:
    snapshot_id: str
    raw_item_id: str
    position: int
    platform: Platform
    provider_id: str
    title: str
    url: str
    external_id: str | None
    rank: int | None
    hot_score: str | None
    published_at: datetime | None
    observed_at: datetime
    raw_data: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.snapshot_id or not self.raw_item_id:
            raise ValueError("snapshot and raw item identifiers cannot be empty")
        if self.position < 1:
            raise ValueError("position must be positive")
        if self.rank is not None and self.rank < 1:
            raise ValueError("rank must be positive")
        _require_aware(self.observed_at, "observed_at")
        if self.published_at is not None:
            _require_aware(self.published_at, "published_at")
        object.__setattr__(self, "raw_data", MappingProxyType(dict(self.raw_data)))


@dataclass(frozen=True, slots=True)
class NormalizedHotItem:
    normalized_item_id: str
    normalization_run_id: str
    snapshot_id: str
    raw_item_id: str
    position: int
    platform: Platform
    provider_id: str
    rank: int | None
    external_id_normalized: str | None
    normalized_title: str | None
    title_fingerprint: str | None
    canonical_url: str | None
    hot_score_value: str | None
    hot_score_unit: str | None
    published_at: datetime | None
    published_at_precision: PublishedAtPrecision
    status: NormalizationStatus
    warnings: tuple[str, ...]
    error_code: str | None
    rule_version: str

    def __post_init__(self) -> None:
        identifiers = (
            self.normalized_item_id,
            self.normalization_run_id,
            self.snapshot_id,
            self.raw_item_id,
            self.rule_version,
        )
        if any(not value for value in identifiers):
            raise ValueError(
                "normalized item identifiers and rule version are required"
            )
        if self.position < 1:
            raise ValueError("position must be positive")
        if self.rank is not None and self.rank < 1:
            raise ValueError("rank must be positive")
        if self.published_at is not None:
            _require_aware(self.published_at, "published_at")
        object.__setattr__(self, "warnings", tuple(self.warnings))
        if self.status is NormalizationStatus.FAILED:
            if self.error_code is None:
                raise ValueError("failed normalization requires an error code")
        elif self.error_code is not None:
            raise ValueError("non-failed normalization cannot contain an error code")


@dataclass(frozen=True, slots=True)
class DedupMember:
    normalized_item_id: str
    is_representative: bool
    match_kind: str
    evidence: tuple[dict[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.normalized_item_id or not self.match_kind:
            raise ValueError("dedup member identifiers cannot be empty")
        object.__setattr__(
            self,
            "evidence",
            tuple(MappingProxyType(dict(value)) for value in self.evidence),
        )


@dataclass(frozen=True, slots=True)
class DedupGroup:
    group_id: str
    normalization_run_id: str
    snapshot_id: str
    algorithm_version: str
    representative_normalized_item_id: str
    members: tuple[DedupMember, ...]

    def __post_init__(self) -> None:
        if not all(
            (
                self.group_id,
                self.normalization_run_id,
                self.snapshot_id,
                self.algorithm_version,
                self.representative_normalized_item_id,
            )
        ):
            raise ValueError("dedup group identifiers cannot be empty")
        object.__setattr__(self, "members", tuple(self.members))
        representative_count = sum(member.is_representative for member in self.members)
        if representative_count != 1:
            raise ValueError("dedup group must have exactly one representative")
        if self.representative_normalized_item_id not in {
            member.normalized_item_id for member in self.members
        }:
            raise ValueError("representative must be a group member")
        representative = next(
            member for member in self.members if member.is_representative
        )
        if representative.normalized_item_id != self.representative_normalized_item_id:
            raise ValueError("representative flag must match representative identifier")


@dataclass(frozen=True, slots=True)
class NormalizationBatch:
    normalization_run_id: str
    snapshot_id: str
    rule_version: str
    config_hash: str
    config_json: str
    algorithm_version: str
    started_at: datetime
    finished_at: datetime
    items: tuple[NormalizedHotItem, ...]
    groups: tuple[DedupGroup, ...]

    def __post_init__(self) -> None:
        if not all(
            (
                self.normalization_run_id,
                self.snapshot_id,
                self.rule_version,
                self.config_hash,
                self.algorithm_version,
            )
        ):
            raise ValueError("normalization batch identifiers cannot be empty")
        _require_aware(self.started_at, "started_at")
        _require_aware(self.finished_at, "finished_at")
        if self.finished_at < self.started_at:
            raise ValueError("normalization cannot finish before it starts")
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "groups", tuple(self.groups))

        if any(
            item.normalization_run_id != self.normalization_run_id
            or item.snapshot_id != self.snapshot_id
            or item.rule_version != self.rule_version
            for item in self.items
        ):
            raise ValueError("normalized items must belong to their batch")
        if any(
            group.normalization_run_id != self.normalization_run_id
            or group.snapshot_id != self.snapshot_id
            or group.algorithm_version != self.algorithm_version
            for group in self.groups
        ):
            raise ValueError("dedup groups must belong to their batch")

        expected = {
            item.normalized_item_id
            for item in self.items
            if item.status is not NormalizationStatus.FAILED
        }
        actual = [
            member.normalized_item_id
            for group in self.groups
            for member in group.members
        ]
        if set(actual) != expected or len(actual) != len(set(actual)):
            raise ValueError("dedup groups must cover each usable item exactly once")

    @property
    def status(self) -> NormalizationStatus:
        statuses = {item.status for item in self.items}
        if not statuses or statuses == {NormalizationStatus.SUCCESS}:
            return NormalizationStatus.SUCCESS
        if statuses == {NormalizationStatus.FAILED}:
            return NormalizationStatus.FAILED
        return NormalizationStatus.PARTIAL


def as_utc(value: datetime) -> datetime:
    _require_aware(value, "datetime")
    return value.astimezone(timezone.utc)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
