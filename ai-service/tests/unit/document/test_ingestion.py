import pytest

from app.core.exceptions import DocumentExtractionError
from app.document.ingestion import DocumentIngestionService
from tests.unit.document.conftest import _build_pdf


def test_ingest_returns_a_record_with_upload_metadata(esg_report_pdf):
    record = DocumentIngestionService().ingest(esg_report_pdf, company="Example Company", report_year=2025)
    assert record.document_id == record.document.document_id
    assert record.source_filename.endswith(".pdf")
    assert record.file_hash
    assert record.upload_timestamp
    assert record.page_count > 0
    assert record.pages_with_text > 0
    assert record.extraction_status == "ok"


def test_ingest_rejects_a_pdf_with_no_usable_text(tmp_path):
    blank_pdf = _build_pdf(tmp_path / "blank.pdf", [[], []])  # two entirely blank pages
    with pytest.raises(DocumentExtractionError) as exc_info:
        DocumentIngestionService().ingest(blank_pdf, company="Example Company", report_year=2025)
    assert exc_info.value.code == "EXTRACTION_FAILED"
    assert exc_info.value.stage == "extraction"


def test_ingest_bytes_matches_ingest_from_path(esg_report_pdf):
    record_from_path = DocumentIngestionService().ingest(esg_report_pdf, company="Example Company", report_year=2025)
    record_from_bytes = DocumentIngestionService().ingest_bytes(
        esg_report_pdf.read_bytes(), source_filename=esg_report_pdf.name, company="Example Company", report_year=2025
    )
    assert record_from_path.document_id == record_from_bytes.document_id
    assert record_from_path.file_hash == record_from_bytes.file_hash


def test_upload_timestamp_is_iso8601_utc(esg_report_pdf):
    from datetime import datetime

    record = DocumentIngestionService().ingest(esg_report_pdf, company="Example Company", report_year=2025)
    parsed = datetime.fromisoformat(record.upload_timestamp)
    assert parsed.tzinfo is not None
