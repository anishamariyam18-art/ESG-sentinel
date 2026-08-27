from __future__ import annotations

import json

from app.core.config import ClaimConfidenceWeights, ClaimsConfig
from app.models.analyzer import AnalyzerResult
from app.models.document import Document, DocumentChunk, PdfMetadata, ProcessingStatistics

# Reuse the generic scripted-LLM test double and manager factory already
# built for the analyzer tests -- neither is analyzer-specific.
from tests.unit.analyzer.conftest import ScriptedLLMProvider, make_manager  # noqa: F401


def claims_config(**overrides) -> ClaimsConfig:
    fields = dict(
        max_batch_chars=100000, max_chunks_per_batch=100, max_schema_retries=0,
        min_claim_length=15, near_duplicate_similarity_threshold=0.85,
        max_classification_batch_size=25,
    )
    fields.update(overrides)
    return ClaimsConfig(_env_file=None, **fields)


def confidence_weights() -> ClaimConfidenceWeights:
    return ClaimConfidenceWeights(_env_file=None)


def build_document(
    chunk_texts: list[str], company: str = "Example Company", report_year: int = 2025,
    section: str = "Environmental > Climate",
) -> Document:
    chunks = [
        DocumentChunk(
            chunk_id=f"CHK-{i:05d}", document_id="DOC-001", company=company, report_year=report_year,
            page_number=i, section=section, text=text,
        )
        for i, text in enumerate(chunk_texts, start=1)
    ]
    return Document(
        document_id="DOC-001", company=company, report_year=report_year, source_filename="report.pdf",
        file_hash="a" * 64, total_pages=len(chunks), metadata=PdfMetadata(page_count=len(chunks)),
        chunks=chunks,
        processing_statistics=ProcessingStatistics(
            page_count=len(chunks), pages_with_text=len(chunks), pages_without_text=0,
            pages_with_errors=0, chunk_count=len(chunks),
        ),
    )


def extraction_batch_json(candidates: list[dict]) -> str:
    return json.dumps({"candidates": candidates})


def classification_batch_json(classifications: list[dict]) -> str:
    return json.dumps({"classifications": classifications})


def minimal_analyzer_result(document_id: str = "DOC-001") -> AnalyzerResult:
    return AnalyzerResult(document_id=document_id, confidence=0.5)
