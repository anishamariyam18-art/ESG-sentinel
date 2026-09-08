"""Integration test: DocumentProcessor -> Claims.

Uses a small, locally generated ESG PDF and a scripted (mocked) LLM
provider -- no live Gemini API call. The AnalyzerResult passed in is
minimal/hand-built rather than produced by a real analyzer run, since this
test's purpose is to verify Document -> Claims provenance flow, not
Analyzer -> Claims (that's covered by unit tests using a real Document
fixture in tests/unit/claims).
"""
from __future__ import annotations

import pytest

from app.claims.service import ClaimExtractionService
from app.document.service import DocumentProcessingService
from app.models.analyzer import AnalyzerResult
from tests.unit.analyzer.conftest import make_manager
from tests.unit.claims.conftest import claims_config, confidence_weights, extraction_batch_json


@pytest.fixture
def build_pdf():
    from tests.unit.document.conftest import _build_pdf

    return _build_pdf


@pytest.fixture
def esg_report_pdf(tmp_path, build_pdf):
    header = "Example Company | 2025 Sustainability Report"
    pages = [
        [header, "Introduction", "This report summarizes our 2025 ESG performance across\nenvironmental, social, and governance dimensions.", "Page 1 of 2"],
        [header, "Environmental", "Climate", "Scope 1 emissions decreased by 18% from the 2020 baseline.\nScope 2 emissions were 45,000 tCO2e in 2025.", "Page 2 of 2"],
    ]
    return build_pdf(tmp_path / "esg_report.pdf", pages)


def test_document_processor_output_flows_into_claims(esg_report_pdf):
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)
    assert document.chunks, "fixture must produce at least one chunk for this test to be meaningful"

    target_chunk = next(c for c in document.chunks if "18%" in c.text)
    manager, _ = make_manager(
        [extraction_batch_json([
            {"claim": "Scope 1 emissions decreased by 18% from the 2020 baseline.",
             "page_number": target_chunk.page_number, "source_chunk_id": target_chunk.chunk_id}
        ])],
        max_retries=0,
    )
    analyzer_result = AnalyzerResult(document_id=document.document_id, confidence=0.5)
    service = ClaimExtractionService(
        llm_manager=manager, claims_config=claims_config(max_schema_retries=0),
        confidence_weights=confidence_weights(),
    )

    result = service.extract_claims(document, analyzer_result)

    assert result.document_id == document.document_id
    assert result.total_claims == 1
    claim = result.claims[0]
    # document_id / page_number / source_chunk_id all flow correctly and
    # trace back into the real, processed document.
    assert claim.document_id == document.document_id
    assert claim.page_number == target_chunk.page_number
    assert claim.source_chunk_id == target_chunk.chunk_id
    assert claim.source_chunk_id in {c.chunk_id for c in document.chunks}
    assert claim.company == "Example Company"
    assert claim.report_year == 2025


def test_claims_extraction_never_uses_analyzer_as_sole_source(esg_report_pdf):
    """The document chunks remain authoritative: an AnalyzerResult claiming
    a metric that isn't grounded in any real chunk must not, by itself,
    produce a Claim -- only the LLM-cited, chunk-verified candidates can."""
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)

    analyzer_result = AnalyzerResult(document_id=document.document_id, confidence=0.9)
    manager, provider = make_manager([extraction_batch_json([])], max_retries=0)
    service = ClaimExtractionService(
        llm_manager=manager, claims_config=claims_config(max_schema_retries=0),
        confidence_weights=confidence_weights(),
    )

    result = service.extract_claims(document, analyzer_result)
    assert result.total_claims == 0
    assert len(provider.calls) >= 1  # extraction still reads the real document chunks
