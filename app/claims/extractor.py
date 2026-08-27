"""Candidate claim extraction (LLM stage).

Produces raw candidates with provenance -- nothing here decides whether a
candidate is actually a valid, ESG-relevant, non-duplicate claim; that's
validator.py/splitter.py/classifier.py/deduplicator.py downstream. This
stage's only job is: read the supplied chunks, propose candidate claim
strings with a cited chunk id/page number, and fail explicitly (never
silently) if the model's response can't be trusted.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.analyzer.context_builder import build_batches
from app.claims.prompt import build_extraction_prompt
from app.core.config import ClaimsConfig
from app.core.llm import LLMGenerationError, LLMJsonError, LLMManager
from app.core.logging import get_logger
from app.models.document import DocumentChunk

logger = get_logger(__name__)


class RawCandidateClaim(BaseModel):
    claim: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    source_chunk_id: str = Field(min_length=1)


class CandidateBatchResult(BaseModel):
    candidates: list[RawCandidateClaim] = Field(default_factory=list)


class ClaimExtractionBatchError(Exception):
    """One batch could not produce usable candidates after retries. The
    caller (service.py) decides whether to continue with other batches or
    treat this as a total failure."""


def build_claim_batches(
    chunks: list[DocumentChunk], config: ClaimsConfig
) -> list[list[DocumentChunk]]:
    return build_batches(chunks, config.max_batch_chars, config.max_chunks_per_batch)


class ClaimExtractor:
    def __init__(self, llm_manager: LLMManager, config: ClaimsConfig) -> None:
        self._llm = llm_manager
        self._config = config

    def extract_batch(
        self, document_id: str, batch: list[DocumentChunk], batch_number: int, total_batches: int
    ) -> tuple[list[RawCandidateClaim], int]:
        """Returns (candidates, repair_count). Raises
        ClaimExtractionBatchError if this batch never produces valid,
        schema-conformant JSON after retries -- never fabricates candidates."""
        prompt = build_extraction_prompt(batch, batch_number, total_batches)
        repair_count = 0
        last_error: Exception | None = None
        attempts = self._config.max_schema_retries + 1

        for attempt in range(attempts):
            try:
                raw_json, meta = self._llm.generate_json(prompt)
            except LLMJsonError as exc:
                last_error = exc
                logger.warning(
                    "claim_batch_json_failed",
                    extra={"document_id": document_id, "batch_number": batch_number, "attempt": attempt},
                )
                continue
            except LLMGenerationError as exc:
                last_error = exc
                logger.warning(
                    "claim_batch_generation_failed",
                    extra={"document_id": document_id, "batch_number": batch_number, "attempt": attempt},
                )
                continue

            repair_count += meta.get("repair_count", 0)
            try:
                result = CandidateBatchResult.model_validate(raw_json)
                return result.candidates, repair_count
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "claim_batch_schema_invalid",
                    extra={"document_id": document_id, "batch_number": batch_number, "attempt": attempt},
                )
                continue

        raise ClaimExtractionBatchError(
            f"Batch {batch_number}/{total_batches} failed after {attempts} attempt(s): {last_error}"
        )
