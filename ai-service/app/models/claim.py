"""ESG claim contract.

A claim is a verifiable assertion extracted from a specific page of a
specific company's report. Provenance fields (document_id, company,
report_year, page_number, section, source_chunk_id) are mandatory and must
never be inferred or defaulted -- they come directly from the source chunk.

`page_number`/`source_chunk_id` are the claim's *primary* location.
`source_references` holds any *additional* chunks the same claim legitimately
spans (Phase 4 section 10) -- a claim is never duplicated just because it
continues across a page/chunk boundary.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.models.provenance import SourceReference


class ClaimCategory(str, Enum):
    ENVIRONMENTAL = "Environmental"
    SOCIAL = "Social"
    GOVERNANCE = "Governance"
    UNKNOWN = "Unknown"


class ClaimType(str, Enum):
    METRIC = "Metric"
    PERFORMANCE = "Performance"
    CERTIFICATION = "Certification"
    POLICY = "Policy"
    COMMITMENT = "Commitment"
    COMPLIANCE = "Compliance"
    GENERAL = "General"


class Claim(BaseModel):
    claim_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    report_year: int = Field(ge=1900, le=2100)
    page_number: int = Field(ge=1)
    section: str | None = None
    source_chunk_id: str = Field(min_length=1)
    source_references: list[SourceReference] = Field(default_factory=list)

    claim: str = Field(min_length=1)
    category: ClaimCategory
    claim_type: ClaimType

    metric_name: str | None = None
    value: float | None = None
    unit: str | None = None
    target: str | None = None
    target_year: int | None = Field(default=None, ge=1900, le=2100)

    confidence: float = Field(ge=0.0, le=1.0)


class ClaimExtractionResult(BaseModel):
    document_id: str = Field(min_length=1)
    total_claims: int = Field(ge=0)
    claims: list[Claim] = Field(default_factory=list)
    rejected_count: int = Field(default=0, ge=0)
    errors: list[str] = Field(default_factory=list)
