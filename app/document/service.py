"""Document processing orchestration: PDF -> validated Document.

PDF -> metadata -> page extraction -> conservative cleaning -> section
detection -> chunking. No LLM is called anywhere in this module.

`company` and `report_year` are supplied by the caller (upload context),
never inferred from PDF content -- inferring them would require the
analyzer (Phase 3), which this phase deliberately does not touch.
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import ChunkingConfig, get_settings
from app.core.logging import get_logger
from app.document.chunker import DocumentChunker
from app.document.cleaner import TextCleaner
from app.document.pdf_extractor import PdfExtractor
from app.document.section_detector import SectionDetector
from app.models.document import (
    Document,
    DocumentPage,
    PageExtractionStatus,
    ProcessingStatistics,
)

logger = get_logger(__name__)


class DocumentProcessingService:
    def __init__(
        self,
        extractor: PdfExtractor | None = None,
        cleaner: TextCleaner | None = None,
        section_detector: SectionDetector | None = None,
        chunker: DocumentChunker | None = None,
        chunking_config: ChunkingConfig | None = None,
    ) -> None:
        self._extractor = extractor or PdfExtractor()
        self._cleaner = cleaner or TextCleaner()
        self._section_detector = section_detector or SectionDetector()
        self._chunker = chunker or DocumentChunker()
        self._chunking_config = chunking_config or get_settings().chunking

    def process(self, pdf_path: Path, company: str, report_year: int) -> Document:
        pdf_path = Path(pdf_path)
        pdf_bytes = pdf_path.read_bytes()
        return self._process_bytes(pdf_bytes, source_file=pdf_path.name, company=company, report_year=report_year)

    def process_bytes(self, pdf_bytes: bytes, source_file: str, company: str, report_year: int) -> Document:
        return self._process_bytes(pdf_bytes, source_file=source_file, company=company, report_year=report_year)

    def _process_bytes(self, pdf_bytes: bytes, source_file: str, company: str, report_year: int) -> Document:
        extraction = self._extractor.extract_bytes(pdf_bytes, source_file=source_file)
        cleaning = self._cleaner.clean(extraction.pages)

        section_input = [(p.page_number, cleaning.cleaned_texts[p.page_number]) for p in extraction.pages]
        sections = self._section_detector.assign_sections(section_input)

        pages: list[DocumentPage] = []
        for extracted_page in extraction.pages:
            pn = extracted_page.page_number
            pages.append(
                DocumentPage(
                    document_id=extraction.document_id,
                    company=company,
                    report_year=report_year,
                    page_number=pn,
                    source_file=source_file,
                    extraction_status=extracted_page.extraction_status,
                    raw_text=extracted_page.raw_text,
                    text=cleaning.cleaned_texts[pn],
                    section=sections.get(pn, "Unknown"),
                )
            )

        chunks = []
        for page in pages:
            if page.extraction_status != PageExtractionStatus.OK:
                continue
            chunks.extend(
                self._chunker.chunk_page(
                    document_id=extraction.document_id,
                    company=company,
                    report_year=report_year,
                    page_number=page.page_number,
                    section=page.section,
                    cleaned_text=page.text,
                    config=self._chunking_config,
                )
            )

        pages_with_text = sum(1 for p in pages if p.extraction_status == PageExtractionStatus.OK)
        pages_without_text = sum(1 for p in pages if p.extraction_status == PageExtractionStatus.EMPTY)
        pages_with_errors = sum(1 for p in pages if p.extraction_status == PageExtractionStatus.ERROR)

        statistics = ProcessingStatistics(
            page_count=len(pages),
            pages_with_text=pages_with_text,
            pages_without_text=pages_without_text,
            pages_with_errors=pages_with_errors,
            chunk_count=len(chunks),
        )

        document = Document(
            document_id=extraction.document_id,
            company=company,
            report_year=report_year,
            source_filename=source_file,
            file_hash=extraction.file_hash,
            total_pages=len(pages),
            metadata=extraction.metadata,
            pages=pages,
            chunks=chunks,
            processing_statistics=statistics,
        )

        logger.info(
            "document_processed",
            extra={
                "document_id": document.document_id,
                "company": company,
                "page_count": statistics.page_count,
                "pages_with_text": statistics.pages_with_text,
                "pages_without_text": statistics.pages_without_text,
                "pages_with_errors": statistics.pages_with_errors,
                "chunk_count": statistics.chunk_count,
                "removed_header_variants": len(cleaning.header_footer_detection.removed_headers),
                "removed_footer_variants": len(cleaning.header_footer_detection.removed_footers),
            },
        )
        return document
