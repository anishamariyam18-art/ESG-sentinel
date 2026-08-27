"""Synthetic PDF fixtures for document-processing tests.

No real ESG PDF is checked into the repo yet (data/reports/company_*/ are
empty placeholders), so these fixtures generate small, realistic multi-page
PDFs locally with PyMuPDF -- not downloaded, not fabricated ESG claims,
just plain text laid out like a report for exercising the pipeline
mechanics (page extraction, cleaning, section detection, chunking).

Each paragraph is inserted as its own `insert_text` call at an increasing
y-offset, which PyMuPDF preserves as a separate text block. The extractor
rejoins blocks with a blank line, so this is what produces real paragraph
boundaries on extraction -- a single `insert_text` call containing "\n\n"
does NOT (PyMuPDF collapses blank lines within one text call).
"""
from __future__ import annotations

from pathlib import Path

import fitz
import pytest


def _build_pdf(path: Path, pages: list[list[str]]) -> Path:
    doc = fitz.open()
    for paragraphs in pages:
        page = doc.new_page(width=612, height=792)
        y = 72.0
        for paragraph in paragraphs:
            page.insert_text((72, y), paragraph, fontsize=11)
            line_count = paragraph.count("\n") + 1
            y += line_count * 14 + 20
    doc.save(str(path))
    doc.close()
    return path


@pytest.fixture
def esg_report_pdf(tmp_path) -> Path:
    header = "Example Company | 2025 Sustainability Report"

    pages = [
        [
            header,
            "Introduction",
            "This report summarizes our 2025 ESG performance across\n"
            "environmental, social, and governance dimensions.",
            "Page 1 of 6",
        ],
        [
            header,
            "Environmental",
            "Climate",
            "Scope 1 emissions decreased by 12% compared to the prior year.\n"
            "Scope 2 emissions were 45,000 tCO2e in 2025. The company has\n"
            "committed to net zero emissions by 2050.",
            "Page 2 of 6",
        ],
        [
            header,
            "GHG Emissions",
            "Total Scope 1 and Scope 2 emissions were 123,456 tCO2e. This\n"
            "represents a 20% reduction from the 2020 baseline of 154,320 tCO2e.",
            "Renewable electricity usage reached 68% of total consumption in\n"
            "2025, up from 55% in 2024, reflecting continued investment in\n"
            "on-site solar and long-term renewable power purchase agreements.",
            "Page 3 of 6",
        ],
        [
            header,
            "Social",
            "Employees",
            "The company employed 12,400 people globally in 2025. Employee\n"
            "engagement scores averaged 82%, and the workforce gender\n"
            "diversity ratio reached 41% in leadership roles.",
            "Page 4 of 6",
        ],
        [
            header,
            "Governance",
            "Board",
            "The Board of Directors consists of 11 members, 9 of whom are\n"
            "independent. The Audit Committee met 6 times during 2025.",
            "Page 5 of 6",
        ],
        [
            header,
            "Page 6 of 6",
        ],
    ]
    return _build_pdf(tmp_path / "esg_report.pdf", pages)


@pytest.fixture
def other_pdf(tmp_path) -> Path:
    pages = [["A different, unrelated single-page document.", "No ESG content here."]]
    return _build_pdf(tmp_path / "other.pdf", pages)


@pytest.fixture
def empty_page_pdf(tmp_path) -> Path:
    doc = fitz.open()
    doc.new_page(width=612, height=792)  # blank page, no inserted text
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Second page has text.", fontsize=11)
    page.insert_text((72, 110), "Scope 1 emissions were 500 tCO2e.", fontsize=11)
    path = tmp_path / "with_blank_page.pdf"
    doc.save(str(path))
    doc.close()
    return path
