"""Complete pipeline integration test (Phase 8 section 36):

Document -> Analyzer -> Claims -> Evidence -> Verification -> Greenwashing
-> Trust Score.

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
from app.greenwashing.service import GreenwashingService
from app.models.verification import VerificationStatus
from app.trust_score.service import TrustScoreService
from app.verification.service import VerificationService
from tests.unit.analyzer.conftest import analyzer_config, batch_json, confidence_weights as analyzer_confidence_weights, make_manager, synthesis_json
from tests.unit.claims.conftest import claims_config, confidence_weights as claim_confidence_weights, extraction_batch_json
from tests.unit.evidence.conftest import FakeEmbeddingProvider, evidence_config
from tests.unit.greenwashing.conftest import (
    greenwashing_aggregation,
    greenwashing_confidence_weights,
    greenwashing_thresholds,
    greenwashing_weights,
)
from tests.unit.trust_score.conftest import trust_rating_thresholds, trust_score_config, trust_weights
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


def test_complete_pipeline_document_to_trust_score(esg_report_pdf, tmp_path):
    # 1. Document
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)
    env_chunk = next(c for c in document.chunks if "20%" in c.text)

    # 2. Analyzer (mocked LLM)
    analyzer_manager, _ = make_manager(
        [batch_json(company_name="Example Company", reporting_year=2025), synthesis_json()], max_retries=0
    )
    analyzer_result = AnalyzerService(
        llm_manager=analyzer_manager, analyzer_config=analyzer_config(max_schema_retries=0),
        confidence_weights=analyzer_confidence_weights(),
    ).analyze(document)

    # 3. Claims (mocked LLM) -- the claim OVERSTATES the report (80% claimed, 20% actual).
    claim_manager, _ = make_manager(
        [extraction_batch_json([
            {"claim": "We reduced Scope 1 emissions by 80%.",
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
    assert claim.page_number == env_chunk.page_number  # 1. claim provenance preserved
    assert claim.source_chunk_id == env_chunk.chunk_id

    # 4. Evidence extraction + storage + indexing
    embedding_provider = FakeEmbeddingProvider()
    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    ingestion_service = EvidenceIngestionService(
        repository=repository, config=evidence_config(), embedding_provider=embedding_provider
    )
    ingestion_service.ingest_uploaded_report(document, claim_result.claims)

    stored_evidence = repository.list_by_document(document.document_id)
    assert stored_evidence  # 2. evidence provenance preserved
    assert stored_evidence[0].page_number == env_chunk.page_number

    indexer = EvidenceIndexer(provider=embedding_provider)
    lexical_index = LexicalIndex()
    indexer.add_many(stored_evidence)
    lexical_index.add_many(stored_evidence)
    retriever = EvidenceRetriever(repository=repository, indexer=indexer, lexical_index=lexical_index)

    # 5. Verification -- the LLM correctly reports the evidence does NOT support an 80% claim.
    judgment_manager, _ = make_manager([
        json.dumps({"judgments": [{
            "evidence_id": repository.list_by_document(document.document_id)[0].evidence_id,
            "supports_claim": False, "support_level": "none", "supported_components": [],
            "unsupported_components": ["value"], "contradictions": ["Evidence states 20%, claim states 80%."],
            "reason": "The evidence reports a smaller reduction than claimed.",
        }]})
    ], max_retries=0)
    verification_service = VerificationService(
        retriever=retriever, repository=repository, llm_manager=judgment_manager,
        config=verification_config(max_schema_retries=0), weights=verification_weights(),
        confidence_weights=verification_confidence_weights(), thresholds=verification_thresholds(),
    )
    verification_result = verification_service.verify_claim(claim)

    assert verification_result.claim_id == claim.claim_id  # 3. verification result preserved
    assert verification_result.status != VerificationStatus.VERIFIED
    assert verification_result.matched_evidence

    # 6. Greenwashing
    greenwashing_manager, _ = make_manager([
        json.dumps({
            "risk_assessment": "high",
            "reasoning": ["The claimed reduction substantially exceeds what the evidence reports."],
            "intent_assumed": False,
        })
    ], max_retries=0)
    greenwashing_service = GreenwashingService(
        llm_manager=greenwashing_manager, weights=greenwashing_weights(),
        confidence_weights=greenwashing_confidence_weights(), thresholds=greenwashing_thresholds(),
        aggregation_config=greenwashing_aggregation(max_schema_retries=0),
        verification_thresholds=verification_thresholds(),
    )
    greenwashing_result = greenwashing_service.analyze_claim(claim, verification_result)

    assert greenwashing_result.claim_id == claim.claim_id  # 4. greenwashing result preserved
    assert greenwashing_result.greenwashing_type != []

    # 7. Trust Score -- no LLM manager supplied, exercising the fully
    # deterministic path (section 25/38: the LLM narrative is optional).
    trust_score_service = TrustScoreService(
        llm_manager=None, weights=trust_weights(), rating_thresholds=trust_rating_thresholds(),
        config=trust_score_config(),
    )
    trust_score = trust_score_service.calculate_trust_score(
        document_id=document.document_id, company=document.company,
        claims=claim_result.claims, verification_results=[verification_result],
        greenwashing_results=[greenwashing_result], analyzer_result=analyzer_result,
    )

    assert trust_score.document_id == document.document_id  # 5. document identity preserved
    assert trust_score.company == "Example Company"
    assert trust_score.statistics.total_claims == 1
    assert trust_score.statistics.unsupported_claims + trust_score.statistics.partially_verified_claims == 1
    assert trust_score.statistics.high_greenwashing_claims + trust_score.statistics.medium_greenwashing_claims >= 0
    # 6. component scores calculated, each independently in 0-100
    for value in trust_score.components.model_dump().values():
        assert 0.0 <= value <= 100.0
    # 7. final Trust Score generated, 0-100
    assert 0.0 <= trust_score.trust_score <= 100.0
    # 8. confidence generated, 0-100, distinct from trust_score
    assert 0.0 <= trust_score.confidence <= 100.0
    # 9. explanation generated, grounded in the actual (single-claim) statistics
    assert trust_score.explanation
    assert any("1" in line for line in trust_score.explanation)
    # A single, contradicted, high-greenwashing-risk claim should not read as trustworthy.
    assert trust_score.trust_score < 60.0
