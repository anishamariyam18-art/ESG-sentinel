from app.claims.deduplicator import deduplicate_claims
from app.models.claim import Claim, ClaimCategory, ClaimType
from tests.unit.claims.conftest import claims_config


def _claim(**overrides) -> Claim:
    fields = dict(
        claim_id="CLM-000001", document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=1, section="Environmental > Climate", source_chunk_id="CHK-00001",
        claim="Scope 1 emissions decreased by 18%.", category=ClaimCategory.ENVIRONMENTAL,
        claim_type=ClaimType.PERFORMANCE, value=18.0, unit="%", confidence=0.9,
    )
    fields.update(overrides)
    return Claim(**fields)


def test_exact_duplicates_are_merged():
    a = _claim(source_chunk_id="CHK-00001", page_number=1)
    b = _claim(source_chunk_id="CHK-00002", page_number=2)
    result = deduplicate_claims([a, b], claims_config())
    assert len(result) == 1
    assert len(result[0].source_references) == 1
    assert result[0].source_references[0].chunk_id == "CHK-00002"


def test_near_duplicates_with_same_metadata_are_merged():
    a = _claim(claim="Scope 1 emissions decreased by 18% versus prior year.", source_chunk_id="CHK-00001")
    b = _claim(claim="Scope 1 emissions decreased by 18% compared to prior year.", source_chunk_id="CHK-00002")
    result = deduplicate_claims([a, b], claims_config(near_duplicate_similarity_threshold=0.8))
    assert len(result) == 1


def test_different_values_are_not_merged():
    a = _claim(claim="Scope 1 emissions in 2024 were 100 tCO2e.", value=100, unit="tCO2e")
    b = _claim(claim="Scope 1 emissions in 2025 were 90 tCO2e.", value=90, unit="tCO2e", source_chunk_id="CHK-00002")
    result = deduplicate_claims([a, b], claims_config())
    assert len(result) == 2


def test_different_reporting_years_are_not_merged():
    a = _claim(claim="Scope 1 emissions were 100 tCO2e.", value=100, unit="tCO2e", report_year=2024)
    b = _claim(
        claim="Scope 1 emissions were 100 tCO2e.", value=100, unit="tCO2e", report_year=2025,
        source_chunk_id="CHK-00002",
    )
    result = deduplicate_claims([a, b], claims_config())
    assert len(result) == 2


def test_different_target_years_are_not_merged():
    a = _claim(
        claim="We aim to reach net zero by 2050.", claim_type=ClaimType.COMMITMENT,
        value=None, unit=None, target_year=2050,
    )
    b = _claim(
        claim="We aim to reach net zero by 2050.", claim_type=ClaimType.COMMITMENT,
        value=None, unit=None, target_year=2040, source_chunk_id="CHK-00002",
    )
    result = deduplicate_claims([a, b], claims_config())
    assert len(result) == 2


def test_different_categories_are_never_merged_even_if_text_is_similar():
    a = _claim(claim="Emissions decreased significantly this year.", category=ClaimCategory.ENVIRONMENTAL, value=None, unit=None)
    b = _claim(claim="Emissions decreased significantly this year.", category=ClaimCategory.SOCIAL, value=None, unit=None, source_chunk_id="CHK-00002")
    result = deduplicate_claims([a, b], claims_config())
    assert len(result) == 2


def test_unrelated_claims_are_both_kept():
    a = _claim(claim="Scope 1 emissions decreased by 18%.")
    b = _claim(
        claim="Women represented 42% of our global workforce.", category=ClaimCategory.SOCIAL,
        claim_type=ClaimType.METRIC, value=42.0, unit="%", source_chunk_id="CHK-00002",
    )
    result = deduplicate_claims([a, b], claims_config())
    assert len(result) == 2
