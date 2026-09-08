from app.evidence.extractor import EvidenceExtractor
from app.models.claim import ClaimCategory
from app.models.evidence import SourceType
from app.models.provenance import SourceReference
from tests.unit.evidence.conftest import FakeEmbeddingProvider, build_claim, build_document, evidence_config


def test_evidence_uses_actual_chunk_not_claim_text():
    document = build_document(["Scope 1 emissions decreased by 18% from the 2020 baseline, driven by efficiency gains."])
    claim = build_claim(claim="Scope 1 emissions decreased by 18%.", source_chunk_id="CHK-00001", page_number=1)
    extractor = EvidenceExtractor(embedding_provider=FakeEmbeddingProvider(), config=evidence_config())

    results = extractor.extract_for_claims(document, [claim])
    assert len(results) == 1
    assert results[0].evidence_found is True
    evidence_text = results[0].evidence[0].evidence_text
    assert evidence_text == document.chunks[0].text
    assert evidence_text != claim.claim  # not just the claim text reused


def test_evidence_preserves_page_chunk_and_document_provenance():
    document = build_document(["Scope 1 emissions decreased by 18% from the 2020 baseline."])
    claim = build_claim(source_chunk_id="CHK-00001", page_number=1)
    extractor = EvidenceExtractor(embedding_provider=FakeEmbeddingProvider(), config=evidence_config())

    evidence = extractor.extract_for_claims(document, [claim])[0].evidence[0]
    assert evidence.document_id == document.document_id
    assert evidence.page_number == 1
    assert evidence.source_chunk_id == "CHK-00001"
    assert evidence.source_type == SourceType.UPLOADED_REPORT


def test_no_evidence_created_when_claim_chunk_does_not_exist():
    document = build_document(["Some other content."])
    claim = build_claim(source_chunk_id="CHK-99999", page_number=1)
    extractor = EvidenceExtractor(embedding_provider=FakeEmbeddingProvider(), config=evidence_config(max_corroborating_chunks_per_claim=0))

    result = extractor.extract_for_claims(document, [claim])[0]
    assert result.evidence_found is False
    assert result.evidence == []


def test_multi_page_claim_produces_evidence_for_each_source_reference():
    document = build_document([
        "Scope 1 emissions decreased by 18% from the 2020 baseline.",
        "This continues onto the next page with more detail.",
    ])
    claim = build_claim(
        source_chunk_id="CHK-00001", page_number=1,
        source_references=[SourceReference(chunk_id="CHK-00002", page_number=2)],
    )
    extractor = EvidenceExtractor(embedding_provider=FakeEmbeddingProvider(), config=evidence_config(max_corroborating_chunks_per_claim=0))

    evidence = extractor.extract_for_claims(document, [claim])[0].evidence
    assert len(evidence) == 2
    assert {e.source_chunk_id for e in evidence} == {"CHK-00001", "CHK-00002"}


def test_multiple_claims_each_get_their_own_evidence():
    document = build_document([
        "Scope 1 emissions decreased by 18% from the 2020 baseline.",
        "Women represented 42% of our global workforce in 2025.",
    ])
    claim_1 = build_claim(claim_id="CLM-000001", source_chunk_id="CHK-00001", page_number=1)
    claim_2 = build_claim(
        claim_id="CLM-000002", source_chunk_id="CHK-00002", page_number=2,
        claim="Women represented 42% of our global workforce in 2025.",
        category=ClaimCategory.SOCIAL, value=42.0, unit="%",
    )
    extractor = EvidenceExtractor(embedding_provider=FakeEmbeddingProvider(), config=evidence_config(max_corroborating_chunks_per_claim=0))

    results = extractor.extract_for_claims(document, [claim_1, claim_2])
    assert len(results) == 2
    assert results[0].claim_id == "CLM-000001"
    assert results[1].claim_id == "CLM-000002"
    assert results[0].evidence[0].source_chunk_id == "CHK-00001"
    assert results[1].evidence[0].source_chunk_id == "CHK-00002"


def test_evidence_inherits_claim_category_and_metric():
    document = build_document(["Scope 1 emissions decreased by 18% from the 2020 baseline."])
    claim = build_claim(source_chunk_id="CHK-00001", page_number=1, value=18.0, unit="%")
    extractor = EvidenceExtractor(embedding_provider=FakeEmbeddingProvider(), config=evidence_config(max_corroborating_chunks_per_claim=0))

    evidence = extractor.extract_for_claims(document, [claim])[0].evidence[0]
    assert evidence.category == ClaimCategory.ENVIRONMENTAL
    assert evidence.value == 18.0
    assert evidence.unit == "%"


def test_unknown_category_claim_produces_no_category_on_evidence():
    document = build_document(["Something happened this year that is hard to classify."])
    claim = build_claim(
        source_chunk_id="CHK-00001", page_number=1, category=ClaimCategory.UNKNOWN,
        claim="Something happened this year that is hard to classify.", value=None, unit=None,
    )
    extractor = EvidenceExtractor(embedding_provider=FakeEmbeddingProvider(), config=evidence_config(max_corroborating_chunks_per_claim=0))

    evidence = extractor.extract_for_claims(document, [claim])[0].evidence[0]
    assert evidence.category is None  # never guessed


def test_empty_claims_list_returns_empty_results():
    document = build_document(["Some content."])
    extractor = EvidenceExtractor(embedding_provider=FakeEmbeddingProvider(), config=evidence_config())
    assert extractor.extract_for_claims(document, []) == []


def test_corroborating_chunk_added_when_similarity_is_strong():
    document = build_document([
        "Scope 1 emissions decreased by 18% from the 2020 baseline.",
        "Scope 1 emissions decreased by 18% is also confirmed in this summary table.",
        "The board has five independent directors overseeing governance.",
    ])
    claim = build_claim(source_chunk_id="CHK-00001", page_number=1)
    extractor = EvidenceExtractor(
        embedding_provider=FakeEmbeddingProvider(),
        config=evidence_config(max_corroborating_chunks_per_claim=2, corroboration_similarity_threshold=0.3),
    )

    evidence = extractor.extract_for_claims(document, [claim])[0].evidence
    chunk_ids = {e.source_chunk_id for e in evidence}
    assert "CHK-00001" in chunk_ids
    assert "CHK-00002" in chunk_ids  # the near-duplicate summary line
    assert "CHK-00003" not in chunk_ids  # unrelated governance content


def test_evidence_ids_are_unique_across_claims():
    document = build_document([
        "Scope 1 emissions decreased by 18% from the 2020 baseline.",
        "Women represented 42% of our global workforce in 2025.",
    ])
    claim_1 = build_claim(claim_id="CLM-000001", source_chunk_id="CHK-00001", page_number=1)
    claim_2 = build_claim(claim_id="CLM-000002", source_chunk_id="CHK-00002", page_number=2)
    extractor = EvidenceExtractor(embedding_provider=FakeEmbeddingProvider(), config=evidence_config(max_corroborating_chunks_per_claim=0))

    all_evidence = [e for r in extractor.extract_for_claims(document, [claim_1, claim_2]) for e in r.evidence]
    ids = [e.evidence_id for e in all_evidence]
    assert len(ids) == len(set(ids))
