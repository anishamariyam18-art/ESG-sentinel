"""Deterministic Trust Score report statistics (section 17).

Every statistic here is a direct, documented count/percentage over the
supplied claims/results -- nothing is estimated or inferred beyond what the
pipeline actually produced.
"""
from __future__ import annotations

from app.models.claim import Claim
from app.models.greenwashing import GreenwashingResult, RiskLevel
from app.models.trust import TrustScoreStatistics
from app.models.verification import VerificationResult, VerificationStatus
from app.trust_score.scorer import evidence_provenance_completeness


def _pct(count: int, total: int) -> float:
    return round((count / total) * 100, 2) if total > 0 else 0.0


def compute_statistics(
    claims: list[Claim],
    verification_results: list[VerificationResult],
    greenwashing_results: list[GreenwashingResult],
) -> TrustScoreStatistics:
    total = len(claims)
    results_by_id = {r.claim_id: r for r in verification_results}

    verified = sum(1 for r in verification_results if r.status == VerificationStatus.VERIFIED)
    partial = sum(1 for r in verification_results if r.status == VerificationStatus.PARTIALLY_VERIFIED)
    unsupported = sum(1 for r in verification_results if r.status == VerificationStatus.UNSUPPORTED)

    high_gw = sum(1 for r in greenwashing_results if r.greenwashing_risk == RiskLevel.HIGH)
    medium_gw = sum(1 for r in greenwashing_results if r.greenwashing_risk == RiskLevel.MEDIUM)
    low_gw = sum(1 for r in greenwashing_results if r.greenwashing_risk == RiskLevel.LOW)

    with_verification = 0
    with_evidence = 0
    with_full_provenance = 0
    for claim in claims:
        result = results_by_id.get(claim.claim_id)
        if result is not None:
            with_verification += 1
        if result is not None and result.matched_evidence:
            with_evidence += 1
        best = result.matched_evidence[0] if result and result.matched_evidence else None
        if evidence_provenance_completeness(best) == 1.0:
            with_full_provenance += 1

    return TrustScoreStatistics(
        total_claims=total,
        verified_claims=verified,
        partially_verified_claims=partial,
        unsupported_claims=unsupported,
        high_greenwashing_claims=high_gw,
        medium_greenwashing_claims=medium_gw,
        low_greenwashing_claims=low_gw,
        evidence_coverage=_pct(with_evidence, total),
        verification_coverage=_pct(with_verification, total),
        provenance_coverage=_pct(with_full_provenance, total),
    )
