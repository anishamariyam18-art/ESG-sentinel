"""Deterministic Trust Score component scoring (sections 5-12, 16-20, 26-27).

Every `calculate_*` function takes exactly the pipeline outputs it needs and
returns a single 0.0-100.0 float -- never a bare pass/fail, never fabricated
when data is missing (a claim with no verification result or no matched
evidence contributes 0, it is never silently skipped or assumed
supported). `calculate_final_score` combines the six components with a
documented weighted sum (`TrustScoreWeights`) -- the Trust Score is never
requested directly from an LLM (section 24).
"""
from __future__ import annotations

import math

from app.core.config import TrustRatingThresholds, TrustScoreConfig, TrustScoreWeights
from app.greenwashing.detector import detect_vague_language
from app.greenwashing.scorer import estimate_claim_importance
from app.models.claim import Claim, ClaimType
from app.models.evidence import EvidenceMatch
from app.models.greenwashing import GreenwashingResult, RiskLevel
from app.models.trust import TrustRating, TrustScoreComponents
from app.models.verification import VerificationResult, VerificationStatus

#: Claim types for which an absent field genuinely means "not applicable",
#: not "missing" (section 8: "do not punish a claim simply because a field
#: does not logically apply to it" -- e.g. a governance policy claim has no
#: target year).
_NUMERIC_CLAIM_TYPES = frozenset({ClaimType.METRIC, ClaimType.PERFORMANCE})
_TARGET_YEAR_CLAIM_TYPES = frozenset({ClaimType.COMMITMENT})
_NAMED_TARGET_CLAIM_TYPES = frozenset(
    {ClaimType.CERTIFICATION, ClaimType.POLICY, ClaimType.COMPLIANCE, ClaimType.COMMITMENT}
)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Section 12: every component and the final score must stay within
    0-100 -- never negative, never above 100, never NaN/infinity. A
    non-finite value is clamped to the low bound rather than propagated,
    since a broken calculation must never be reported as a high score."""
    if not math.isfinite(value):
        return lo
    return round(min(hi, max(lo, value)), 2)


def evidence_provenance_completeness(match: EvidenceMatch | None) -> float:
    """Fraction (0.0-1.0) of the 4 evidence-side provenance fields present
    on the claim's best-matched evidence (section 10/34): `evidence_id`,
    `document_id`, `page_number`, `source_chunk_id`. A claim's OWN
    provenance (document_id/page_number/source_chunk_id) is mandatory on
    every `Claim` record and therefore never varies -- what actually
    distinguishes a well-traced claim from a poorly-traced one is whether
    its supporting EVIDENCE carries the same complete trail."""
    if match is None:
        return 0.0
    fields = (match.evidence_id, match.document_id, match.page_number, match.source_chunk_id)
    present = sum(1 for f in fields if f is not None and f != "")
    return present / len(fields)


def calculate_claim_support(
    claims: list[Claim], verification_results: list[VerificationResult], config: TrustScoreConfig
) -> float:
    """Section 5: verified claims contribute fully, partially verified
    claims partially, unsupported claims little/no credit -- weighted by
    `estimate_claim_importance` (reused directly from Phase 7's
    materiality proxy, never re-invented here) so a report isn't judged
    purely by claim COUNT (section 13). A claim with no verification
    result at all earns zero credit -- it is never assumed supported."""
    if not claims:
        return 0.0
    results_by_id = {r.claim_id: r for r in verification_results}
    weighted_sum = 0.0
    weight_total = 0.0
    for claim in claims:
        result = results_by_id.get(claim.claim_id)
        importance = estimate_claim_importance(claim, neutral_weight=0.5)
        if result is None:
            credit = 0.0
        elif result.status == VerificationStatus.VERIFIED:
            credit = config.verified_credit
        elif result.status == VerificationStatus.PARTIALLY_VERIFIED:
            credit = config.partially_verified_credit
        else:
            credit = config.unsupported_credit
        weighted_sum += importance * credit
        weight_total += importance
    if weight_total <= 0:
        return 0.0
    return _clamp((weighted_sum / weight_total) * 100)


def calculate_evidence_quality(claims: list[Claim], verification_results: list[VerificationResult]) -> float:
    """Section 6: reuses each claim's best-matched `EvidenceMatch.quality_score`
    directly (Phase 5's source-authority/completeness/source-type-aware
    formula) rather than re-deriving it -- this is exactly what keeps an
    external report from being silently treated as government-authoritative:
    that distinction already lives in `quality_score`'s own source-type
    handling, never assumed here. A claim with no matched evidence
    contributes 0."""
    if not claims:
        return 0.0
    results_by_id = {r.claim_id: r for r in verification_results}
    scores: list[float] = []
    for claim in claims:
        result = results_by_id.get(claim.claim_id)
        if result is None or not result.matched_evidence:
            scores.append(0.0)
            continue
        best = result.matched_evidence[0]
        quality = best.quality_score if best.quality_score is not None else 0.0
        scores.append(quality * 100)
    return _clamp(sum(scores) / len(scores))


def calculate_consistency(verification_results: list[VerificationResult]) -> float:
    """Section 7: averages the numeric/unit/temporal/entity/category
    consistency checks Phase 6 already computed per claim (`numeric`
    already folds in direction consistency, per Phase 6's architecture).
    Claims with no verification result don't contribute -- consistency is
    only ever measured where a comparison was actually possible."""
    if not verification_results:
        return 0.0
    per_claim: list[float] = []
    for result in verification_results:
        checks = result.checks
        avg = (checks.numeric + checks.unit + checks.temporal + checks.entity + checks.category) / 5.0
        per_claim.append(avg * 100)
    return _clamp(sum(per_claim) / len(per_claim))


def _transparency_criteria(claim: Claim) -> tuple[int, int]:
    """Returns (met, applicable) for the transparency criteria that
    genuinely apply to this claim's type (section 8) -- an inapplicable
    criterion is excluded from the denominator entirely, never counted as
    a failure."""
    applicable = 1
    met = 0 if detect_vague_language(claim.claim).detected else 1  # "specific rather than vague" always applies

    if claim.claim_type in _NUMERIC_CLAIM_TYPES:
        applicable += 1
        if claim.value is not None and claim.unit is not None:
            met += 1

    if claim.claim_type in _TARGET_YEAR_CLAIM_TYPES:
        applicable += 1
        if claim.target_year is not None:
            met += 1

    if claim.claim_type in _NAMED_TARGET_CLAIM_TYPES:
        applicable += 1
        if claim.target is not None:
            met += 1

    return met, applicable


def calculate_transparency(claims: list[Claim]) -> float:
    """Section 8: measurable metrics, target years, and named targets/
    methodologies only count against a claim when its `claim_type` makes
    them relevant (`_transparency_criteria`) -- a governance policy claim
    is never penalized for lacking a target year."""
    if not claims:
        return 0.0
    per_claim: list[float] = []
    for claim in claims:
        met, applicable = _transparency_criteria(claim)
        per_claim.append((met / applicable) * 100 if applicable else 0.0)
    return _clamp(sum(per_claim) / len(per_claim))


def calculate_greenwashing_component(
    greenwashing_results: list[GreenwashingResult], config: TrustScoreConfig
) -> float:
    """Section 9: NOT a bare `100 - greenwashing_score` subtraction. The
    base is the average per-claim "safety" (`100 - greenwashing_score`),
    then a capped penalty scaled by the FRACTION of High/Medium-risk claims
    is subtracted on top -- so a report with a small number of genuinely
    high-risk claims is penalized more than a flat average would, matching
    the same "don't let volume dilute a real signal" principle Phase 7 uses
    for report-level aggregation, applied here in the opposite (penalizing)
    direction. With no greenwashing results at all, returns a documented
    neutral default -- never fabricated as "no risk"."""
    if not greenwashing_results:
        return _clamp(config.no_greenwashing_data_default)

    total = len(greenwashing_results)
    safety_scores = [100.0 - r.greenwashing_score for r in greenwashing_results]
    base = sum(safety_scores) / total

    high = sum(1 for r in greenwashing_results if r.greenwashing_risk == RiskLevel.HIGH)
    medium = sum(1 for r in greenwashing_results if r.greenwashing_risk == RiskLevel.MEDIUM)
    penalty = min(
        config.max_greenwashing_penalty,
        (high / total) * config.high_risk_penalty_scale + (medium / total) * config.medium_risk_penalty_scale,
    )
    return _clamp(base - penalty)


def calculate_provenance(claims: list[Claim], verification_results: list[VerificationResult]) -> float:
    """Section 10: whether a claim's supporting evidence can be traced back
    to document/page/chunk/evidence-record. A claim with no matched
    evidence contributes 0 -- provenance is never assumed."""
    if not claims:
        return 0.0
    results_by_id = {r.claim_id: r for r in verification_results}
    scores: list[float] = []
    for claim in claims:
        result = results_by_id.get(claim.claim_id)
        best = result.matched_evidence[0] if result and result.matched_evidence else None
        scores.append(evidence_provenance_completeness(best) * 100)
    return _clamp(sum(scores) / len(scores))


def calculate_final_score(components: TrustScoreComponents, weights: TrustScoreWeights) -> float:
    """Section 11/30: a documented weighted sum of all 6 components --
    never a simplistic `verified_claims / total_claims * 100` shortcut."""
    raw = (
        components.claim_support * weights.claim_support
        + components.evidence_quality * weights.evidence_quality
        + components.consistency * weights.consistency
        + components.transparency * weights.transparency
        + components.greenwashing_risk * weights.greenwashing_risk
        + components.provenance * weights.provenance
    )
    return _clamp(raw)


def determine_rating(score: float, thresholds: TrustRatingThresholds) -> TrustRating:
    if score >= thresholds.excellent_min:
        return TrustRating.EXCELLENT
    if score >= thresholds.good_min:
        return TrustRating.GOOD
    if score >= thresholds.moderate_min:
        return TrustRating.MODERATE
    return TrustRating.LOW


def calculate_confidence(
    total_claims: int,
    evidence_coverage: float,
    verification_coverage: float,
    provenance_coverage: float,
    components: TrustScoreComponents,
    config: TrustScoreConfig,
) -> float:
    """Section 14/15: confidence answers "how reliable is this computed
    Trust Score?", a deliberately different question from the score
    itself. Equally-weighted average of 5 documented factors: (1) sample
    size, scaled linearly up to `min_claims_for_full_confidence` claims,
    (2) evidence coverage, (3) verification coverage, (4) provenance
    coverage, and (5) agreement between the 6 components (how close
    together they are -- widely disagreeing signals mean a less certain
    read, even if the score itself is unaffected). A report with very few
    claims is never given the same confidence as one with hundreds, even
    if every one of those few claims is fully verified."""
    if total_claims <= 0:
        # No claims at all means no signal of any kind -- component
        # "agreement" would otherwise be trivially perfect (0 == 0 == ...)
        # and falsely inflate confidence above zero.
        return 0.0

    sample_size_factor = min(1.0, total_claims / config.min_claims_for_full_confidence)

    values = (
        components.claim_support, components.evidence_quality, components.consistency,
        components.transparency, components.greenwashing_risk, components.provenance,
    )
    agreement_factor = 1.0 - ((max(values) - min(values)) / 100.0)

    factors = [
        sample_size_factor,
        evidence_coverage / 100.0,
        verification_coverage / 100.0,
        provenance_coverage / 100.0,
        agreement_factor,
    ]
    return _clamp((sum(factors) / len(factors)) * 100)
