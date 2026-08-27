import pytest
from pydantic import ValidationError

from app.models.claim import Claim, ClaimCategory, ClaimType


def _base_claim(**overrides):
    fields = dict(
        claim_id="CLM-000001",
        document_id="DOC-001",
        company="Example Company",
        report_year=2025,
        page_number=17,
        section="Environmental > GHG Emissions",
        source_chunk_id="CHK-001",
        claim="Scope 1 emissions decreased by 12%.",
        category=ClaimCategory.ENVIRONMENTAL,
        claim_type=ClaimType.METRIC,
        metric_name="Scope 1 emissions",
        value=12,
        unit="%",
        confidence=0.9,
    )
    fields.update(overrides)
    return Claim(**fields)


def test_valid_claim_construction():
    claim = _base_claim()
    assert claim.category == ClaimCategory.ENVIRONMENTAL
    assert claim.claim_type == ClaimType.METRIC


def test_claim_rejects_empty_claim_text():
    with pytest.raises(ValidationError):
        _base_claim(claim="")


def test_claim_rejects_invalid_category():
    with pytest.raises(ValidationError):
        _base_claim(category="NotACategory")


def test_claim_rejects_invalid_claim_type():
    with pytest.raises(ValidationError):
        _base_claim(claim_type="NotAType")


def test_claim_requires_page_number_at_least_one():
    with pytest.raises(ValidationError):
        _base_claim(page_number=0)


def test_claim_confidence_bounded_zero_to_one():
    with pytest.raises(ValidationError):
        _base_claim(confidence=1.1)


def test_claim_optional_metric_fields_may_be_absent():
    claim = _base_claim(
        claim="The company has committed to net zero emissions by 2050.",
        claim_type=ClaimType.COMMITMENT,
        metric_name=None,
        value=None,
        unit=None,
        target="net zero emissions",
        target_year=2050,
    )
    assert claim.value is None
    assert claim.target_year == 2050
