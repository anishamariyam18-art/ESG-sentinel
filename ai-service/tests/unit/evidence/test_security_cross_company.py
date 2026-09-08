"""Mandatory critical security/correctness test (Phase 5 section 28).

Company A claim: "Company A reduced emissions by 20%."
Company B evidence: "Company B reduced emissions by 20%."

When company filtering is company=Company A, Company B's evidence MUST
NOT be returned -- even though the text is nearly identical and would
score highly on pure semantic/lexical similarity. This is exercised twice:
once against the repository/retriever directly, and once through the full
extractor -> ingestion -> repository -> retriever pipeline, since the
isolation guarantee has to hold at every layer, not just one.
"""
from __future__ import annotations

from app.evidence.indexer import EvidenceIndexer
from app.evidence.ingestion import EvidenceIngestionService
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.evidence.retriever import EvidenceRetriever
from app.models.evidence import Evidence, SourceType
from tests.unit.evidence.conftest import FakeEmbeddingProvider, build_claim, build_document, evidence_config


def test_company_b_evidence_never_returned_when_filtering_for_company_a(tmp_repository):
    tmp_repository.add(
        Evidence(
            evidence_id="EVD-A", source_type=SourceType.UPLOADED_REPORT, document_id="DOC-A",
            company="Company A", page_number=1, source_chunk_id="CHK-A-00001",
            evidence_text="Company A reduced emissions by 20%.",
        )
    )
    tmp_repository.add(
        Evidence(
            evidence_id="EVD-B", source_type=SourceType.UPLOADED_REPORT, document_id="DOC-B",
            company="Company B", page_number=1, source_chunk_id="CHK-B-00001",
            evidence_text="Company B reduced emissions by 20%.",
        )
    )

    indexer = EvidenceIndexer(provider=FakeEmbeddingProvider())
    lexical_index = LexicalIndex()
    all_evidence = tmp_repository.all()
    indexer.add_many(all_evidence)
    lexical_index.add_many(all_evidence)
    retriever = EvidenceRetriever(repository=tmp_repository, indexer=indexer, lexical_index=lexical_index)

    results = retriever.search("Company A reduced emissions by 20%.", company="Company A", top_k=10)

    assert len(results) == 1
    assert results[0].evidence_id == "EVD-A"
    assert results[0].company == "Company A"
    assert not any(r.company == "Company B" for r in results)
    assert not any(r.evidence_id == "EVD-B" for r in results)


def test_company_b_evidence_never_returned_through_full_ingestion_pipeline(tmp_path):
    """Same guarantee, exercised end-to-end: real claim -> extractor ->
    ingestion -> repository -> retriever, for two separately-ingested
    companies sharing a near-identical evidence sentence."""
    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    provider = FakeEmbeddingProvider()
    service = EvidenceIngestionService(
        repository=repository, config=evidence_config(), embedding_provider=provider
    )

    document_a = build_document(
        ["Company A reduced emissions by 20% from the prior year."],
        company="Company A", document_id="DOC-A",
    )
    claim_a = build_claim(
        document_id="DOC-A", company="Company A", claim="Company A reduced emissions by 20%.",
        source_chunk_id="CHK-00001", page_number=1,
    )
    service.ingest_uploaded_report(document_a, [claim_a])

    document_b = build_document(
        ["Company B reduced emissions by 20% from the prior year."],
        company="Company B", document_id="DOC-B",
    )
    claim_b = build_claim(
        document_id="DOC-B", company="Company B", claim="Company B reduced emissions by 20%.",
        source_chunk_id="CHK-00001", page_number=1,
    )
    service.ingest_uploaded_report(document_b, [claim_b])

    indexer = EvidenceIndexer(provider=provider)
    lexical_index = LexicalIndex()
    all_evidence = repository.all()
    indexer.add_many(all_evidence)
    lexical_index.add_many(all_evidence)
    retriever = EvidenceRetriever(repository=repository, indexer=indexer, lexical_index=lexical_index)

    results = retriever.search("reduced emissions by 20%", company="Company A", top_k=10)

    assert len(results) >= 1
    assert all(r.company == "Company A" for r in results)
    assert not any(r.company == "Company B" for r in results)
