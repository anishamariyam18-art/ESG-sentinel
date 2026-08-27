"""ESG claim verification orchestration (sections 2, 27, 28).

Pipeline: Claim -> Evidence Retrieval -> Candidate Filtering (via the
retriever's metadata filtering, already company-scoped) -> Evidence
Reranking -> per-candidate Consistency Checks -> LLM Evidence Judgment ->
Weighted Verification Score -> Status -> Explanation.

`verify_claims` never lets one claim's failure stop the batch: a claim
that raises gets a structured Unsupported result explaining the failure,
never a propagated exception and never a fabricated success.
"""
from __future__ import annotations

import time

from app.core.config import (
    EvidencePolicy,
    VerificationConfidenceWeights,
    VerificationConfig,
    VerificationThresholds,
    VerificationWeights,
    get_settings,
)
from app.core.llm import LLMManager, get_llm_manager
from app.core.logging import get_logger
from app.evidence.repository import EvidenceRepository
from app.evidence.retriever import EvidenceRetriever
from app.evidence.validator import compute_evidence_quality
from app.models.claim import Claim
from app.models.evidence import Evidence, EvidenceMatch, SourceType
from app.models.verification import VerificationChecks, VerificationResult, VerificationStatus
from app.verification.consistency import run_consistency_checks
from app.verification.judge import EvidenceJudge, JudgmentResult, judgment_to_score
from app.verification.scorer import compute_confidence_score, compute_verification_score, determine_status

logger = get_logger(__name__)

_NO_EVIDENCE_EXPLANATION = [
    "No sufficiently relevant evidence was found.",
    "The available evidence does not establish the claimed value.",
]


def _neutral_checks() -> VerificationChecks:
    """Used for the no-evidence / retrieval-failure short-circuits, where
    most signals genuinely have nothing to measure -- entity/llm_support/
    provenance/semantic/lexical stay at 0 (nothing confirmed), while
    numeric/unit/temporal/category default to 1.0 (no contradiction is
    possible when there is nothing to compare against)."""
    return VerificationChecks(
        semantic=0.0, lexical=0.0, numeric=1.0, unit=1.0, temporal=1.0,
        entity=0.0, category=1.0, llm_support=0.0, provenance=0.0,
    )


class VerificationService:
    def __init__(
        self,
        retriever: EvidenceRetriever,
        repository: EvidenceRepository,
        llm_manager: LLMManager | None = None,
        config: VerificationConfig | None = None,
        weights: VerificationWeights | None = None,
        confidence_weights: VerificationConfidenceWeights | None = None,
        thresholds: VerificationThresholds | None = None,
    ) -> None:
        settings = get_settings()
        self._retriever = retriever
        self._repository = repository
        self._llm = llm_manager or get_llm_manager()
        self._config = config or settings.verification
        self._weights = weights or settings.verification_weights
        self._confidence_weights = confidence_weights or settings.verification_confidence_weights
        self._thresholds = thresholds or settings.verification_thresholds
        self._judge = EvidenceJudge(self._llm, self._config)

    def verify_claims(self, claims: list[Claim], evidence_policy: EvidencePolicy | None = None) -> list[VerificationResult]:
        results = []
        for claim in claims:
            try:
                results.append(self.verify_claim(claim, evidence_policy=evidence_policy))
            except Exception as exc:  # noqa: BLE001 -- one claim's bug must never abort the batch
                logger.error(
                    "verification_claim_failed_unexpectedly",
                    extra={"claim_id": claim.claim_id, "error": str(exc)},
                )
                results.append(self._failure_result(claim, f"Verification failed unexpectedly: {exc}"))
        return results

    def verify_claim(self, claim: Claim, evidence_policy: EvidencePolicy | None = None) -> VerificationResult:
        started = time.monotonic()
        policy = evidence_policy or self._config.default_evidence_policy
        exclude_document_id = claim.document_id if policy == EvidencePolicy.EXTERNAL_EVIDENCE_ONLY else None

        try:
            matches = self._retriever.search(
                claim.claim, company=claim.company, exclude_document_id=exclude_document_id,
                top_k=self._config.candidates_per_claim,
            )
        except Exception as exc:  # noqa: BLE001 -- retrieval failure must not crash verification
            logger.warning("verification_retrieval_failed", extra={"claim_id": claim.claim_id, "error": str(exc)})
            return self._failure_result(claim, f"Evidence retrieval failed: {exc}")

        if not matches:
            logger.info(
                "verification_completed",
                extra={
                    "claim_id": claim.claim_id, "retrieval_count": 0, "selected_evidence_ids": [],
                    "verification_score": 0.0, "status": VerificationStatus.UNSUPPORTED.value,
                    "processing_time_seconds": round(time.monotonic() - started, 3),
                },
            )
            return self._no_evidence_result(claim)

        candidates = self._rerank(matches)
        judgment_pool = [evidence for _, _, evidence in candidates[: self._config.max_llm_judgment_candidates]]
        judgments = self._judge.judge(claim, judgment_pool)
        llm_available = bool(judgments)

        matched_evidence: list[EvidenceMatch] = []
        candidate_scores: list[float] = []
        best: tuple[float, VerificationChecks, list[str], Evidence, JudgmentResult | None] | None = None

        for rerank_score, match, evidence in candidates:
            consistency, _claim_components, _evidence_components = run_consistency_checks(
                claim, evidence, self._thresholds
            )
            judgment = judgments.get(evidence.evidence_id)
            provenance = match.quality_score if match.quality_score is not None else compute_evidence_quality(evidence)

            checks = VerificationChecks(
                semantic=match.semantic_score, lexical=match.lexical_score,
                numeric=consistency.numeric, unit=consistency.unit, temporal=consistency.temporal,
                entity=consistency.entity, category=consistency.category,
                llm_support=judgment_to_score(judgment), provenance=provenance,
            )
            candidate_score = compute_verification_score(checks, self._weights)
            candidate_scores.append(candidate_score)

            hard_fail_reasons = list(consistency.hard_fail_reasons)
            if judgment and judgment.contradictions:
                hard_fail_reasons.append("explicit_contradiction")

            matched_evidence.append(
                match.model_copy(update={"reranker_score": round(rerank_score, 4), "final_score": round(candidate_score / 100, 4)})
            )

            if best is None or candidate_score > best[0]:
                best = (candidate_score, checks, hard_fail_reasons, evidence, judgment)

        assert best is not None  # candidates is non-empty because matches is non-empty
        best_score, best_checks, best_hard_fails, best_evidence, best_judgment = best

        status = determine_status(best_score, best_hard_fails, self._thresholds)
        confidence = compute_confidence_score(
            best_checks, llm_available, candidate_scores, len(candidates), self._confidence_weights
        )
        explanation = self._build_explanation(status, best_checks, best_hard_fails, best_judgment, best_evidence)

        matched_evidence.sort(key=lambda m: m.final_score, reverse=True)

        result = VerificationResult(
            claim_id=claim.claim_id, status=status, verification_score=best_score, confidence_score=confidence,
            matched_evidence=matched_evidence, checks=best_checks,
            reason=explanation[0] if explanation else "", explanation=explanation,
        )

        logger.info(
            "verification_completed",
            extra={
                "claim_id": claim.claim_id, "retrieval_count": len(matches),
                "selected_evidence_ids": [m.evidence_id for m in matched_evidence],
                "verification_score": best_score, "status": status.value,
                "processing_time_seconds": round(time.monotonic() - started, 3),
            },
        )
        return result

    def _rerank(self, matches: list[EvidenceMatch]) -> list[tuple[float, EvidenceMatch, Evidence]]:
        """Combines semantic/lexical/quality into a provisional reranking
        score, with a small bonus for uploaded_report evidence (section
        20). Candidates whose full Evidence record can no longer be found
        (deleted between retrieval and now) are silently skipped rather
        than fabricated."""
        settings = get_settings()
        ranked = []
        for match in matches:
            evidence = self._repository.get(match.evidence_id)
            if evidence is None:
                continue
            bonus = (
                self._config.uploaded_report_priority_bonus
                if evidence.source_type == SourceType.UPLOADED_REPORT else 0.0
            )
            score = (
                match.semantic_score * settings.retrieval.semantic_weight
                + match.lexical_score * settings.retrieval.lexical_weight
                + (match.quality_score or 0.0) * 0.1
                + bonus
            )
            ranked.append((score, match, evidence))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return ranked

    def _no_evidence_result(self, claim: Claim) -> VerificationResult:
        checks = _neutral_checks()
        confidence = compute_confidence_score(checks, False, [], 0, self._confidence_weights)
        return VerificationResult(
            claim_id=claim.claim_id, status=VerificationStatus.UNSUPPORTED, verification_score=0.0,
            confidence_score=confidence, matched_evidence=[], checks=checks,
            reason=_NO_EVIDENCE_EXPLANATION[0], explanation=list(_NO_EVIDENCE_EXPLANATION),
        )

    def _failure_result(self, claim: Claim, reason: str) -> VerificationResult:
        checks = _neutral_checks()
        return VerificationResult(
            claim_id=claim.claim_id, status=VerificationStatus.UNSUPPORTED, verification_score=0.0,
            confidence_score=0.0, matched_evidence=[], checks=checks, reason=reason, explanation=[reason],
        )

    def _build_explanation(
        self, status: VerificationStatus, checks: VerificationChecks, hard_fail_reasons: list[str],
        judgment: JudgmentResult | None, evidence: Evidence,
    ) -> list[str]:
        lines: list[str] = []
        source_desc = "the uploaded ESG report" if evidence.source_type == SourceType.UPLOADED_REPORT else "an external ESG report"

        if status == VerificationStatus.VERIFIED:
            lines.append("The evidence refers to the same metric and matches the claimed value.")
            lines.append(f"The evidence originates from {source_desc} (page {evidence.page_number}).")
            if checks.temporal >= 0.99:
                lines.append("The reporting period matches.")
            lines.append("No numerical or directional contradiction was detected.")
            if judgment and judgment.reason:
                lines.append(f"LLM assessment: {judgment.reason}")
            elif checks.llm_support == 0.5:
                lines.append("LLM judgment was unavailable for this claim; the score reflects deterministic signals only.")
            return lines

        # PARTIALLY_VERIFIED and UNSUPPORTED (with at least one evidence
        # candidate -- the true no-evidence case is handled by
        # _no_evidence_result, never by this method) share the same
        # contradiction-specific explanations; only the framing differs.
        if status == VerificationStatus.PARTIALLY_VERIFIED:
            lines.append("The evidence relates to the claimed topic but does not fully match every component.")
        else:
            if "wrong_company" in hard_fail_reasons:
                lines.append("The retrieved evidence belongs to a different company and cannot support this claim.")
            else:
                lines.append("The available evidence does not sufficiently establish the claimed value.")

        if "numeric_contradiction" in hard_fail_reasons:
            lines.append("The claimed numeric value differs from the value stated in the evidence.")
        if "direction_contradiction" in hard_fail_reasons:
            lines.append("The evidence reports the opposite direction of change from the claim.")
        if "unit_incompatible" in hard_fail_reasons:
            lines.append("The evidence uses a different, incompatible unit.")
        if "target_year_incompatible" in hard_fail_reasons:
            lines.append("The evidence states a different target year than the claim.")
        if checks.temporal < 0.99 and not any(
            r in hard_fail_reasons for r in ("numeric_contradiction", "direction_contradiction")
        ):
            lines.append("The reporting period does not clearly match.")

        if judgment and judgment.reason:
            lines.append(f"LLM assessment: {judgment.reason}")
        elif checks.llm_support == 0.5:
            lines.append("LLM judgment was unavailable for this claim; the score reflects deterministic signals only.")

        return lines
