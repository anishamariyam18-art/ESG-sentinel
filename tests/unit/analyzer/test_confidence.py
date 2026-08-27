from app.analyzer.confidence import compute_confidence
from app.core.config import AnalyzerConfidenceWeights
from app.models.analyzer import NOT_FOUND, AnalyzerMetric, SourceReference
from app.models.document import (
    Document,
    DocumentChunk,
    PdfMetadata,
    ProcessingStatistics,
)


def _document(chunk_count: int) -> Document:
    chunks = [
        DocumentChunk(
            chunk_id=f"CHK-{i:05d}", document_id="DOC-001", company="Example Company",
            report_year=2025, page_number=i, text="text",
        )
        for i in range(1, chunk_count + 1)
    ]
    return Document(
        document_id="DOC-001", company="Example Company", report_year=2025,
        source_filename="report.pdf", file_hash="a" * 64, total_pages=chunk_count,
        metadata=PdfMetadata(page_count=chunk_count), chunks=chunks,
        processing_statistics=ProcessingStatistics(
            page_count=chunk_count, pages_with_text=chunk_count, pages_without_text=0,
            pages_with_errors=0, chunk_count=chunk_count,
        ),
    )


def _weights() -> AnalyzerConfidenceWeights:
    return AnalyzerConfidenceWeights(_env_file=None)


def test_full_coverage_and_complete_fields_yields_high_confidence():
    document = _document(2)
    metric = AnalyzerMetric(metric_name="Scope 1 emissions", page_number=1, source_chunk_id="CHK-00001")
    refs = [SourceReference(chunk_id="CHK-00001", page_number=1), SourceReference(chunk_id="CHK-00002", page_number=2)]
    breakdown, confidence = compute_confidence(
        document=document, company_name="Example Company", reporting_year=2025,
        industry="Financial Services", report_type="Sustainability Report",
        executive_summary="Summary.", environment_summary="Env.", social_summary="Soc.",
        governance_summary="Gov.", provenance_items=[metric], source_references=refs,
        batch_count=1, failed_batch_count=0, json_repair_count=0, weights=_weights(),
    )
    assert breakdown.source_coverage == 1.0
    assert breakdown.extraction_completeness == 1.0
    assert breakdown.structured_field_availability == 1.0
    assert breakdown.model_response_validity == 1.0
    assert confidence > 0.9


def test_no_extraction_at_all_yields_zero_confidence():
    document = _document(3)
    breakdown, confidence = compute_confidence(
        document=document, company_name=NOT_FOUND, reporting_year=None,
        industry=NOT_FOUND, report_type=NOT_FOUND,
        executive_summary=NOT_FOUND, environment_summary=NOT_FOUND, social_summary=NOT_FOUND,
        governance_summary=NOT_FOUND, provenance_items=[], source_references=[],
        batch_count=1, failed_batch_count=1, json_repair_count=0, weights=_weights(),
    )
    assert breakdown.source_coverage == 0.0
    assert breakdown.extraction_completeness == 0.0
    assert breakdown.model_response_validity == 0.0
    # parsing_quality alone (JSON syntax health) can still be nonzero, but
    # with everything else at zero the overall score must stay near-zero.
    assert confidence < 0.15


def test_failed_batches_reduce_model_response_validity():
    document = _document(1)
    breakdown, _ = compute_confidence(
        document=document, company_name="X", reporting_year=2025, industry=NOT_FOUND,
        report_type=NOT_FOUND, executive_summary=NOT_FOUND, environment_summary=NOT_FOUND,
        social_summary=NOT_FOUND, governance_summary=NOT_FOUND, provenance_items=[],
        source_references=[], batch_count=4, failed_batch_count=2, json_repair_count=0,
        weights=_weights(),
    )
    assert breakdown.model_response_validity == 0.5


def test_json_repairs_reduce_parsing_quality():
    document = _document(1)
    clean, _ = compute_confidence(
        document=document, company_name=NOT_FOUND, reporting_year=None, industry=NOT_FOUND,
        report_type=NOT_FOUND, executive_summary=NOT_FOUND, environment_summary=NOT_FOUND,
        social_summary=NOT_FOUND, governance_summary=NOT_FOUND, provenance_items=[],
        source_references=[], batch_count=2, failed_batch_count=0, json_repair_count=0,
        weights=_weights(),
    )
    repaired, _ = compute_confidence(
        document=document, company_name=NOT_FOUND, reporting_year=None, industry=NOT_FOUND,
        report_type=NOT_FOUND, executive_summary=NOT_FOUND, environment_summary=NOT_FOUND,
        social_summary=NOT_FOUND, governance_summary=NOT_FOUND, provenance_items=[],
        source_references=[], batch_count=2, failed_batch_count=0, json_repair_count=2,
        weights=_weights(),
    )
    assert repaired.parsing_quality < clean.parsing_quality


def test_source_coverage_never_exceeds_one_even_with_extra_references():
    document = _document(1)
    refs = [SourceReference(chunk_id="CHK-00001", page_number=1), SourceReference(chunk_id="CHK-99999", page_number=2)]
    breakdown, _ = compute_confidence(
        document=document, company_name=NOT_FOUND, reporting_year=None, industry=NOT_FOUND,
        report_type=NOT_FOUND, executive_summary=NOT_FOUND, environment_summary=NOT_FOUND,
        social_summary=NOT_FOUND, governance_summary=NOT_FOUND, provenance_items=[],
        source_references=refs, batch_count=1, failed_batch_count=0, json_repair_count=0,
        weights=_weights(),
    )
    assert breakdown.source_coverage == 1.0


def test_confidence_score_never_exceeds_one():
    document = _document(1)
    metric = AnalyzerMetric(metric_name="X", page_number=1, source_chunk_id="CHK-00001")
    _, confidence = compute_confidence(
        document=document, company_name="X", reporting_year=2025, industry="Y",
        report_type="Z", executive_summary="S", environment_summary="E",
        social_summary="So", governance_summary="G", provenance_items=[metric],
        source_references=[SourceReference(chunk_id="CHK-00001", page_number=1)],
        batch_count=1, failed_batch_count=0, json_repair_count=0, weights=_weights(),
    )
    assert 0.0 <= confidence <= 1.0
