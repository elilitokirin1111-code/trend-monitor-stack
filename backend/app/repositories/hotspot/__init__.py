"""Append-only hotspot persistence."""

from .classifications import ClassificationRepository, ClassificationRepositoryInput
from .clustering import ClusteringRepository
from .dashboard import HotspotDashboardRepository
from .migrations import HotspotMigrationRunner, MigrationDriftError
from .normalization import NormalizationRepository
from .reports import ReportRepository
from .repository import HotspotRepository, WindowedCollectionWriter
from .trends import StoredPreviousTrend, TrendRepository, TrendRepositoryInput

__all__ = [
    "ClassificationRepository",
    "ClassificationRepositoryInput",
    "ClusteringRepository",
    "HotspotDashboardRepository",
    "HotspotMigrationRunner",
    "HotspotRepository",
    "MigrationDriftError",
    "NormalizationRepository",
    "ReportRepository",
    "StoredPreviousTrend",
    "TrendRepository",
    "TrendRepositoryInput",
    "WindowedCollectionWriter",
]
