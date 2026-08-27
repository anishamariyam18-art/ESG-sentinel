import pytest

from app.document.pdf_extractor import PdfExtractionError
from app.document.service import DocumentProcessingService
from app.models.document import Document, PageExtractionStatus


@pytest.fixture
def build_pdf():
    from tests.unit.document.conftest import _build_pdf

    return _build_pdf


@pytest.fixture
def esg_report_pdf(tmp_path, build_pdf):
    header = "Example Company | 2025 Sustainability Report"
    pages = [
        [header, "Introduction", "This report summarizes our 2025 ESG performance across\nenvironmental, social, and governance dimensions.", "Page 1 of 6"],
        [header, "Environmental", "Climate", "Scope 1 emissions decreased by 12% compared to the prior year.\nScope 2 emissions were 45,000 tCO2e in 2025. The company has\ncommitted to net zero emissions by 2050.", "Page 2 of 6"],
        [header, "GHG Emissions", "Total Scope 1 and Scope 2 emissions were 123,456 tCO2e. This\nrepresents a 20% reduction from the 2020 baseline of 154,320 tCO2e.", "Renewable electricity usage reached 68% of total consumption in\n2025, up from 55% in 2024, reflecting continued investment in\non-site solar and long-term renewable power purchase agreements.", "Page 3 of 6"],
        [header, "Social", "Employees", "The company employed 12,400 people globally in 2025. Employee\nengagement scores averaged 82%, and the workforce gender\ndiversity ratio reached 41% in leadership roles.", "Page 4 of 6"],
        [header, "Governance", "Board", "The Board of Directors consists of 11 members, 9 of whom are\nindependent. The Audit Committee met 6 times during 2025.", "Page 5 of 6"],
        [header, "Page 6 of 6"],
    ]
    return build_pdf(tmp_path / "esg_report.pdf", pages)


@pytest.fixture
def empty_page_pdf(tmp_path):
    import fitz

    doc = fitz.open()
    doc.new_page(width=612, height=792)
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Second page has text.", fontsize=11)
    page.insert_text((72, 110), "Scope 1 emissions were 500 tCO2e.", fontsize=11)
    path = tmp_path / "with_blank_page.pdf"
    doc.save(str(path))
    doc.close()
    return path


def test_full_pipeline_produces_valid_document(esg_report_pdf):
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)

    assert isinstance(document, Document)
    assert document.total_pages == 6
    assert document.processing_statistics.page_count == 6
    assert document.processing_statistics.pages_with_text == 6
    assert document.processing_statistics.pages_without_text == 0
    assert document.processing_statistics.chunk_count == len(document.chunks)


def test_pipeline_output_round_trips_through_json(esg_report_pdf):
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)
    payload = document.model_dump_json()
    reloaded = Document.model_validate_json(payload)
    assert reloaded.document_id == document.document_id
    assert len(reloaded.pages) == len(document.pages)


def test_every_page_and_chunk_carries_full_provenance(esg_report_pdf):
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)

    for page in document.pages:
        assert page.document_id == document.document_id
        assert page.company == "Example Company"
        assert page.report_year == 2025
        assert page.page_number >= 1

    for chunk in document.chunks:
        assert chunk.document_id == document.document_id
        assert chunk.company == "Example Company"
        assert chunk.report_year == 2025
        page_numbers = {p.page_number for p in document.pages}
        assert chunk.page_number in page_numbers


def test_esg_numeric_content_survives_into_chunks(esg_report_pdf):
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)
    combined = " ".join(c.text for c in document.chunks)
    assert "123,456 tCO2e" in combined
    assert "12%" in combined
    assert "net zero emissions by 2050" in combined


def test_sections_detected_and_never_fabricated(esg_report_pdf):
    document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)
    sections = {p.section for p in document.pages}
    assert "Environmental > GHG Emissions" in sections
    assert "Governance > Board" in sections


def test_blank_page_preserved_and_excluded_from_chunking(empty_page_pdf):
    document = DocumentProcessingService().process(empty_page_pdf, company="Example Company", report_year=2025)

    assert document.total_pages == 2
    assert document.pages[0].extraction_status == PageExtractionStatus.EMPTY
    assert document.pages[1].extraction_status == PageExtractionStatus.OK
    assert all(chunk.page_number != document.pages[0].page_number for chunk in document.chunks)
    assert any("500 tCO2e" in chunk.text for chunk in document.chunks)


def test_same_pdf_processed_twice_yields_same_document_id(esg_report_pdf):
    service = DocumentProcessingService()
    first = service.process(esg_report_pdf, company="Example Company", report_year=2025)
    second = service.process(esg_report_pdf, company="Example Company", report_year=2025)
    assert first.document_id == second.document_id


def test_company_isolation_across_independently_processed_documents(esg_report_pdf, tmp_path, build_pdf):
    other_path = build_pdf(tmp_path / "other.pdf", [["A different, unrelated single-page document."]])

    service = DocumentProcessingService()
    doc_a = service.process(esg_report_pdf, company="Company A", report_year=2025)
    doc_b = service.process(other_path, company="Company B", report_year=2024)

    assert doc_a.document_id != doc_b.document_id
    assert doc_a.company == "Company A"
    assert doc_b.company == "Company B"
    assert all(p.company == "Company A" for p in doc_a.pages)
    assert all(p.company == "Company B" for p in doc_b.pages)


def test_corrupt_pdf_fails_explicitly_not_silently(tmp_path):
    bad_file = tmp_path / "corrupt.pdf"
    bad_file.write_bytes(b"not a real pdf")
    with pytest.raises(PdfExtractionError):
        DocumentProcessingService().process(bad_file, company="Example Company", report_year=2025)
