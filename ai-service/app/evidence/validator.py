"""Deterministic evidence validation.

Pydantic's `Evidence` model already enforces structural rules (required
fields, enum validity, uploaded_report provenance). This module adds
domain rules Pydantic can't express on its own:

- external_report provenance completeness (section 11: organization,
  report title, report year, document id, page number, source authority,
  evidence text are all required; source_url is optional).
- uploaded_report anti-fabrication: the cited chunk must actually exist in
  the document it claims to come from.
- a minimum-usefulness text-length floor.
"""
from __future__ import annotations

from app.core.config import EvidenceConfig
from app.models.evidence import Evidence, SourceType

_EXTERNAL_REQUIRED_FIELDS = (
    "organization", "report_title", "report_year", "document_id",
    "page_number", "source_authority", "evidence_text",
)


def validate_evidence(
    evidence: Evidence, config: EvidenceConfig, valid_chunk_ids: set[str] | None = None
) -> tuple[bool, str | None]:
    if len(evidence.evidence_text.strip()) < config.min_evidence_text_length:
        return False, f"evidence_text shorter than minimum length ({config.min_evidence_text_length} chars)"

    if evidence.source_type == SourceType.UPLOADED_REPORT:
        if valid_chunk_ids is not None and evidence.source_chunk_id not in valid_chunk_ids:
            return False, (
                f"source_chunk_id '{evidence.source_chunk_id}' was not found in the document "
                "it claims to come from (fabricated provenance)"
            )

    if evidence.source_type == SourceType.EXTERNAL_REPORT:
        missing = [f for f in _EXTERNAL_REQUIRED_FIELDS if getattr(evidence, f) in (None, "")]
        if missing:
            return False, f"external_report evidence missing required provenance field(s): {missing}"

    if evidence.source_type in (SourceType.GOVERNMENT, SourceType.REGULATORY, SourceType.DATASET, SourceType.FILING):
        # Layer 3 is schema-ready but not implemented -- reject rather than
        # silently accept a record we have no ingestion path for yet, so a
        # caller can't accidentally mislabel a corporate report this way.
        return False, f"source_type={evidence.source_type.value} is not yet implemented in Phase 5"

    return True, None


_SOURCE_TYPE_QUALITY = {
    SourceType.UPLOADED_REPORT: 1.0,  # strongest: the report the claim itself came from
    SourceType.EXTERNAL_REPORT: 0.8,
}


def compute_evidence_quality(evidence: Evidence) -> float:
    """Documented, deterministic quality signal from measurable properties
    of the record itself -- source authority, provenance completeness,
    page traceability, text completeness, and source type. This is NOT a
    verification score (that's Phase 6's job): a high-quality piece of
    evidence can still turn out not to support a given claim."""
    authority_score = 1.0 if evidence.source_authority else 0.5

    provenance_flags = [
        evidence.document_id is not None,
        evidence.page_number is not None,
        evidence.source_chunk_id is not None,
    ]
    provenance_score = sum(provenance_flags) / len(provenance_flags)

    text_length = len(evidence.evidence_text.strip())
    completeness_score = min(1.0, text_length / 100)

    source_type_score = _SOURCE_TYPE_QUALITY.get(evidence.source_type, 0.5)

    return round(
        (authority_score + provenance_score + completeness_score + source_type_score) / 4, 3
    )
