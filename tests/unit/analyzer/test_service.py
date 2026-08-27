import pytest
from pydantic import ValidationError

from app.analyzer.service import AnalyzerError, AnalyzerService
from app.core.llm import LLMJsonError
from app.models.analyzer import NOT_FOUND
from tests.unit.analyzer.conftest import (
    analyzer_config,
    batch_json,
    build_document,
    confidence_weights,
    make_manager,
    synthesis_json,
)


def _service(manager, config=None):
    return AnalyzerService(
        llm_manager=manager,
        analyzer_config=config or analyzer_config(),
        confidence_weights=confidence_weights(),
    )


def test_analyzer_returns_valid_result_for_valid_document(small_document):
    manager, provider = make_manager([
        batch_json(company_name="Example Company", reporting_year=2025, industry="Financial Services"),
        synthesis_json(executive_summary="A short summary."),
    ])
    result = _service(manager).analyze(small_document)

    assert result.document_id == "DOC-001"
    assert result.company_name == "Example Company"
    assert result.reporting_year == 2025
    assert result.executive_summary == "A short summary."
    assert result.errors == []


def test_missing_fields_become_not_found_or_empty_list(small_document):
    manager, _ = make_manager([batch_json(), synthesis_json()])
    result = _service(manager).analyze(small_document)

    assert result.company_name == NOT_FOUND
    assert result.industry == NOT_FOUND
    assert result.reporting_year is None
    assert result.metrics == []
    assert result.targets == []
    assert result.risks == []


def test_analyzer_never_fabricates_missing_information(small_document):
    # The mock never mentions an industry or reporting year -- the result
    # must reflect that honestly, never guess a plausible-looking value.
    manager, _ = make_manager([batch_json(company_name="Example Company"), synthesis_json()])
    result = _service(manager).analyze(small_document)

    assert result.company_name == "Example Company"
    assert result.industry == NOT_FOUND
    assert result.reporting_year is None


def test_invalid_json_batch_is_rejected_and_recorded(small_document):
    # llm max_retries=0 and analyzer max_schema_retries=0 -> exactly one
    # provider call for the one batch, which never becomes valid JSON.
    manager, _ = make_manager(["not json at all {{{"], max_retries=0)
    with pytest.raises(AnalyzerError):
        _service(manager, analyzer_config(max_schema_retries=0)).analyze(small_document)


def test_required_provenance_fields_are_validated(small_document):
    # A metric missing source_chunk_id/page_number must fail Pydantic
    # validation and ultimately be excluded -- never silently accepted
    # with fabricated provenance.
    bad_metric_batch = batch_json(metrics=[{"metric_name": "Scope 1 emissions"}])
    manager, _ = make_manager([bad_metric_batch], max_retries=0)
    with pytest.raises(AnalyzerError):
        _service(manager, analyzer_config(max_schema_retries=0)).analyze(small_document)


def test_metrics_preserve_value_and_unit(small_document):
    batch = batch_json(metrics=[
        {"metric_name": "Scope 1 emissions", "value": 123456, "unit": "tCO2e",
         "reporting_year": 2025, "page_number": 1, "source_chunk_id": "CHK-00001"}
    ])
    manager, _ = make_manager([batch, synthesis_json()])
    result = _service(manager).analyze(small_document)

    assert len(result.metrics) == 1
    assert result.metrics[0].value == 123456
    assert result.metrics[0].unit == "tCO2e"


def test_targets_preserve_target_year(small_document):
    batch = batch_json(targets=[
        {"target": "Reduce Scope 1 and 2 emissions", "target_value": 50, "unit": "%",
         "baseline_year": 2020, "target_year": 2030, "page_number": 1, "source_chunk_id": "CHK-00001"}
    ])
    manager, _ = make_manager([batch, synthesis_json()])
    result = _service(manager).analyze(small_document)

    assert result.targets[0].target_year == 2030
    assert result.targets[0].baseline_year == 2020


def test_page_and_source_references_are_preserved(small_document):
    batch = batch_json(metrics=[
        {"metric_name": "Scope 1 emissions", "page_number": 1, "source_chunk_id": "CHK-00001"}
    ])
    manager, _ = make_manager([batch, synthesis_json()])
    result = _service(manager).analyze(small_document)

    assert any(ref.chunk_id == "CHK-00001" and ref.page_number == 1 for ref in result.source_references)


def test_large_document_is_processed_in_multiple_batches():
    document = build_document(5)
    manager, provider = make_manager(
        [batch_json(), batch_json(), batch_json(), batch_json(), batch_json(), synthesis_json()]
    )
    config = analyzer_config(max_chunks_per_batch=1, max_batch_chars=100000)
    result = _service(manager, config).analyze(document)

    batch_calls = [c for c in provider.calls if "batch" in c["prompt"].lower()]
    assert len(batch_calls) == 5
    assert result.document_id == "DOC-001"


def test_duplicate_metrics_across_batches_are_merged():
    document = build_document(2)
    metric_payload = {
        "metric_name": "Scope 1 emissions", "value": 123456, "unit": "tCO2e",
        "reporting_year": 2025, "page_number": 1, "source_chunk_id": "CHK-00001",
    }
    other_payload = dict(metric_payload, page_number=2, source_chunk_id="CHK-00002")
    manager, _ = make_manager([
        batch_json(metrics=[metric_payload]),
        batch_json(metrics=[other_payload]),
        synthesis_json(),
    ])
    config = analyzer_config(max_chunks_per_batch=1, max_batch_chars=100000)
    result = _service(manager, config).analyze(document)

    assert len(result.metrics) == 1
    assert len(result.metrics[0].additional_references) == 1


def test_empty_document_returns_zero_confidence_without_llm_call():
    document = build_document(0)
    manager, provider = make_manager([])
    result = _service(manager).analyze(document)

    assert result.confidence == 0.0
    assert result.errors != []
    assert provider.calls == []


def test_partial_batch_failure_continues_with_remaining_batches():
    document = build_document(2)
    config = analyzer_config(max_chunks_per_batch=1, max_batch_chars=100000, max_schema_retries=0)
    manager, _ = make_manager([
        "unparseable {{{",  # batch 1 fails (single attempt: llm + analyzer retries both 0)
        batch_json(company_name="Example Company"),  # batch 2 succeeds
        synthesis_json(),
    ], max_retries=0)
    result = _service(manager, config).analyze(document)

    assert result.company_name == "Example Company"
    assert len(result.errors) == 1
    assert "Batch 1/2" in result.errors[0]


def test_synthesis_failure_falls_back_to_not_found_without_crashing(small_document):
    manager, _ = make_manager([batch_json(), "unparseable {{{", "unparseable {{{"], max_retries=1)
    result = _service(manager).analyze(small_document)

    assert result.executive_summary == NOT_FOUND
    assert result.errors == []  # synthesis failure is not a batch failure
