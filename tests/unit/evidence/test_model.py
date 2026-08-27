import pytest
from pydantic import ValidationError

from app.models.evidence import ClaimEvidenceResult, Evidence, EvidenceMatch, SourceType


def test_uploaded_report_evidence_requires_full_provenance():
    with pytest.raises(ValidationError):
        Evidence(
            evidence_id="EVD-000001", source_type=SourceType.UPLOADED_REPORT,
            company="Example Company", evidence_text="Scope 1 emissions were 500 tCO2e.",
        )


def test_evidence_supports_target_year_and_metadata_extension():
    evidence = Evidence(
        evidence_id="EVD-000001", source_type=SourceType.UPLOADED_REPORT,
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=42, source_chunk_id="CHK-00042",
        evidence_text="We aim to reduce emissions 50% by 2030.", target_year=2030,
        metadata={"dataset_id": "future-use-only"},
    )
    assert evidence.target_year == 2030
    assert evidence.metadata == {"dataset_id": "future-use-only"}


def test_evidence_metadata_defaults_to_empty_dict():
    evidence = Evidence(
        evidence_id="EVD-000001", source_type=SourceType.EXTERNAL_REPORT,
        company="Example Company", evidence_text="Some evidence text here.",
    )
    assert evidence.metadata == {}


def test_dataset_source_type_is_schema_ready():
    # The enum accepts it (government-ready schema, section 12) even though
    # Phase 5 never actually ingests one -- see evidence/validator.py which
    # explicitly rejects it at the domain-validation layer.
    evidence = Evidence(
        evidence_id="EVD-000001", source_type=SourceType.DATASET,
        company="Example Company", evidence_text="Some evidence text here.",
    )
    assert evidence.source_type == SourceType.DATASET


def test_evidence_match_carries_quality_score():
    match = EvidenceMatch(
        evidence_id="EVD-000001", source_type=SourceType.UPLOADED_REPORT, company="Example Company",
        document_id="DOC-001", page_number=42, evidence_text="Scope 1 emissions were 500 tCO2e.",
        semantic_score=0.8, lexical_score=0.7, quality_score=0.9,
    )
    assert match.quality_score == 0.9
    assert match.final_score == 0.0  # Phase 6's job, not set here


def test_claim_evidence_result_represents_not_found_explicitly():
    result = ClaimEvidenceResult(claim_id="CLM-000001", evidence_found=False)
    assert result.evidence == []
    assert result.evidence_found is False


def test_claim_evidence_result_supports_multiple_matches():
    ev1 = Evidence(
        evidence_id="EVD-000001", source_type=SourceType.UPLOADED_REPORT, document_id="DOC-001",
        company="Example Company", page_number=1, source_chunk_id="CHK-00001", evidence_text="First passage.",
    )
    ev2 = Evidence(
        evidence_id="EVD-000002", source_type=SourceType.UPLOADED_REPORT, document_id="DOC-001",
        company="Example Company", page_number=2, source_chunk_id="CHK-00002", evidence_text="Second passage.",
    )
    result = ClaimEvidenceResult(claim_id="CLM-000001", evidence_found=True, evidence=[ev1, ev2])
    assert len(result.evidence) == 2
