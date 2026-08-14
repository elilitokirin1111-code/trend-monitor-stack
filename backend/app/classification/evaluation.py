"""Offline metrics over a fixed, reviewable Phase 7 acceptance set."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from app.domain.hotspot import HospitalityRelevance, TopicCategory


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    case_id: str
    title: str
    expected_category: TopicCategory
    expected_relevance: HospitalityRelevance
    label_basis: str


@dataclass(frozen=True, slots=True)
class EvaluationPrediction:
    case_id: str
    category: TopicCategory
    relevance: HospitalityRelevance


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    case_count: int
    category_accuracy: Decimal
    relevance_accuracy: Decimal


def load_eval_cases() -> tuple[EvaluationCase, ...]:
    path = Path(__file__).with_name("eval_cases.json")
    values = json.loads(path.read_text(encoding="utf-8"))
    return tuple(
        EvaluationCase(
            case_id=value["case_id"],
            title=value["title"],
            expected_category=TopicCategory(value["expected_category"]),
            expected_relevance=HospitalityRelevance(value["expected_relevance"]),
            label_basis=value["label_basis"],
        )
        for value in values
    )


def evaluate_predictions(
    cases: tuple[EvaluationCase, ...],
    predictions: tuple[EvaluationPrediction, ...],
) -> EvaluationMetrics:
    if not cases:
        raise ValueError("evaluation requires at least one labeled case")
    indexed = {prediction.case_id: prediction for prediction in predictions}
    if len(indexed) != len(predictions):
        raise ValueError("evaluation predictions must have unique case ids")
    category_matches = sum(
        indexed.get(case.case_id) is not None
        and indexed[case.case_id].category is case.expected_category
        for case in cases
    )
    relevance_matches = sum(
        indexed.get(case.case_id) is not None
        and indexed[case.case_id].relevance is case.expected_relevance
        for case in cases
    )
    count = Decimal(len(cases))
    return EvaluationMetrics(
        case_count=len(cases),
        category_accuracy=Decimal(category_matches) / count,
        relevance_accuracy=Decimal(relevance_matches) / count,
    )
