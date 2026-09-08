import math

import pytest
from pydantic import ValidationError

from app.models.claim import ClaimCategory, ClaimType
from app.models.evidence import EvidenceMatch, SourceType
from app.models.greenwashing import RiskLevel
from app.models.trust import TrustRating, TrustScoreComponents
from app.models.verification import VerificationChecks, VerificationStatus
from app.trust_score.scorer import (
    _clamp,
    calculate_claim_support,
    calculate_confidence,
    calculate_consistency,
    calculate_evidence_quality,
    calculate_final_score,
    calculate_greenwashing_component,
    calculate_provenance,
    calculate_transparency,
    determine_rating,
    evidence_provenance_completeness,
)
from tests.unit.trust_score.conftest import (
    build_claim,
    build_evidence_match,
    build_greenwashing_result,
    build_verification_result,
    trust_rating_thresholds,
    trust_score_config,
    trust_weights,
)


# --- Normalization -------------------------------------------------------

def test_clamp_never_exceeds_100_or_goes_below_0():
    assert _clamp(1000.0) == 100.0
    assert _clamp(-50.0) == 0.0


def test_clamp_handles_nan_and_infinity():
    """A non-finite value is fail-safe clamped to the low bound (0.0) --
    never propagated as a fabricated high score."""
    assert _clamp(float("nan")) == 0.0
    assert _clamp(float("inf")) == 0.0
    assert _clamp(float("-inf")) == 0.0
    assert math.isfinite(_clamp(float("inf")))
    assert math.isfinite(_clamp(float("-inf")))


# --- 1-3: Claim support (verified / partial / unsupported) ---------------

def test_1_all_claims_verified_gives_high_claim_support():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(5)]
    results = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.VERIFIED) for i in range(5)]
    score = calculate_claim_support(claims, results, trust_score_config())
    assert score == 100.0


def test_2_some_claims_partially_verified_reduces_claim_support():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(4)]
    results = [
        build_verification_result(claim_id="CLM-0", status=VerificationStatus.VERIFIED),
        build_verification_result(claim_id="CLM-1", status=VerificationStatus.VERIFIED),
        build_verification_result(claim_id="CLM-2", status=VerificationStatus.PARTIALLY_VERIFIED),
        build_verification_result(claim_id="CLM-3", status=VerificationStatus.PARTIALLY_VERIFIED),
    ]
    score = calculate_claim_support(claims, results, trust_score_config())
    assert 0.0 < score < 100.0


def test_3_unsupported_claims_give_little_to_no_claim_support():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(3)]
    results = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.UNSUPPORTED) for i in range(3)]
    score = calculate_claim_support(claims, results, trust_score_config())
    assert score == 0.0


# --- 4-5: Greenwashing component -----------------------------------------

def test_4_high_greenwashing_risk_lowers_the_component():
    results = [build_greenwashing_result(claim_id=f"CLM-{i}", greenwashing_risk=RiskLevel.HIGH, greenwashing_score=85.0) for i in range(5)]
    score = calculate_greenwashing_component(results, trust_score_config())
    assert score < 30.0


def test_5_low_greenwashing_risk_keeps_the_component_high():
    results = [build_greenwashing_result(claim_id=f"CLM-{i}", greenwashing_risk=RiskLevel.LOW, greenwashing_score=5.0) for i in range(5)]
    score = calculate_greenwashing_component(results, trust_score_config())
    assert score >= 90.0


def test_greenwashing_component_does_not_simply_subtract_score_from_100():
    """Section 9: a fraction of High-risk claims must push the component
    below the flat average (100 - mean(greenwashing_score)) -- a bare
    subtraction would treat every claim's risk level as irrelevant."""
    results = [
        build_greenwashing_result(claim_id="CLM-0", greenwashing_risk=RiskLevel.HIGH, greenwashing_score=65.0),
        build_greenwashing_result(claim_id="CLM-1", greenwashing_risk=RiskLevel.LOW, greenwashing_score=5.0),
        build_greenwashing_result(claim_id="CLM-2", greenwashing_risk=RiskLevel.LOW, greenwashing_score=5.0),
        build_greenwashing_result(claim_id="CLM-3", greenwashing_risk=RiskLevel.LOW, greenwashing_score=5.0),
    ]
    flat_average = 100.0 - sum(r.greenwashing_score for r in results) / len(results)
    score = calculate_greenwashing_component(results, trust_score_config())
    assert score < flat_average


def test_greenwashing_component_neutral_default_when_no_data():
    config = trust_score_config()
    assert calculate_greenwashing_component([], config) == config.no_greenwashing_data_default


# --- 6-7: Provenance -------------------------------------------------------

def test_6_strong_provenance_scores_high():
    claims = [build_claim(claim_id="CLM-0")]
    results = [build_verification_result(claim_id="CLM-0", matched_evidence=[
        build_evidence_match(evidence_id="EVD-1", document_id="DOC-1", page_number=3, source_chunk_id="CHK-1")
    ])]
    score = calculate_provenance(claims, results)
    assert score == 100.0


def test_7_missing_provenance_scores_low():
    claims = [build_claim(claim_id="CLM-0")]
    results = [build_verification_result(claim_id="CLM-0", matched_evidence=[])]  # no evidence match at all
    score = calculate_provenance(claims, results)
    assert score == 0.0


def test_34_case_a_full_provenance_beats_case_b_no_provenance():
    case_a = build_evidence_match(evidence_id="EVD-A", document_id="DOC-1", page_number=1, source_chunk_id="CHK-1")
    case_b = EvidenceMatch(evidence_id="EVD-B", source_type=SourceType.EXTERNAL_REPORT, company="Example Company",
                            evidence_text="text", document_id=None, page_number=None, source_chunk_id=None)
    assert evidence_provenance_completeness(case_a) > evidence_provenance_completeness(case_b)
    assert evidence_provenance_completeness(case_a) == 1.0
    assert evidence_provenance_completeness(case_b) == 0.25  # evidence_id alone is present


# --- 8-9, 33: Consistency --------------------------------------------------

def test_8_numerical_inconsistencies_reduce_consistency():
    clean = [build_verification_result(claim_id="CLM-0", checks=VerificationChecks(numeric=1.0, unit=1.0, temporal=1.0, entity=1.0, category=1.0))]
    mismatched = [build_verification_result(claim_id="CLM-0", checks=VerificationChecks(numeric=0.0, unit=1.0, temporal=1.0, entity=1.0, category=1.0))]
    assert calculate_consistency(mismatched) < calculate_consistency(clean)


def test_9_temporal_inconsistencies_reduce_consistency():
    clean = [build_verification_result(claim_id="CLM-0", checks=VerificationChecks(numeric=1.0, unit=1.0, temporal=1.0, entity=1.0, category=1.0))]
    mismatched = [build_verification_result(claim_id="CLM-0", checks=VerificationChecks(numeric=1.0, unit=1.0, temporal=0.0, entity=1.0, category=1.0))]
    assert calculate_consistency(mismatched) < calculate_consistency(clean)


def test_33_many_numerical_contradictions_reduce_consistency_more_than_none():
    no_contradictions = [
        build_verification_result(claim_id=f"CLM-{i}", checks=VerificationChecks(numeric=1.0, unit=1.0, temporal=1.0, entity=1.0, category=1.0))
        for i in range(10)
    ]
    ten_contradictions = [
        build_verification_result(claim_id=f"CLM-{i}", checks=VerificationChecks(numeric=0.0, unit=1.0, temporal=1.0, entity=1.0, category=1.0))
        for i in range(10)
    ]
    assert calculate_consistency(ten_contradictions) < calculate_consistency(no_contradictions)


# --- 10-11: Evidence quality -------------------------------------------------

def test_10_strong_evidence_coverage_scores_high():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(3)]
    results = [build_verification_result(claim_id=f"CLM-{i}", matched_evidence=[build_evidence_match(quality_score=0.95)]) for i in range(3)]
    assert calculate_evidence_quality(claims, results) >= 90.0


def test_11_weak_evidence_coverage_scores_low():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(3)]
    results = [build_verification_result(claim_id="CLM-0", matched_evidence=[])]  # only 1 of 3 claims even has a result
    assert calculate_evidence_quality(claims, results) < 20.0


# --- Transparency -----------------------------------------------------------

def test_transparency_does_not_penalize_inapplicable_target_year():
    governance_claim = build_claim(
        claim_id="CLM-0", claim="The board adopted a formal anti-corruption policy.",
        category=ClaimCategory.GOVERNANCE, claim_type=ClaimType.POLICY, value=None, unit=None,
        target="Anti-Corruption Policy", target_year=None,
    )
    score = calculate_transparency([governance_claim])
    assert score == 100.0  # every applicable criterion (specificity + named policy) is met


def test_transparency_rewards_quantified_claims_with_target_year():
    claim = build_claim(
        claim_id="CLM-0", claim="We commit to reducing Scope 1 emissions by 50% by 2030.",
        claim_type=ClaimType.COMMITMENT, value=50.0, unit="%", target="Net Zero", target_year=2030,
    )
    score = calculate_transparency([claim])
    assert score == 100.0


def test_transparency_penalizes_vague_unquantified_claims():
    claim = build_claim(claim_id="CLM-0", claim="We are committed to a greener future.", claim_type=ClaimType.GENERAL, value=None, unit=None)
    score = calculate_transparency([claim])
    assert score == 0.0


# --- 12: Confidence (sample size) -------------------------------------------

def test_12_very_small_claim_sample_lowers_confidence_not_score():
    config = trust_score_config()
    small_components = TrustScoreComponents(claim_support=90, evidence_quality=90, consistency=90, transparency=90, greenwashing_risk=90, provenance=90)
    small_confidence = calculate_confidence(2, 100.0, 100.0, 100.0, small_components, config)
    large_confidence = calculate_confidence(200, 100.0, 100.0, 100.0, small_components, config)
    assert small_confidence < large_confidence


# --- 13: Empty claims ---------------------------------------------------

def test_13_empty_claims_gives_zero_components_not_a_crash():
    assert calculate_claim_support([], [], trust_score_config()) == 0.0
    assert calculate_evidence_quality([], []) == 0.0
    assert calculate_consistency([]) == 0.0
    assert calculate_transparency([]) == 0.0
    assert calculate_provenance([], []) == 0.0
    assert calculate_confidence(0, 0.0, 0.0, 0.0, TrustScoreComponents(claim_support=0, evidence_quality=0, consistency=0, transparency=0, greenwashing_risk=0, provenance=0), trust_score_config()) == 0.0


# --- 14: Missing verification results ------------------------------------

def test_14_claim_with_no_verification_result_contributes_zero_not_assumed_verified():
    claims = [build_claim(claim_id="CLM-0"), build_claim(claim_id="CLM-1")]
    results = [build_verification_result(claim_id="CLM-0", status=VerificationStatus.VERIFIED)]  # CLM-1 has none
    score = calculate_claim_support(claims, results, trust_score_config())
    assert score < 100.0


# --- 15-17: Component/score bounds ----------------------------------------

def test_15_invalid_component_values_are_rejected_by_the_model():
    with pytest.raises(ValidationError):
        TrustScoreComponents(claim_support=-1, evidence_quality=0, consistency=0, transparency=0, greenwashing_risk=0, provenance=0)
    with pytest.raises(ValidationError):
        TrustScoreComponents(claim_support=0, evidence_quality=0, consistency=0, transparency=0, greenwashing_risk=0, provenance=200)


def test_16_final_score_cannot_exceed_100():
    components = TrustScoreComponents(claim_support=100, evidence_quality=100, consistency=100, transparency=100, greenwashing_risk=100, provenance=100)
    score = calculate_final_score(components, trust_weights())
    assert score <= 100.0


def test_17_final_score_cannot_go_below_0():
    components = TrustScoreComponents(claim_support=0, evidence_quality=0, consistency=0, transparency=0, greenwashing_risk=0, provenance=0)
    score = calculate_final_score(components, trust_weights())
    assert score >= 0.0


# --- 18: Weights validated (also see tests/unit/test_config.py) ----------

def test_18_weights_must_sum_to_one():
    with pytest.raises(ValidationError):
        trust_weights(claim_support=0.99)


# --- 19: Deterministic --------------------------------------------------

def test_19_final_score_is_deterministic():
    components = TrustScoreComponents(claim_support=85, evidence_quality=90, consistency=80, transparency=75, greenwashing_risk=90, provenance=95)
    weights = trust_weights()
    assert calculate_final_score(components, weights) == calculate_final_score(components, weights)


# --- Section 29 worked example --------------------------------------------

def test_section_29_worked_example():
    components = TrustScoreComponents(claim_support=85, evidence_quality=90, consistency=80, transparency=75, greenwashing_risk=90, provenance=95)
    weights = trust_weights()
    expected = (85 * 0.30 + 90 * 0.20 + 80 * 0.15 + 75 * 0.15 + 90 * 0.15 + 95 * 0.05)
    score = calculate_final_score(components, weights)
    assert score == round(expected, 2)


# --- Rating thresholds -----------------------------------------------------

def test_rating_bands_follow_configured_thresholds():
    thresholds = trust_rating_thresholds()
    assert determine_rating(85.0, thresholds) == TrustRating.EXCELLENT
    assert determine_rating(70.0, thresholds) == TrustRating.GOOD
    assert determine_rating(45.0, thresholds) == TrustRating.MODERATE
    assert determine_rating(10.0, thresholds) == TrustRating.LOW
