from app.greenwashing.detector import run_detectors
from app.greenwashing.explainability import build_explanation, build_reason, build_recommendation
from app.models.evidence import Evidence, SourceType
from app.models.greenwashing import GreenwashingType, RiskLevel
from app.models.verification import VerificationStatus
from tests.unit.greenwashing.conftest import build_claim


def _evidence(text, **overrides):
    fields = dict(
        evidence_id="EVD-000001", source_type=SourceType.UPLOADED_REPORT, document_id="DOC-001",
        company="Example Company", report_year=2025, page_number=1, source_chunk_id="CHK-00001",
        evidence_text=text,
    )
    fields.update(overrides)
    return Evidence(**fields)


def test_explanation_for_fully_supported_claim():
    claim = build_claim(claim="Scope 1 emissions decreased by 20%.", value=20.0, unit="%")
    evidence = _evidence("Scope 1 emissions decreased by 20%.")
    report = run_detectors(claim, evidence, 2.0)
    explanation = build_explanation(VerificationStatus.VERIFIED, report)
    assert len(explanation) == 1
    assert "no greenwashing signals" in explanation[0].lower()


def test_explanation_for_unsupported_with_no_signals_uses_exact_spec_wording():
    # Deliberately free of any vague/absolute/benefit keyword so no
    # detector fires -- isolates the "genuinely no signal" explanation path.
    claim = build_claim(claim="The facility completed its annual third-party audit in March.", value=None, unit=None)
    report = run_detectors(claim, None, 2.0)
    explanation = build_explanation(VerificationStatus.UNSUPPORTED, report)
    assert explanation == [
        "The claim could not be verified from the available evidence, but the available "
        "information is insufficient to establish intentional or misleading environmental representation."
    ]


def test_explanation_matches_detected_signals():
    claim = build_claim(claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    evidence = _evidence("Scope 1 emissions decreased by 20%.")
    report = run_detectors(claim, evidence, 2.0)
    explanation = build_explanation(VerificationStatus.UNSUPPORTED, report)
    assert any("80.0%" in line for line in explanation)
    assert any("20.0%" in line for line in explanation)


def test_explanation_includes_llm_reasoning_when_present():
    claim = build_claim(claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    evidence = _evidence("Scope 1 emissions decreased by 20%.")
    report = run_detectors(claim, evidence, 2.0)
    explanation = build_explanation(VerificationStatus.UNSUPPORTED, report, llm_reasoning=["This is a large discrepancy."])
    assert any(line.startswith("LLM assessment:") for line in explanation)


def test_explanation_never_asserts_intent():
    claim = build_claim(claim="Our operations are completely environmentally friendly.", value=None, unit=None)
    report = run_detectors(claim, None, 2.0)
    explanation = build_explanation(VerificationStatus.UNSUPPORTED, report)
    joined = " ".join(explanation).lower()
    assert "intentionally" not in joined
    assert "deliberately" not in joined
    assert "deceiv" not in joined


def test_reason_for_no_significant_signal():
    reason = build_reason(RiskLevel.LOW, [GreenwashingType.NO_SIGNIFICANT_SIGNAL])
    assert "adequately supported" in reason.lower()


def test_reason_names_detected_types():
    reason = build_reason(RiskLevel.HIGH, [GreenwashingType.EXAGGERATED_CLAIM])
    assert "Exaggerated Claim" in reason
    assert "High" in reason


def test_recommendation_for_exaggerated_claim():
    recommendation = build_recommendation([GreenwashingType.EXAGGERATED_CLAIM])
    assert "underlying report" in recommendation.lower() or "discrepancy" in recommendation.lower()


def test_recommendation_for_no_signal():
    recommendation = build_recommendation([GreenwashingType.NO_SIGNIFICANT_SIGNAL])
    assert "no action" in recommendation.lower()


def test_recommendation_is_single_string_not_list():
    recommendation = build_recommendation([GreenwashingType.VAGUE_CLAIM, GreenwashingType.MISSING_QUALIFICATION])
    assert isinstance(recommendation, str)
