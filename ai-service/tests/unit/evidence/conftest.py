from __future__ import annotations

import hashlib
import math

import pytest

from app.core.config import EvidenceConfig
from app.evidence.lexical import tokenize
from app.evidence.repository import EvidenceRepository
from app.models.claim import Claim, ClaimCategory, ClaimType
from app.models.document import Document, DocumentChunk, PdfMetadata, ProcessingStatistics


class FakeEmbeddingProvider:
    """Deterministic, hash-based bag-of-words embedding -- no real model,
    no network, but genuinely text-similarity-sensitive (similar token sets
    produce similar vectors), so retrieval-ranking tests are meaningful."""

    DIM = 64

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [self._encode_one(text) for text in texts]

    def _encode_one(self, text: str) -> list[float]:
        vector = [0.0] * self.DIM
        for token in tokenize(text):
            bucket = int(hashlib.md5(token.encode()).hexdigest(), 16) % self.DIM
            vector[bucket] += 1.0
        norm = math.sqrt(sum(x * x for x in vector)) or 1.0
        return [x / norm for x in vector]


def evidence_config(**overrides) -> EvidenceConfig:
    fields = dict(
        corroboration_similarity_threshold=0.5, max_corroborating_chunks_per_claim=2,
        default_top_k=10, min_evidence_text_length=10, storage_filename="evidence_store.json",
    )
    fields.update(overrides)
    return EvidenceConfig(_env_file=None, **fields)


def build_document(
    chunk_texts: list[str], company: str = "Example Company", report_year: int = 2025,
    document_id: str = "DOC-001", section: str = "Environmental > Climate",
) -> Document:
    chunks = [
        DocumentChunk(
            chunk_id=f"CHK-{i:05d}", document_id=document_id, company=company, report_year=report_year,
            page_number=i, section=section, text=text,
        )
        for i, text in enumerate(chunk_texts, start=1)
    ]
    return Document(
        document_id=document_id, company=company, report_year=report_year, source_filename="report.pdf",
        file_hash="a" * 64, total_pages=len(chunks), metadata=PdfMetadata(page_count=len(chunks)),
        chunks=chunks,
        processing_statistics=ProcessingStatistics(
            page_count=len(chunks), pages_with_text=len(chunks), pages_without_text=0,
            pages_with_errors=0, chunk_count=len(chunks),
        ),
    )


def build_claim(
    *, claim_id: str = "CLM-000001", document_id: str = "DOC-001", company: str = "Example Company",
    report_year: int = 2025, page_number: int = 1, section: str | None = "Environmental > Climate",
    source_chunk_id: str = "CHK-00001", claim: str = "Scope 1 emissions decreased by 18%.",
    category: ClaimCategory = ClaimCategory.ENVIRONMENTAL, claim_type: ClaimType = ClaimType.PERFORMANCE,
    value: float | None = 18.0, unit: str | None = "%", target_year: int | None = None,
    confidence: float = 0.9, source_references: list | None = None,
) -> Claim:
    return Claim(
        claim_id=claim_id, document_id=document_id, company=company, report_year=report_year,
        page_number=page_number, section=section, source_chunk_id=source_chunk_id, claim=claim,
        category=category, claim_type=claim_type, value=value, unit=unit, target_year=target_year,
        confidence=confidence, source_references=source_references or [],
    )


@pytest.fixture
def tmp_repository(tmp_path) -> EvidenceRepository:
    return EvidenceRepository(tmp_path / "evidence_store.json")
