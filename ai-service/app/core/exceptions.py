"""Centralized pipeline exceptions (Phase 10 section 20).

Every stage of the pipeline can fail in a structured, identifiable way.
`PipelineStageError` carries a machine-readable `code` and the `stage` that
failed, so the API layer can turn any of them into the same documented
`{"error": {"code", "message", "stage"}}` shape without inspecting free-text
messages. Stack traces are always logged internally (`app.core.logging`)
and never included in an API response.
"""
from __future__ import annotations


class PipelineStageError(Exception):
    """Base class for a structured, stage-attributed pipeline failure."""

    code: str = "PIPELINE_ERROR"
    stage: str = "pipeline"
    status_code: int = 500

    def __init__(self, message: str, *, stage: str | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if stage is not None:
            self.stage = stage
        if code is not None:
            self.code = code

    def to_dict(self) -> dict:
        return {"error": {"code": self.code, "message": self.message, "stage": self.stage}}


class InvalidUploadError(PipelineStageError):
    """Rejected before any processing starts: wrong file type, oversized,
    unsafe filename, or a path-traversal attempt."""

    code = "INVALID_UPLOAD"
    stage = "ingestion"
    status_code = 400


class DocumentExtractionError(PipelineStageError):
    """The PDF could not be opened, or contains no usable text at all
    (empty/scanned) -- extraction never continues silently with empty text."""

    code = "EXTRACTION_FAILED"
    stage = "extraction"
    status_code = 422


class AnalyzerOutputInvalidError(PipelineStageError):
    code = "ANALYZER_OUTPUT_INVALID"
    stage = "analyzer"
    status_code = 502


class ClaimExtractionFailedError(PipelineStageError):
    code = "CLAIM_EXTRACTION_FAILED"
    stage = "claims"
    status_code = 502


class EvidenceUnavailableError(PipelineStageError):
    """The evidence database/index could not be reached or built."""

    code = "EVIDENCE_UNAVAILABLE"
    stage = "evidence"
    status_code = 503


class VerificationFailedError(PipelineStageError):
    code = "VERIFICATION_FAILED"
    stage = "verification"
    status_code = 502


class GreenwashingFailedError(PipelineStageError):
    code = "GREENWASHING_FAILED"
    stage = "greenwashing"
    status_code = 502


class TrustScoreFailedError(PipelineStageError):
    code = "TRUST_SCORE_FAILED"
    stage = "trust_score"
    status_code = 502


class RecommendationFailedError(PipelineStageError):
    code = "RECOMMENDATION_FAILED"
    stage = "recommendations"
    status_code = 502


class DocumentNotFoundError(PipelineStageError):
    """Raised by the API layer when a `document_id` has no stored result."""

    code = "DOCUMENT_NOT_FOUND"
    stage = "lookup"
    status_code = 404


class LLMNotConfiguredError(PipelineStageError):
    """`POST /analyze` needs a working LLM manager (Analyzer, Claims, and
    Verification/Greenwashing judgment all call one) -- raised immediately,
    with a clear actionable message, rather than letting the pipeline start
    and fail confusingly partway through the Analyzer stage."""

    code = "LLM_NOT_CONFIGURED"
    stage = "configuration"
    status_code = 503
