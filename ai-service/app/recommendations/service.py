"""ESG Recommendation orchestration (sections 1-3, 23-25, 27-30, 37-38).

Input is exactly what section 2 allows: `Claim`s, Phase 6
`VerificationResult`s, Phase 7 `GreenwashingResult`s, and the Phase 8
`TrustScore` -- nothing here independently re-fetches or re-derives
anything from the evidence store. Every `Recommendation` traces back to at
least one `Finding` (`app.recommendations.rules`); a finding_type with zero
supporting findings never produces a recommendation (section 6).

The recommendation set is 100% deterministic (`rules.py` + `prioritizer.py`)
and is fully computed BEFORE any LLM call is attempted. An optional LLM
synthesis (`prompt.py`) may append a short narrative to `overall_assessment`,
but -- exactly like Phase 8's `TrustScoreService` -- the LLM manager is NOT
auto-constructed when omitted, and the deterministic result always stands
on its own regardless of LLM availability (section 24).
"""
from __future__ import annotations

import time
from collections import defaultdict

from pydantic import BaseModel, Field, ValidationError

from app.core.config import (
    RecommendationConfig,
    RecommendationPriorityWeights,
    RecommendationThresholds,
    get_settings,
)
from app.core.llm import LLMGenerationError, LLMJsonError, LLMManager
from app.core.logging import get_logger
from app.models.claim import Claim
from app.models.greenwashing import GreenwashingResult
from app.models.recommendation import (
    PriorityAction,
    Recommendation,
    RecommendationCategory,
    RecommendationPriority,
    RecommendationResult,
)
from app.models.trust import TrustScore
from app.models.verification import VerificationResult
from app.recommendations.explainability import (
    build_implementation_areas,
    build_limitations,
    build_overall_assessment,
    build_recommendation_explanation,
    derive_strengths,
    derive_weaknesses,
)
from app.recommendations.prioritizer import calculate_priority_score, determine_priority
from app.recommendations.prompt import build_synthesis_prompt
from app.recommendations.rules import (
    FINDING_TEMPLATES,
    Finding,
    collect_claim_findings,
    rule_low_evidence_coverage,
    rule_weak_trust_components,
)

logger = get_logger(__name__)


class _SynthesisResponse(BaseModel):
    narrative: list[str] = Field(default_factory=list)


class RecommendationService:
    def __init__(
        self,
        llm_manager: LLMManager | None = None,
        priority_weights: RecommendationPriorityWeights | None = None,
        thresholds: RecommendationThresholds | None = None,
        config: RecommendationConfig | None = None,
    ) -> None:
        settings = get_settings()
        self._llm = llm_manager
        self._priority_weights = priority_weights or settings.recommendation_priority_weights
        self._thresholds = thresholds or settings.recommendation_thresholds
        self._config = config or settings.recommendation_config

    def generate_recommendations(
        self,
        document_id: str,
        company: str,
        claims: list[Claim],
        verification_results: list[VerificationResult],
        greenwashing_results: list[GreenwashingResult],
        trust_score: TrustScore,
    ) -> RecommendationResult:
        started = time.monotonic()

        verification_by_id = {r.claim_id: r for r in verification_results}
        greenwashing_by_id = {r.claim_id: r for r in greenwashing_results}

        groups: dict[tuple[str, RecommendationCategory], list[Finding]] = defaultdict(list)
        for claim in claims:
            findings = collect_claim_findings(
                claim, verification_by_id.get(claim.claim_id), greenwashing_by_id.get(claim.claim_id),
                trust_score.components, self._config,
            )
            for finding in findings:
                groups[(finding.finding_type, finding.category)].append(finding)

        for finding in rule_weak_trust_components(trust_score, self._config):
            groups[(finding.finding_type, finding.category)].append(finding)
        low_coverage_finding = rule_low_evidence_coverage(trust_score, self._config)
        if low_coverage_finding is not None:
            groups[(low_coverage_finding.finding_type, low_coverage_finding.category)].append(low_coverage_finding)

        candidates: list[Recommendation] = []
        for index, ((finding_type, category), group_findings) in enumerate(groups.items(), start=1):
            template = FINDING_TEMPLATES.get(finding_type)
            if template is None or not group_findings:
                continue  # section 6: never generate a recommendation with no identifiable source finding

            claim_ids = sorted({f.claim_id for f in group_findings if f.claim_id is not None})
            priority_score = calculate_priority_score(group_findings, self._priority_weights, self._config)
            priority = determine_priority(priority_score, self._thresholds, group_findings)

            problem = (
                f"{len(claim_ids)} {category.value.lower()} claim(s) affected by {finding_type.split(':')[0].replace('_', ' ')}."
                if claim_ids else group_findings[0].description
            )

            candidates.append(Recommendation(
                recommendation_id=f"REC-{index:06d}",
                title=template.title.format(category=category.value),
                problem=problem,
                source_claim_ids=claim_ids,
                source_findings=[f.description for f in group_findings[: self._config.max_source_findings_per_recommendation]],
                category=category,
                priority=priority,
                priority_score=priority_score,
                action=template.action,
                reason=template.reason,
                expected_impact=template.expected_impact,
                time_horizon=template.time_horizon,
                explanation=build_recommendation_explanation(group_findings, self._config),
            ))

        candidates.sort(key=lambda rec: rec.priority_score, reverse=True)
        recommendations = candidates[: self._config.max_recommendations]

        priority_actions = [
            PriorityAction(recommendation_id=rec.recommendation_id, priority=rec.priority, action=rec.action, reason=rec.reason)
            for rec in recommendations[: self._config.max_priority_actions]
        ]

        overall_assessment = build_overall_assessment(trust_score, recommendations)
        if self._llm is not None and self._config.enable_llm_synthesis and claims:
            try:
                narrative = self._generate_narrative(document_id, trust_score, recommendations)
            except Exception as exc:  # noqa: BLE001 -- synthesis failure must never affect the deterministic result
                logger.warning("recommendation_synthesis_failed", extra={"document_id": document_id, "error": str(exc)})
                narrative = None
            if narrative:
                overall_assessment = overall_assessment + " " + " ".join(narrative)

        result = RecommendationResult(
            document_id=document_id, company=company, overall_assessment=overall_assessment,
            strengths=derive_strengths(trust_score), weaknesses=derive_weaknesses(trust_score),
            recommendations=recommendations, priority_actions=priority_actions,
            implementation_areas=build_implementation_areas(recommendations),
            limitations=build_limitations(trust_score),
        )

        logger.info(
            "recommendations_generated",
            extra={
                "document_id": document_id, "findings_count": sum(len(g) for g in groups.values()),
                "recommendations_count": len(recommendations),
                "priority_distribution": {
                    p.value: sum(1 for rec in recommendations if rec.priority == p)
                    for p in RecommendationPriority
                },
                "processing_time_seconds": round(time.monotonic() - started, 3),
            },
        )
        return result

    def _generate_narrative(self, document_id: str, trust_score: TrustScore, recommendations: list[Recommendation]) -> list[str] | None:
        prompt = build_synthesis_prompt(document_id, trust_score, recommendations)
        attempts = self._config.max_schema_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                raw_json, _meta = self._llm.generate_json(prompt)
            except (LLMJsonError, LLMGenerationError) as exc:
                last_error = exc
                logger.warning("recommendation_synthesis_call_failed", extra={"document_id": document_id, "attempt": attempt})
                continue
            try:
                parsed = _SynthesisResponse.model_validate(raw_json)
            except ValidationError as exc:
                last_error = exc
                logger.warning("recommendation_synthesis_schema_invalid", extra={"document_id": document_id, "attempt": attempt})
                continue
            return parsed.narrative

        logger.warning("recommendation_synthesis_unavailable", extra={"document_id": document_id, "error": str(last_error)})
        return None
