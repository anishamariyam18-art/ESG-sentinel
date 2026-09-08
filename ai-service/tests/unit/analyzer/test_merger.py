from app.analyzer.merger import (
    collect_source_references,
    dedupe_text_list,
    merge_metrics,
    merge_report_info,
    merge_risks,
    merge_targets,
)
from app.analyzer.schemas import BatchExtractionResult
from app.models.analyzer import NOT_FOUND, AnalyzerMetric, AnalyzerRisk, AnalyzerTarget, SourceReference


def test_dedupe_text_list_normalizes_whitespace_and_case():
    result = dedupe_text_list(["Solar power  investment.", "solar power investment.", "Wind power investment."])
    assert result == ["Solar power  investment.", "Wind power investment."]


def test_dedupe_text_list_drops_blank_entries():
    assert dedupe_text_list(["", "   ", "Real statement."]) == ["Real statement."]


def test_merge_report_info_takes_first_non_not_found_value():
    batches = [
        BatchExtractionResult(company_name=NOT_FOUND, industry=NOT_FOUND),
        BatchExtractionResult(company_name="Example Company", industry="Financial Services", reporting_year=2025),
        BatchExtractionResult(company_name="Should Not Win", reporting_year=2020),
    ]
    company, year, industry, report_type = merge_report_info(batches)
    assert company == "Example Company"
    assert year == 2025
    assert industry == "Financial Services"
    assert report_type == NOT_FOUND


def test_merge_metrics_merges_exact_duplicate_and_preserves_second_reference():
    metric_a = AnalyzerMetric(
        metric_name="Scope 1 emissions", value=123456, unit="tCO2e", reporting_year=2025,
        page_number=10, source_chunk_id="CHK-00010",
    )
    metric_b = AnalyzerMetric(
        metric_name="scope 1 emissions", value=123456, unit="tCO2e", reporting_year=2025,
        page_number=87, source_chunk_id="CHK-00087",
    )
    batches = [BatchExtractionResult(metrics=[metric_a]), BatchExtractionResult(metrics=[metric_b])]
    merged = merge_metrics(batches)
    assert len(merged) == 1
    assert merged[0].page_number == 10
    assert len(merged[0].additional_references) == 1
    assert merged[0].additional_references[0].chunk_id == "CHK-00087"


def test_merge_metrics_keeps_different_values_as_separate_entries():
    # Same metric name/unit/year but a DIFFERENT value is a contradiction,
    # not a duplicate -- both must survive, not be silently collapsed.
    metric_a = AnalyzerMetric(
        metric_name="Scope 1 emissions", value=100, unit="tCO2e", reporting_year=2025,
        page_number=10, source_chunk_id="CHK-00010",
    )
    metric_b = AnalyzerMetric(
        metric_name="Scope 1 emissions", value=200, unit="tCO2e", reporting_year=2025,
        page_number=11, source_chunk_id="CHK-00011",
    )
    merged = merge_metrics([BatchExtractionResult(metrics=[metric_a, metric_b])])
    assert len(merged) == 2
    assert {m.value for m in merged} == {100, 200}


def test_merge_metrics_keeps_different_years_as_separate_entries():
    metric_2024 = AnalyzerMetric(
        metric_name="Scope 1 emissions", value=100, unit="tCO2e", reporting_year=2024,
        page_number=10, source_chunk_id="CHK-00010",
    )
    metric_2025 = AnalyzerMetric(
        metric_name="Scope 1 emissions", value=90, unit="tCO2e", reporting_year=2025,
        page_number=11, source_chunk_id="CHK-00011",
    )
    merged = merge_metrics([BatchExtractionResult(metrics=[metric_2024, metric_2025])])
    assert len(merged) == 2


def test_merge_targets_merges_duplicate_target_across_batches():
    target_a = AnalyzerTarget(
        target="Reduce Scope 1 and 2 emissions", target_value=50, unit="%",
        target_year=2030, page_number=42, source_chunk_id="CHK-00042",
    )
    target_b = AnalyzerTarget(
        target="reduce scope 1 and 2 emissions", target_value=50, unit="%",
        target_year=2030, page_number=99, source_chunk_id="CHK-00099",
    )
    merged = merge_targets([BatchExtractionResult(targets=[target_a]), BatchExtractionResult(targets=[target_b])])
    assert len(merged) == 1
    assert len(merged[0].additional_references) == 1


def test_merge_risks_never_removes_distinct_risks():
    risk_a = AnalyzerRisk(risk="Physical climate risk to facilities.", page_number=5, source_chunk_id="CHK-00005")
    risk_b = AnalyzerRisk(risk="Regulatory transition risk.", page_number=6, source_chunk_id="CHK-00006")
    merged = merge_risks([BatchExtractionResult(risks=[risk_a, risk_b])])
    assert len(merged) == 2


def test_collect_source_references_deduplicates_by_chunk_id():
    metric = AnalyzerMetric(
        metric_name="Scope 1 emissions", page_number=10, source_chunk_id="CHK-00010",
    )
    target = AnalyzerTarget(target="Net zero by 2050", page_number=10, source_chunk_id="CHK-00010")
    refs = collect_source_references([metric], [target])
    assert len(refs) == 1
    assert refs[0].chunk_id == "CHK-00010"


def test_collect_source_references_includes_additional_references():
    metric = AnalyzerMetric(
        metric_name="Scope 1 emissions", page_number=10, source_chunk_id="CHK-00010",
        additional_references=[SourceReference(chunk_id="CHK-00099", page_number=99)],
    )
    refs = collect_source_references([metric])
    chunk_ids = {r.chunk_id for r in refs}
    assert chunk_ids == {"CHK-00010", "CHK-00099"}
