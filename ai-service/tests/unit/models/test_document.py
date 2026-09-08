import pytest
from pydantic import ValidationError

from app.models.document import (
    Document,
    DocumentChunk,
    DocumentPage,
    PageExtractionStatus,
    PdfMetadata,
    ProcessingStatistics,
)


def test_document_page_valid():
    page = DocumentPage(
        document_id="DOC-001",
        company="Example Company",
        report_year=2025,
        page_number=17,
        source_file="report.pdf",
        extraction_status=PageExtractionStatus.OK,
        raw_text="Scope 1  emissions decreased by 12%.",
        text="Scope 1 emissions decreased by 12%.",
        section="Environmental > Climate",
    )
    assert page.page_number == 17
    assert page.section == "Environmental > Climate"
    assert page.raw_text != page.text


def test_document_page_rejects_zero_page_number():
    with pytest.raises(ValidationError):
        DocumentPage(
            document_id="DOC-001",
            company="Example Company",
            report_year=2025,
            page_number=0,
            source_file="report.pdf",
            extraction_status=PageExtractionStatus.OK,
            raw_text="text",
            text="text",
        )


def test_document_page_section_optional():
    page = DocumentPage(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=1, source_file="report.pdf",
        extraction_status=PageExtractionStatus.EMPTY, raw_text="", text="",
    )
    assert page.section is None


def test_document_page_preserves_empty_and_error_status():
    empty_page = DocumentPage(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=2, source_file="report.pdf",
        extraction_status=PageExtractionStatus.EMPTY, raw_text="", text="",
    )
    error_page = DocumentPage(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=3, source_file="report.pdf",
        extraction_status=PageExtractionStatus.ERROR, raw_text="", text="",
    )
    assert empty_page.extraction_status == PageExtractionStatus.EMPTY
    assert error_page.extraction_status == PageExtractionStatus.ERROR


def test_document_chunk_requires_nonempty_text():
    with pytest.raises(ValidationError):
        DocumentChunk(
            chunk_id="CHK-001", document_id="DOC-001", company="Example Company",
            report_year=2025, page_number=1, text="",
        )


def test_document_chunk_start_end_char_optional():
    chunk = DocumentChunk(
        chunk_id="CHK-001", document_id="DOC-001", company="Example Company",
        report_year=2025, page_number=1, text="text",
    )
    assert chunk.start_char is None
    assert chunk.end_char is None

    chunk_with_span = DocumentChunk(
        chunk_id="CHK-002", document_id="DOC-001", company="Example Company",
        report_year=2025, page_number=1, text="text", start_char=0, end_char=4,
    )
    assert chunk_with_span.start_char == 0
    assert chunk_with_span.end_char == 4


def test_document_aggregates_pages_and_chunks():
    doc = Document(
        document_id="DOC-001",
        company="Example Company",
        report_year=2025,
        source_filename="report.pdf",
        file_hash="a" * 64,
        total_pages=1,
        metadata=PdfMetadata(page_count=1),
        pages=[
            DocumentPage(
                document_id="DOC-001", company="Example Company", report_year=2025,
                page_number=1, source_file="report.pdf",
                extraction_status=PageExtractionStatus.OK, raw_text="text", text="text",
            )
        ],
        chunks=[
            DocumentChunk(
                chunk_id="CHK-001", document_id="DOC-001", company="Example Company",
                report_year=2025, page_number=1, text="text",
            )
        ],
        processing_statistics=ProcessingStatistics(
            page_count=1, pages_with_text=1, pages_without_text=0,
            pages_with_errors=0, chunk_count=1,
        ),
    )
    assert len(doc.pages) == 1
    assert len(doc.chunks) == 1
    assert doc.metadata.page_count == 1


def test_pdf_metadata_treats_missing_fields_as_none():
    metadata = PdfMetadata(page_count=5)
    assert metadata.title is None
    assert metadata.author is None
