"""Verification (LLM evidence judgment) prompt.

No Python logic lives here -- only prompt text and a thin formatting
function. The LLM receives ONLY the claim, its structured metadata, and
the candidate evidence texts -- never outside knowledge, never asked to
produce a final score (section 15/16: the LLM's structured judgment is one
input signal, the deterministic scorer decides the number).
"""
from __future__ import annotations

from app.models.claim import Claim
from app.models.evidence import Evidence

_JUDGE_RULES = """You are an ESG claim verification system. You judge whether a piece of
evidence supports a claim. Follow these rules exactly:

1. Use ONLY the claim and evidence text supplied below -- never outside knowledge about
   this company, industry, or ESG topic in general.
2. Never guess or invent what the evidence "probably" says. If the evidence text does not
   explicitly state something, treat it as not supported.
3. Judge each evidence candidate independently against the claim.
4. support_level must be exactly one of: "full", "partial", "none".
   - "full": the evidence states the same metric, value, unit, and time period as the claim.
   - "partial": the evidence relates to the same topic but differs in value, unit, period,
     or omits some part of what the claim asserts.
   - "none": the evidence does not support the claim, or contradicts it.
5. List which specific components of the claim (metric, value, unit, direction, period,
   target_year) the evidence actually supports, and which it does not.
6. If the evidence explicitly states something that conflicts with the claim (a different
   number, the opposite direction, a different year), list that in contradictions --
   be specific about what conflicts.
7. Respond with a single JSON object only -- no markdown, no commentary, no text before or
   after the JSON.
"""


def build_judgment_prompt(claim: Claim, evidence_candidates: list[Evidence]) -> str:
    claim_block = (
        f"CLAIM:\n{claim.claim}\n\n"
        f"Claim metadata: category={claim.category.value}, claim_type={claim.claim_type.value}, "
        f"metric_name={claim.metric_name!r}, value={claim.value!r}, unit={claim.unit!r}, "
        f"target_year={claim.target_year!r}, reporting_year={claim.report_year}"
    )

    evidence_blocks = []
    for evidence in evidence_candidates:
        evidence_blocks.append(
            f"evidence_id: {evidence.evidence_id}\n"
            f"source_type: {evidence.source_type.value}\n"
            f"page_number: {evidence.page_number}\n"
            f"text: {evidence.evidence_text}"
        )
    evidence_block = "\n\n---\n\n".join(evidence_blocks)

    schema = """Respond with a JSON object with exactly this shape:

{
  "judgments": [
    {
      "evidence_id": "string, copied verbatim from the evidence_id above",
      "supports_claim": true or false,
      "support_level": "full" | "partial" | "none",
      "supported_components": ["metric", "value", "unit", "direction", "period", "target_year"],
      "unsupported_components": [...],
      "contradictions": ["string describing a specific conflict, or omit if none"],
      "reason": "short explanation, <= 30 words"
    }
  ]
}

Include exactly one judgment per evidence candidate above, in any order, each keyed by its evidence_id.
"""
    return f"{_JUDGE_RULES}\n{claim_block}\n\nCandidate evidence:\n\n{evidence_block}\n\n{schema}"
