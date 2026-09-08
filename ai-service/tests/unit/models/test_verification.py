import pytest
from pydantic import ValidationError

from app.models.evidence import EvidenceMatch, SourceType
from app.models.verification import (
    VerificationChecks,
    VerificationResult,
    VerificationStatus,
)


def test_unsupported_status_is_distinct_from_false():
    result = VerificationResult(
        claim_id="CLM-000001",
        status=VerificationStatus.UNSUPPORTED,
        verification_score=10.0,
        confidence_score=40.0,
        checks=VerificationChecks(),
        explanation=["No adequate supporting evidence found."],
    )
    assert result.status == VerificationStatus.UNSUPPORTED
    assert result.status.value != "False"


def test_verification_result_with_matched_evidence():
    match = EvidenceMatch(
        evidence_id="EVD-000001",
        source_type=SourceType.UPLOADED_REPORT,
        company="Example Company",
        document_id="DOC-001",
        page_number=87,
        source_chunk_id="CHK-00087",
        report_title="2025 Sustainability Report",
        evidence_text="Scope 1 emissions were 123,456 tCO2e in 2025.",
        final_score=0.9,
    )
    result = VerificationResult(
        claim_id="CLM-000001",
        status=VerificationStatus.VERIFIED,
        verification_score=94.0,
        confidence_score=90.0,
        matched_evidence=[match],
        checks=VerificationChecks(
            semantic=0.9, lexical=0.85, numeric=1.0, unit=1.0, temporal=1.0,
            entity=1.0, category=1.0, llm_support=1.0, provenance=0.95,
        ),
        reason="Evidence directly supports the claim.",
        explanation=["Evidence on page 87 matches the claimed metric and value."],
    )
    assert result.matched_evidence[0].evidence_id == "EVD-000001"
    assert result.matched_evidence[0].source_chunk_id == "CHK-00087"
    assert result.checks.numeric == 1.0


def test_verification_score_bounded_zero_to_hundred():
    with pytest.raises(ValidationError):
        VerificationResult(
            claim_id="CLM-000001",
            status=VerificationStatus.VERIFIED,
            verification_score=120.0,
            confidence_score=50.0,
            checks=VerificationChecks(),
        )


def test_confidence_score_bounded_zero_to_hundred():
    with pytest.raises(ValidationError):
        VerificationResult(
            claim_id="CLM-000001",
            status=VerificationStatus.VERIFIED,
            verification_score=50.0,
            confidence_score=-1.0,
            checks=VerificationChecks(),
        )


def test_verification_rejects_invalid_status():
    with pytest.raises(ValidationError):
        VerificationResult(
            claim_id="CLM-000001",
            status="Confirmed",
            verification_score=50.0,
            confidence_score=50.0,
            checks=VerificationChecks(),
        )


def test_verification_checks_scores_bounded():
    with pytest.raises(ValidationError):
        VerificationChecks(numeric=1.5)
