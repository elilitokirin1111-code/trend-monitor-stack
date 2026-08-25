"""Optional semantic boundary port; no production model is coupled to Phase 5."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.domain.hotspot import ClusterInputItem


@dataclass(frozen=True, slots=True)
class SemanticBoundaryResult:
    same_event: bool
    confidence: Decimal | None
    reason: str
    model_id: str

    def __post_init__(self) -> None:
        if type(self.same_event) is not bool:  # bool only, not truthy model output
            raise ValueError("same_event must be a boolean")
        if self.confidence is not None:
            confidence = Decimal(str(self.confidence))
            if not confidence.is_finite() or not Decimal(0) <= confidence <= Decimal(1):
                raise ValueError("semantic confidence must be between zero and one")
            object.__setattr__(self, "confidence", confidence)
        if not self.reason.strip() or not self.model_id.strip():
            raise ValueError("semantic reason and model identifier are required")


class SemanticBoundaryJudge(Protocol):
    async def judge(
        self,
        left: ClusterInputItem,
        right: ClusterInputItem,
        evidence: Mapping[str, str],
    ) -> SemanticBoundaryResult: ...
