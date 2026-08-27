"""Optional manual integration test against the real Gemini API.

Skipped unless GEMINI_API_KEY is set in the environment -- never part of
the default test run and never a CI dependency. Run explicitly with:

    GEMINI_API_KEY=... python -m pytest tests/integration/test_analyzer_live_gemini.py -v -s

The API key is read only from the environment (via Settings) and is never
logged or printed.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY not set; skipping live Gemini integration test",
)


def test_live_analyzer_on_synthetic_report(tmp_path):
    from app.analyzer.service import AnalyzerService
    from app.document.service import DocumentProcessingService
    from tests.unit.document.conftest import _build_pdf

    header = "Example Company | 2025 Sustainability Report"
    pages = [
        [header, "Environmental", "Climate",
         "Scope 1 emissions decreased by 12% compared to the prior year.\n"
         "Scope 2 emissions were 45,000 tCO2e in 2025."],
        [header, "Governance", "Board",
         "The Board of Directors consists of 11 members, 9 of whom are\nindependent."],
    ]
    pdf_path = _build_pdf(tmp_path / "live_test_report.pdf", pages)

    document = DocumentProcessingService().process(pdf_path, company="Example Company", report_year=2025)
    result = AnalyzerService().analyze(document)

    assert result.document_id == document.document_id
    assert 0.0 <= result.confidence <= 1.0
