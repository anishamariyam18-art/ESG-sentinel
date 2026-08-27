"""ESG Analyzer orchestration: Document -> AnalyzerResult.

DocumentProcessor -> Analyzer is the only pipeline edge implemented so far.
Analyzer never calls Claims/Evidence/Verification/etc -- those are later
phases. On total failure (every batch failed) this raises `AnalyzerError`;
callers must not treat a caught error as a valid, empty result and must not
proceed to downstream modules when it's raised.
"""
from __future__ import annotations

import time

from pydantic import ValidationError

from app.analyzer.confidence import compute_confidence
from app.analyzer.context_builder import build_batches
from app.analyzer.merger import (
    collect_source_references,
    merge_claims,
    merge_commitments,
    merge_costing,
    merge_environment,
    merge_governance,
    merge_metrics,
    merge_opportunities,
    merge_report_info,
    merge_risks,
    merge_social,
    merge_targets,
)
from app.analyzer.prompt import build_batch_prompt, build_synthesis_prompt
from app.analyzer.schemas import BatchExtractionResult, SynthesisResult
from app.core.config import AnalyzerConfig, AnalyzerConfidenceWeights, get_settings
from app.core.llm import LLMGenerationError, LLMJsonError, LLMManager, get_llm_manager
from app.core.logging import get_logger
from app.models.analyzer import AnalyzerResult, ConfidenceBreakdown
from app.models.document import Document

logger = get_logger(__name__)


class AnalyzerError(Exception):
    """Raised when the analyzer cannot produce any usable result (every
    batch failed). Never caught to fabricate a fake success -- the pipeline
    must not continue to Claims when this is raised."""


class AnalyzerService:
    def __init__(
        self,
        llm_manager: LLMManager | None = None,
        analyzer_config: AnalyzerConfig | None = None,
        confidence_weights: AnalyzerConfidenceWeights | None = None,
    ) -> None:
        settings = get_settings()
        self._llm = llm_manager or get_llm_manager()
        self._config = analyzer_config or settings.analyzer
        self._confidence_weights = confidence_weights or settings.analyzer_confidence_weights

    def analyze(self, document: Document) -> AnalyzerResult:
        started = time.monotonic()

        if not document.chunks:
            logger.warning("analyzer_no_chunks", extra={"document_id": document.document_id})
            return self._empty_result(
                document, reason="Document has no extractable chunks; nothing to analyze."
            )

        batches = build_batches(document.chunks, self._config.max_batch_chars, self._config.max_chunks_per_batch)
        batch_results: list[BatchExtractionResult] = []
        errors: list[str] = []
        json_repair_count = 0

        for i, batch in enumerate(batches, start=1):
            prompt = build_batch_prompt(batch, i, len(batches))
            batch_result, repair_count, error = self._extract_batch(prompt, document.document_id, i, len(batches))
            json_repair_count += repair_count
            if batch_result is not None:
                batch_results.append(batch_result)
            else:
                errors.append(error)

        if not batch_results:
            raise AnalyzerError(
                f"Analyzer failed for document {document.document_id}: all {len(batches)} batch(es) "
                f"failed. Errors: {'; '.join(errors)}"
            )

        company_name, reporting_year, industry, report_type = merge_report_info(batch_results)
        environment = merge_environment(batch_results)
        social = merge_social(batch_results)
        governance = merge_governance(batch_results)
        claims = merge_claims(batch_results)
        metrics = merge_metrics(batch_results)
        targets = merge_targets(batch_results)
        commitments = merge_commitments(batch_results)
        risks = merge_risks(batch_results)
        opportunities = merge_opportunities(batch_results)
        costing_summary = merge_costing(batch_results)
        source_references = collect_source_references(
            metrics, targets, commitments, risks, opportunities, costing_summary, claims
        )

        synthesis = self._synthesize(
            document.document_id, company_name, environment, social, governance, metrics, targets, commitments
        )
        environment = environment.model_copy(update={"summary": synthesis.environment_summary})
        social = social.model_copy(update={"summary": synthesis.social_summary})
        governance = governance.model_copy(update={"summary": synthesis.governance_summary})

        provenance_items = [*metrics, *targets, *commitments, *risks, *opportunities, *costing_summary]
        breakdown, confidence = compute_confidence(
            document=document,
            company_name=company_name,
            reporting_year=reporting_year,
            industry=industry,
            report_type=report_type,
            executive_summary=synthesis.executive_summary,
            environment_summary=environment.summary,
            social_summary=social.summary,
            governance_summary=governance.summary,
            provenance_items=provenance_items,
            source_references=source_references,
            batch_count=len(batches),
            failed_batch_count=len(errors),
            json_repair_count=json_repair_count,
            weights=self._confidence_weights,
        )

        elapsed = time.monotonic() - started
        logger.info(
            "analyzer_completed",
            extra={
                "document_id": document.document_id,
                "batch_count": len(batches),
                "failed_batches": len(errors),
                "chunk_count": len(document.chunks),
                "metric_count": len(metrics),
                "target_count": len(targets),
                "commitment_count": len(commitments),
                "confidence": confidence,
                "processing_time_seconds": round(elapsed, 3),
                "model_name": get_settings().gemini_model_name,
            },
        )

        return AnalyzerResult(
            document_id=document.document_id,
            company_name=company_name,
            reporting_year=reporting_year,
            industry=industry,
            report_type=report_type,
            executive_summary=synthesis.executive_summary,
            environment=environment,
            social=social,
            governance=governance,
            claims=claims,
            metrics=metrics,
            targets=targets,
            commitments=commitments,
            risks=risks,
            opportunities=opportunities,
            costing_summary=costing_summary,
            confidence=confidence,
            confidence_breakdown=breakdown,
            source_references=source_references,
            errors=errors,
        )

    def _extract_batch(
        self, prompt: str, document_id: str, batch_number: int, total_batches: int
    ) -> tuple[BatchExtractionResult | None, int, str | None]:
        """Implements the retry -> repair -> validate -> fail-explicitly
        pipeline for one batch. JSON-syntax repair/retry happens inside
        LLMManager.generate_json (its own, separate budget); this loop
        additionally retries on Pydantic schema-validation failure, since a
        syntactically valid JSON object can still not match
        BatchExtractionResult. Kept as a small, independent budget
        (AnalyzerConfig.max_schema_retries) rather than reusing
        LLMConfig.max_retries, so the two retry loops don't compound into
        an unbounded-feeling number of provider calls per batch."""
        repair_count = 0
        last_error: Exception | None = None
        attempts = self._config.max_schema_retries + 1

        for attempt in range(attempts):
            try:
                raw_json, meta = self._llm.generate_json(prompt)
            except LLMJsonError as exc:
                last_error = exc
                logger.warning(
                    "analyzer_batch_json_failed",
                    extra={"document_id": document_id, "batch_number": batch_number, "attempt": attempt},
                )
                continue
            except LLMGenerationError as exc:
                last_error = exc
                logger.warning(
                    "analyzer_batch_generation_failed",
                    extra={"document_id": document_id, "batch_number": batch_number, "attempt": attempt},
                )
                continue

            repair_count += meta.get("repair_count", 0)
            try:
                return BatchExtractionResult.model_validate(raw_json), repair_count, None
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "analyzer_batch_schema_invalid",
                    extra={"document_id": document_id, "batch_number": batch_number, "attempt": attempt},
                )
                continue

        message = f"Batch {batch_number}/{total_batches} failed after {attempts} attempt(s): {last_error}"
        return None, repair_count, message

    def _synthesize(
        self, document_id, company_name, environment, social, governance, metrics, targets, commitments
    ) -> SynthesisResult:
        prompt = build_synthesis_prompt(
            company_name=company_name,
            environment_findings=environment.model_dump(exclude={"summary"}),
            social_findings=social.model_dump(exclude={"summary"}),
            governance_findings=governance.model_dump(exclude={"summary"}),
            top_metrics=[f"{m.metric_name}: {m.value} {m.unit or ''}".strip() for m in metrics[:20]],
            top_targets=[t.target for t in targets[:20]],
            top_commitments=[c.commitment for c in commitments[:20]],
        )
        try:
            raw_json, _ = self._llm.generate_json(prompt)
            return SynthesisResult.model_validate(raw_json)
        except (LLMJsonError, LLMGenerationError, ValidationError) as exc:
            logger.warning("analyzer_synthesis_failed", extra={"document_id": document_id, "error": str(exc)})
            return SynthesisResult()

    def _empty_result(self, document: Document, reason: str) -> AnalyzerResult:
        breakdown = ConfidenceBreakdown(
            source_coverage=0.0,
            extraction_completeness=0.0,
            structured_field_availability=0.0,
            model_response_validity=0.0,
            parsing_quality=0.0,
        )
        return AnalyzerResult(
            document_id=document.document_id,
            confidence=0.0,
            confidence_breakdown=breakdown,
            errors=[reason],
        )
