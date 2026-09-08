"""Page-aware document contracts.

The PDF is never flattened into a single string. `DocumentPage` keeps every
page individually addressable; `DocumentChunk` keeps section/paragraph/page
aware slices for downstream retrieval. Every model that references a page
carries `document_id`, `company`, and `report_year` so provenance survives
as data flows through later modules.

`DocumentPage.text` is the conservatively cleaned text used by downstream
modules; `DocumentPage.raw_text` is exactly what PyMuPDF extracted, kept for
audit so cleaning is never a one-way, unverifiable transformation.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class PageExtractionStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    ERROR = "error"


class PdfMetadata(BaseModel):
    """PDF-reported metadata. Never treated as authoritative ESG
    information -- these are document properties, not report content."""

    title: str | None = None
    author: str | None = None
    subject: str | None = None
    creator: str | None = None
    producer: str | None = None
    page_count: int = Field(ge=0)


class ProcessingStatistics(BaseModel):
    page_count: int = Field(ge=0)
    pages_with_text: int = Field(ge=0)
    pages_without_text: int = Field(ge=0)
    pages_with_errors: int = Field(ge=0)
    chunk_count: int = Field(ge=0)


class DocumentPage(BaseModel):
    document_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    report_year: int = Field(ge=1900, le=2100)
    page_number: int = Field(ge=1)
    source_file: str = Field(min_length=1)
    extraction_status: PageExtractionStatus
    raw_text: str
    text: str = Field(description="Conservatively cleaned text; see app.document.cleaner")
    section: str | None = None


class DocumentChunk(BaseModel):
    chunk_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    report_year: int = Field(ge=1900, le=2100)
    page_number: int = Field(ge=1)
    section: str | None = None
    text: str = Field(min_length=1)
    start_char: int | None = Field(default=None, ge=0)
    end_char: int | None = Field(default=None, ge=0)


class Document(BaseModel):
    document_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    report_year: int = Field(ge=1900, le=2100)
    source_filename: str = Field(min_length=1)
    file_hash: str = Field(min_length=1, description="SHA-256 of the uploaded PDF bytes")
    total_pages: int = Field(ge=0)
    metadata: PdfMetadata
    pages: list[DocumentPage] = Field(default_factory=list)
    chunks: list[DocumentChunk] = Field(default_factory=list)
    processing_statistics: ProcessingStatistics
