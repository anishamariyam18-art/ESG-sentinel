"""Deterministic verification scoring (sections 17, 18, 29, 30).

Two distinct numbers, on purpose:

- `verification_score` ("how strongly does the evidence support the
  claim?"): a documented weighted sum of the 9 check signals
  (`VerificationWeights`), scaled to 0-100.
- `confidence_score` ("how reliable is this verification decision?"): a
  separate weighted combination of evidence quality, agreement between the
  semantic/lexical signals, whether the LLM judgment was actually
  available, and how much candidates disagreed with each other
  (`VerificationConfidenceWeights`).

A hard-fail reason (wrong company, an explicit numeric/direction
contradiction, an incompatible unit, an incompatible target year) can never
be outvoted by an otherwise-high score -- `determine_status` applies those
caps after the threshold comparison, not instead of it.
"""
from __future__ import annotations

import statistics

from app.core.config import VerificationConfidenceWeights, VerificationThresholds, VerificationWeights
from app.models.verification import VerificationChecks, VerificationStatus

#: Hard-fail reasons severe enough to force Unsupported outright, regardless
#: of score -- these mean the evidence is fundamentally not about the same
#: claim (wrong company) or actively contradicts it.
SEVERE_HARD_FAILS = frozenset({"wrong_company", "explicit_contradiction"})

_CHECK_FIELDS = (
    "semantic", "lexical", "numeric", "unit", "temporal", "entity", "category", "llm_support", "provenance",
)


def compute_verification_score(checks: VerificationChecks, weights: VerificationWeights) -> float:
    """weighted result x 100 (section 17), never hidden -- every component
    and its weight is a named, documented field."""
    weighted = sum(getattr(checks, field) * getattr(weights, field) for field in _CHECK_FIELDS)
    return round(min(1.0, max(0.0, weighted)) * 100, 2)


def determine_status(
    score: float, hard_fail_reasons: list[str], thresholds: VerificationThresholds
) -> VerificationStatus:
    if any(reason in SEVERE_HARD_FAILS for reason in hard_fail_reasons):
        return VerificationStatus.UNSUPPORTED

    if score >= thresholds.verified_score_min:
        status = VerificationStatus.VERIFIED
    elif score >= thresholds.partially_verified_score_min:
        status = VerificationStatus.PARTIALLY_VERIFIED
    else:
        status = VerificationStatus.UNSUPPORTED

    if hard_fail_reasons and status == VerificationStatus.VERIFIED:
        # A moderate hard-fail (numeric/direction contradiction, incompatible
        # unit or target year) can still coexist with a high weighted score
        # if other signals are strong -- but it must never reach Verified.
        status = VerificationStatus.PARTIALLY_VERIFIED

    return status


def compute_confidence_score(
    checks: VerificationChecks,
    llm_available: bool,
    candidate_scores: list[float],
    evidence_count: int,
    weights: VerificationConfidenceWeights,
) -> float:
    """Deliberately independent of verification_score -- see module
    docstring. `candidate_scores` are the (0-100) verification_score of
    every evaluated candidate, used to measure agreement/ambiguity across
    them, not just the winning one."""
    provenance_quality = checks.provenance
    signal_agreement = 1.0 - abs(checks.semantic - checks.lexical)
    llm_reliability = 1.0 if llm_available else 0.5

    if evidence_count == 0:
        ambiguity = 1.0  # maximally ambiguous: no evidence to agree or disagree
    elif len(candidate_scores) >= 2:
        spread = statistics.pstdev(s / 100 for s in candidate_scores)
        ambiguity = min(1.0, spread * 2)
    else:
        ambiguity = 0.1  # a single candidate is mildly less certain than corroborated agreement

    low_ambiguity = 1.0 - ambiguity

    raw = (
        provenance_quality * weights.provenance_quality
        + signal_agreement * weights.signal_agreement
        + llm_reliability * weights.llm_reliability
        + low_ambiguity * weights.low_ambiguity
    )
    return round(min(1.0, max(0.0, raw)) * 100, 2)
