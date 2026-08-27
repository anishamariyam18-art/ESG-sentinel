from app.models.verification import VerificationChecks, VerificationStatus
from app.verification.scorer import compute_confidence_score, compute_verification_score, determine_status
from tests.unit.verification.conftest import (
    verification_confidence_weights,
    verification_thresholds,
    verification_weights,
)


def _full_checks(**overrides) -> VerificationChecks:
    fields = dict(
        semantic=1.0, lexical=1.0, numeric=1.0, unit=1.0, temporal=1.0,
        entity=1.0, category=1.0, llm_support=1.0, provenance=1.0,
    )
    fields.update(overrides)
    return VerificationChecks(**fields)


def test_compute_verification_score_all_ones_is_100():
    score = compute_verification_score(_full_checks(), verification_weights())
    assert score == 100.0


def test_compute_verification_score_all_zeros_is_0():
    score = compute_verification_score(_full_checks(
        semantic=0, lexical=0, numeric=0, unit=0, temporal=0, entity=0, category=0, llm_support=0, provenance=0,
    ), verification_weights())
    assert score == 0.0


def test_compute_verification_score_reflects_documented_weights():
    weights = verification_weights()
    checks = _full_checks(numeric=0.0)
    score = compute_verification_score(checks, weights)
    expected = round((1.0 - weights.numeric) * 100, 2)
    assert score == expected


def test_determine_status_verified_above_threshold():
    status = determine_status(85.0, [], verification_thresholds())
    assert status == VerificationStatus.VERIFIED


def test_determine_status_partially_verified_in_range():
    status = determine_status(70.0, [], verification_thresholds())
    assert status == VerificationStatus.PARTIALLY_VERIFIED


def test_determine_status_unsupported_below_threshold():
    status = determine_status(30.0, [], verification_thresholds())
    assert status == VerificationStatus.UNSUPPORTED


def test_determine_status_wrong_company_forces_unsupported_even_with_high_score():
    status = determine_status(95.0, ["wrong_company"], verification_thresholds())
    assert status == VerificationStatus.UNSUPPORTED


def test_determine_status_explicit_contradiction_forces_unsupported():
    status = determine_status(90.0, ["explicit_contradiction"], verification_thresholds())
    assert status == VerificationStatus.UNSUPPORTED


def test_determine_status_moderate_hard_fail_caps_below_verified():
    # High score but a numeric contradiction was flagged -- must never reach Verified.
    status = determine_status(95.0, ["numeric_contradiction"], verification_thresholds())
    assert status == VerificationStatus.PARTIALLY_VERIFIED


def test_determine_status_moderate_hard_fail_does_not_raise_a_low_score():
    status = determine_status(30.0, ["unit_incompatible"], verification_thresholds())
    assert status == VerificationStatus.UNSUPPORTED


def test_compute_confidence_score_bounded_zero_to_hundred():
    confidence = compute_confidence_score(_full_checks(), True, [90.0, 88.0], 2, verification_confidence_weights())
    assert 0.0 <= confidence <= 100.0


def test_compute_confidence_score_lower_when_llm_unavailable():
    with_llm = compute_confidence_score(_full_checks(), True, [90.0], 1, verification_confidence_weights())
    without_llm = compute_confidence_score(_full_checks(), False, [90.0], 1, verification_confidence_weights())
    assert without_llm < with_llm


def test_compute_confidence_score_lower_with_no_evidence():
    with_evidence = compute_confidence_score(_full_checks(), True, [90.0], 1, verification_confidence_weights())
    no_evidence = compute_confidence_score(_full_checks(), False, [], 0, verification_confidence_weights())
    assert no_evidence < with_evidence


def test_compute_confidence_score_lower_when_candidates_disagree():
    agreement = compute_confidence_score(_full_checks(), True, [90.0, 91.0], 2, verification_confidence_weights())
    disagreement = compute_confidence_score(_full_checks(), True, [95.0, 10.0], 2, verification_confidence_weights())
    assert disagreement < agreement
