"""Greenwashing detection orchestration (sections 21, 24-27).

Input is exactly what the spec allows: a `Claim`, its Phase 6
`VerificationResult` (which already carries `matched_evidence`) -- nothing
is independently searched or pulled from outside the pipeline. The best-
matched `EvidenceMatch` is expanded into a full `Evidence` record purely
from its own fields (never a repository lookup), then handed to the
deterministic detectors reused from Phase 6.

`analyze_claims` never lets one claim's failure stop the batch: a failing
claim gets a structured, LOW-risk (never fabricated HIGH) result explaining
what went wrong.
"""
from __future__ import annotations

import time

from app.core.config import (
    GreenwashingAggregationConfig,
    GreenwashingConfidenceWeights,
    GreenwashingThresholds,
    GreenwashingWeights,
    VerificationThresholds,
    get_settings,
)
from app.core.llm import LLMManager, get_llm_manager
from app.core.logging import get_logger
from app.greenwashing.detector import DetectorReport, run_detectors
from app.greenwashing.explainability import build_explanation, build_reason, build_recommendation
from app.greenwashing.judge import GreenwashingJudge
from app.greenwashing.scorer import (
    build_features,
    compute_greenwashing_confidence,
    compute_greenwashing_score,
    derive_hard_signals,
    determine_greenwashing_types,
    determine_risk_level,
    estimate_claim_importance,
)
from app.models.claim import Claim
from app.models.evidence import Evidence, EvidenceMatch
from app.models.greenwashing import GreenwashingFeatures, GreenwashingReport, GreenwashingResult, GreenwashingType, RiskLevel
from app.models.verification import VerificationResult, VerificationStatus

logger = get_logger(__name__)


def _evidence_from_match(match: EvidenceMatch) -> Evidence:
    """Expands a retrieval-time EvidenceMatch back into a full Evidence
    record using only fields the match already carries -- no store lookup,
    matching section 1's "do not independently search" constraint."""
    return Evidence(
        evidence_id=match.evidence_id, source_type=match.source_type, company=match.company,
        document_id=match.document_id, report_year=match.report_year, report_title=match.report_title,
        page_number=match.page_number, source_chunk_id=match.source_chunk_id, evidence_text=match.evidence_text,
    )


class GreenwashingService:
    def __init__(
        self,
        llm_manager: LLMManager | None = None,
        weights: GreenwashingWeights | None = None,
        confidence_weights: GreenwashingConfidenceWeights | None = None,
        thresholds: GreenwashingThresholds | None = None,
        aggregation_config: GreenwashingAggregationConfig | None = None,
        verification_thresholds: VerificationThresholds | None = None,
    ) -> None:
        settings = get_settings()
        self._llm = llm_manager or get_llm_manager()
        self._weights = weights or settings.greenwashing_weights
        self._confidence_weights = confidence_weights or settings.greenwashing_confidence_weights
        self._thresholds = thresholds or settings.greenwashing_thresholds
        self._aggregation_config = aggregation_config or settings.greenwashing_aggregation
        self._verification_thresholds = verification_thresholds or settings.verification_thresholds
        self._judge = GreenwashingJudge(self._llm, self._aggregation_config)

    def analyze_claims(self, claims: list[Claim], verification_results: list[VerificationResult]) -> list[GreenwashingResult]:
        results_by_claim_id = {r.claim_id: r for r in verification_results}
        results: list[GreenwashingResult] = []
        for claim in claims:
            verification_result = results_by_claim_id.get(claim.claim_id)
            if verification_result is None:
                results.append(self._failure_result(claim, None, "No verification result was supplied for this claim."))
                continue
            try:
                results.append(self.analyze_claim(claim, verification_result))
            except Exception as exc:  # noqa: BLE001 -- one claim's bug must never abort the batch
                logger.error("greenwashing_claim_failed_unexpectedly", extra={"claim_id": claim.claim_id, "error": str(exc)})
                results.append(self._failure_result(claim, verification_result, f"Greenwashing analysis failed unexpectedly: {exc}"))
        return results

    def analyze_claim(self, claim: Claim, verification_result: VerificationResult) -> GreenwashingResult:
        started = time.monotonic()

        best_match = verification_result.matched_evidence[0] if verification_result.matched_evidence else None
        best_evidence = _evidence_from_match(best_match) if best_match else None

        report = run_detectors(claim, best_evidence, self._verification_thresholds.numerical_tolerance_pct)
        has_evidence = best_evidence is not None

        llm_judgment = None
        if report.any_detected():
            try:
                llm_judgment = self._judge.judge(claim, verification_result, best_evidence, report)
            except Exception as exc:  # noqa: BLE001 -- LLM failure must fall back, never crash
                logger.warning("greenwashing_judgment_failed", extra={"claim_id": claim.claim_id, "error": str(exc)})
                llm_judgment = None

        features = build_features(report, verification_result, best_match)
        score = compute_greenwashing_score(features, self._weights)
        hard_signals = derive_hard_signals(report, has_evidence)
        risk = determine_risk_level(score, hard_signals, self._thresholds)
        types = determine_greenwashing_types(report, verification_result.status)
        confidence = compute_greenwashing_confidence(features, llm_judgment is not None, self._confidence_weights)

        llm_reasoning = llm_judgment.reasoning if llm_judgment else None
        explanation = build_explanation(verification_result.status, report, llm_reasoning)
        reason = build_reason(risk, types)
        recommendation = build_recommendation(types)

        result = GreenwashingResult(
            claim_id=claim.claim_id, claim=claim.claim, verification_status=verification_result.status,
            greenwashing_risk=risk, greenwashing_type=types, greenwashing_score=score, confidence_score=confidence,
            reason=reason, evidence=verification_result.matched_evidence, features=features,
            explanation=explanation, recommendation=recommendation,
        )

        logger.info(
            "greenwashing_analyzed",
            extra={
                "claim_id": claim.claim_id, "verification_status": verification_result.status.value,
                "detected_signals": [s.signal for s in report.all_signals() if s.detected],
                "greenwashing_score": score, "greenwashing_risk": risk.value,
                "processing_time_seconds": round(time.monotonic() - started, 3),
            },
        )
        return result

    def analyze_greenwashing(self, claims: list[Claim], results: list[GreenwashingResult]) -> GreenwashingReport:
        """Report-level aggregation (section 25). Requires the source
        claims too (not just results) so importance-weighting (section 27)
        has real data to work from rather than inventing materiality."""
        total = len(results)
        low = sum(1 for r in results if r.greenwashing_risk == RiskLevel.LOW)
        medium = sum(1 for r in results if r.greenwashing_risk == RiskLevel.MEDIUM)
        high = sum(1 for r in results if r.greenwashing_risk == RiskLevel.HIGH)

        if total == 0:
            return GreenwashingReport(
                total_claims=0, low_risk=0, medium_risk=0, high_risk=0,
                overall_risk=RiskLevel.LOW, overall_score=0.0, claims=[],
            )

        claims_by_id = {c.claim_id: c for c in claims}
        weighted_sum = 0.0
        weight_total = 0.0
        for result in results:
            claim = claims_by_id.get(result.claim_id)
            importance = (
                estimate_claim_importance(claim, self._aggregation_config.neutral_importance_weight)
                if claim is not None else self._aggregation_config.neutral_importance_weight
            )
            weighted_sum += result.greenwashing_score * importance
            weight_total += importance

        base_score = weighted_sum / weight_total if weight_total > 0 else 0.0
        high_risk_fraction = high / total
        bonus = min(
            self._aggregation_config.max_high_risk_bonus,
            high_risk_fraction * self._aggregation_config.high_risk_bonus_scale,
        )
        overall_score = round(min(100.0, base_score + bonus), 2)
        overall_risk = determine_risk_level(overall_score, [], self._thresholds)

        logger.info(
            "greenwashing_report_completed",
            extra={
                "total_claims": total, "low_risk": low, "medium_risk": medium, "high_risk": high,
                "overall_score": overall_score, "overall_risk": overall_risk.value,
            },
        )
        return GreenwashingReport(
            total_claims=total, low_risk=low, medium_risk=medium, high_risk=high,
            overall_risk=overall_risk, overall_score=overall_score, claims=results,
        )

    def _failure_result(
        self, claim: Claim, verification_result: VerificationResult | None, error_reason: str
    ) -> GreenwashingResult:
        features = GreenwashingFeatures(
            evidence_support=0.0, provenance_quality=0.0, numerical_consistency=1.0, contradiction=0.0,
            vagueness=0.0, absolute_language=0.0, unsupported_benefit=0.0, missing_qualification=0.0,
            misleading_comparison=0.0,
        )
        return GreenwashingResult(
            claim_id=claim.claim_id, claim=claim.claim,
            verification_status=verification_result.status if verification_result else VerificationStatus.UNSUPPORTED,
            greenwashing_risk=RiskLevel.LOW,  # uncertainty is never fabricated as risk (section 32)
            greenwashing_type=[GreenwashingType.NO_SIGNIFICANT_SIGNAL], greenwashing_score=0.0, confidence_score=0.0,
            reason=f"Greenwashing analysis failed: {error_reason}",
            evidence=verification_result.matched_evidence if verification_result else [],
            features=features, explanation=[f"Greenwashing analysis failed: {error_reason}"],
            recommendation="Re-run analysis once the underlying issue is resolved.",
        )
