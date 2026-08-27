"""Deterministic greenwashing scoring (sections 16-20, 26, 27).

`compute_greenwashing_score` is a documented weighted sum -- never hidden,
never asked of the LLM (section 25: "Do not simply ask the LLM for
overall_score"). `determine_risk_level` applies configurable thresholds,
but certain signal *combinations* (section 18) force High regardless of
where the weighted score alone would land -- the same "hard-fail can't be
outvoted by a good score" principle Phase 6 uses for verification status.
"""
from __future__ import annotations

from app.core.config import GreenwashingConfidenceWeights, GreenwashingThresholds, GreenwashingWeights
from app.greenwashing.detector import DetectorReport
from app.models.claim import Claim, ClaimType
from app.models.evidence import EvidenceMatch
from app.models.greenwashing import GreenwashingFeatures, GreenwashingType, RiskLevel
from app.models.verification import VerificationResult, VerificationStatus

#: Signal combinations severe enough to force High risk outright,
#: regardless of the weighted score (section 18).
SEVERE_HARD_SIGNALS = frozenset({
    "explicit_contradiction", "absolute_contradicted",
    "unsupported_major_claim_with_misleading_language", "major_numerical_mismatch",
})

_MAJOR_NUMERICAL_MISMATCH_SEVERITY = 0.9


def build_features(
    report: DetectorReport,
    verification_result: VerificationResult,
    best_evidence_match: EvidenceMatch | None,
) -> GreenwashingFeatures:
    numerical_consistency = round(1.0 - report.numerical_mismatch.severity, 3)
    contradiction = round(
        max(
            report.direction_mismatch.severity, report.absolute_contradiction.severity,
            report.unit_mismatch.severity, report.target_year_mismatch.severity,
        ),
        3,
    )
    provenance_quality = best_evidence_match.quality_score if best_evidence_match and best_evidence_match.quality_score is not None else 0.0

    return GreenwashingFeatures(
        evidence_support=round(verification_result.verification_score / 100, 3),
        provenance_quality=round(provenance_quality, 3),
        numerical_consistency=numerical_consistency,
        contradiction=contradiction,
        vagueness=report.vague_language.severity,
        absolute_language=report.absolute_language.severity,
        unsupported_benefit=report.unsupported_benefit.severity,
        missing_qualification=report.missing_qualification.severity,
        misleading_comparison=report.misleading_comparison.severity,
    )


def compute_greenwashing_score(features: GreenwashingFeatures, weights: GreenwashingWeights) -> float:
    risk = (
        (1.0 - features.evidence_support) * weights.lack_of_evidence_support
        + (1.0 - features.numerical_consistency) * weights.numerical_inconsistency
        + features.contradiction * weights.contradiction
        + features.vagueness * weights.vagueness
        + features.absolute_language * weights.absolute_language
        + features.unsupported_benefit * weights.unsupported_benefit
        + features.missing_qualification * weights.missing_qualification
        + features.misleading_comparison * weights.misleading_comparison
        + (1.0 - features.provenance_quality) * weights.weak_provenance
    )
    return round(min(1.0, max(0.0, risk)) * 100, 2)


def derive_hard_signals(report: DetectorReport, has_evidence: bool) -> list[str]:
    signals: list[str] = []
    if report.direction_mismatch.detected and report.direction_mismatch.severity >= 0.7:
        signals.append("explicit_contradiction")
    if report.absolute_contradiction.detected:
        signals.append("absolute_contradicted")
    if report.unsupported_benefit.detected and report.vague_language.detected and not has_evidence:
        signals.append("unsupported_major_claim_with_misleading_language")
    if report.numerical_mismatch.detected and report.numerical_mismatch.severity >= _MAJOR_NUMERICAL_MISMATCH_SEVERITY:
        signals.append("major_numerical_mismatch")
    return signals


def determine_risk_level(score: float, hard_signals: list[str], thresholds: GreenwashingThresholds) -> RiskLevel:
    if any(s in SEVERE_HARD_SIGNALS for s in hard_signals):
        return RiskLevel.HIGH
    if score >= thresholds.high_risk_min:
        return RiskLevel.HIGH
    if score >= thresholds.medium_risk_min:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def determine_greenwashing_types(
    report: DetectorReport, verification_status: VerificationStatus
) -> list[GreenwashingType]:
    types: list[GreenwashingType] = []

    if report.direction_mismatch.detected or report.absolute_contradiction.detected or report.unit_mismatch.detected:
        types.append(GreenwashingType.CONTRADICTORY_CLAIM)

    if report.numerical_mismatch.detected and not report.direction_mismatch.detected:
        claim_value = report.claim_components.value
        evidence_value = report.evidence_components.value if report.evidence_components else None
        if claim_value is not None and evidence_value is not None and abs(claim_value) > abs(evidence_value):
            types.append(GreenwashingType.EXAGGERATED_CLAIM)
        elif GreenwashingType.CONTRADICTORY_CLAIM not in types:
            types.append(GreenwashingType.CONTRADICTORY_CLAIM)

    if report.vague_language.detected:
        types.append(GreenwashingType.VAGUE_CLAIM)
    if report.absolute_language.detected:
        types.append(GreenwashingType.ABSOLUTE_CLAIM)
    if report.unsupported_benefit.detected:
        types.append(GreenwashingType.UNSUBSTANTIATED_BENEFIT)
    if report.missing_qualification.detected:
        types.append(GreenwashingType.MISSING_QUALIFICATION)
    if report.misleading_comparison.detected:
        types.append(GreenwashingType.MISLEADING_COMPARISON)
    if report.selective_presentation.detected:
        types.append(GreenwashingType.SELECTIVE_PRESENTATION)

    promotional_signal_count = sum([
        report.vague_language.detected, report.absolute_language.detected,
        report.unsupported_benefit.detected, report.missing_qualification.detected,
        report.misleading_comparison.detected,
    ])
    if promotional_signal_count >= 2:
        types.append(GreenwashingType.MISLEADING_CLAIM)

    if verification_status == VerificationStatus.UNSUPPORTED:
        types.append(GreenwashingType.UNSUPPORTED_ENVIRONMENTAL_CLAIM)

    if not types:
        types.append(GreenwashingType.NO_SIGNIFICANT_SIGNAL)

    # de-duplicate while preserving first-seen order
    seen: set[GreenwashingType] = set()
    ordered: list[GreenwashingType] = []
    for t in types:
        if t not in seen:
            seen.add(t)
            ordered.append(t)
    return ordered


def compute_greenwashing_confidence(
    features: GreenwashingFeatures, llm_available: bool, weights: GreenwashingConfidenceWeights
) -> float:
    llm_reliability = 1.0 if llm_available else 0.5
    raw = (
        features.provenance_quality * weights.provenance_reliability
        + features.evidence_support * weights.evidence_reliability
        + llm_reliability * weights.llm_reliability
    )
    return round(min(1.0, max(0.0, raw)) * 100, 2)


def estimate_claim_importance(claim: Claim, neutral_weight: float) -> float:
    """Deterministic materiality proxy from data already on the claim
    (section 27) -- never invented. Falls back to a neutral weight when no
    signal of materiality is present."""
    signals: list[float] = []
    if claim.value is not None and claim.unit is not None:
        signals.append(1.0)
    if claim.target_year is not None:
        signals.append(1.0)
    if claim.claim_type == ClaimType.COMMITMENT:
        signals.append(0.9)
    if claim.claim_type == ClaimType.CERTIFICATION:
        signals.append(0.8)
    if not signals:
        return neutral_weight
    return min(1.0, sum(signals) / len(signals))
