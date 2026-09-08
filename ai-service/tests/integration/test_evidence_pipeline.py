"""Integration test: DocumentProcessor -> Claims -> Evidence.

Uses small, locally generated ESG PDFs and scripted (mocked) LLM /
embedding providers -- no live Gemini API call and no real model download.
"""
from __future__ import annotations

import pytest

from app.claims.service import ClaimExtractionService
from app.document.service import DocumentProcessingService
from app.evidence.ingestion import EvidenceIngestionService
from app.evidence.indexer import EvidenceIndexer
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.evidence.retriever import EvidenceRetriever
from app.models.analyzer import AnalyzerResult
from app.models.evidence import SourceType
from tests.unit.analyzer.conftest import make_manager
from tests.unit.claims.conftest import claims_config, confidence_weights, extraction_batch_json
from tests.unit.evidence.conftest import FakeEmbeddingProvider, evidence_config


@pytest.fixture
def build_pdf():
    from tests.unit.document.conftest import _build_pdf

    return _build_pdf


@pytest.fixture
def esg_report_pdf(tmp_path, build_pdf):
    header = "Example Company | 2025 Sustainability Report"
    pages = [
        [header, "Environmental", "Climate",
         "Scope 1 emissions decreased by 18% from the 2020 baseline.\n"
         "Scope 2 emissions were 45,000 tCO2e in 2025.", "Page 1 of 2"],
        [header, "Social", "Employees",
         "Women represented 42% of our global workforce in 2025.", "Page 2 of 2"],
    ]
    return build_pdf(tmp_path / "esg_report.pdf", pages)


def test_full_document_to_evidence_pipeline(esg_report_pdf, tmp_path):
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)
    assert document.chunks

    env_chunk = next(c for c in document.chunks if "18%" in c.text)
    social_chunk = next(c for c in document.chunks if "42%" in c.text)

    claim_manager, _ = make_manager(
        [extraction_batch_json([
            {"claim": "Scope 1 emissions decreased by 18% from the 2020 baseline.",
             "page_number": env_chunk.page_number, "source_chunk_id": env_chunk.chunk_id},
            {"claim": "Women represented 42% of our global workforce in 2025.",
             "page_number": social_chunk.page_number, "source_chunk_id": social_chunk.chunk_id},
        ])],
        max_retries=0,
    )
    claims_service = ClaimExtractionService(
        llm_manager=claim_manager, claims_config=claims_config(max_schema_retries=0),
        confidence_weights=confidence_weights(),
    )
    claim_result = claims_service.extract_claims(document, AnalyzerResult(document_id=document.document_id, confidence=0.5))
    assert claim_result.total_claims == 2

    provider = FakeEmbeddingProvider()
    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    ingestion_service = EvidenceIngestionService(
        repository=repository, config=evidence_config(), embedding_provider=provider
    )
    ingestion_result = ingestion_service.ingest_uploaded_report(document, claim_result.claims)

    assert ingestion_result.evidence_validated >= 2
    assert ingestion_result.evidence_rejected == 0

    stored = repository.list_by_document(document.document_id)
    assert all(e.source_type == SourceType.UPLOADED_REPORT for e in stored)
    assert all(e.company == "Example Company" for e in stored)
    # Evidence text is the real chunk text, never the bare claim text.
    assert any("baseline" in e.evidence_text for e in stored)

    indexer = EvidenceIndexer(provider=provider)
    lexical_index = LexicalIndex()
    indexer.add_many(stored)
    lexical_index.add_many(stored)
    retriever = EvidenceRetriever(repository=repository, indexer=indexer, lexical_index=lexical_index)

    results = retriever.search(
        "Scope 1 emissions baseline", company="Example Company", document_id=document.document_id
    )
    assert results
    assert results[0].page_number == env_chunk.page_number
