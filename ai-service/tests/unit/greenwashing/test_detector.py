from app.greenwashing.detector import (
    detect_absolute_contradiction,
    detect_absolute_language,
    detect_misleading_comparison,
    detect_selective_presentation,
    detect_unsupported_benefit,
    detect_vague_language,
    run_detectors,
)
from tests.unit.greenwashing.conftest import build_claim


def _evidence(text, **overrides):
    from app.models.evidence import Evidence, SourceType

    fields = dict(
        evidence_id="EVD-000001", source_type=SourceType.UPLOADED_REPORT, document_id="DOC-001",
        company="Example Company", report_year=2025, page_number=1, source_chunk_id="CHK-00001",
        evidence_text=text,
    )
    fields.update(overrides)
    return Evidence(**fields)


def test_vague_language_detected_without_numbers():
    signal = detect_vague_language("We are committed to a greener future.")
    assert signal.detected is True
    assert signal.severity > 0


def test_vague_language_not_detected_when_quantified():
    signal = detect_vague_language("We reduced our sustainable packaging waste by 40%.")
    assert signal.detected is False


def test_vague_language_word_boundary_does_not_false_positive_on_greener():
    # "greener" must not trigger via naive substring match on "green".
    signal = detect_vague_language("We published a greener product roadmap for 2030.")
    # "greener" itself isn't in the vague phrase list (only "green" is),
    # and word-boundary matching must not match "green" inside "greener".
    assert signal.detected is False


def test_absolute_language_detected():
    signal = detect_absolute_language("Our operations are completely environmentally friendly.")
    assert signal.detected is True


def test_absolute_language_not_detected_for_normal_claim():
    signal = detect_absolute_language("Scope 1 emissions decreased by 20%.")
    assert signal.detected is False


def test_unsupported_benefit_detected_without_evidence():
    signal = detect_unsupported_benefit("We planted 500 trees.", has_evidence=False)
    assert signal.detected is True


def test_unsupported_benefit_not_detected_with_evidence():
    signal = detect_unsupported_benefit("We planted 500 trees.", has_evidence=True)
    assert signal.detected is False


def test_unsupported_benefit_word_boundary_does_not_false_positive():
    # "greener" contains "green" as a substring but must not trigger the
    # benefit-keyword detector via naive substring matching.
    signal = detect_unsupported_benefit("We are committed to a greener future.", has_evidence=False)
    assert signal.detected is False


def test_misleading_comparison_detected_without_basis():
    signal = detect_misleading_comparison("We are 50% greener than last year.", None)
    assert signal.detected is True


def test_misleading_comparison_not_detected_with_basis():
    signal = detect_misleading_comparison(
        "We are 50% greener than the industry average.",
        "Compared to the industry average, our emissions intensity is 50% lower.",
    )
    assert signal.detected is False


def test_misleading_comparison_not_detected_without_comparison_language():
    signal = detect_misleading_comparison("Scope 1 emissions decreased by 20%.", None)
    assert signal.detected is False


def test_absolute_contradiction_detected():
    signal = detect_absolute_contradiction(
        "Our operations achieved zero waste.", "Only 60% of operational waste was diverted from landfill."
    )
    assert signal.detected is True
    assert "60" in signal.details


def test_absolute_contradiction_not_detected_when_evidence_confirms():
    signal = detect_absolute_contradiction(
        "Our operations achieved zero waste.", "100% of operational waste was diverted from landfill."
    )
    assert signal.detected is False


def test_absolute_contradiction_not_detected_without_absolute_language():
    signal = detect_absolute_contradiction(
        "We reduced waste significantly.", "Only 60% of operational waste was diverted from landfill."
    )
    assert signal.detected is False


def test_selective_presentation_detected():
    signal = detect_selective_presentation(
        "Our emissions decreased by 50%.",
        "Scope 1 emissions decreased by 50%, while Scope 3 emissions increased.",
    )
    assert signal.detected is True
    assert "scope" in signal.details.lower()


def test_selective_presentation_not_detected_when_claim_already_scopes():
    signal = detect_selective_presentation(
        "Scope 1 emissions decreased by 50%.",
        "Scope 1 emissions decreased by 50%, while Scope 3 emissions increased.",
    )
    assert signal.detected is False


def test_selective_presentation_not_detected_without_evidence_basis():
    # Never infer omitted information that doesn't exist in the evidence.
    signal = detect_selective_presentation("Our emissions decreased by 50%.", "Emissions decreased by 50%.")
    assert signal.detected is False


def test_run_detectors_with_no_evidence_skips_evidence_dependent_checks():
    claim = build_claim(claim="We planted 500 trees.", value=None, unit=None)
    report = run_detectors(claim, None, 2.0)
    assert report.numerical_mismatch.detected is False
    assert report.direction_mismatch.detected is False
    assert report.unsupported_benefit.detected is True


def test_run_detectors_any_detected_false_for_clean_claim():
    claim = build_claim(claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence = _evidence("Scope 1 emissions decreased by 20% in 2025.")
    report = run_detectors(claim, evidence, 2.0)
    assert report.any_detected() is False
