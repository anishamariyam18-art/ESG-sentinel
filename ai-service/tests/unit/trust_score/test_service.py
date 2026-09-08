import json

from app.core.llm import LLMGenerationError
from app.models.claim import ClaimType
from app.models.greenwashing import RiskLevel
from app.models.trust import TrustRating
from app.models.verification import VerificationChecks, VerificationStatus
from app.trust_score.service import TrustScoreService
from tests.unit.trust_score.conftest import (
    build_claim,
    build_evidence_match,
    build_greenwashing_result,
    build_verification_result,
    make_manager,
    trust_rating_thresholds,
    trust_score_config,
    trust_weights,
)


def _make_service(llm_manager=None, **config_overrides):
    return TrustScoreService(
        llm_manager=llm_manager, weights=trust_weights(), rating_thresholds=trust_rating_thresholds(),
        config=trust_score_config(**config_overrides),
    )


# --- Critical test case (section 32), first scenario -----------------------

def test_critical_case_1_high_verification_low_greenwashing_gives_high_trust_score():
    claims = [build_claim(claim_id=f"CLM-{i:03d}") for i in range(100)]
    results = []
    for i in range(90):
        results.append(build_verification_result(
            claim_id=f"CLM-{i:03d}", status=VerificationStatus.VERIFIED,
            checks=VerificationChecks(numeric=1.0, unit=1.0, temporal=1.0, entity=1.0, category=1.0),
            matched_evidence=[build_evidence_match(evidence_id=f"EVD-{i:03d}", quality_score=0.95)],
        ))
    for i in range(90, 95):
        results.append(build_verification_result(
            claim_id=f"CLM-{i:03d}", status=VerificationStatus.PARTIALLY_VERIFIED,
            checks=VerificationChecks(numeric=0.7, unit=1.0, temporal=1.0, entity=0.7, category=1.0),
            matched_evidence=[build_evidence_match(evidence_id=f"EVD-{i:03d}", quality_score=0.8)],
        ))
    for i in range(95, 100):
        results.append(build_verification_result(
            claim_id=f"CLM-{i:03d}", status=VerificationStatus.UNSUPPORTED, matched_evidence=[],
        ))
    greenwashing = [
        build_greenwashing_result(claim_id=f"CLM-{i:03d}", greenwashing_risk=RiskLevel.LOW, greenwashing_score=3.0)
        for i in range(100)
    ]

    service = _make_service()
    result = service.calculate_trust_score("DOC-001", "Example Company", claims, results, greenwashing)

    assert result.rating in (TrustRating.EXCELLENT, TrustRating.GOOD)
    assert result.trust_score >= 70.0
    assert result.statistics.verified_claims == 90
    assert result.statistics.partially_verified_claims == 5
    assert result.statistics.unsupported_claims == 5
    joined = " ".join(result.explanation)
    assert "90" in joined
    assert "5" in joined


# --- Critical test case (section 32), second scenario -----------------------

def test_critical_case_2_low_verification_high_greenwashing_gives_low_trust_score():
    # Vague, unquantified claims (section 8/9) so `transparency` doesn't
    # mask the poor verification/evidence/provenance signals -- a report
    # this weakly supported would realistically also read as promotional
    # rather than specific.
    claims = [
        build_claim(
            claim_id=f"CLM-{i:03d}", claim="Our operations reflect a strong commitment to a sustainable future.",
            claim_type=ClaimType.GENERAL, value=None, unit=None,
        )
        for i in range(100)
    ]
    results = []
    for i in range(40):
        results.append(build_verification_result(
            claim_id=f"CLM-{i:03d}", status=VerificationStatus.VERIFIED,
            checks=VerificationChecks(numeric=1.0, unit=1.0, temporal=1.0, entity=1.0, category=1.0),
            matched_evidence=[build_evidence_match(evidence_id=f"EVD-{i:03d}", quality_score=0.6, source_chunk_id=None)],
        ))
    for i in range(40, 60):
        results.append(build_verification_result(
            claim_id=f"CLM-{i:03d}", status=VerificationStatus.PARTIALLY_VERIFIED,
            checks=VerificationChecks(numeric=0.2, unit=0.3, temporal=0.3, entity=0.2, category=0.5),
            matched_evidence=[build_evidence_match(evidence_id=f"EVD-{i:03d}", quality_score=0.3, page_number=None, source_chunk_id=None)],
        ))
    for i in range(60, 100):
        results.append(build_verification_result(
            claim_id=f"CLM-{i:03d}", status=VerificationStatus.UNSUPPORTED,
            checks=VerificationChecks(numeric=0.0, unit=0.1, temporal=0.1, entity=0.1, category=0.2),
            matched_evidence=[build_evidence_match(evidence_id=f"EVD-{i:03d}", quality_score=0.2, document_id=None, page_number=None, source_chunk_id=None)],
        ))
    greenwashing = [
        build_greenwashing_result(claim_id=f"CLM-{i:03d}", greenwashing_risk=RiskLevel.HIGH, greenwashing_score=80.0)
        for i in range(50)
    ] + [
        build_greenwashing_result(claim_id=f"CLM-{i:03d}", greenwashing_risk=RiskLevel.MEDIUM, greenwashing_score=45.0)
        for i in range(50, 100)
    ]

    service = _make_service()
    result = service.calculate_trust_score("DOC-001", "Example Company", claims, results, greenwashing)

    assert result.rating in (TrustRating.LOW, TrustRating.MODERATE)
    assert result.trust_score < 50.0
    weaknesses_and_explanation = " ".join(result.weaknesses + result.explanation).lower()
    assert "unsupported" in weaknesses_and_explanation
    assert "greenwashing" in weaknesses_and_explanation
    assert "evidence" in weaknesses_and_explanation or "provenance" in weaknesses_and_explanation


# --- Empty / missing data ---------------------------------------------------

def test_empty_claims_produces_zero_score_without_crashing():
    service = _make_service()
    result = service.calculate_trust_score("DOC-001", "Example Company", [], [], [])
    assert result.trust_score == 0.0
    assert result.confidence == 0.0
    assert result.statistics.total_claims == 0
    assert result.rating == TrustRating.LOW


def test_missing_verification_results_is_handled_explicitly():
    claims = [build_claim(claim_id="CLM-0"), build_claim(claim_id="CLM-1")]
    service = _make_service()
    result = service.calculate_trust_score("DOC-001", "Example Company", claims, [], [])
    assert result.trust_score < 100.0
    assert result.statistics.verification_coverage == 0.0


# --- 20/35: LLM never controls or blocks the numerical score ---------------

def test_20_llm_failure_does_not_affect_numerical_score():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(5)]
    results = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.VERIFIED) for i in range(5)]
    greenwashing = [build_greenwashing_result(claim_id=f"CLM-{i}") for i in range(5)]

    manager_ok, _ = make_manager([LLMGenerationError("simulated outage")], max_retries=0)
    service_with_failing_llm = _make_service(llm_manager=manager_ok)
    service_without_llm = _make_service(llm_manager=None)

    result_a = service_with_failing_llm.calculate_trust_score("DOC-001", "Example Company", claims, results, greenwashing)
    result_b = service_without_llm.calculate_trust_score("DOC-001", "Example Company", claims, results, greenwashing)

    assert result_a.trust_score == result_b.trust_score
    assert result_a.components == result_b.components


def test_35_llm_failure_still_returns_deterministic_explanation():
    claims = [build_claim(claim_id="CLM-0")]
    results = [build_verification_result(claim_id="CLM-0", status=VerificationStatus.VERIFIED)]
    greenwashing = [build_greenwashing_result(claim_id="CLM-0")]

    manager, provider = make_manager(["not valid json {{{"], max_retries=0)
    service = _make_service(llm_manager=manager)

    result = service.calculate_trust_score("DOC-001", "Example Company", claims, results, greenwashing)
    assert result.trust_score > 0.0
    assert result.explanation
    assert not any(line.startswith("LLM narrative:") for line in result.explanation)


def test_llm_narrative_is_appended_on_success():
    claims = [build_claim(claim_id="CLM-0")]
    results = [build_verification_result(claim_id="CLM-0", status=VerificationStatus.VERIFIED)]
    greenwashing = [build_greenwashing_result(claim_id="CLM-0")]

    manager, provider = make_manager(
        [json.dumps({"narrative": ["Most claims were well-supported by the available evidence."]})], max_retries=0
    )
    service = _make_service(llm_manager=manager)

    result = service.calculate_trust_score("DOC-001", "Example Company", claims, results, greenwashing)
    assert any(line.startswith("LLM narrative:") for line in result.explanation)
    assert len(provider.calls) == 1


def test_no_llm_call_when_manager_not_supplied():
    claims = [build_claim(claim_id="CLM-0")]
    results = [build_verification_result(claim_id="CLM-0", status=VerificationStatus.VERIFIED)]
    greenwashing = [build_greenwashing_result(claim_id="CLM-0")]

    service = _make_service(llm_manager=None)
    result = service.calculate_trust_score("DOC-001", "Example Company", claims, results, greenwashing)
    assert result.trust_score > 0.0  # never raises, never requires an LLM


def test_no_llm_call_when_narrative_disabled():
    claims = [build_claim(claim_id="CLM-0")]
    results = [build_verification_result(claim_id="CLM-0", status=VerificationStatus.VERIFIED)]
    greenwashing = [build_greenwashing_result(claim_id="CLM-0")]

    manager, provider = make_manager([json.dumps({"narrative": ["x"]})], max_retries=0)
    service = _make_service(llm_manager=manager, enable_llm_narrative=False)

    service.calculate_trust_score("DOC-001", "Example Company", claims, results, greenwashing)
    assert provider.calls == []


# --- Confidence vs. score independence --------------------------------------

def test_small_sample_gives_lower_confidence_than_large_sample_at_same_quality():
    small_claims = [build_claim(claim_id="CLM-0")]
    small_results = [build_verification_result(claim_id="CLM-0", status=VerificationStatus.VERIFIED)]
    small_gw = [build_greenwashing_result(claim_id="CLM-0")]

    large_claims = [build_claim(claim_id=f"CLM-{i}") for i in range(50)]
    large_results = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.VERIFIED) for i in range(50)]
    large_gw = [build_greenwashing_result(claim_id=f"CLM-{i}") for i in range(50)]

    service = _make_service()
    small_result = service.calculate_trust_score("DOC-001", "Example Company", small_claims, small_results, small_gw)
    large_result = service.calculate_trust_score("DOC-002", "Example Company", large_claims, large_results, large_gw)

    assert small_result.confidence < large_result.confidence
