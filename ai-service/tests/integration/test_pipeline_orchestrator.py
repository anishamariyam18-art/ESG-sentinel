"""End-to-end test of `PipelineOrchestrator.run` (Phase 10 section 39).

Unlike `tests/integration/test_recommendations_pipeline.py` (which chains
every phase's service manually, one call at a time, to prove each stage's
output really is the next stage's input), this test exercises the single
orchestrated entry point a real API endpoint would call -- one call in,
one `PipelineResult` out -- and checks `pipeline_status`, `stage_timings`,
and that every stage's data survives into the final result.
"""
from __future__ import annotations

import json

import pytest

from app.core.exceptions import DocumentExtractionError, LLMNotConfiguredError
from app.evidence.indexer import EvidenceIndexer
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.pipeline.service import PipelineOrchestrator
from tests.unit.analyzer.conftest import batch_json, make_manager, synthesis_json
from tests.unit.claims.conftest import extraction_batch_json
from tests.unit.evidence.conftest import FakeEmbeddingProvider


@pytest.fixture
def esg_report_pdf(tmp_path):
    from tests.unit.document.conftest import _build_pdf

    header = "Example Company | 2025 Sustainability Report"
    pages = [
        [header, "Introduction", "This report summarizes our 2025 ESG performance across\nenvironmental, social, and governance dimensions.", "Page 1 of 2"],
        [header, "Environmental", "Climate",
         "Scope 1 emissions decreased by 20% from the 2020 baseline.\n"
         "Scope 2 emissions were 45,000 tCO2e in 2025.", "Page 2 of 2"],
    ]
    return _build_pdf(tmp_path / "esg_report.pdf", pages)


def test_orchestrator_runs_the_complete_pipeline_and_returns_completed_status(esg_report_pdf, tmp_path):
    from app.document.service import DocumentProcessingService

    probe_document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)
    env_chunk = next(c for c in probe_document.chunks if "20%" in c.text)

    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    embedding_provider = FakeEmbeddingProvider()
    indexer = EvidenceIndexer(provider=embedding_provider)
    lexical_index = LexicalIndex()

    judgment = json.dumps({"judgments": [{
        "evidence_id": "PLACEHOLDER", "supports_claim": False, "support_level": "none",
        "supported_components": [], "unsupported_components": ["value"],
        "contradictions": ["Evidence states 20%, claim states 80%."],
        "reason": "The evidence reports a smaller reduction than claimed.",
    }]})
    greenwashing_judgment = json.dumps({
        "risk_assessment": "high",
        "reasoning": ["The claimed reduction substantially exceeds what the evidence reports."],
        "intent_assumed": False,
    })

    manager, provider = make_manager(
        [
            batch_json(company_name="Example Company", reporting_year=2025),
            synthesis_json(),
            extraction_batch_json([
                {"claim": "We reduced Scope 1 emissions by 80%.", "page_number": env_chunk.page_number, "source_chunk_id": env_chunk.chunk_id}
            ]),
            judgment,
            greenwashing_judgment,
        ],
        max_retries=0,
    )

    orchestrator = PipelineOrchestrator(
        repository=repository, indexer=indexer, lexical_index=lexical_index,
        llm_manager=manager, embedding_provider=embedding_provider,
    )

    result = orchestrator.run(esg_report_pdf, company="Example Company", report_year=2025)

    assert result.pipeline_status == "completed"
    assert result.document_id
    assert len(result.claims) == 1
    assert result.claims[0].claim == "We reduced Scope 1 emissions by 80%."
    assert len(result.verification_results) == 1
    assert result.verification_results[0].claim_id == result.claims[0].claim_id
    assert len(result.greenwashing_results) == 1
    assert result.trust_score is not None
    assert result.trust_score.document_id == result.document_id
    assert result.recommendations is not None
    assert result.recommendations.document_id == result.document_id
    assert "ingestion" in result.stage_timings
    assert "analyzer" in result.stage_timings
    assert "claims" in result.stage_timings
    assert "verification" in result.stage_timings
    assert "greenwashing" in result.stage_timings
    assert "trust_score" in result.stage_timings
    assert "recommendations" in result.stage_timings
    assert result.stage_timings["total"] >= 0.0
    assert result.errors == []


def test_orchestrator_raises_on_a_pdf_with_no_usable_text(tmp_path):
    from tests.unit.document.conftest import _build_pdf

    blank_pdf = _build_pdf(tmp_path / "blank.pdf", [[]])
    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    embedding_provider = FakeEmbeddingProvider()
    indexer = EvidenceIndexer(provider=embedding_provider)
    lexical_index = LexicalIndex()
    manager, _ = make_manager([], max_retries=0)

    orchestrator = PipelineOrchestrator(
        repository=repository, indexer=indexer, lexical_index=lexical_index,
        llm_manager=manager, embedding_provider=embedding_provider,
    )

    with pytest.raises(DocumentExtractionError):
        orchestrator.run(blank_pdf, company="Example Company", report_year=2025)


def test_orchestrator_returns_failed_status_when_analyzer_fails(esg_report_pdf, tmp_path):
    from app.core.llm import LLMGenerationError

    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    embedding_provider = FakeEmbeddingProvider()
    indexer = EvidenceIndexer(provider=embedding_provider)
    lexical_index = LexicalIndex()
    manager, _ = make_manager([LLMGenerationError("simulated outage")], max_retries=0)

    orchestrator = PipelineOrchestrator(
        repository=repository, indexer=indexer, lexical_index=lexical_index,
        llm_manager=manager, embedding_provider=embedding_provider,
    )

    result = orchestrator.run(esg_report_pdf, company="Example Company", report_year=2025)
    assert result.pipeline_status == "failed"
    assert any("analyzer" in e.lower() for e in result.errors)
    assert result.claims == []


def test_orchestrator_raises_a_clear_error_when_no_llm_manager_is_configured(esg_report_pdf, tmp_path):
    """Regression test: previously, llm_manager=None let AnalyzerService's
    own constructor raise a bare LLMGenerationError with no document_id to
    build a PipelineResult around, which surfaced as an opaque, unhandled
    500 at the API layer. Now it fails fast with a clear, typed error."""
    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    embedding_provider = FakeEmbeddingProvider()
    indexer = EvidenceIndexer(provider=embedding_provider)
    lexical_index = LexicalIndex()

    orchestrator = PipelineOrchestrator(
        repository=repository, indexer=indexer, lexical_index=lexical_index,
        llm_manager=None, embedding_provider=embedding_provider,
    )

    with pytest.raises(LLMNotConfiguredError) as exc_info:
        orchestrator.run(esg_report_pdf, company="Example Company", report_year=2025)
    assert exc_info.value.code == "LLM_NOT_CONFIGURED"
    assert exc_info.value.status_code == 503
