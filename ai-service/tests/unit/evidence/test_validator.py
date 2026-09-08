from app.evidence.validator import compute_evidence_quality, validate_evidence
from app.models.evidence import Evidence, SourceType
from tests.unit.evidence.conftest import evidence_config


def _uploaded_evidence(**overrides) -> Evidence:
    fields = dict(
        evidence_id="EVD-000001", source_type=SourceType.UPLOADED_REPORT, document_id="DOC-001",
        company="Example Company", report_year=2025, page_number=42, source_chunk_id="CHK-00042",
        evidence_text="Scope 1 emissions decreased by 18% from the 2020 baseline.",
        source_authority="Uploaded ESG Report",
    )
    fields.update(overrides)
    return Evidence(**fields)


def _external_evidence(**overrides) -> Evidence:
    fields = dict(
        evidence_id="EVD-100001", source_type=SourceType.EXTERNAL_REPORT, company="Company B",
        document_id="DOC-002", organization="Company B", report_title="2025 Sustainability Report",
        report_year=2025, page_number=10, evidence_text="Company B reduced emissions by 20% in 2025.",
        source_authority="External ESG Report",
    )
    fields.update(overrides)
    return Evidence(**fields)


def test_valid_uploaded_evidence_passes():
    evidence = _uploaded_evidence()
    ok, reason = validate_evidence(evidence, evidence_config(), valid_chunk_ids={"CHK-00042"})
    assert ok is True
    assert reason is None


def test_uploaded_evidence_with_fabricated_chunk_id_is_rejected():
    evidence = _uploaded_evidence(source_chunk_id="CHK-99999")
    ok, reason = validate_evidence(evidence, evidence_config(), valid_chunk_ids={"CHK-00042"})
    assert ok is False
    assert "fabricated" in reason.lower()


def test_evidence_text_below_minimum_length_is_rejected():
    evidence = _uploaded_evidence(evidence_text="Short.")
    ok, reason = validate_evidence(evidence, evidence_config(min_evidence_text_length=20))
    assert ok is False


def test_valid_external_evidence_passes():
    evidence = _external_evidence()
    ok, reason = validate_evidence(evidence, evidence_config())
    assert ok is True
    assert reason is None


def test_external_evidence_missing_organization_is_rejected():
    evidence = _external_evidence(organization=None)
    ok, reason = validate_evidence(evidence, evidence_config())
    assert ok is False
    assert "organization" in reason


def test_external_evidence_missing_report_year_is_rejected():
    evidence = _external_evidence(report_year=None)
    ok, reason = validate_evidence(evidence, evidence_config())
    assert ok is False


def test_government_source_type_is_rejected_in_phase_5():
    evidence = Evidence(
        evidence_id="EVD-999999", source_type=SourceType.GOVERNMENT, company="EPA",
        evidence_text="A government dataset record that must not be accepted yet.",
        source_authority="EPA",
    )
    ok, reason = validate_evidence(evidence, evidence_config())
    assert ok is False
    assert "not yet implemented" in reason


def test_dataset_source_type_is_rejected_in_phase_5():
    evidence = Evidence(
        evidence_id="EVD-999998", source_type=SourceType.DATASET, company="Registry",
        evidence_text="A structured dataset record that must not be accepted yet.",
    )
    ok, reason = validate_evidence(evidence, evidence_config())
    assert ok is False


def test_compute_evidence_quality_higher_for_uploaded_than_external():
    uploaded = _uploaded_evidence()
    external = _external_evidence()
    assert compute_evidence_quality(uploaded) >= compute_evidence_quality(external)


def test_compute_evidence_quality_bounded_zero_to_one():
    quality = compute_evidence_quality(_uploaded_evidence())
    assert 0.0 <= quality <= 1.0


def test_compute_evidence_quality_lower_without_source_authority():
    with_authority = compute_evidence_quality(_uploaded_evidence())
    without_authority = compute_evidence_quality(_uploaded_evidence(source_authority=None))
    assert without_authority < with_authority
