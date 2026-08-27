"""Integration test: DocumentProcessor -> Analyzer.

Uses a small, locally generated ESG PDF (see tests/unit/document/conftest.py)
and a scripted (mocked) LLM provider -- no live Gemini API call, matching
the project rule that CI tests must not depend on API availability.
"""
from __future__ import annotations

import pytest

from app.analyzer.service import AnalyzerService
from app.document.service import DocumentProcessingService
from tests.unit.analyzer.conftest import analyzer_config, batch_json, confidence_weights, make_manager, synthesis_json


@pytest.fixture
def build_pdf():
    from tests.unit.document.conftest import _build_pdf

    return _build_pdf


@pytest.fixture
def esg_report_pdf(tmp_path, build_pdf):
    header = "Example Company | 2025 Sustainability Report"
    pages = [
        [header, "Introduction", "This report summarizes our 2025 ESG performance across\nenvironmental, social, and governance dimensions.", "Page 1 of 3"],
        [header, "Environmental", "Climate", "Scope 1 emissions decreased by 12% compared to the prior year.\nScope 2 emissions were 45,000 tCO2e in 2025.", "Page 2 of 3"],
        [header, "Governance", "Board", "The Board of Directors consists of 11 members, 9 of whom are\nindependent.", "Page 3 of 3"],
    ]
    return build_pdf(tmp_path / "esg_report.pdf", pages)


def test_document_processor_output_flows_into_analyzer(esg_report_pdf):
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)
    assert document.chunks, "fixture must produce at least one chunk for this test to be meaningful"

    first_chunk = document.chunks[0]
    manager, provider = make_manager(
        [
            batch_json(
                company_name="Example Company",
                reporting_year=2025,
                industry="Not Found",
                metrics=[
                    {
                        "metric_name": "Scope 2 emissions", "value": 45000, "unit": "tCO2e",
                        "reporting_year": 2025, "page_number": first_chunk.page_number,
                        "source_chunk_id": first_chunk.chunk_id,
                    }
                ],
            ),
            synthesis_json(executive_summary="Example Company reported 2025 ESG performance."),
        ],
        max_retries=0,
    )
    service = AnalyzerService(
        llm_manager=manager,
        analyzer_config=analyzer_config(max_schema_retries=0),
        confidence_weights=confidence_weights(),
    )

    result = service.analyze(document)

    # document_id flows correctly
    assert result.document_id == document.document_id
    # analyzer output is valid (AnalyzerResult already validated by construction)
    assert result.company_name == "Example Company"
    assert result.reporting_year == 2025
    # provenance is preserved end to end: the chunk id cited by the mocked
    # LLM must be a chunk id that actually exists in the processed document
    assert result.metrics[0].source_chunk_id == first_chunk.chunk_id
    assert result.metrics[0].page_number == first_chunk.page_number
    assert any(c.chunk_id == first_chunk.chunk_id for c in document.chunks)
    # source_references trace back into the real document's chunks
    referenced_ids = {ref.chunk_id for ref in result.source_references}
    document_chunk_ids = {c.chunk_id for c in document.chunks}
    assert referenced_ids <= document_chunk_ids


def test_analyzer_confidence_reflects_real_chunk_count(esg_report_pdf):
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)
    manager, _ = make_manager(
        [batch_json(company_name="Example Company"), synthesis_json()], max_retries=0
    )
    service = AnalyzerService(
        llm_manager=manager,
        analyzer_config=analyzer_config(max_schema_retries=0),
        confidence_weights=confidence_weights(),
    )
    result = service.analyze(document)

    # No metrics/targets/etc were cited, so source coverage must be zero --
    # confidence must not be inflated just because the document has content.
    assert result.confidence_breakdown.source_coverage == 0.0
