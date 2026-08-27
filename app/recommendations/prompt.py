"""Optional LLM synthesis prompt (section 23-24).

No Python logic lives here -- only prompt text and a thin formatting
function. The LLM receives ONLY the already-computed, deterministic
recommendations and Trust Score summary; it MUST NOT invent findings,
claims, statistics, evidence, or recommendations unrelated to what was
supplied, and it MUST NOT change any priority, score, or status -- those
are already final. Its only allowed contribution is a short narrative
appended to (never replacing) the deterministic `overall_assessment`.
"""
from __future__ import annotations

from app.models.recommendation import Recommendation
from app.models.trust import TrustScore

_SYNTHESIS_RULES = """You are an ESG recommendation-summary assistant. Follow these rules exactly:

1. Use ONLY the structured data supplied below -- never outside knowledge about this company,
   its industry, or ESG topics in general, and never any claim, statistic, or finding not
   explicitly given to you.
2. Do NOT invent recommendations, findings, claims, or evidence.
3. Do NOT change, restate as different, or override any priority, score, status, or category --
   they are already final and authoritative.
4. Do NOT introduce external ESG standards, legal or regulatory requirements, or industry
   benchmarks unless they are explicitly present in the supplied data.
5. Write 2-4 short, neutral, plain-English sentences synthesizing the overall assessment,
   referencing only the supplied numbers and recommendation titles.
6. Respond with a single JSON object only -- no markdown, no commentary, no text before or
   after the JSON.
"""


def build_synthesis_prompt(document_id: str, trust_score: TrustScore, recommendations: list[Recommendation]) -> str:
    trust_block = (
        f"trust_score: {trust_score.trust_score}\nrating: {trust_score.rating.value}\n"
        f"confidence: {trust_score.confidence}\ncomponents: {trust_score.components.model_dump()}"
    )
    recommendations_block = "\n".join(
        f"- [{rec.priority.value}] {rec.title} ({rec.category.value}): {rec.problem}"
        for rec in recommendations
    ) or "No recommendations were generated."

    schema = """Respond with a JSON object with exactly this shape:

{
  "narrative": ["short neutral sentence referencing only the supplied numbers/titles", ...]
}
"""
    return (
        f"{_SYNTHESIS_RULES}\n"
        f"DOCUMENT: {document_id}\n\n"
        f"TRUST SCORE:\n{trust_block}\n\n"
        f"RECOMMENDATIONS:\n{recommendations_block}\n\n"
        f"{schema}"
    )
