"""Deterministic recommendation priority scoring (section 8).

`calculate_priority_score` combines the 6 factors the spec lists --
severity, number of affected claims, verification impact, greenwashing
risk, trust-score impact, and claim importance -- into one documented
weighted 0-100 score. The LLM is never consulted for this (section 23:
"LLM must not change priority scores")."""
from __future__ import annotations

from app.core.config import RecommendationConfig, RecommendationPriorityWeights, RecommendationThresholds
from app.models.recommendation import RecommendationPriority
from app.recommendations.rules import Finding


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def calculate_priority_score(
    findings: list[Finding], weights: RecommendationPriorityWeights, config: RecommendationConfig,
) -> float:
    if not findings:
        return 0.0

    affected_claim_ids = {f.claim_id for f in findings if f.claim_id is not None}
    affected_count = len(affected_claim_ids) if affected_claim_ids else len(findings)
    affected_claims_factor = min(1.0, affected_count / config.affected_claims_full_credit)

    raw = (
        _mean([f.severity for f in findings]) * weights.severity
        + affected_claims_factor * weights.affected_claims
        + _mean([f.verification_impact for f in findings]) * weights.verification_impact
        + _mean([f.greenwashing_risk for f in findings]) * weights.greenwashing_risk
        + _mean([f.trust_impact for f in findings]) * weights.trust_impact
        + _mean([f.claim_importance for f in findings]) * weights.claim_importance
    )
    return round(min(1.0, max(0.0, raw)) * 100, 2)


def determine_priority(score: float, thresholds: RecommendationThresholds, findings: list[Finding] | None = None) -> RecommendationPriority:
    if findings and any(f.hard_priority_override for f in findings):
        return RecommendationPriority.HIGH
    if score >= thresholds.high_priority_min:
        return RecommendationPriority.HIGH
    if score >= thresholds.medium_priority_min:
        return RecommendationPriority.MEDIUM
    return RecommendationPriority.LOW
