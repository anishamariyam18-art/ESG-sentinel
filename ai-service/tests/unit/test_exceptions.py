import pytest

from app.core.exceptions import (
    AnalyzerOutputInvalidError,
    DocumentExtractionError,
    DocumentNotFoundError,
    InvalidUploadError,
    PipelineStageError,
)


def test_pipeline_stage_error_carries_code_and_stage():
    exc = PipelineStageError("something broke")
    assert exc.code == "PIPELINE_ERROR"
    assert exc.stage == "pipeline"
    assert exc.message == "something broke"


def test_subclass_has_documented_code_and_stage():
    exc = AnalyzerOutputInvalidError("bad json")
    assert exc.code == "ANALYZER_OUTPUT_INVALID"
    assert exc.stage == "analyzer"


def test_to_dict_matches_the_documented_error_shape():
    exc = DocumentExtractionError("no usable text")
    assert exc.to_dict() == {"error": {"code": "EXTRACTION_FAILED", "message": "no usable text", "stage": "extraction"}}


def test_invalid_upload_error_code():
    assert InvalidUploadError("bad file").code == "INVALID_UPLOAD"


def test_document_not_found_error_code():
    assert DocumentNotFoundError("DOC-999 not found").code == "DOCUMENT_NOT_FOUND"


def test_exceptions_are_raisable_and_catchable_as_base_class():
    with pytest.raises(PipelineStageError) as exc_info:
        raise AnalyzerOutputInvalidError("boom")
    assert exc_info.value.code == "ANALYZER_OUTPUT_INVALID"


def test_stage_and_code_overridable_per_instance():
    exc = PipelineStageError("custom", stage="custom_stage", code="CUSTOM_CODE")
    assert exc.stage == "custom_stage"
    assert exc.code == "CUSTOM_CODE"
