from app.models.recommendation import Recommendation, RecommendationCategory, RecommendationPriority, TimeHorizon
from app.recommendations.explainability import (
    build_implementation_areas,
    build_limitations,
    build_overall_assessment,
    build_recommendation_explanation,
    derive_strengths,
    derive_weaknesses,
)
from app.recommendations.rules import Finding
from tests.unit.recommendations.conftest import build_trust_score, recommendation_config


def _finding(**overrides) -> Finding:
    fields = dict(finding_type="unsupported_claim", claim_id="CLM-000001", category=RecommendationCategory.ENVIRONMENTAL, severity=0.5, description="Claim CLM-000001 is unsupported.")
    fields.update(overrides)
    return Finding(**fields)


def _recommendation(**overrides) -> Recommendation:
    fields = dict(
        recommendation_id="REC-000001", title="t", problem="p", source_claim_ids=["CLM-000001"], source_findings=["f"],
        category=RecommendationCategory.ENVIRONMENTAL, priority=RecommendationPriority.HIGH, priority_score=85.0,
        action="a", reason="r", expected_impact="e", time_horizon=TimeHorizon.SHORT_TERM, explanation="exp",
    )
    fields.update(overrides)
    return Recommendation(**fields)


# --- 18: Actionability / explanation grounded in real findings -------------

def test_18_recommendation_explanation_references_actual_claim_ids():
    findings = [_finding(claim_id="CLM-000001"), _finding(claim_id="CLM-000002")]
    explanation = build_recommendation_explanation(findings, recommendation_config())
    assert "2 claim(s)" in explanation
    assert "CLM-000001" in explanation or "unsupported" in explanation.lower()


def test_explanation_caps_displayed_findings_but_notes_the_remainder():
    findings = [_finding(claim_id=f"CLM-{i}", description=f"Claim CLM-{i} is unsupported.") for i in range(8)]
    explanation = build_recommendation_explanation(findings, recommendation_config(max_source_findings_per_recommendation=3))
    assert "and 5 more" in explanation


def test_explanation_for_report_level_finding_has_no_claim_count():
    findings = [_finding(claim_id=None, description="Trust Score component 'consistency' is weak.")]
    explanation = build_recommendation_explanation(findings, recommendation_config())
    assert "report-level findings" in explanation.lower()


# --- 18/20: Strengths reused from Trust Score, not re-derived --------------

def test_strengths_are_reused_from_trust_score_verbatim():
    trust_score = build_trust_score(strengths=["92% of claims were verified against source-level evidence."])
    assert derive_strengths(trust_score) == ["92% of claims were verified against source-level evidence."]


def test_weaknesses_are_reused_from_trust_score_verbatim():
    trust_score = build_trust_score(weaknesses=["15% of claims were unsupported by available evidence."])
    assert derive_weaknesses(trust_score) == ["15% of claims were unsupported by available evidence."]


# --- Implementation areas ----------------------------------------------------

def test_implementation_areas_deduplicated_and_ordered():
    recs = [
        _recommendation(category=RecommendationCategory.GOVERNANCE),
        _recommendation(category=RecommendationCategory.ENVIRONMENTAL),
        _recommendation(category=RecommendationCategory.ENVIRONMENTAL),
    ]
    areas = build_implementation_areas(recs)
    assert areas == ["Environmental", "Governance"]


def test_implementation_areas_empty_when_no_recommendations():
    assert build_implementation_areas([]) == []


# --- 22: Overall assessment based on actual calculated results -------------

def test_22_overall_assessment_mentions_trust_score_and_rating():
    trust_score = build_trust_score(trust_score=72.0)
    assessment = build_overall_assessment(trust_score, [_recommendation()])
    assert "72.0" in assessment
    assert trust_score.rating.value in assessment


def test_overall_assessment_empty_claims_says_so():
    trust_score = build_trust_score(total_claims=0, verified_claims=0, partially_verified_claims=0, unsupported_claims=0)
    assessment = build_overall_assessment(trust_score, [])
    assert "no esg claims" in assessment.lower()


# --- 33: Near-perfect report gets a maintenance message, not fake weaknesses ---

def test_33_no_recommendations_yields_maintenance_message():
    trust_score = build_trust_score(trust_score=92.0)
    assessment = build_overall_assessment(trust_score, [])
    assert "maintain" in assessment.lower()


# --- 23: Limitations never assert fraud, always disclose no external data --

def test_23_limitations_disclose_no_external_standards_used():
    trust_score = build_trust_score()
    limitations = build_limitations(trust_score)
    joined = " ".join(limitations).lower()
    assert "external" in joined
    assert "regulatory" in joined or "standards" in joined
