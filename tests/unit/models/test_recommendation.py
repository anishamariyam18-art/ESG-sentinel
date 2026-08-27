import pytest
from pydantic import ValidationError

from app.models.recommendation import (
    PriorityAction,
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
    RecommendationResult,
    TimeHorizon,
)


def _recommendation(**overrides) -> Recommendation:
    fields = dict(
        recommendation_id="REC-000001", title="Provide evidence for unsupported Environmental claims",
        problem="1 environmental claim(s) affected by unsupported claim.",
        source_claim_ids=["CLM-000001"], source_findings=["Claim CLM-000001 is unsupported by available evidence."],
        category=RecommendationCategory.ENVIRONMENTAL, priority=RecommendationPriority.HIGH, priority_score=85.0,
        action="Provide supporting evidence for the claim(s).", reason="Improves verification confidence.",
        expected_impact="Higher evidence coverage.", time_horizon=TimeHorizon.SHORT_TERM,
        explanation="Based on 1 claim(s): Claim CLM-000001 is unsupported by available evidence.",
    )
    fields.update(overrides)
    return Recommendation(**fields)


def test_recommendation_traces_to_source_claim_ids():
    rec = _recommendation()
    assert rec.source_claim_ids == ["CLM-000001"]
    assert rec.category == RecommendationCategory.ENVIRONMENTAL
    assert rec.priority == RecommendationPriority.HIGH


def test_recommendation_requires_nonempty_problem():
    with pytest.raises(ValidationError):
        _recommendation(problem="")


def test_recommendation_priority_score_bounded_0_to_100():
    with pytest.raises(ValidationError):
        _recommendation(priority_score=150.0)
    with pytest.raises(ValidationError):
        _recommendation(priority_score=-1.0)


def test_recommendation_rejects_invalid_category():
    with pytest.raises(ValidationError):
        _recommendation(category="Not A Category")


def test_priority_action_requires_fields():
    action = PriorityAction(recommendation_id="REC-000001", priority=RecommendationPriority.HIGH, action="Do X.", reason="Because Y.")
    assert action.priority == RecommendationPriority.HIGH


def test_recommendation_result_aggregates_list_and_defaults_empty():
    result = RecommendationResult(document_id="DOC-001", company="Example Company")
    assert result.recommendations == []
    assert result.priority_actions == []
    assert result.implementation_areas == []

    result_with_rec = RecommendationResult(
        document_id="DOC-001", company="Example Company", recommendations=[_recommendation()],
    )
    assert len(result_with_rec.recommendations) == 1
