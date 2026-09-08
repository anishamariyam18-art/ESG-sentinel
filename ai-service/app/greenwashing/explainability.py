"""Converts technical detector signals into human-readable explanations
(section 23). Every sentence traces back to an actual detected signal or a
documented default -- nothing here is generated without the underlying
data that justifies it, and nothing here ever asserts intent (section 14).
"""
from __future__ import annotations

from app.greenwashing.detector import DetectorReport
from app.models.greenwashing import GreenwashingType, RiskLevel
from app.models.verification import VerificationStatus

_UNSUPPORTED_NO_SIGNAL_EXPLANATION = (
    "The claim could not be verified from the available evidence, but the available "
    "information is insufficient to establish intentional or misleading environmental representation."
)

_RECOMMENDATIONS: dict[GreenwashingType, str] = {
    GreenwashingType.EXAGGERATED_CLAIM: (
        "Align the reported figure with the value stated in the underlying report, or clarify the discrepancy."
    ),
    GreenwashingType.CONTRADICTORY_CLAIM: "Resolve the contradiction between the claim and the evidence before publishing this claim externally.",
    GreenwashingType.VAGUE_CLAIM: "Add a measurable metric, target, or timeframe to substantiate this claim.",
    GreenwashingType.ABSOLUTE_CLAIM: "Provide clear, verifiable evidence for this absolute claim, or qualify it to reflect actual performance.",
    GreenwashingType.UNSUBSTANTIATED_BENEFIT: "Provide supporting evidence for the stated environmental benefit.",
    GreenwashingType.MISSING_QUALIFICATION: "Include the qualifying information present in the underlying evidence (e.g. the baseline year).",
    GreenwashingType.MISLEADING_COMPARISON: "Provide a clear, substantiated basis for this comparison.",
    GreenwashingType.SELECTIVE_PRESENTATION: "Present the full scope of results rather than a subset that may create a misleading overall impression.",
    GreenwashingType.UNSUPPORTED_ENVIRONMENTAL_CLAIM: "Provide supporting evidence for this claim from the underlying report.",
    GreenwashingType.MISLEADING_CLAIM: "Review this claim for clarity and ensure it is fully substantiated by the underlying evidence.",
    GreenwashingType.NO_SIGNIFICANT_SIGNAL: "No action needed -- the claim is adequately supported.",
}


def build_explanation(
    verification_status: VerificationStatus, report: DetectorReport, llm_reasoning: list[str] | None = None,
) -> list[str]:
    if not report.any_detected():
        if verification_status == VerificationStatus.UNSUPPORTED:
            return [_UNSUPPORTED_NO_SIGNAL_EXPLANATION]
        return ["The claim is supported by the matched evidence with no greenwashing signals detected."]

    lines = [signal.details for signal in report.all_signals() if signal.detected]
    if llm_reasoning:
        lines.extend(f"LLM assessment: {line}" for line in llm_reasoning)
    return lines


def build_reason(risk_level: RiskLevel, greenwashing_types: list[GreenwashingType]) -> str:
    if GreenwashingType.NO_SIGNIFICANT_SIGNAL in greenwashing_types:
        return "The claim is adequately supported by the available evidence."
    labels = [t.value for t in greenwashing_types if t != GreenwashingType.UNSUPPORTED_ENVIRONMENTAL_CLAIM]
    if not labels:
        labels = [t.value for t in greenwashing_types]
    return f"Potential greenwashing risk ({risk_level.value}) driven by: {', '.join(labels)}."


def build_recommendation(greenwashing_types: list[GreenwashingType]) -> str:
    for greenwashing_type in greenwashing_types:
        if greenwashing_type != GreenwashingType.NO_SIGNIFICANT_SIGNAL and greenwashing_type in _RECOMMENDATIONS:
            return _RECOMMENDATIONS[greenwashing_type]
    return _RECOMMENDATIONS[GreenwashingType.NO_SIGNIFICANT_SIGNAL]
