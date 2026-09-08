from app.models.recommendation import RecommendationCategory, RecommendationPriority
from app.recommendations.prioritizer import calculate_priority_score, determine_priority
from app.recommendations.rules import Finding
from tests.unit.recommendations.conftest import recommendation_config, recommendation_priority_weights, recommendation_thresholds


def _finding(**overrides) -> Finding:
    fields = dict(
        finding_type="unsupported_claim", claim_id="CLM-000001", category=RecommendationCategory.ENVIRONMENTAL,
        severity=0.5, verification_impact=0.5, greenwashing_risk=0.0, trust_impact=0.5, claim_importance=0.5,
        description="text",
    )
    fields.update(overrides)
    return Finding(**fields)


# --- 14: Deterministic ------------------------------------------------------

def test_14_priority_score_is_deterministic():
    findings = [_finding(claim_id=f"CLM-{i}") for i in range(3)]
    weights = recommendation_priority_weights()
    config = recommendation_config()
    assert calculate_priority_score(findings, weights, config) == calculate_priority_score(findings, weights, config)


def test_empty_findings_gives_zero_priority_score():
    assert calculate_priority_score([], recommendation_priority_weights(), recommendation_config()) == 0.0


def test_more_severe_findings_score_higher():
    weak = [_finding(severity=0.2, verification_impact=0.2, trust_impact=0.2)]
    strong = [_finding(severity=0.9, verification_impact=0.9, trust_impact=0.9)]
    config = recommendation_config()
    weights = recommendation_priority_weights()
    assert calculate_priority_score(strong, weights, config) > calculate_priority_score(weak, weights, config)


def test_more_affected_claims_scores_higher_up_to_a_point():
    few = [_finding(claim_id="CLM-1")]
    many = [_finding(claim_id=f"CLM-{i}") for i in range(20)]
    config = recommendation_config(affected_claims_full_credit=10)
    weights = recommendation_priority_weights()
    assert calculate_priority_score(many, weights, config) > calculate_priority_score(few, weights, config)


def test_high_greenwashing_risk_increases_priority_score():
    low_risk = [_finding(greenwashing_risk=0.1)]
    high_risk = [_finding(greenwashing_risk=0.9)]
    config = recommendation_config()
    weights = recommendation_priority_weights()
    assert calculate_priority_score(high_risk, weights, config) > calculate_priority_score(low_risk, weights, config)


def test_high_greenwashing_risk_forces_high_priority_via_hard_override():
    """Section 7 lists 'high greenwashing risk' and 'explicit contradiction'
    as standalone High-priority triggers -- a single such finding must not
    be outvoted by an otherwise-moderate weighted score."""
    finding = _finding(
        finding_type="exaggerated_claim", severity=0.4, verification_impact=0.0, greenwashing_risk=0.4,
        trust_impact=0.4, claim_importance=0.5, hard_priority_override=True,
    )
    config = recommendation_config(affected_claims_full_credit=10)
    weights = recommendation_priority_weights()
    thresholds = recommendation_thresholds()
    score = calculate_priority_score([finding], weights, config)
    assert score < thresholds.high_priority_min  # the weighted score alone would NOT reach High
    assert determine_priority(score, thresholds, [finding]) == RecommendationPriority.HIGH


def test_no_hard_override_falls_back_to_weighted_score():
    finding = _finding(hard_priority_override=False, severity=0.1, verification_impact=0.1, trust_impact=0.1, greenwashing_risk=0.0)
    thresholds = recommendation_thresholds()
    score = calculate_priority_score([finding], recommendation_priority_weights(), recommendation_config())
    assert determine_priority(score, thresholds, [finding]) == RecommendationPriority.LOW


def test_priority_bands_follow_configured_thresholds():
    thresholds = recommendation_thresholds(high_priority_min=70.0, medium_priority_min=40.0)
    assert determine_priority(85.0, thresholds) == RecommendationPriority.HIGH
    assert determine_priority(50.0, thresholds) == RecommendationPriority.MEDIUM
    assert determine_priority(10.0, thresholds) == RecommendationPriority.LOW
