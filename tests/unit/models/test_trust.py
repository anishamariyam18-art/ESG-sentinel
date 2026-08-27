import pytest
from pydantic import ValidationError

from app.models.trust import TrustRating, TrustScore, TrustScoreComponents, TrustScoreStatistics


def _components(**overrides):
    fields = dict(
        claim_support=85.0, evidence_quality=90.0, consistency=80.0,
        transparency=75.0, greenwashing_risk=90.0, provenance=95.0,
    )
    fields.update(overrides)
    return TrustScoreComponents(**fields)


def _statistics(**overrides):
    fields = dict(
        total_claims=10, verified_claims=8, partially_verified_claims=1, unsupported_claims=1,
        high_greenwashing_claims=0, medium_greenwashing_claims=1, low_greenwashing_claims=9,
        evidence_coverage=90.0, verification_coverage=100.0, provenance_coverage=85.0,
    )
    fields.update(overrides)
    return TrustScoreStatistics(**fields)


def test_trust_score_valid_construction():
    score = TrustScore(
        document_id="DOC-001", company="Example Company", trust_score=78, rating=TrustRating.GOOD,
        confidence=82, components=_components(), statistics=_statistics(),
        explanation=["78% of claims were fully verified."],
    )
    assert score.trust_score == 78
    assert score.rating == TrustRating.GOOD
    assert score.components.provenance == 95.0


def test_trust_score_bounded_zero_to_hundred():
    with pytest.raises(ValidationError):
        TrustScore(
            document_id="DOC-001", company="Example Company", trust_score=150, rating=TrustRating.LOW,
            confidence=50, components=_components(), statistics=_statistics(),
        )


def test_trust_score_rejects_invalid_rating():
    with pytest.raises(ValidationError):
        TrustScore(
            document_id="DOC-001", company="Example Company", trust_score=50, rating="Amazing",
            confidence=50, components=_components(), statistics=_statistics(),
        )


def test_trust_score_components_bounded():
    with pytest.raises(ValidationError):
        _components(claim_support=150.0)
    with pytest.raises(ValidationError):
        _components(provenance=-1.0)


def test_trust_score_statistics_reject_negative_counts():
    with pytest.raises(ValidationError):
        _statistics(verified_claims=-1)


def test_trust_score_lists_default_to_empty():
    score = TrustScore(
        document_id="DOC-001", company="Example Company", trust_score=0, rating=TrustRating.LOW,
        confidence=0, components=_components(claim_support=0, evidence_quality=0, consistency=0,
                                              transparency=0, greenwashing_risk=0, provenance=0),
        statistics=_statistics(total_claims=0, verified_claims=0, partially_verified_claims=0,
                                unsupported_claims=0, high_greenwashing_claims=0, medium_greenwashing_claims=0,
                                low_greenwashing_claims=0, evidence_coverage=0, verification_coverage=0,
                                provenance_coverage=0),
    )
    assert score.explanation == []
    assert score.strengths == []
    assert score.weaknesses == []
    assert score.limitations == []
