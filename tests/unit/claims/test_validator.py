import pytest

from app.claims.validator import (
    clean_claim_text,
    is_esg_relevant,
    is_structurally_valid_candidate,
    validate_final_claim,
)
from app.models.claim import Claim, ClaimCategory, ClaimType
from tests.unit.claims.conftest import claims_config


def test_valid_esg_sentence_passes_structural_validation():
    ok, reason = is_structurally_valid_candidate(
        "Scope 1 emissions decreased by 18% from the 2020 baseline.", claims_config()
    )
    assert ok is True
    assert reason is None


@pytest.mark.parametrize("text", [
    "Table of Contents",
    "About This Report",
    "See page 42",
    "Environmental",
    "Governance",
    "www.example.com",
    "contact@example.com",
    "",
    "   ",
])
def test_non_claim_text_is_rejected(text):
    ok, reason = is_structurally_valid_candidate(text, claims_config())
    assert ok is False
    assert reason is not None


def test_non_esg_sentence_is_rejected():
    ok, reason = is_structurally_valid_candidate(
        "Total revenue increased due to higher product sales volumes this year.", claims_config()
    )
    assert ok is False


def test_clean_claim_text_normalizes_whitespace_without_rewriting():
    assert clean_claim_text("  Scope 1   emissions\n decreased by 12%.  ") == "Scope 1 emissions decreased by 12%."


def test_is_esg_relevant_true_for_environmental_keyword():
    assert is_esg_relevant("Scope 1 emissions were 50,000 tCO2e.") is True


def test_is_esg_relevant_false_for_unrelated_text():
    assert is_esg_relevant("Total revenue increased due to higher product sales.") is False


def _claim(**overrides) -> Claim:
    fields = dict(
        claim_id="CLM-000001", document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=1, section="Environmental > Climate", source_chunk_id="CHK-00001",
        claim="Scope 1 emissions decreased by 18%.", category=ClaimCategory.ENVIRONMENTAL,
        claim_type=ClaimType.PERFORMANCE, confidence=0.9,
    )
    fields.update(overrides)
    return Claim(**fields)


def test_validate_final_claim_rejects_fabricated_provenance():
    claim = _claim(source_chunk_id="CHK-99999")
    ok, reason = validate_final_claim(claim, valid_chunk_ids={"CHK-00001"})
    assert ok is False
    assert "not found" in reason.lower()


def test_validate_final_claim_accepts_real_provenance():
    claim = _claim()
    ok, reason = validate_final_claim(claim, valid_chunk_ids={"CHK-00001"})
    assert ok is True
    assert reason is None


def test_validate_final_claim_rejects_non_esg_text():
    claim = _claim(claim="Total revenue increased due to higher product sales volumes.")
    ok, reason = validate_final_claim(claim, valid_chunk_ids={"CHK-00001"})
    assert ok is False
