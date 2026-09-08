"""Claim extraction orchestration: Document + AnalyzerResult -> ClaimExtractionResult.

Pipeline (section 1): Candidate Extraction -> Validation -> Cleaning ->
Splitting -> Classification -> Deduplication -> Final Claims, with an
additional full-claim validation checkpoint right before deduplication
(section 13/24: confirms provenance is real and the claim is ESG-relevant,
things Pydantic's field validation alone cannot check).

The AnalyzerResult is accepted as context but the original document chunks
remain authoritative -- claims are never synthesized purely from analyzer
output (section 23).
"""
from __future__ import annotations

import time

from app.claims.classifier import ClaimClassifier, compute_claim_confidence, extract_numeric_info, extract_target_info
from app.claims.deduplicator import deduplicate_claims
from app.claims.extractor import ClaimExtractionBatchError, ClaimExtractor, RawCandidateClaim, build_claim_batches
from app.claims.splitter import split_candidate
from app.claims.validator import clean_claim_text, is_structurally_valid_candidate, validate_final_claim
from app.core.config import ClaimConfidenceWeights, ClaimsConfig, get_settings
from app.core.llm import LLMManager, get_llm_manager
from app.core.logging import get_logger
from app.models.analyzer import AnalyzerResult
from app.models.claim import Claim, ClaimExtractionResult
from app.models.document import Document, DocumentChunk

logger = get_logger(__name__)


class ClaimExtractionError(Exception):
    """Raised when claim extraction cannot produce any usable result (every
    batch failed). Callers must not treat a caught error as a valid, empty
    result."""


class ClaimExtractionService:
    def __init__(
        self,
        llm_manager: LLMManager | None = None,
        claims_config: ClaimsConfig | None = None,
        confidence_weights: ClaimConfidenceWeights | None = None,
    ) -> None:
        settings = get_settings()
        self._llm = llm_manager or get_llm_manager()
        self._config = claims_config or settings.claims
        self._confidence_weights = confidence_weights or settings.claim_confidence_weights
        self._extractor = ClaimExtractor(self._llm, self._config)
        self._classifier = ClaimClassifier(self._llm, self._config)

    def extract_claims(self, document: Document, analyzer_result: AnalyzerResult) -> ClaimExtractionResult:
        started = time.monotonic()

        if not document.chunks:
            logger.warning("claims_no_chunks", extra={"document_id": document.document_id})
            return ClaimExtractionResult(
                document_id=document.document_id, total_claims=0, claims=[],
                rejected_count=0, errors=["Document has no extractable chunks; nothing to analyze."],
            )

        candidates, batch_errors, batch_count = self._extract_all_candidates(document)
        if not candidates and batch_errors and len(batch_errors) == batch_count:
            raise ClaimExtractionError(
                f"Claim extraction failed for document {document.document_id}: all {batch_count} "
                f"batch(es) failed. Errors: {'; '.join(batch_errors)}"
            )

        chunk_by_id: dict[str, DocumentChunk] = {c.chunk_id: c for c in document.chunks}
        valid_chunk_ids = set(chunk_by_id)

        rejected_reasons: list[str] = []
        survivors: list[RawCandidateClaim] = []
        for cand in candidates:
            ok, reason = is_structurally_valid_candidate(cand.claim, self._config)
            if not ok:
                rejected_reasons.append(reason or "invalid candidate")
                continue
            if cand.source_chunk_id not in valid_chunk_ids:
                rejected_reasons.append(f"source_chunk_id '{cand.source_chunk_id}' not found in document")
                continue
            cleaned_text = clean_claim_text(cand.claim)
            survivors.append(RawCandidateClaim(
                claim=cleaned_text, page_number=cand.page_number, source_chunk_id=cand.source_chunk_id
            ))

        split_candidates: list[RawCandidateClaim] = []
        for cand in survivors:
            for piece in split_candidate(cand.claim):
                split_candidates.append(RawCandidateClaim(
                    claim=piece, page_number=cand.page_number, source_chunk_id=cand.source_chunk_id
                ))

        classifications = self._classifier.classify(
            [c.claim for c in split_candidates], document.document_id
        )

        built_claims: list[Claim] = []
        for cand, classification in zip(split_candidates, classifications):
            chunk = chunk_by_id[cand.source_chunk_id]
            numeric_info = extract_numeric_info(cand.claim)
            target_text, target_year = extract_target_info(cand.claim)
            confidence = compute_claim_confidence(
                claim_text=cand.claim, provenance_complete=True,
                classification_confidence=classification.confidence,
                numeric_info=numeric_info, claim_type=classification.claim_type,
                weights=self._confidence_weights,
            )
            claim = Claim(
                claim_id="PENDING",
                document_id=document.document_id, company=document.company, report_year=document.report_year,
                page_number=cand.page_number, section=chunk.section, source_chunk_id=cand.source_chunk_id,
                claim=cand.claim, category=classification.category, claim_type=classification.claim_type,
                metric_name=numeric_info.metric_name, value=numeric_info.value, unit=numeric_info.unit,
                target=target_text, target_year=target_year, confidence=confidence,
            )
            ok, reason = validate_final_claim(claim, valid_chunk_ids)
            if not ok:
                rejected_reasons.append(reason or "final validation failed")
                continue
            built_claims.append(claim)

        deduped = deduplicate_claims(built_claims, self._config)
        deduped.sort(key=lambda c: (c.page_number, c.claim))
        final_claims = [
            c.model_copy(update={"claim_id": f"CLM-{i + 1:06d}"}) for i, c in enumerate(deduped)
        ]

        elapsed = time.monotonic() - started
        logger.info(
            "claims_extraction_completed",
            extra={
                "document_id": document.document_id,
                "candidate_count": len(candidates),
                "split_candidate_count": len(split_candidates),
                "rejected_count": len(rejected_reasons),
                "final_claim_count": len(final_claims),
                "failed_batches": len(batch_errors),
                "processing_time_seconds": round(elapsed, 3),
            },
        )
        for reason in rejected_reasons:
            logger.info("claim_rejected", extra={"document_id": document.document_id, "reason": reason})

        return ClaimExtractionResult(
            document_id=document.document_id,
            total_claims=len(final_claims),
            claims=final_claims,
            rejected_count=len(rejected_reasons),
            errors=batch_errors,
        )

    def _extract_all_candidates(
        self, document: Document
    ) -> tuple[list[RawCandidateClaim], list[str], int]:
        batches = build_claim_batches(document.chunks, self._config)
        candidates: list[RawCandidateClaim] = []
        errors: list[str] = []
        for i, batch in enumerate(batches, start=1):
            try:
                batch_candidates, _repair_count = self._extractor.extract_batch(
                    document.document_id, batch, i, len(batches)
                )
                candidates.extend(batch_candidates)
            except ClaimExtractionBatchError as exc:
                errors.append(str(exc))
        return candidates, errors, len(batches)
