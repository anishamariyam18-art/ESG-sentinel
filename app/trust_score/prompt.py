"""Optional Trust Score narrative prompt (section 24).

No Python logic lives here -- only prompt text and a thin formatting
function. The LLM is given ONLY the already-computed, deterministic
component scores and statistics and asked to phrase them as a short,
neutral narrative -- it MUST NOT invent numbers, calculate a score, assert
fraud/deception, or introduce any claim/evidence not already supplied.
Its output is appended to (never a replacement for) the deterministic
`explanation` built by `app.trust_score.explainability`.
"""
from __future__ import annotations

from app.models.trust import TrustRating, TrustScoreComponents, TrustScoreStatistics

_NARRATIVE_RULES = """You are an ESG trust-score narration assistant. Follow these rules exactly:

1. Use ONLY the numbers supplied below -- never outside knowledge about this company, its
   industry, or ESG topics in general, and never any number not explicitly given to you.
2. Do NOT calculate, restate as different, or override the trust_score, rating, confidence,
   or any component value -- they are already final and authoritative.
3. Do NOT invent statistics, claims, or evidence that were not supplied.
4. Do NOT assert or imply fraud, intentional deception, or bad faith -- a low score reflects
   missing or inconsistent evidence, never a legal or ethical determination.
5. Write 2-4 short, neutral, plain-English sentences summarizing why the score is what it is,
   referencing only the supplied numbers.
6. Respond with a single JSON object only -- no markdown, no commentary, no text before or
   after the JSON.
"""


def build_narrative_prompt(
    document_id: str,
    trust_score: float,
    rating: TrustRating,
    confidence: float,
    components: TrustScoreComponents,
    statistics: TrustScoreStatistics,
) -> str:
    components_block = (
        f"claim_support: {components.claim_support}\n"
        f"evidence_quality: {components.evidence_quality}\n"
        f"consistency: {components.consistency}\n"
        f"transparency: {components.transparency}\n"
        f"greenwashing_risk (higher = safer, lower risk): {components.greenwashing_risk}\n"
        f"provenance: {components.provenance}"
    )
    stats_block = (
        f"total_claims: {statistics.total_claims}\n"
        f"verified_claims: {statistics.verified_claims}\n"
        f"partially_verified_claims: {statistics.partially_verified_claims}\n"
        f"unsupported_claims: {statistics.unsupported_claims}\n"
        f"high_greenwashing_claims: {statistics.high_greenwashing_claims}\n"
        f"medium_greenwashing_claims: {statistics.medium_greenwashing_claims}\n"
        f"low_greenwashing_claims: {statistics.low_greenwashing_claims}\n"
        f"evidence_coverage: {statistics.evidence_coverage}%\n"
        f"verification_coverage: {statistics.verification_coverage}%\n"
        f"provenance_coverage: {statistics.provenance_coverage}%"
    )
    schema = """Respond with a JSON object with exactly this shape:

{
  "narrative": ["short neutral sentence referencing only the supplied numbers", ...]
}
"""
    return (
        f"{_NARRATIVE_RULES}\n"
        f"DOCUMENT: {document_id}\n\n"
        f"TRUST SCORE: {trust_score}\nRATING: {rating.value}\nCONFIDENCE: {confidence}\n\n"
        f"COMPONENTS:\n{components_block}\n\n"
        f"STATISTICS:\n{stats_block}\n\n"
        f"{schema}"
    )
