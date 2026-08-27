import pytest

from app.claims.service import ClaimExtractionError, ClaimExtractionService
from app.models.claim import ClaimCategory, ClaimType
from tests.unit.claims.conftest import (
    build_document,
    claims_config,
    confidence_weights,
    extraction_batch_json,
    make_manager,
    minimal_analyzer_result,
)


def _service(manager, config=None):
    return ClaimExtractionService(
        llm_manager=manager, claims_config=config or claims_config(max_schema_retries=0),
        confidence_weights=confidence_weights(),
    )


def test_valid_esg_sentence_becomes_a_claim():
    document = build_document(["Scope 1 emissions decreased by 18% from the 2020 baseline."])
    manager, _ = make_manager([
        extraction_batch_json([
            {"claim": "Scope 1 emissions decreased by 18% from the 2020 baseline.",
             "page_number": 1, "source_chunk_id": "CHK-00001"}
        ])
    ], max_retries=0)

    result = _service(manager).extract_claims(document, minimal_analyzer_result())

    assert result.document_id == "DOC-001"
    assert result.total_claims == 1
    claim = result.claims[0]
    assert claim.document_id == "DOC-001"
    assert claim.page_number == 1
    assert claim.source_chunk_id == "CHK-00001"
    assert claim.category == ClaimCategory.ENVIRONMENTAL
    assert claim.value == 18
    assert claim.unit == "%"
    assert claim.claim_id == "CLM-000001"


def test_non_esg_heading_is_rejected():
    document = build_document(["Table of contents page.", "Scope 1 emissions decreased by 18%."])
    manager, _ = make_manager([
        extraction_batch_json([
            {"claim": "Table of Contents", "page_number": 1, "source_chunk_id": "CHK-00001"},
            {"claim": "Scope 1 emissions decreased by 18%.", "page_number": 2, "source_chunk_id": "CHK-00002"},
        ])
    ], max_retries=0)

    result = _service(manager).extract_claims(document, minimal_analyzer_result())

    assert result.total_claims == 1
    assert result.rejected_count == 1
    assert result.claims[0].claim == "Scope 1 emissions decreased by 18%."


def test_compound_claim_is_split_into_multiple_final_claims():
    document = build_document(["chunk text"])
    manager, _ = make_manager([
        extraction_batch_json([
            {"claim": "We reduced emissions by 20%, increased renewable energy to 80%, "
                      "and recycled 95% of operational waste.",
             "page_number": 1, "source_chunk_id": "CHK-00001"}
        ])
    ], max_retries=0)

    result = _service(manager).extract_claims(document, minimal_analyzer_result())
    assert result.total_claims == 3


def test_commitment_with_target_year_is_detected():
    document = build_document(["chunk text"])
    manager, _ = make_manager([
        extraction_batch_json([
            {"claim": "The company has committed to achieving net zero emissions by 2050.",
             "page_number": 1, "source_chunk_id": "CHK-00001"}
        ])
    ], max_retries=0)

    result = _service(manager).extract_claims(document, minimal_analyzer_result())
    claim = result.claims[0]
    assert claim.claim_type == ClaimType.COMMITMENT
    assert claim.category == ClaimCategory.ENVIRONMENTAL
    assert claim.target_year == 2050


def test_social_claim_classified_correctly():
    document = build_document(["chunk text"])
    manager, _ = make_manager([
        extraction_batch_json([
            {"claim": "Women represented 42% of our global workforce.",
             "page_number": 1, "source_chunk_id": "CHK-00001"}
        ])
    ], max_retries=0)

    result = _service(manager).extract_claims(document, minimal_analyzer_result())
    claim = result.claims[0]
    assert claim.category == ClaimCategory.SOCIAL
    assert claim.claim_type == ClaimType.METRIC
    assert claim.value == 42
    assert claim.unit == "%"


def test_governance_claim_category_is_preserved():
    document = build_document(["chunk text"])
    manager, _ = make_manager([
        extraction_batch_json([
            {"claim": "The board has 5 independent directors overseeing governance.",
             "page_number": 1, "source_chunk_id": "CHK-00001"}
        ])
    ], max_retries=0)

    result = _service(manager).extract_claims(document, minimal_analyzer_result())
    # Category MUST be preserved; claim_type is acceptable as Metric or
    # General for a plain governance headcount statement like this one.
    assert result.claims[0].category == ClaimCategory.GOVERNANCE
    assert result.claims[0].claim_type in (ClaimType.METRIC, ClaimType.GENERAL)


def test_candidate_with_fabricated_chunk_id_is_rejected():
    document = build_document(["real chunk"])
    manager, _ = make_manager([
        extraction_batch_json([
            {"claim": "Scope 1 emissions decreased by 18%.", "page_number": 1, "source_chunk_id": "CHK-99999"}
        ])
    ], max_retries=0)

    result = _service(manager).extract_claims(document, minimal_analyzer_result())
    assert result.total_claims == 0
    assert result.rejected_count == 1


def test_exact_duplicate_claims_from_different_chunks_are_merged():
    document = build_document(["c1", "c2"])
    manager, _ = make_manager([
        extraction_batch_json([
            {"claim": "Scope 1 emissions decreased by 18%.", "page_number": 1, "source_chunk_id": "CHK-00001"},
            {"claim": "Scope 1 emissions decreased by 18%.", "page_number": 2, "source_chunk_id": "CHK-00002"},
        ])
    ], max_retries=0)

    result = _service(manager).extract_claims(document, minimal_analyzer_result())
    assert result.total_claims == 1
    assert len(result.claims[0].source_references) == 1


def test_near_duplicate_claims_are_merged():
    document = build_document(["c1", "c2"])
    manager, _ = make_manager([
        extraction_batch_json([
            {"claim": "Scope 1 emissions decreased by 18% versus prior year.",
             "page_number": 1, "source_chunk_id": "CHK-00001"},
            {"claim": "Scope 1 emissions decreased by 18% compared to prior year.",
             "page_number": 2, "source_chunk_id": "CHK-00002"},
        ])
    ], max_retries=0)

    result = _service(manager).extract_claims(document, minimal_analyzer_result())
    assert result.total_claims == 1


def test_different_year_measurements_are_not_incorrectly_merged():
    document = build_document(["c1", "c2"])
    manager, _ = make_manager([
        extraction_batch_json([
            {"claim": "Scope 1 emissions in 2024 were 100 tCO2e.", "page_number": 1, "source_chunk_id": "CHK-00001"},
            {"claim": "Scope 1 emissions in 2025 were 90 tCO2e.", "page_number": 2, "source_chunk_id": "CHK-00002"},
        ])
    ], max_retries=0)

    result = _service(manager).extract_claims(document, minimal_analyzer_result())
    assert result.total_claims == 2


def test_total_batch_failure_raises_claim_extraction_error():
    document = build_document(["c1"])
    manager, _ = make_manager(["not json {{{"], max_retries=0)
    with pytest.raises(ClaimExtractionError):
        _service(manager).extract_claims(document, minimal_analyzer_result())


def test_empty_document_returns_empty_result_without_llm_call():
    document = build_document([])
    manager, provider = make_manager([])
    result = _service(manager).extract_claims(document, minimal_analyzer_result())
    assert result.total_claims == 0
    assert result.errors != []
    assert provider.calls == []


def test_exhaustive_extraction_is_not_arbitrarily_truncated():
    texts = [f"Scope 1 emissions at site {i} decreased by {i}% from the prior year." for i in range(1, 21)]
    document = build_document([f"chunk {i}" for i in range(1, 21)])
    candidates = [
        {"claim": text, "page_number": i, "source_chunk_id": f"CHK-{i:05d}"}
        for i, text in enumerate(texts, start=1)
    ]
    manager, _ = make_manager([extraction_batch_json(candidates)], max_retries=0)

    result = _service(manager).extract_claims(document, minimal_analyzer_result())
    assert result.total_claims == 20
