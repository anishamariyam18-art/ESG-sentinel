import json

from app.greenwashing.service import GreenwashingService
from app.models.greenwashing import GreenwashingType, RiskLevel
from app.models.verification import VerificationStatus
from tests.unit.greenwashing.conftest import (
    build_claim,
    build_evidence_match,
    build_verification_result,
    greenwashing_aggregation,
    greenwashing_confidence_weights,
    greenwashing_thresholds,
    greenwashing_weights,
    make_manager,
    verification_thresholds,
)


def _service(manager, aggregation=None):
    return GreenwashingService(
        llm_manager=manager, weights=greenwashing_weights(), confidence_weights=greenwashing_confidence_weights(),
        thresholds=greenwashing_thresholds(), aggregation_config=aggregation or greenwashing_aggregation(max_schema_retries=0),
        verification_thresholds=verification_thresholds(),
    )


def _judgment(risk="low", reasoning=None):
    return json.dumps({"risk_assessment": risk, "reasoning": reasoning or [], "intent_assumed": False})


# --- Critical tests (section 29) ----------------------------------------

def test_critical_1_supported_claim_is_low_risk():
    claim = build_claim(claim="We reduced Scope 1 emissions by 20%.", value=20.0, unit="%")
    match = build_evidence_match(evidence_text="Scope 1 emissions decreased by 20%.")
    vr = build_verification_result(status=VerificationStatus.VERIFIED, verification_score=95.0, matched_evidence=[match])
    manager, provider = make_manager([], max_retries=0)  # no signals -> no LLM call expected

    result = _service(manager).analyze_claim(claim, vr)

    assert result.verification_status == VerificationStatus.VERIFIED
    assert result.greenwashing_risk == RiskLevel.LOW
    assert provider.calls == []


def test_critical_2_exaggeration_is_elevated_with_explicit_numbers_in_explanation():
    claim = build_claim(claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    match = build_evidence_match(evidence_text="Scope 1 emissions decreased by 20%.")
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=20.0, matched_evidence=[match])
    manager, _ = make_manager([_judgment("high", ["Large discrepancy between claimed and evidenced value."])], max_retries=0)

    result = _service(manager).analyze_claim(claim, vr)

    assert result.greenwashing_risk in (RiskLevel.MEDIUM, RiskLevel.HIGH)
    assert GreenwashingType.EXAGGERATED_CLAIM in result.greenwashing_type
    assert any("80.0%" in line for line in result.explanation)
    assert any("20.0%" in line for line in result.explanation)


def test_critical_3_absolute_claim_no_evidence_flags_absolute_and_vague_without_intent():
    claim = build_claim(claim="Our operations are completely environmentally friendly.", value=None, unit=None)
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=0.0, matched_evidence=[])
    manager, _ = make_manager([_judgment("medium")], max_retries=0)

    result = _service(manager).analyze_claim(claim, vr)

    assert GreenwashingType.ABSOLUTE_CLAIM in result.greenwashing_type
    joined = " ".join(result.explanation).lower() + result.reason.lower()
    assert "intentionally" not in joined
    assert "deliberately" not in joined


def test_critical_4_vague_claim_not_automatically_high():
    claim = build_claim(claim="We are committed to a greener future.", value=None, unit=None)
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=0.0, matched_evidence=[])
    manager, _ = make_manager([_judgment("low")], max_retries=0)

    result = _service(manager).analyze_claim(claim, vr)

    assert GreenwashingType.VAGUE_CLAIM in result.greenwashing_type
    assert result.greenwashing_risk != RiskLevel.HIGH


def test_critical_5_selective_presentation_explanation_names_scope():
    claim = build_claim(claim="Our emissions decreased by 50%.", value=50.0, unit="%")
    match = build_evidence_match(evidence_text="Scope 1 emissions decreased by 50%, while Scope 3 emissions increased.")
    vr = build_verification_result(status=VerificationStatus.PARTIALLY_VERIFIED, verification_score=65.0, matched_evidence=[match])
    manager, _ = make_manager([_judgment("medium")], max_retries=0)

    result = _service(manager).analyze_claim(claim, vr)

    assert GreenwashingType.SELECTIVE_PRESENTATION in result.greenwashing_type
    assert any("scope 1" in line.lower() for line in result.explanation)


# --- Section 28 numbered test list --------------------------------------

def test_1_fully_supported_claim_is_low_risk():
    claim = build_claim()
    match = build_evidence_match()
    vr = build_verification_result(matched_evidence=[match])
    manager, _ = make_manager([], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert result.greenwashing_risk == RiskLevel.LOW


def test_2_unsupported_claim_not_automatically_high():
    claim = build_claim(claim="The facility completed its annual audit in March.", value=None, unit=None)
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=0.0, matched_evidence=[])
    manager, _ = make_manager([], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert result.greenwashing_risk != RiskLevel.HIGH


def test_3_numerical_exaggeration_appropriate_risk():
    claim = build_claim(claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    match = build_evidence_match(evidence_text="Scope 1 emissions decreased by 20%.")
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=20.0, matched_evidence=[match])
    manager, _ = make_manager([_judgment("high")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert result.greenwashing_risk in (RiskLevel.MEDIUM, RiskLevel.HIGH)


def test_4_direction_contradiction_is_high():
    claim = build_claim(claim="Water consumption decreased.", value=None, unit=None)
    match = build_evidence_match(evidence_text="Water consumption increased this year.")
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=10.0, matched_evidence=[match])
    manager, _ = make_manager([_judgment("high")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert result.greenwashing_risk == RiskLevel.HIGH


def test_5_unit_mismatch_elevated_risk():
    claim = build_claim(claim="Scope 2 emissions were 45,000 tCO2e.", value=45000.0, unit="tCO2e")
    match = build_evidence_match(evidence_text="Scope 2 emissions were 45,000 MWh.")
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=20.0, matched_evidence=[match])
    manager, _ = make_manager([_judgment("medium")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert result.greenwashing_risk != RiskLevel.LOW


def test_6_target_year_mismatch_elevated_risk():
    claim = build_claim(claim="We aim to achieve net zero by 2050.", value=None, unit=None, target_year=2050)
    match = build_evidence_match(evidence_text="We aim to achieve net zero by 2040.")
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=20.0, matched_evidence=[match])
    manager, _ = make_manager([_judgment("medium")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert result.greenwashing_risk != RiskLevel.LOW


def test_7_vague_claim_appropriate_risk():
    claim = build_claim(claim="We are committed to a greener future.", value=None, unit=None)
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=0.0, matched_evidence=[])
    manager, _ = make_manager([_judgment("low")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert GreenwashingType.VAGUE_CLAIM in result.greenwashing_type
    assert result.greenwashing_risk in (RiskLevel.LOW, RiskLevel.MEDIUM)


def test_8_absolute_claim_with_evidence_assessed_not_auto_flagged_high():
    claim = build_claim(claim="Our operations achieved zero waste.", value=None, unit=None)
    match = build_evidence_match(evidence_text="100% of operational waste was diverted from landfill.")
    vr = build_verification_result(status=VerificationStatus.VERIFIED, verification_score=90.0, matched_evidence=[match])
    manager, _ = make_manager([_judgment("low")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert GreenwashingType.ABSOLUTE_CLAIM in result.greenwashing_type
    assert result.greenwashing_risk != RiskLevel.HIGH


def test_9_absolute_claim_contradicted_by_evidence_is_high():
    claim = build_claim(claim="Our operations achieved zero waste.", value=None, unit=None)
    match = build_evidence_match(evidence_text="Only 60% of operational waste was diverted from landfill.")
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=10.0, matched_evidence=[match])
    manager, _ = make_manager([_judgment("high")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert result.greenwashing_risk == RiskLevel.HIGH
    assert GreenwashingType.CONTRADICTORY_CLAIM in result.greenwashing_type


def test_10_misleading_comparison_appropriate_risk():
    claim = build_claim(claim="We are 50% greener than last year.", value=None, unit=None)
    match = build_evidence_match(evidence_text="No comparison basis is provided in this report.")
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=20.0, matched_evidence=[match])
    manager, _ = make_manager([_judgment("medium")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert GreenwashingType.MISLEADING_COMPARISON in result.greenwashing_type


def test_11_missing_qualification_appropriate_risk():
    claim = build_claim(claim="Emissions reduced by 50%.", value=50.0, unit="%")
    match = build_evidence_match(evidence_text="Emissions reduced by 50% compared with the 2020 baseline.")
    vr = build_verification_result(status=VerificationStatus.VERIFIED, verification_score=90.0, matched_evidence=[match])
    manager, _ = make_manager([_judgment("low")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert GreenwashingType.MISSING_QUALIFICATION in result.greenwashing_type


def test_12_selective_presentation_only_when_evidence_supports_it():
    claim = build_claim(claim="Our emissions decreased.", value=None, unit=None)
    match = build_evidence_match(evidence_text="Emissions decreased across the board.")
    vr = build_verification_result(status=VerificationStatus.VERIFIED, verification_score=80.0, matched_evidence=[match])
    manager, _ = make_manager([], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert GreenwashingType.SELECTIVE_PRESENTATION not in result.greenwashing_type


def test_13_no_evidence_uncertainty_handled_correctly():
    claim = build_claim(claim="We planted 500 trees.", value=None, unit=None)
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=0.0, matched_evidence=[])
    manager, _ = make_manager([_judgment("medium")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert result.evidence == []
    assert result.greenwashing_risk != RiskLevel.HIGH  # a single unsupported-benefit signal alone isn't High


def test_14_llm_malformed_json_safe_failure():
    claim = build_claim(claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    match = build_evidence_match(evidence_text="Scope 1 emissions decreased by 20%.")
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=20.0, matched_evidence=[match])
    manager, _ = make_manager(["not valid json {{{"], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert result.greenwashing_score > 0  # deterministic signals still drove a real score
    assert result.confidence_score < 100.0


def test_15_llm_unavailable_deterministic_fallback():
    from app.core.llm import LLMGenerationError

    claim = build_claim(claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    match = build_evidence_match(evidence_text="Scope 1 emissions decreased by 20%.")
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=20.0, matched_evidence=[match])
    manager, _ = make_manager([LLMGenerationError("simulated outage")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert GreenwashingType.EXAGGERATED_CLAIM in result.greenwashing_type


def test_16_explanation_matches_detected_signals():
    claim = build_claim(claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    match = build_evidence_match(evidence_text="Scope 1 emissions decreased by 20%.")
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=20.0, matched_evidence=[match])
    manager, _ = make_manager([_judgment("high")], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert any("80.0" in line and "20.0" in line for line in result.explanation)


def test_17_overall_score_aggregates_claim_level_results():
    claim_a = build_claim(claim_id="CLM-A", claim="Scope 1 emissions decreased by 20%.", value=20.0, unit="%")
    claim_b = build_claim(claim_id="CLM-B", claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    match_a = build_evidence_match(evidence_text="Scope 1 emissions decreased by 20%.")
    match_b = build_evidence_match(evidence_text="Scope 1 emissions decreased by 20%.")
    vr_a = build_verification_result(claim_id="CLM-A", status=VerificationStatus.VERIFIED, verification_score=95.0, matched_evidence=[match_a])
    vr_b = build_verification_result(claim_id="CLM-B", status=VerificationStatus.UNSUPPORTED, verification_score=20.0, matched_evidence=[match_b])

    manager, _ = make_manager([_judgment("high")], max_retries=0)
    service = _service(manager)
    results = service.analyze_claims([claim_a, claim_b], [vr_a, vr_b])
    report = service.analyze_greenwashing([claim_a, claim_b], results)

    assert report.total_claims == 2
    assert report.overall_score > results[0].greenwashing_score  # pulled up by claim B
    assert report.overall_score < 100.0


def test_18_low_risk_claims_do_not_dominate_incorrectly():
    manager, _ = make_manager([_judgment("high")], max_retries=0)
    service = _service(manager)

    high_claim = build_claim(claim_id="CLM-HIGH", claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    high_match = build_evidence_match(evidence_text="Scope 1 emissions decreased by 20%.")
    high_vr = build_verification_result(claim_id="CLM-HIGH", status=VerificationStatus.UNSUPPORTED, verification_score=20.0, matched_evidence=[high_match])
    high_result = service.analyze_claim(high_claim, high_vr)

    low_claims, low_results = [], []
    for i in range(10):
        c = build_claim(claim_id=f"CLM-LOW-{i}", claim=f"Scope 1 emissions decreased by {i + 1}%.", value=float(i + 1), unit="%")
        m = build_evidence_match(evidence_text=f"Scope 1 emissions decreased by {i + 1}%.")
        vr = build_verification_result(claim_id=f"CLM-LOW-{i}", status=VerificationStatus.VERIFIED, verification_score=95.0, matched_evidence=[m])
        low_claims.append(c)
        low_results.append(service.analyze_claim(c, vr))

    report = service.analyze_greenwashing([high_claim, *low_claims], [high_result, *low_results])
    assert report.high_risk == 1
    # a high-risk claim among ten low-risk ones must still be visible in the aggregate.
    assert report.overall_score > 5.0


def test_19_intent_is_never_inferred_even_if_llm_reasoning_asserts_it():
    # The LLM sets intent_assumed=False (self-report) but its reasoning text
    # itself asserts intent -- the judge must catch this regardless of the
    # self-reported flag (never trust it alone) and the line must never reach
    # the final explanation.
    claim = build_claim(claim="Our operations are completely environmentally friendly.", value=None, unit=None)
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, verification_score=0.0, matched_evidence=[])
    manager, _ = make_manager([_judgment("high", ["The company intentionally deceived investors."])], max_retries=0)

    result = _service(manager).analyze_claim(claim, vr)

    joined = " ".join(result.explanation).lower()
    assert "intentionally" not in joined
    assert "deceived" not in joined


def test_20_company_provenance_preserved_in_evidence():
    claim = build_claim(company="Example Company")
    match = build_evidence_match(company="Example Company", document_id="DOC-001", page_number=42, source_chunk_id="CHK-00042")
    vr = build_verification_result(matched_evidence=[match])
    manager, _ = make_manager([], max_retries=0)
    result = _service(manager).analyze_claim(claim, vr)
    assert result.evidence[0].company == "Example Company"
    assert result.evidence[0].page_number == 42
    assert result.evidence[0].source_chunk_id == "CHK-00042"


# --- Batch / failure handling --------------------------------------------

def test_analyze_claims_continues_after_one_claim_fails():
    good_claim = build_claim(claim_id="CLM-GOOD")
    good_match = build_evidence_match()
    good_vr = build_verification_result(claim_id="CLM-GOOD", matched_evidence=[good_match])
    bad_claim = build_claim(claim_id="CLM-BAD")

    manager, _ = make_manager([], max_retries=0)
    service = _service(manager)
    # no verification result supplied for CLM-BAD -> structured failure, not a crash
    results = service.analyze_claims([good_claim, bad_claim], [good_vr])

    assert len(results) == 2
    assert results[0].claim_id == "CLM-GOOD"
    assert results[1].claim_id == "CLM-BAD"
    assert results[1].greenwashing_risk == RiskLevel.LOW  # never fabricated as High on failure


def test_empty_report_has_zero_claims():
    manager, _ = make_manager([], max_retries=0)
    service = _service(manager)
    report = service.analyze_greenwashing([], [])
    assert report.total_claims == 0
    assert report.overall_risk == RiskLevel.LOW
