"""Recommendation explainability (sections 18, 20-22, 28, 36).

`build_recommendation_explanation` only ever quotes/summarizes the actual
`Finding.description` lines that triggered a recommendation (section 18:
what/why/what-to-do/what-evidence/what-outcome). Strengths and weaknesses
are intentionally NOT re-derived here -- Phase 8's `TrustScore.strengths`/
`.weaknesses` are already deterministic, grounded in the same statistics,
and reused as-is (`derive_strengths`/`derive_weaknesses`) rather than
risking a second, potentially inconsistent computation of the same facts.
"""
from __future__ import annotations

from app.core.config import RecommendationConfig
from app.models.recommendation import Recommendation
from app.models.trust import TrustScore
from app.recommendations.rules import Finding

_CATEGORY_ORDER = ("Environmental", "Social", "Governance", "Cross-cutting")


def build_recommendation_explanation(findings: list[Finding], config: RecommendationConfig) -> str:
    claim_ids = sorted({f.claim_id for f in findings if f.claim_id is not None})
    lines = [f.description for f in findings[: config.max_source_findings_per_recommendation]]
    remaining = len(findings) - len(lines)
    summary = "; ".join(lines)
    if remaining > 0:
        summary += f"; and {remaining} more."
    if claim_ids:
        return f"Based on {len(claim_ids)} claim(s): {summary}"
    return f"Based on report-level findings: {summary}"


def derive_strengths(trust_score: TrustScore) -> list[str]:
    return list(trust_score.strengths)


def derive_weaknesses(trust_score: TrustScore) -> list[str]:
    return list(trust_score.weaknesses)


def build_implementation_areas(recommendations: list[Recommendation]) -> list[str]:
    present = {rec.category.value for rec in recommendations}
    return [category for category in _CATEGORY_ORDER if category in present]


def build_overall_assessment(trust_score: TrustScore, recommendations: list[Recommendation]) -> str:
    stats = trust_score.statistics
    components = trust_score.components

    if stats.total_claims == 0:
        return "No ESG claims were available, so no meaningful assessment could be produced."

    verified_pct = round((stats.verified_claims / stats.total_claims) * 100, 1)
    component_items = components.model_dump()
    strongest = max(component_items, key=lambda name: component_items[name])
    weakest = min(component_items, key=lambda name: component_items[name])

    sentences = [
        f"The report reaches a Trust Score of {trust_score.trust_score} ({trust_score.rating.value}), "
        f"with {verified_pct}% of claims fully verified.",
    ]
    if stats.high_greenwashing_claims > 0:
        sentences.append(f"{stats.high_greenwashing_claims} claim(s) carry a High greenwashing risk signal.")
    elif stats.medium_greenwashing_claims > 0:
        sentences.append(f"{stats.medium_greenwashing_claims} claim(s) carry a Medium greenwashing risk signal.")
    else:
        sentences.append("Greenwashing risk across assessed claims is low.")
    sentences.append(f"The strongest area is {strongest} ({component_items[strongest]}); the weakest is {weakest} ({component_items[weakest]}).")
    if not recommendations:
        # section 33: a near-perfect report should not have issues invented
        # for it -- no finding fired, so no Recommendation object was
        # generated (section 6), but the assessment can still say so.
        sentences.append("No significant issues were identified; maintain current evidence and provenance practices.")
    return " ".join(sentences)


def build_limitations(trust_score: TrustScore) -> list[str]:
    limitations = list(trust_score.limitations)
    limitations.append(
        "Recommendations are generated only from findings already produced by the analyzer, claim, evidence, "
        "verification, greenwashing, and trust score stages of this pipeline -- no external ESG standards, "
        "regulatory requirements, or industry benchmarks were consulted."
    )
    return limitations
