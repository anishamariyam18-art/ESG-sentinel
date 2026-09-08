"""Page-aware PDF extraction using PyMuPDF.

Every page is extracted individually and preserved -- a page with no
extractable text is kept with `extraction_status=EMPTY` rather than
dropped, and a page whose extraction raises is kept with
`extraction_status=ERROR` rather than aborting the whole document. Only a
document that cannot be opened at all raises `PdfExtractionError`.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import fitz
from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.models.document import PageExtractionStatus, PdfMetadata

logger = get_logger(__name__)

_PDF_MAGIC = b"%PDF-"


class PdfExtractionError(Exception):
    """Raised when a PDF cannot be opened/read at all."""


class ExtractedPage(BaseModel):
    """Raw, per-page extraction output -- internal to app.document, prior
    to cleaning and section detection."""

    document_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    source_file: str = Field(min_length=1)
    extraction_status: PageExtractionStatus
    raw_text: str


class PdfExtractionResult(BaseModel):
    document_id: str = Field(min_length=1)
    file_hash: str = Field(min_length=1)
    source_file: str = Field(min_length=1)
    metadata: PdfMetadata
    pages: list[ExtractedPage] = Field(default_factory=list)


def compute_document_id(pdf_bytes: bytes) -> tuple[str, str]:
    """Return (document_id, file_hash) deterministically derived from the
    PDF's bytes. Identical bytes always yield identical ids; different
    bytes (even a single-byte difference) yield different ids."""
    file_hash = hashlib.sha256(pdf_bytes).hexdigest()
    document_id = f"DOC-{file_hash[:16].upper()}"
    return document_id, file_hash


def _validate_pdf_bytes(pdf_bytes: bytes, source_file: str) -> None:
    if not pdf_bytes:
        raise PdfExtractionError(f"'{source_file}' is empty")
    if not pdf_bytes.lstrip(b"\x00\xef\xbb\xbf").startswith(_PDF_MAGIC):
        raise PdfExtractionError(f"'{source_file}' does not look like a PDF (missing %PDF header)")


def _extract_metadata(doc: "fitz.Document") -> PdfMetadata:
    raw = doc.metadata or {}

    def _clean(value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    return PdfMetadata(
        title=_clean(raw.get("title")),
        author=_clean(raw.get("author")),
        subject=_clean(raw.get("subject")),
        creator=_clean(raw.get("creator")),
        producer=_clean(raw.get("producer")),
        page_count=doc.page_count,
    )


class PdfExtractor:
    """Extracts a PDF into page-aware, provenance-carrying records. Never
    calls an LLM and never flattens the document into a single string."""

    def extract(self, pdf_path: Path) -> PdfExtractionResult:
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise PdfExtractionError(f"File not found: {pdf_path}")

        pdf_bytes = pdf_path.read_bytes()
        return self.extract_bytes(pdf_bytes, source_file=pdf_path.name)

    def extract_bytes(self, pdf_bytes: bytes, source_file: str) -> PdfExtractionResult:
        _validate_pdf_bytes(pdf_bytes, source_file)
        document_id, file_hash = compute_document_id(pdf_bytes)

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:  # PyMuPDF raises its own exception types
            raise PdfExtractionError(f"Failed to open '{source_file}': {exc}") from exc

        try:
            metadata = _extract_metadata(doc)
            page_count = doc.page_count
            pages = [
                self._extract_page(doc, index, document_id, source_file)
                for index in range(page_count)
            ]
        finally:
            doc.close()

        pages_with_errors = sum(1 for p in pages if p.extraction_status == PageExtractionStatus.ERROR)
        logger.info(
            "pdf_extracted",
            extra={
                "document_id": document_id,
                "source_file": source_file,
                "page_count": page_count,
                "pages_with_errors": pages_with_errors,
            },
        )

        return PdfExtractionResult(
            document_id=document_id,
            file_hash=file_hash,
            source_file=source_file,
            metadata=metadata,
            pages=pages,
        )

    def _extract_page(
        self, doc: "fitz.Document", index: int, document_id: str, source_file: str
    ) -> ExtractedPage:
        page_number = index + 1
        try:
            page = doc[index]
            raw_text = self._extract_page_text(page)
        except Exception as exc:
            logger.warning(
                "page_extraction_failed",
                extra={"document_id": document_id, "page_number": page_number, "error": str(exc)},
            )
            return ExtractedPage(
                document_id=document_id,
                page_number=page_number,
                source_file=source_file,
                extraction_status=PageExtractionStatus.ERROR,
                raw_text="",
            )

        status = PageExtractionStatus.OK if raw_text.strip() else PageExtractionStatus.EMPTY
        return ExtractedPage(
            document_id=document_id,
            page_number=page_number,
            source_file=source_file,
            extraction_status=status,
            raw_text=raw_text,
        )

    @staticmethod
    def _extract_page_text(page: "fitz.Page") -> str:
        """Extracts text at block (paragraph) granularity and rejoins
        blocks with a blank line between them, so real paragraph
        boundaries survive as `\\n\\n` for downstream chunking -- PyMuPDF's
        plain "text" mode only inserts a single newline between blocks,
        which destroys that signal. Internal line wraps within a block are
        preserved as single newlines. Table-like blocks are preserved as-is
        (no reconstruction attempted; see app.document architecture note
        for a future dedicated table extractor)."""
        blocks = page.get_text("blocks")
        text_blocks = [b for b in blocks if b[6] == 0 and b[4].strip()]
        text_blocks.sort(key=lambda b: (round(b[1], 1), round(b[0], 1)))
        return "\n\n".join(b[4].rstrip("\n") for b in text_blocks)
