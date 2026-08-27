"""Document ingestion layer (Phase 10 section 3-4).

A thin wrapper around Phase 2's already-working `DocumentProcessingService`
-- nothing about extraction, cleaning, section detection, or chunking is
reimplemented here. This layer adds exactly what an upload-facing API needs
on top of a `Document`: an upload timestamp, and a hard stop when a PDF
extracted with no usable text at all (section 4: "do NOT silently continue
with empty text"). `Document` itself already carries `document_id`
(deterministic `DOC-<sha256[:16]>` of the raw PDF bytes), `file_hash`,
`source_filename`, `total_pages`, and per-page `extraction_status` -- none
of that is duplicated here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from app.core.exceptions import DocumentExtractionError
from app.core.logging import get_logger
from app.document.pdf_extractor import PdfExtractionError
from app.document.service import DocumentProcessingService
from app.models.document import Document

logger = get_logger(__name__)


class DocumentIngestionRecord(BaseModel):
    """Upload-facing metadata, layered on top of the already-validated
    `Document` (section 3: filename, upload timestamp, page count, document
    hash, extraction status)."""

    document_id: str = Field(min_length=1)
    source_filename: str = Field(min_length=1)
    file_hash: str = Field(min_length=1)
    upload_timestamp: str = Field(min_length=1, description="ISO-8601 UTC")
    page_count: int = Field(ge=0)
    pages_with_text: int = Field(ge=0)
    extraction_status: str
    document: Document


class DocumentIngestionService:
    def __init__(self, processor: DocumentProcessingService | None = None) -> None:
        self._processor = processor or DocumentProcessingService()

    def ingest(self, pdf_path: Path, company: str, report_year: int) -> DocumentIngestionRecord:
        pdf_path = Path(pdf_path)
        try:
            document = self._processor.process(pdf_path, company=company, report_year=report_year)
        except PdfExtractionError as exc:
            raise DocumentExtractionError(f"Could not open or extract the PDF: {exc}") from exc
        return self._finalize(document)

    def ingest_bytes(self, pdf_bytes: bytes, source_filename: str, company: str, report_year: int) -> DocumentIngestionRecord:
        try:
            document = self._processor.process_bytes(pdf_bytes, source_file=source_filename, company=company, report_year=report_year)
        except PdfExtractionError as exc:
            raise DocumentExtractionError(f"Could not open or extract the PDF: {exc}") from exc
        return self._finalize(document)

    def _finalize(self, document: Document) -> DocumentIngestionRecord:
        stats = document.processing_statistics
        if stats.pages_with_text == 0:
            # Section 4: a PDF with no usable text (empty or scanned-image-only)
            # must not silently continue as if it had real content.
            logger.warning(
                "document_ingestion_no_usable_text",
                extra={"document_id": document.document_id, "page_count": stats.page_count},
            )
            raise DocumentExtractionError(
                f"The PDF contains no extractable text ({stats.page_count} page(s), 0 with usable text) -- "
                "it may be empty or a scanned image without OCR.",
            )

        extraction_status = "ok" if stats.pages_with_errors == 0 else "partial"
        record = DocumentIngestionRecord(
            document_id=document.document_id, source_filename=document.source_filename,
            file_hash=document.file_hash, upload_timestamp=datetime.now(timezone.utc).isoformat(),
            page_count=document.total_pages, pages_with_text=stats.pages_with_text,
            extraction_status=extraction_status, document=document,
        )
        logger.info(
            "document_ingested",
            extra={
                "document_id": record.document_id, "source_filename": record.source_filename,
                "page_count": record.page_count, "pages_with_text": record.pages_with_text,
                "extraction_status": record.extraction_status,
            },
        )
        return record
