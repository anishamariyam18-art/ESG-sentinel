"""Complete pipeline integration test (Phase 6 section 37):

Document -> Analyzer -> Claims -> Evidence Retrieval -> Verification.

Uses a small, locally generated ESG PDF and scripted (mocked) LLM /
embedding providers throughout -- no live Gemini API call, no real model
download.
"""
from __future__ import annotations

import json

import pytest

from app.analyzer.service import AnalyzerService
from app.claims.service import ClaimExtractionService
from app.document.service import DocumentProcessingService
from app.evidence.indexer import EvidenceIndexer
from app.evidence.ingestion import EvidenceIngestionService
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.evidence.retriever import EvidenceRetriever
from app.models.evidence import SourceType
from app.models.verification import VerificationStatus
from app.verification.service import VerificationService
from tests.unit.analyzer.conftest import analyzer_config, batch_json, confidence_weights as analyzer_confidence_weights, make_manager, synthesis_json
from tests.unit.claims.conftest import claims_config, confidence_weights as claim_confidence_weights, extraction_batch_json
from tests.unit.evidence.conftest import FakeEmbeddingProvider, evidence_config
from tests.unit.verification.conftest import (
    verification_config,
    verification_confidence_weights,
    verification_thresholds,
    verification_weights,
)


@pytest.fixture
def build_pdf():
    from tests.unit.document.conftest import _build_pdf

    return _build_pdf


@pytest.fixture
def esg_report_pdf(tmp_path, build_pdf):
    header = "Example Company | 2025 Sustainability Report"
    pages = [
        [header, "Introduction", "This report summarizes our 2025 ESG performance across\nenvironmental, social, and governance dimensions.", "Page 1 of 2"],
        [header, "Environmental", "Climate",
         "Scope 1 emissions decreased by 20% from the 2020 baseline.\n"
         "Scope 2 emissions were 45,000 tCO2e in 2025.", "Page 2 of 2"],
    ]
    return build_pdf(tmp_path / "esg_report.pdf", pages)


def test_complete_pipeline_document_to_verification(esg_report_pdf, tmp_path):
    # 1. Document
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)
    assert document.chunks

    env_chunk = next(c for c in document.chunks if "20%" in c.text)

    # 2. Analyzer (mocked LLM)
    analyzer_manager, _ = make_manager(
        [batch_json(company_name="Example Company", reporting_year=2025), synthesis_json()], max_retries=0
    )
    analyzer_result = AnalyzerService(
        llm_manager=analyzer_manager, analyzer_config=analyzer_config(max_schema_retries=0),
        confidence_weights=analyzer_confidence_weights(),
    ).analyze(document)

    # 3. Claims (mocked LLM) -- extract the Scope 1 claim, source-cited to the real chunk.
    claim_manager, _ = make_manager(
        [extraction_batch_json([
            {"claim": "Scope 1 emissions decreased by 20% from the 2020 baseline.",
             "page_number": env_chunk.page_number, "source_chunk_id": env_chunk.chunk_id}
        ])],
        max_retries=0,
    )
    claim_result = ClaimExtractionService(
        llm_manager=claim_manager, claims_config=claims_config(max_schema_retries=0),
        confidence_weights=claim_confidence_weights(),
    ).extract_claims(document, analyzer_result)

    assert claim_result.total_claims == 1
    claim = claim_result.claims[0]
    # source page preserved
    assert claim.page_number == env_chunk.page_number
    assert claim.source_chunk_id == env_chunk.chunk_id

    # 4. Evidence extraction + storage + indexing
    embedding_provider = FakeEmbeddingProvider()
    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    ingestion_service = EvidenceIngestionService(
        repository=repository, config=evidence_config(), embedding_provider=embedding_provider
    )
    ingestion_result = ingestion_service.ingest_uploaded_report(document, claim_result.claims)
    assert ingestion_result.evidence_validated >= 1

    stored_evidence = repository.list_by_document(document.document_id)
    assert stored_evidence
    assert all(e.company == "Example Company" for e in stored_evidence)  # 4. correct company

    indexer = EvidenceIndexer(provider=embedding_provider)
    lexical_index = LexicalIndex()
    indexer.add_many(stored_evidence)
    lexical_index.add_many(stored_evidence)
    retriever = EvidenceRetriever(repository=repository, indexer=indexer, lexical_index=lexical_index)

    # sanity: evidence is retrievable for this claim/company
    retrieval_check = retriever.search(claim.claim, company=claim.company, top_k=5)
    assert retrieval_check
    assert all(m.company == "Example Company" for m in retrieval_check)

    # 5/6/7. Verification
    judgment_manager, _ = make_manager([
        json.dumps({"judgments": [{
            "evidence_id": retrieval_check[0].evidence_id, "supports_claim": True, "support_level": "full",
            "supported_components": ["metric", "value", "unit", "period"], "unsupported_components": [],
            "contradictions": [], "reason": "The evidence states the same metric, value, unit and period.",
        }]})
    ], max_retries=0)
    verification_service = VerificationService(
        retriever=retriever, repository=repository, llm_manager=judgment_manager,
        config=verification_config(max_schema_retries=0), weights=verification_weights(),
        confidence_weights=verification_confidence_weights(), thresholds=verification_thresholds(),
    )

    result = verification_service.verify_claim(claim)

    assert result.claim_id == claim.claim_id
    assert result.status == VerificationStatus.VERIFIED  # numeric consistency checked and matches
    assert result.checks.numeric == 1.0
    assert result.checks.entity == 1.0
    assert result.verification_score > 0  # verification score generated
    assert result.explanation  # explanation generated
    assert result.matched_evidence
    assert result.matched_evidence[0].source_type == SourceType.UPLOADED_REPORT
    assert result.matched_evidence[0].page_number == env_chunk.page_number
