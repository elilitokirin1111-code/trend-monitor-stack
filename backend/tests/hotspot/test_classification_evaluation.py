from __future__ import annotations

from app.classification import (
    EvaluationPrediction,
    evaluate_predictions,
    load_eval_cases,
)


def test_fixed_reviewable_eval_set_and_metrics_are_not_model_self_scores() -> None:
    cases = load_eval_cases()
    assert len(cases) >= 12
    assert all(case.expected_category and case.expected_relevance for case in cases)

    predictions = tuple(
        EvaluationPrediction(
            case_id=case.case_id,
            category=case.expected_category,
            relevance=case.expected_relevance,
        )
        for case in cases
    )
    metrics = evaluate_predictions(cases, predictions)

    assert metrics.case_count == len(cases)
    assert metrics.category_accuracy == 1
    assert metrics.relevance_accuracy == 1


def test_evaluator_counts_missing_predictions_as_incorrect() -> None:
    cases = load_eval_cases()[:2]
    metrics = evaluate_predictions(cases, ())

    assert metrics.case_count == 2
    assert metrics.category_accuracy == 0
    assert metrics.relevance_accuracy == 0
