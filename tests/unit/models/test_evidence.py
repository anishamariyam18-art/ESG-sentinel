import pytest
from pydantic import ValidationError

from app.models.evidence import Evidence, EvidenceMatch, SourceType


def test_uploaded_report_evidence_requires_page_provenance():
    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="EVD-000001",
            source_type=SourceType.UPLOADED_REPORT,
            company="Example Company",
            evidence_text="Scope 1 emissions were 123,456 tCO2e in 2025.",
        )


def test_uploaded_report_evidence_valid_with_full_provenance():
    evidence = Evidence(
        evidence_id="EVD-000001",
        source_type=SourceType.UPLOADED_REPORT,
        document_id="DOC-001",
        company="Example Company",
        report_year=2025,
        page_number=87,
        section="Environmental > GHG Emissions",
        source_chunk_id="CHK-041",
        evidence_text="Scope 1 emissions were 123,456 tCO2e in 2025.",
        metric_name="Scope 1 emissions",
        value=123456,
        unit="tCO2e",
    )
    assert evidence.page_number == 87
    assert evidence.source_type == SourceType.UPLOADED_REPORT


def test_external_report_evidence_does_not_require_page_provenance():
    evidence = Evidence(
        evidence_id="EVD-100001",
        source_type=SourceType.EXTERNAL_REPORT,
        company="Example Company",
        organization="Example Company",
        report_title="Sustainability Report",
        reporting_period="2025",
        evidence_text="Scope 1 emissions reported at 123,456 tCO2e.",
        source_authority="Corporate ESG Report",
        verification_status="documented",
    )
    assert evidence.document_id is None
    assert evidence.source_type == SourceType.EXTERNAL_REPORT


def test_evidence_rejects_invalid_source_type():
    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="EVD-000001",
            source_type="not_a_source_type",
            company="Example Company",
            evidence_text="text",
        )


def test_evidence_match_carries_all_score_signals():
    match = EvidenceMatch(
        evidence_id="EVD-000001",
        source_type=SourceType.UPLOADED_REPORT,
        company="Example Company",
        document_id="DOC-001",
        page_number=87,
        evidence_text="Scope 1 emissions were 123,456 tCO2e in 2025.",
        lexical_score=0.7,
        semantic_score=0.8,
        reranker_score=0.85,
        final_score=0.81,
    )
    assert match.final_score == 0.81
    assert match.reranker_score == 0.85
