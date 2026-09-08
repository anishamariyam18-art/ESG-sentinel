"""ESG Trust Score orchestration (sections 1-2, 24-26, 38-39).

Input is exactly what section 1 allows: the already-computed `Claim` list,
Phase 6 `VerificationResult`s, and Phase 7 `GreenwashingResult`s (an
`AnalyzerResult` may optionally be supplied for context/logging, but no
scoring formula in `app.trust_score.scorer` reads it -- nothing here
independently re-derives or re-fetches anything from the evidence store).

The numerical `trust_score` is 100% deterministic (`app.trust_score.scorer`)
and is computed BEFORE any LLM call is attempted. An optional LLM
narrative (`app.trust_score.prompt.build_narrative_prompt`) may be appended
to `explanation`, but unlike Phase 6/7's services, the LLM manager here is
NOT auto-constructed via `get_llm_manager()` when omitted -- Trust Score
must work with zero LLM configuration at all (section 38: "do not make
unnecessary LLM calls"; section 25: "the numerical score must never depend
on LLM availability"). If no manager is supplied, or the call fails for any
reason, the deterministic explanation/strengths/weaknesses/limitations
still fully stand on their own.
"""
from __future__ import annotations

import time

from pydantic import BaseModel, Field, ValidationError

from app.core.config import TrustRatingThresholds, TrustScoreConfig, TrustScoreWeights, get_settings
from app.core.llm import LLMGenerationError, LLMJsonError, LLMManager
from app.core.logging import get_logger
from app.models.analyzer import AnalyzerResult
from app.models.claim import Claim
from app.models.greenwashing import GreenwashingResult
from app.models.trust import TrustRating, TrustScore, TrustScoreComponents, TrustScoreStatistics
from app.models.verification import VerificationResult
from app.trust_score.explainability import build_explanation, build_limitations, build_strengths, build_weaknesses
from app.trust_score.metrics import compute_statistics
from app.trust_score.prompt import build_narrative_prompt
from app.trust_score.scorer import (
    calculate_claim_support,
    calculate_confidence,
    calculate_consistency,
    calculate_evidence_quality,
    calculate_final_score,
    calculate_greenwashing_component,
    calculate_provenance,
    calculate_transparency,
    determine_rating,
)

logger = get_logger(__name__)


class _NarrativeResponse(BaseModel):
    narrative: list[str] = Field(default_factory=list)


class TrustScoreService:
    def __init__(
        self,
        llm_manager: LLMManager | None = None,
        weights: TrustScoreWeights | None = None,
        rating_thresholds: TrustRatingThresholds | None = None,
        config: TrustScoreConfig | None = None,
    ) -> None:
        settings = get_settings()
        self._llm = llm_manager
        self._weights = weights or settings.trust_score_weights
        self._rating_thresholds = rating_thresholds or settings.trust_rating_thresholds
        self._config = config or settings.trust_score_config

    def calculate_trust_score(
        self,
        document_id: str,
        company: str,
        claims: list[Claim],
        verification_results: list[VerificationResult],
        greenwashing_results: list[GreenwashingResult],
        analyzer_result: AnalyzerResult | None = None,
    ) -> TrustScore:
        started = time.monotonic()

        statistics = compute_statistics(claims, verification_results, greenwashing_results)
        if not claims:
            # No claims at all means there is nothing to assess -- the
            # greenwashing component's "no data supplied" neutral default
            # (`no_greenwashing_data_default`) exists for a real report
            # that simply wasn't greenwashing-analyzed, not for "no report
            # data exists whatsoever"; every component is honestly 0 here.
            components = TrustScoreComponents(
                claim_support=0.0, evidence_quality=0.0, consistency=0.0,
                transparency=0.0, greenwashing_risk=0.0, provenance=0.0,
            )
        else:
            components = TrustScoreComponents(
                claim_support=calculate_claim_support(claims, verification_results, self._config),
                evidence_quality=calculate_evidence_quality(claims, verification_results),
                consistency=calculate_consistency(verification_results),
                transparency=calculate_transparency(claims),
                greenwashing_risk=calculate_greenwashing_component(greenwashing_results, self._config),
                provenance=calculate_provenance(claims, verification_results),
            )
        score = calculate_final_score(components, self._weights)
        rating = determine_rating(score, self._rating_thresholds)
        confidence = calculate_confidence(
            statistics.total_claims, statistics.evidence_coverage, statistics.verification_coverage,
            statistics.provenance_coverage, components, self._config,
        )

        explanation = build_explanation(statistics, components, rating)
        strengths = build_strengths(statistics, components)
        weaknesses = build_weaknesses(statistics, components)
        limitations = build_limitations(statistics, self._config)

        if self._llm is not None and self._config.enable_llm_narrative and statistics.total_claims > 0:
            try:
                narrative = self._generate_narrative(document_id, score, rating, confidence, components, statistics)
            except Exception as exc:  # noqa: BLE001 -- narrative failure must never affect the numerical score
                logger.warning("trust_score_narrative_failed", extra={"document_id": document_id, "error": str(exc)})
                narrative = None
            if narrative:
                explanation = explanation + [f"LLM narrative: {line}" for line in narrative]

        result = TrustScore(
            document_id=document_id, company=company, trust_score=score, rating=rating, confidence=confidence,
            components=components, statistics=statistics, explanation=explanation, strengths=strengths,
            weaknesses=weaknesses, limitations=limitations,
        )

        logger.info(
            "trust_score_calculated",
            extra={
                "document_id": document_id, "total_claims": statistics.total_claims,
                "verified_claims": statistics.verified_claims, "partially_verified_claims": statistics.partially_verified_claims,
                "unsupported_claims": statistics.unsupported_claims, "high_greenwashing_claims": statistics.high_greenwashing_claims,
                "medium_greenwashing_claims": statistics.medium_greenwashing_claims, "low_greenwashing_claims": statistics.low_greenwashing_claims,
                "components": components.model_dump(), "trust_score": score, "rating": rating.value, "confidence": confidence,
                "processing_time_seconds": round(time.monotonic() - started, 3),
            },
        )
        return result

    def _generate_narrative(
        self, document_id: str, score: float, rating: TrustRating, confidence: float,
        components: TrustScoreComponents, statistics: TrustScoreStatistics,
    ) -> list[str] | None:
        prompt = build_narrative_prompt(document_id, score, rating, confidence, components, statistics)
        attempts = self._config.max_schema_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                raw_json, _meta = self._llm.generate_json(prompt)
            except (LLMJsonError, LLMGenerationError) as exc:
                last_error = exc
                logger.warning("trust_score_narrative_call_failed", extra={"document_id": document_id, "attempt": attempt})
                continue
            try:
                parsed = _NarrativeResponse.model_validate(raw_json)
            except ValidationError as exc:
                last_error = exc
                logger.warning("trust_score_narrative_schema_invalid", extra={"document_id": document_id, "attempt": attempt})
                continue
            return parsed.narrative

        logger.warning("trust_score_narrative_unavailable", extra={"document_id": document_id, "error": str(last_error)})
        return None
