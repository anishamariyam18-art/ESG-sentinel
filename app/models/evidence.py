"""Evidence contracts.

Three source layers share the same `Evidence` shape, distinguished by
`source_type`:

- uploaded_report: extracted directly from the company's uploaded PDF
  (primary evidence, Phase 5 Layer 1). document_id/page_number/
  source_chunk_id are required.
- external_report: the external ESG-report evidence layer (Phase 5 Layer 2)
  -- other companies' or other reports' ESG disclosures. document_id/
  page_number may be absent, but `organization`/`report_title`/
  `source_authority` should be populated when known.
- government / regulatory / filing / dataset: reserved for future
  authoritative sources (Phase 5 Layer 3, NOT implemented here). The
  `metadata` field exists specifically so source-specific attributes for
  these (dataset_name, dataset_id, record_id, retrieved_at, ...) can be
  added later without another schema migration. A corporate ESG report must
  NEVER be tagged with one of these source types -- that would misrepresent
  it as government/regulatory evidence.

`EvidenceMatch` is the retrieval-time view of an Evidence record, carrying
per-signal scores so a verification result can show exactly how a piece of
evidence was ranked. `reranker_score`/`final_score` are Phase 6's job to
populate (hybrid combination + reranking); Phase 5 only fills in
`semantic_score`/`lexical_score`/`quality_score`.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from app.models.claim import ClaimCategory


class SourceType(str, Enum):
    UPLOADED_REPORT = "uploaded_report"
    EXTERNAL_REPORT = "external_report"
    GOVERNMENT = "government"
    REGULATORY = "regulatory"
    FILING = "filing"
    DATASET = "dataset"
    XBRL = "XBRL"


class Evidence(BaseModel):
    evidence_id: str = Field(min_length=1)
    source_type: SourceType
    company: str = Field(min_length=1)

    # Uploaded-report provenance (required when source_type == uploaded_report)
    document_id: str | None = None
    report_year: int | None = Field(default=None, ge=1900, le=2100)
    page_number: int | None = Field(default=None, ge=1)
    section: str | None = None
    source_chunk_id: str | None = None

    category: ClaimCategory | None = None
    evidence_text: str = Field(min_length=1)
    metric_name: str | None = None
    value: float | None = None
    unit: str | None = None
    target_year: int | None = Field(default=None, ge=1900, le=2100)

    # External-evidence-layer provenance
    organization: str | None = None
    report_title: str | None = None
    reporting_period: str | None = None
    sub_category: str | None = None
    claim_text: str | None = None
    source_url: str | None = None
    source_authority: str | None = None
    verification_status: str | None = None
    last_updated: str | None = None

    #: Extension point for future source types (Layer 3) -- e.g.
    #: {"dataset_name": ..., "dataset_id": ..., "record_id": ...,
    #: "retrieved_at": ...} for source_type=government/regulatory/dataset.
    #: Never used to store fields the current source types already have
    #: dedicated columns for.
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_uploaded_report_provenance(self) -> "Evidence":
        if self.source_type == SourceType.UPLOADED_REPORT:
            missing = [
                field
                for field in ("document_id", "page_number", "source_chunk_id")
                if getattr(self, field) is None
            ]
            if missing:
                raise ValueError(
                    f"source_type=uploaded_report requires {missing} to be set"
                )
        return self


class EvidenceMatch(BaseModel):
    evidence_id: str = Field(min_length=1)
    source_type: SourceType
    company: str = Field(min_length=1)
    document_id: str | None = None
    report_year: int | None = None
    report_title: str | None = None
    page_number: int | None = None
    source_chunk_id: str | None = None
    evidence_text: str = Field(min_length=1)

    lexical_score: float = 0.0
    semantic_score: float = 0.0
    quality_score: float | None = None
    reranker_score: float | None = None
    final_score: float = 0.0


class ClaimEvidenceResult(BaseModel):
    """Per-claim evidence-extraction outcome. Always present for every
    claim passed to the extractor -- `evidence_found=False` with an empty
    `evidence` list is the explicit, structured representation of "no
    supporting passage found", never a fabricated placeholder record."""

    claim_id: str = Field(min_length=1)
    evidence_found: bool
    evidence: list[Evidence] = Field(default_factory=list)
