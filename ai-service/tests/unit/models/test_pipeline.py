from app.models.pipeline import PipelineResult, ProcessingMetadata


def test_pipeline_result_minimal_construction():
    result = PipelineResult(document_id="DOC-001", company="Example Company", report_year=2025)
    assert result.claims == []
    assert result.trust_score is None
    assert result.errors == []


def test_pipeline_result_records_reproducibility_metadata():
    metadata = ProcessingMetadata(
        document_hash="a" * 64,
        processing_timestamp="2026-08-20T00:00:00+00:00",
        llm_model_name="gemini-2.5-flash",
        embedding_model_name="sentence-transformers/all-mpnet-base-v2",
        retrieval_config={"top_k": 5},
        trust_score_weights={"claim_quality": 0.15},
    )
    result = PipelineResult(
        document_id="DOC-001",
        company="Example Company",
        report_year=2025,
        processing_metadata=metadata,
    )
    assert result.processing_metadata.llm_model_name == "gemini-2.5-flash"
    assert result.processing_metadata.retrieval_config == {"top_k": 5}


def test_pipeline_result_accumulates_errors_without_crashing():
    result = PipelineResult(
        document_id="DOC-001",
        company="Example Company",
        report_year=2025,
        errors=["Claim CLM-000004 failed validation: empty claim text."],
    )
    assert len(result.errors) == 1
