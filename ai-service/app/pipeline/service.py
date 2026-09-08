"""End-to-end pipeline orchestration (Phase 10 sections 1-2, 17).

`PipelineOrchestrator.run` is the ONLY place that wires all 9 analysis
phases together in order -- it does not reimplement anything from them.
Every stage's OUTPUT is exactly what the next stage's documented INPUT
requires (section 2):

    Document -> AnalyzerResult -> Claims -> Evidence (ingest current doc)
    -> Verification -> Greenwashing -> (Verification + Greenwashing) TrustScore
    -> (Analyzer + Verification + Greenwashing + TrustScore) Recommendations

If document ingestion itself fails (invalid/unreadable PDF, or a PDF with
no usable text), `run` raises a `PipelineStageError` subclass -- there is no
`document_id` yet, so there is nothing valid to build a `PipelineResult`
from. Once ingestion succeeds, every LATER stage failure is instead caught
and turned into a `PipelineResult` with `pipeline_status="partial"` (or
`"failed"` if the very next stage after ingestion, the Analyzer, fails) --
whatever was already computed is preserved and returned rather than lost,
and `errors` names exactly which stage failed and why (section 20/45).
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from app.analyzer.service import AnalyzerError, AnalyzerService
from app.claims.service import ClaimExtractionError, ClaimExtractionService
from app.core.config import EvidencePolicy, get_settings
from app.core.exceptions import LLMNotConfiguredError
from app.core.llm import LLMGenerationError, LLMJsonError, LLMManager
from app.core.logging import get_logger
from app.document.ingestion import DocumentIngestionService
from app.evidence.indexer import EmbeddingProvider, EvidenceIndexer
from app.evidence.ingestion import EvidenceIngestionService
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.evidence.retriever import EvidenceRetriever
from app.greenwashing.service import GreenwashingService
from app.models.analyzer import AnalyzerResult
from app.models.claim import Claim
from app.models.greenwashing import GreenwashingResult
from app.models.pipeline import PipelineResult, ProcessingMetadata
from app.models.recommendation import RecommendationResult
from app.models.trust import TrustScore
from app.models.verification import VerificationResult
from app.recommendations.service import RecommendationService
from app.trust_score.service import TrustScoreService
from app.verification.service import VerificationService

logger = get_logger(__name__)


class PipelineOrchestrator:
    def __init__(
        self,
        repository: EvidenceRepository,
        indexer: EvidenceIndexer,
        lexical_index: LexicalIndex,
        retriever: EvidenceRetriever | None = None,
        llm_manager: LLMManager | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        ingestion_service: DocumentIngestionService | None = None,
    ) -> None:
        settings = get_settings()
        self._repository = repository
        self._indexer = indexer
        self._lexical_index = lexical_index
        self._retriever = retriever or EvidenceRetriever(repository=repository, indexer=indexer, lexical_index=lexical_index)
        self._llm = llm_manager
        self._ingestion_service = ingestion_service or DocumentIngestionService()
        self._evidence_ingestion = EvidenceIngestionService(
            repository=repository, indexer=indexer, lexical_index=lexical_index,
            config=settings.evidence, embedding_provider=embedding_provider,
        )
        self._settings = settings

    def run(
        self,
        pdf_path: Path,
        company: str,
        report_year: int,
        evidence_policy: EvidencePolicy | None = None,
        ingest_as_evidence: bool = True,
    ) -> PipelineResult:
        if self._llm is None:
            # Fail fast, before spending any time on ingestion: the
            # Analyzer/Claims/Verification/Greenwashing stages all require
            # a working LLM manager. Without this check, the underlying
            # `LLMGenerationError` from Phase 3's `get_llm_manager()` would
            # otherwise surface only once the Analyzer stage tried to
            # construct itself -- correct, but confusing and slower to
            # diagnose than a clear, immediate, dedicated error.
            raise LLMNotConfiguredError(
                "No LLM manager is configured (GEMINI_API_KEY is not set). "
                "POST /api/v1/analyze requires a working LLM for the Analyzer, "
                "claim extraction, and evidence/greenwashing judgment stages."
            )

        started = time.monotonic()
        stage_timings: dict[str, float] = {}

        # --- Stage: document ingestion -- failures here have no document_id
        # to build a PipelineResult around, so they propagate (section 4/20).
        t = time.monotonic()
        record = self._ingestion_service.ingest(pdf_path, company=company, report_year=report_year)
        document = record.document
        stage_timings["ingestion"] = round(time.monotonic() - t, 3)

        errors: list[str] = []
        analyzer_result: AnalyzerResult | None = None
        claims: list[Claim] = []
        verification_results: list[VerificationResult] = []
        greenwashing_results: list[GreenwashingResult] = []
        trust_score: TrustScore | None = None
        recommendations: RecommendationResult | None = None

        def _finalize(status: str) -> PipelineResult:
            stage_timings["total"] = round(time.monotonic() - started, 3)
            metadata = ProcessingMetadata(
                document_hash=document.file_hash,
                processing_timestamp=datetime.now(timezone.utc).isoformat(),
                llm_model_name=self._settings.gemini_model_name,
                embedding_model_name=self._settings.embedding_model_name,
                retrieval_config=self._settings.retrieval.model_dump(),
                verification_thresholds=self._settings.verification_thresholds.model_dump(),
                trust_score_weights=self._settings.trust_score_weights.model_dump(),
            )
            result = PipelineResult(
                document_id=document.document_id, company=company, report_year=report_year,
                pipeline_status=status, analyzer_result=analyzer_result, claims=claims,
                verification_results=verification_results, greenwashing_results=greenwashing_results,
                trust_score=trust_score, recommendations=recommendations, stage_timings=stage_timings,
                processing_metadata=metadata, errors=errors,
            )
            logger.info(
                "pipeline_run_completed",
                extra={
                    "document_id": document.document_id, "company": company, "pipeline_status": status,
                    "claim_count": len(claims), "verification_count": len(verification_results),
                    "greenwashing_count": len(greenwashing_results),
                    "trust_score": trust_score.trust_score if trust_score else None,
                    "stage_timings": stage_timings, "error_count": len(errors),
                },
            )
            return result

        # --- Stage: Analyzer ---
        t = time.monotonic()
        try:
            analyzer_result = AnalyzerService(llm_manager=self._llm).analyze(document)
        except (AnalyzerError, LLMGenerationError, LLMJsonError) as exc:
            errors.append(f"analyzer: {exc}")
            logger.error("pipeline_stage_failed", extra={"document_id": document.document_id, "stage": "analyzer", "error": str(exc)})
            return _finalize("failed")
        stage_timings["analyzer"] = round(time.monotonic() - t, 3)

        # --- Stage: Claim extraction ---
        t = time.monotonic()
        try:
            claim_result = ClaimExtractionService(llm_manager=self._llm).extract_claims(document, analyzer_result)
        except (ClaimExtractionError, LLMGenerationError, LLMJsonError) as exc:
            errors.append(f"claims: {exc}")
            logger.error("pipeline_stage_failed", extra={"document_id": document.document_id, "stage": "claims", "error": str(exc)})
            return _finalize("partial")
        claims = claim_result.claims
        stage_timings["claims"] = round(time.monotonic() - t, 3)

        # --- Stage: Evidence (ingest the current document's own claims as Layer-1 evidence) ---
        t = time.monotonic()
        if ingest_as_evidence and claims:
            try:
                self._evidence_ingestion.ingest_uploaded_report(document, claims)
            except Exception as exc:  # noqa: BLE001 -- evidence ingestion failure must not abort the pipeline
                errors.append(f"evidence: {exc}")
                logger.warning("pipeline_stage_degraded", extra={"document_id": document.document_id, "stage": "evidence", "error": str(exc)})
        stage_timings["evidence"] = round(time.monotonic() - t, 3)

        # --- Stage: Verification ---
        t = time.monotonic()
        try:
            verification_service = VerificationService(retriever=self._retriever, repository=self._repository, llm_manager=self._llm)
            verification_results = verification_service.verify_claims(claims, evidence_policy=evidence_policy)
        except Exception as exc:  # noqa: BLE001 -- a whole-batch failure must still return what's known so far
            errors.append(f"verification: {exc}")
            logger.error("pipeline_stage_failed", extra={"document_id": document.document_id, "stage": "verification", "error": str(exc)})
            return _finalize("partial")
        stage_timings["verification"] = round(time.monotonic() - t, 3)

        # --- Stage: Greenwashing ---
        t = time.monotonic()
        try:
            greenwashing_service = GreenwashingService(llm_manager=self._llm)
            greenwashing_results = greenwashing_service.analyze_claims(claims, verification_results)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"greenwashing: {exc}")
            logger.error("pipeline_stage_failed", extra={"document_id": document.document_id, "stage": "greenwashing", "error": str(exc)})
            return _finalize("partial")
        stage_timings["greenwashing"] = round(time.monotonic() - t, 3)

        # --- Stage: Trust Score ---
        t = time.monotonic()
        try:
            trust_score = TrustScoreService(llm_manager=self._llm).calculate_trust_score(
                document_id=document.document_id, company=company, claims=claims,
                verification_results=verification_results, greenwashing_results=greenwashing_results,
                analyzer_result=analyzer_result,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"trust_score: {exc}")
            logger.error("pipeline_stage_failed", extra={"document_id": document.document_id, "stage": "trust_score", "error": str(exc)})
            return _finalize("partial")
        stage_timings["trust_score"] = round(time.monotonic() - t, 3)

        # --- Stage: Recommendations ---
        t = time.monotonic()
        try:
            recommendations = RecommendationService(llm_manager=self._llm).generate_recommendations(
                document_id=document.document_id, company=company, claims=claims,
                verification_results=verification_results, greenwashing_results=greenwashing_results,
                trust_score=trust_score,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"recommendations: {exc}")
            logger.error("pipeline_stage_failed", extra={"document_id": document.document_id, "stage": "recommendations", "error": str(exc)})
            return _finalize("partial")
        stage_timings["recommendations"] = round(time.monotonic() - t, 3)

        return _finalize("completed")


__all__ = ["PipelineOrchestrator"]
