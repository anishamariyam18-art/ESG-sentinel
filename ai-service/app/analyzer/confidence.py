"""Deterministic analyzer confidence methodology.

Never asks the LLM for a confidence number. The score is a weighted
combination of measurable factors (app.core.config.AnalyzerConfidenceWeights
documents and controls the weights) -- it is not a statement of statistical
certainty, only a documented, reproducible signal of how well-grounded and
complete this particular extraction run was.
"""
from __future__ import annotations

from app.core.config import AnalyzerConfidenceWeights
from app.models.analyzer import NOT_FOUND, ConfidenceBreakdown, SourceReference
from app.models.document import Document


def compute_confidence(
    document: Document,
    company_name: str,
    reporting_year: int | None,
    industry: str,
    report_type: str,
    executive_summary: str,
    environment_summary: str,
    social_summary: str,
    governance_summary: str,
    provenance_items: list,
    source_references: list[SourceReference],
    batch_count: int,
    failed_batch_count: int,
    json_repair_count: int,
    weights: AnalyzerConfidenceWeights,
) -> tuple[ConfidenceBreakdown, float]:
    total_chunks = len(document.chunks) or 1
    referenced_chunk_ids = {ref.chunk_id for ref in source_references}
    source_coverage = min(1.0, len(referenced_chunk_ids) / total_chunks)

    field_flags = [
        company_name != NOT_FOUND,
        reporting_year is not None,
        industry != NOT_FOUND,
        report_type != NOT_FOUND,
        executive_summary != NOT_FOUND,
        environment_summary != NOT_FOUND,
        social_summary != NOT_FOUND,
        governance_summary != NOT_FOUND,
    ]
    extraction_completeness = sum(field_flags) / len(field_flags)

    if provenance_items:
        fully_grounded = sum(
            1
            for item in provenance_items
            if getattr(item, "source_chunk_id", None) and getattr(item, "page_number", None) is not None
        )
        structured_field_availability = fully_grounded / len(provenance_items)
    else:
        structured_field_availability = 0.0

    model_response_validity = (batch_count - failed_batch_count) / batch_count if batch_count else 0.0
    parsing_quality = max(0.0, 1.0 - (json_repair_count / max(batch_count, 1)) * 0.5)

    breakdown = ConfidenceBreakdown(
        source_coverage=round(source_coverage, 3),
        extraction_completeness=round(extraction_completeness, 3),
        structured_field_availability=round(structured_field_availability, 3),
        model_response_validity=round(model_response_validity, 3),
        parsing_quality=round(parsing_quality, 3),
    )

    overall = (
        breakdown.source_coverage * weights.source_coverage
        + breakdown.extraction_completeness * weights.extraction_completeness
        + breakdown.structured_field_availability * weights.structured_field_availability
        + breakdown.model_response_validity * weights.model_response_validity
        + breakdown.parsing_quality * weights.parsing_quality
    )
    return breakdown, round(min(1.0, max(0.0, overall)), 3)
