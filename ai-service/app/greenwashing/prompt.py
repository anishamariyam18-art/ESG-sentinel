"""Greenwashing judgment prompt (section 13).

No Python logic lives here -- only prompt text and a thin formatting
function. The LLM receives the claim, the verification result, the
matched evidence, and the deterministic signals already found -- never
outside knowledge, and it is explicitly told not to assume intent or
independently invent a finding beyond what's supplied.
"""
from __future__ import annotations

from app.greenwashing.detector import DetectorReport
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.verification import VerificationResult

_JUDGE_RULES = """You are an ESG greenwashing-risk reasoning assistant. Follow these rules exactly:

1. Use ONLY the claim, verification result, evidence, and deterministic signals supplied
   below -- never outside knowledge about this company, industry, or ESG topic in general.
2. Do NOT assume intent. Never say a company "intentionally deceived" or "deliberately
   misled" anyone -- that determination is not something this analysis can establish.
3. Distinguish "unsupported" (no evidence was found, which is not by itself greenwashing)
   from "misleading" (the evidence actively conflicts with or undermines the claim).
4. Do NOT invent a new finding that isn't grounded in the supplied deterministic signals --
   your job is to help interpret and explain the signals already detected, not to discover
   new ones.
5. Prefer cautious language: "potentially misleading", "potential greenwashing signal",
   "insufficient evidence to substantiate the claim", "evidence indicates a discrepancy".
6. risk_assessment must be exactly one of: "low", "medium", "high" -- your own qualitative
   read of the situation; it is one input to a separate deterministic scoring system, not
   the final decision.
7. Respond with a single JSON object only -- no markdown, no commentary, no text before or
   after the JSON.
"""


def build_judgment_prompt(claim: Claim, verification_result: VerificationResult, evidence: Evidence | None, report: DetectorReport) -> str:
    evidence_block = (
        f"evidence_text: {evidence.evidence_text}\nsource_type: {evidence.source_type.value}\npage_number: {evidence.page_number}"
        if evidence else "No matched evidence was found for this claim."
    )
    detected_signals = [s for s in report.all_signals() if s.detected]
    signals_block = (
        "\n".join(f"- {s.signal} (severity={s.severity}): {s.details}" for s in detected_signals)
        or "No deterministic signals were detected."
    )

    schema = """Respond with a JSON object with exactly this shape:

{
  "risk_assessment": "low" | "medium" | "high",
  "reasoning": ["string explaining a specific detected signal or the overall assessment", ...],
  "intent_assumed": false
}

intent_assumed must be true only if your reasoning text happens to assert intent (it should
always be false, since you must not assume intent per the rules above).
"""
    return (
        f"{_JUDGE_RULES}\n"
        f"CLAIM:\n{claim.claim}\n\n"
        f"VERIFICATION RESULT:\nstatus: {verification_result.status.value}\n"
        f"verification_score: {verification_result.verification_score}\n\n"
        f"EVIDENCE:\n{evidence_block}\n\n"
        f"DETERMINISTIC SIGNALS ALREADY DETECTED:\n{signals_block}\n\n"
        f"{schema}"
    )
