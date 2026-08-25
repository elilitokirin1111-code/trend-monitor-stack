"""Deterministic hotspot normalization and basic deduplication."""

from .engine import HotspotNormalizer
from .rules import NormalizationRules

__all__ = ["HotspotNormalizer", "NormalizationRules"]
