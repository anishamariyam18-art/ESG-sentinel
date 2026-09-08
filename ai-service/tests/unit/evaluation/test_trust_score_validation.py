"""Trust Score validation (Phase 10 section 30) -- exercised against the
real, production `TrustScoreService`, not just the underlying scorer
functions (which already have their own dedicated Phase 8 unit tests).
Confirms the specific properties section 30 calls out; does not test the
score against any arbitrary expected company rating."""
from __future__ import annotations

from app.models.greenwashing import RiskLevel
from app.models.verification import VerificationChecks, VerificationStatus
from app.trust_score.service import TrustScoreService
from tests.unit.trust_score.conftest import build_claim, build_evidence_match, build_greenwashing_result, build_verification_result


def _service() -> TrustScoreService:
    return TrustScoreService()


def test_same_input_gives_the_same_trust_score():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(5)]
    results = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.VERIFIED) for i in range(5)]
    greenwashing = [build_greenwashing_result(claim_id=f"CLM-{i}") for i in range(5)]

    service = _service()
    score_a = service.calculate_trust_score("DOC-1", "Example Co", claims, results, greenwashing)
    score_b = service.calculate_trust_score("DOC-1", "Example Co", claims, results, greenwashing)
    assert score_a.trust_score == score_b.trust_score
    assert score_a.components == score_b.components


def test_changing_verification_results_changes_the_score():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(5)]
    all_verified = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.VERIFIED) for i in range(5)]
    all_unsupported = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.UNSUPPORTED, matched_evidence=[]) for i in range(5)]
    greenwashing = [build_greenwashing_result(claim_id=f"CLM-{i}") for i in range(5)]

    service = _service()
    verified_score = service.calculate_trust_score("DOC-1", "Example Co", claims, all_verified, greenwashing)
    unsupported_score = service.calculate_trust_score("DOC-1", "Example Co", claims, all_unsupported, greenwashing)
    assert verified_score.trust_score > unsupported_score.trust_score


def test_increasing_contradiction_decreases_consistency_component():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(5)]
    consistent = [build_verification_result(claim_id=f"CLM-{i}", checks=VerificationChecks(numeric=1.0, unit=1.0, temporal=1.0, entity=1.0, category=1.0)) for i in range(5)]
    contradicted = [build_verification_result(claim_id=f"CLM-{i}", checks=VerificationChecks(numeric=0.0, unit=1.0, temporal=1.0, entity=1.0, category=1.0)) for i in range(5)]
    greenwashing = [build_greenwashing_result(claim_id=f"CLM-{i}") for i in range(5)]

    service = _service()
    consistent_result = service.calculate_trust_score("DOC-1", "Example Co", claims, consistent, greenwashing)
    contradicted_result = service.calculate_trust_score("DOC-1", "Example Co", claims, contradicted, greenwashing)
    assert contradicted_result.components.consistency < consistent_result.components.consistency
    assert contradicted_result.trust_score < consistent_result.trust_score


def test_increasing_greenwashing_risk_decreases_trust_score():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(5)]
    results = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.VERIFIED) for i in range(5)]
    low_risk = [build_greenwashing_result(claim_id=f"CLM-{i}", greenwashing_risk=RiskLevel.LOW, greenwashing_score=5.0) for i in range(5)]
    high_risk = [build_greenwashing_result(claim_id=f"CLM-{i}", greenwashing_risk=RiskLevel.HIGH, greenwashing_score=85.0) for i in range(5)]

    service = _service()
    low_risk_result = service.calculate_trust_score("DOC-1", "Example Co", claims, results, low_risk)
    high_risk_result = service.calculate_trust_score("DOC-1", "Example Co", claims, results, high_risk)
    assert high_risk_result.components.greenwashing_risk < low_risk_result.components.greenwashing_risk
    assert high_risk_result.trust_score < low_risk_result.trust_score


def test_improving_evidence_support_increases_trust_score():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(5)]
    weak_evidence = [build_verification_result(claim_id=f"CLM-{i}", matched_evidence=[build_evidence_match(quality_score=0.2)]) for i in range(5)]
    strong_evidence = [build_verification_result(claim_id=f"CLM-{i}", matched_evidence=[build_evidence_match(quality_score=0.95)]) for i in range(5)]
    greenwashing = [build_greenwashing_result(claim_id=f"CLM-{i}") for i in range(5)]

    service = _service()
    weak_result = service.calculate_trust_score("DOC-1", "Example Co", claims, weak_evidence, greenwashing)
    strong_result = service.calculate_trust_score("DOC-1", "Example Co", claims, strong_evidence, greenwashing)
    assert strong_result.components.evidence_quality > weak_result.components.evidence_quality
    assert strong_result.trust_score > weak_result.trust_score
