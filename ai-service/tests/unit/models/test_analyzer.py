import pytest
from pydantic import ValidationError

from app.models.analyzer import (
    NOT_FOUND,
    AnalyzerClaim,
    AnalyzerMetric,
    AnalyzerResult,
    AnalyzerTarget,
    ConfidenceBreakdown,
    SourceReference,
)


def _confidence() -> ConfidenceBreakdown:
    return ConfidenceBreakdown(
        source_coverage=0.5, extraction_completeness=0.5,
        structured_field_availability=0.5, model_response_validity=1.0,
        parsing_quality=1.0,
    )


def test_analyzer_result_defaults_represent_missing_data_explicitly():
    result = AnalyzerResult(document_id="DOC-001", confidence=0.5)
    assert result.company_name == NOT_FOUND
    assert result.industry == NOT_FOUND
    assert result.environment.summary == NOT_FOUND
    assert result.metrics == []
    assert result.targets == []
    assert result.errors == []


def test_analyzer_result_confidence_must_be_bounded():
    with pytest.raises(ValidationError):
        AnalyzerResult(document_id="DOC-001", confidence=1.5)


def test_analyzer_result_accepts_populated_fields():
    result = AnalyzerResult(
        document_id="DOC-001",
        company_name="Example Company",
        reporting_year=2025,
        industry="Financial Services",
        report_type="Sustainability Report",
        confidence=0.9,
        confidence_breakdown=_confidence(),
        metrics=[
            AnalyzerMetric(
                metric_name="Scope 1 emissions", value=123456, unit="tCO2e",
                reporting_year=2025, page_number=87, source_chunk_id="CHK-00087",
            )
        ],
        source_references=[SourceReference(chunk_id="CHK-00087", page_number=87)],
    )
    assert result.company_name == "Example Company"
    assert result.metrics[0].value == 123456
    assert result.confidence_breakdown.source_coverage == 0.5


def test_metric_preserves_value_unit_and_provenance():
    metric = AnalyzerMetric(
        metric_name="Scope 2 emissions", value=45000, unit="tCO2e",
        reporting_year=2025, page_number=12, source_chunk_id="CHK-00012",
    )
    assert metric.value == 45000
    assert metric.unit == "tCO2e"
    assert metric.page_number == 12
    assert metric.source_chunk_id == "CHK-00012"
    assert metric.additional_references == []


def test_metric_requires_page_and_chunk_provenance():
    with pytest.raises(ValidationError):
        AnalyzerMetric(metric_name="Scope 1 emissions", page_number=1)  # missing source_chunk_id


def test_target_preserves_target_year_and_baseline():
    target = AnalyzerTarget(
        target="Reduce Scope 1 and 2 emissions", target_value=50, unit="%",
        baseline_year=2020, target_year=2030, page_number=42, source_chunk_id="CHK-00042",
    )
    assert target.target_year == 2030
    assert target.baseline_year == 2020


def test_metric_additional_references_preserve_multiple_page_occurrences():
    metric = AnalyzerMetric(
        metric_name="Scope 1 emissions", value=123456, unit="tCO2e", reporting_year=2025,
        page_number=10, source_chunk_id="CHK-00010",
        additional_references=[SourceReference(chunk_id="CHK-00087", page_number=87)],
    )
    assert len(metric.additional_references) == 1
    assert metric.additional_references[0].page_number == 87


def test_analyzer_claim_provenance_is_optional():
    claim = AnalyzerClaim(claim="The company committed to net zero by 2050.")
    assert claim.page_number is None
    assert claim.source_chunk_id is None


def test_analyzer_result_never_invents_reporting_year_when_absent():
    result = AnalyzerResult(document_id="DOC-001", confidence=0.0)
    assert result.reporting_year is None
