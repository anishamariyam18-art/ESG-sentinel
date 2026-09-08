"""Deterministic finding detection and finding-to-action mappings
(sections 1, 9, 19, 26).

Every `Finding` here is derived directly from an already-computed upstream
signal -- `VerificationResult.checks` (Phase 6), `GreenwashingResult.
greenwashing_type` (Phase 7), `TrustScoreResult.components` (Phase 8), or a
claim's own fields -- never invented. Each `rule_*` function is a pure,
independently-testable `IF <condition> THEN <finding>` mapping (section 26).
`FINDING_TEMPLATES` is the deterministic problem->action mapping (section 9)
-- no Python logic decides recommendation wording, only which template
applies.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.config import RecommendationConfig
from app.models.claim import Claim, ClaimCategory, ClaimType
from app.models.greenwashing import GreenwashingResult, GreenwashingType, RiskLevel
from app.models.recommendation import RecommendationCategory, TimeHorizon
from app.models.trust import TrustScore, TrustScoreComponents
from app.models.verification import VerificationResult, VerificationStatus
from app.trust_score.scorer import _NUMERIC_CLAIM_TYPES, _TARGET_YEAR_CLAIM_TYPES, evidence_provenance_completeness


class Finding(BaseModel):
    finding_type: str
    claim_id: str | None = None
    category: RecommendationCategory
    severity: float = Field(ge=0.0, le=1.0)
    verification_impact: float = Field(ge=0.0, le=1.0, default=0.0)
    greenwashing_risk: float = Field(ge=0.0, le=1.0, default=0.0)
    trust_impact: float = Field(ge=0.0, le=1.0, default=0.0)
    claim_importance: float = Field(ge=0.0, le=1.0, default=0.5)
    description: str = Field(min_length=1)
    #: section 7's explicit High-priority examples ("explicit contradiction",
    #: "major numerical mismatch", "high greenwashing risk") are structural,
    #: not a matter of degree on the weighted formula -- a finding carrying
    #: this forces its recommendation group to High priority regardless of
    #: the weighted score, the same "a hard signal can't be outvoted by a
    #: good score" pattern used throughout this pipeline (Phases 6-8).
    hard_priority_override: bool = False


def _category_of(claim: Claim) -> RecommendationCategory:
    mapping = {
        ClaimCategory.ENVIRONMENTAL: RecommendationCategory.ENVIRONMENTAL,
        ClaimCategory.SOCIAL: RecommendationCategory.SOCIAL,
        ClaimCategory.GOVERNANCE: RecommendationCategory.GOVERNANCE,
    }
    return mapping.get(claim.category, RecommendationCategory.CROSS_CUTTING)


#: Which Trust Score component each per-claim finding_type most directly
#: relates to (section 8: "trust-score impact" as one priority factor) --
#: used only to look up that component's current value, never to alter it.
_FINDING_TRUST_COMPONENT = {
    "unsupported_claim": "claim_support",
    "partially_verified_claim": "claim_support",
    "numerical_mismatch": "consistency",
    "unit_mismatch": "consistency",
    "target_year_mismatch": "consistency",
    "missing_provenance": "provenance",
    "vague_claim": "greenwashing_risk",
    "absolute_claim": "greenwashing_risk",
    "exaggerated_claim": "greenwashing_risk",
    "contradictory_claim": "greenwashing_risk",
    "unsubstantiated_benefit": "greenwashing_risk",
    "missing_qualification": "transparency",
    "misleading_comparison": "greenwashing_risk",
    "selective_presentation": "greenwashing_risk",
    "missing_target": "transparency",
    "missing_metrics": "transparency",
}


def _trust_impact(finding_type: str, trust_score: TrustScoreComponents | None) -> float:
    if trust_score is None:
        return 0.0
    component_name = _FINDING_TRUST_COMPONENT.get(finding_type)
    if component_name is None:
        return 0.0
    value = getattr(trust_score, component_name)
    return round((100.0 - value) / 100.0, 3)


def _greenwashing_severity(greenwashing_result: GreenwashingResult | None) -> float:
    if greenwashing_result is None:
        return 0.0
    return round(greenwashing_result.greenwashing_score / 100.0, 3)


# --- Per-claim rules: verification-derived (section 9, 15) ----------------

def rule_unsupported_claim(claim: Claim, verification_result: VerificationResult | None, trust_components) -> Finding | None:
    if verification_result is None or verification_result.status != VerificationStatus.UNSUPPORTED:
        return None
    return Finding(
        finding_type="unsupported_claim", claim_id=claim.claim_id, category=_category_of(claim),
        severity=1.0, verification_impact=1.0, trust_impact=_trust_impact("unsupported_claim", trust_components),
        claim_importance=0.5, description=f"Claim {claim.claim_id} ({claim.category.value}) is unsupported by available evidence.",
    )


def rule_partially_verified_claim(claim: Claim, verification_result: VerificationResult | None, trust_components) -> Finding | None:
    if verification_result is None or verification_result.status != VerificationStatus.PARTIALLY_VERIFIED:
        return None
    return Finding(
        finding_type="partially_verified_claim", claim_id=claim.claim_id, category=_category_of(claim),
        severity=0.5, verification_impact=0.5, trust_impact=_trust_impact("partially_verified_claim", trust_components),
        claim_importance=0.5, description=f"Claim {claim.claim_id} ({claim.category.value}) was only partially verified against available evidence.",
    )


#: A numerical check score at or below this (i.e. severity >= 0.9) counts
#: as a "major" mismatch (section 7's High-priority example), not just an
#: ordinary inconsistency.
_MAJOR_NUMERICAL_MISMATCH_SEVERITY = 0.9


def rule_numerical_mismatch(claim: Claim, verification_result: VerificationResult | None, trust_components, config: RecommendationConfig) -> Finding | None:
    if verification_result is None:
        return None
    numeric_score = verification_result.checks.numeric
    if numeric_score >= config.numerical_mismatch_threshold:
        return None
    severity = round(1.0 - numeric_score, 3)
    return Finding(
        finding_type="numerical_mismatch", claim_id=claim.claim_id, category=_category_of(claim),
        severity=severity, verification_impact=severity, trust_impact=_trust_impact("numerical_mismatch", trust_components),
        claim_importance=0.5, description=f"Claim {claim.claim_id} states a numerical value inconsistent with the matched evidence.",
        hard_priority_override=severity >= _MAJOR_NUMERICAL_MISMATCH_SEVERITY,
    )


def rule_unit_mismatch(claim: Claim, verification_result: VerificationResult | None, trust_components) -> Finding | None:
    if verification_result is None or verification_result.checks.unit >= 1.0:
        return None
    return Finding(
        finding_type="unit_mismatch", claim_id=claim.claim_id, category=_category_of(claim),
        severity=round(1.0 - verification_result.checks.unit, 3), verification_impact=round(1.0 - verification_result.checks.unit, 3),
        trust_impact=_trust_impact("unit_mismatch", trust_components), claim_importance=0.5,
        description=f"Claim {claim.claim_id} uses a unit incompatible with the matched evidence.",
        hard_priority_override=True,  # Phase 6 only flags this on genuine incompatibility, never by degree
    )


def rule_target_year_mismatch(claim: Claim, verification_result: VerificationResult | None, trust_components) -> Finding | None:
    if verification_result is None or verification_result.checks.temporal >= 1.0:
        return None
    return Finding(
        finding_type="target_year_mismatch", claim_id=claim.claim_id, category=_category_of(claim),
        severity=round(1.0 - verification_result.checks.temporal, 3), verification_impact=round(1.0 - verification_result.checks.temporal, 3),
        trust_impact=_trust_impact("target_year_mismatch", trust_components), claim_importance=0.5,
        description=f"Claim {claim.claim_id} states a target/reporting year inconsistent with the matched evidence.",
        hard_priority_override=True,  # Phase 6 only flags this on genuine incompatibility, never by degree
    )


def rule_missing_provenance(claim: Claim, verification_result: VerificationResult | None, trust_components, config: RecommendationConfig) -> Finding | None:
    best_match = verification_result.matched_evidence[0] if verification_result and verification_result.matched_evidence else None
    completeness = evidence_provenance_completeness(best_match)
    if completeness >= config.provenance_completeness_threshold:
        return None
    return Finding(
        finding_type="missing_provenance", claim_id=claim.claim_id, category=_category_of(claim),
        severity=round(1.0 - completeness, 3), verification_impact=0.0,
        trust_impact=_trust_impact("missing_provenance", trust_components), claim_importance=0.5,
        description=f"Claim {claim.claim_id}'s supporting evidence lacks complete document/page/chunk/evidence-id traceability.",
    )


# --- Per-claim rules: greenwashing-derived (section 9, 14) ----------------

_GREENWASHING_RULE_TYPES = {
    GreenwashingType.VAGUE_CLAIM: "vague_claim",
    GreenwashingType.ABSOLUTE_CLAIM: "absolute_claim",
    GreenwashingType.EXAGGERATED_CLAIM: "exaggerated_claim",
    GreenwashingType.CONTRADICTORY_CLAIM: "contradictory_claim",
    GreenwashingType.UNSUBSTANTIATED_BENEFIT: "unsubstantiated_benefit",
    GreenwashingType.MISSING_QUALIFICATION: "missing_qualification",
    GreenwashingType.MISLEADING_COMPARISON: "misleading_comparison",
    GreenwashingType.SELECTIVE_PRESENTATION: "selective_presentation",
}


def rules_from_greenwashing(claim: Claim, greenwashing_result: GreenwashingResult | None, trust_components) -> list[Finding]:
    if greenwashing_result is None:
        return []
    findings: list[Finding] = []
    risk_severity = _greenwashing_severity(greenwashing_result)
    # Phase 7 already produced grounded, signal-specific detail text
    # (e.g. "The claim states 80.0%; the evidence states 20.0%.") --
    # reuse it directly rather than re-deriving the discrepancy.
    detail = f" {' '.join(greenwashing_result.explanation)}" if greenwashing_result.explanation else ""
    for gw_type in greenwashing_result.greenwashing_type:
        finding_type = _GREENWASHING_RULE_TYPES.get(gw_type)
        if finding_type is None:
            continue
        findings.append(Finding(
            finding_type=finding_type, claim_id=claim.claim_id, category=_category_of(claim),
            severity=max(risk_severity, 0.3), verification_impact=0.0, greenwashing_risk=risk_severity,
            trust_impact=_trust_impact(finding_type, trust_components), claim_importance=0.5,
            description=f"Claim {claim.claim_id}: {gw_type.value.lower()} ({greenwashing_result.greenwashing_risk.value} greenwashing risk).{detail}",
            # section 7: "high greenwashing risk" and "explicit contradiction"
            # are both named as standalone High-priority triggers.
            hard_priority_override=(greenwashing_result.greenwashing_risk == RiskLevel.HIGH or gw_type == GreenwashingType.CONTRADICTORY_CLAIM),
        ))
    return findings


# --- Per-claim rules: claim-field-derived (section 1: missing targets/metrics) ---

def rule_missing_target(claim: Claim, trust_components) -> Finding | None:
    if claim.claim_type not in _TARGET_YEAR_CLAIM_TYPES or claim.target_year is not None:
        return None
    return Finding(
        finding_type="missing_target", claim_id=claim.claim_id, category=_category_of(claim),
        severity=0.4, trust_impact=_trust_impact("missing_target", trust_components), claim_importance=0.5,
        description=f"Commitment claim {claim.claim_id} does not state a target year.",
    )


def rule_missing_metrics(claim: Claim, trust_components) -> Finding | None:
    if claim.claim_type not in _NUMERIC_CLAIM_TYPES or (claim.value is not None and claim.unit is not None):
        return None
    return Finding(
        finding_type="missing_metrics", claim_id=claim.claim_id, category=_category_of(claim),
        severity=0.4, trust_impact=_trust_impact("missing_metrics", trust_components), claim_importance=0.5,
        description=f"Claim {claim.claim_id} reports a metric/performance outcome without a measurable value and unit.",
    )


# --- Report-level rules (section 13, 16) -----------------------------------

def rule_weak_trust_components(trust_score: TrustScore, config: RecommendationConfig) -> list[Finding]:
    """One Finding per Trust Score component below `weak_component_threshold`,
    ordered weakest-first (section 13: prioritize the weakest, highest-impact
    areas -- never a bare "increase trust score" recommendation). A report
    with zero claims has nothing to recommend -- every component being 0 in
    that case reflects "nothing was assessed", not a discovered weakness."""
    if trust_score.statistics.total_claims == 0:
        return []
    components = trust_score.components.model_dump()
    weak = [(name, value) for name, value in components.items() if value < config.weak_component_threshold]
    weak.sort(key=lambda pair: pair[1])
    findings: list[Finding] = []
    for name, value in weak:
        findings.append(Finding(
            finding_type=f"weak_trust_component:{name}", category=RecommendationCategory.CROSS_CUTTING,
            severity=round((config.weak_component_threshold - value) / config.weak_component_threshold, 3),
            trust_impact=round((100.0 - value) / 100.0, 3), claim_importance=0.5,
            description=f"Trust Score component '{name}' is {value} (below the {config.weak_component_threshold} threshold).",
        ))
    return findings


def rule_low_evidence_coverage(trust_score: TrustScore, config: RecommendationConfig) -> Finding | None:
    if trust_score.statistics.total_claims == 0:
        return None
    coverage = trust_score.statistics.evidence_coverage
    if coverage >= config.low_evidence_coverage_threshold:
        return None
    return Finding(
        finding_type="low_evidence_coverage", category=RecommendationCategory.CROSS_CUTTING,
        severity=round((config.low_evidence_coverage_threshold - coverage) / config.low_evidence_coverage_threshold, 3),
        trust_impact=round((100.0 - trust_score.components.evidence_quality) / 100.0, 3), claim_importance=0.5,
        description=f"Evidence coverage is {coverage}% of claims -- below the {config.low_evidence_coverage_threshold}% threshold.",
    )


# --- Deterministic problem -> action templates (section 9, 18, 19) --------

class RecommendationTemplate(BaseModel):
    title: str
    action: str
    reason: str
    expected_impact: str
    time_horizon: TimeHorizon


FINDING_TEMPLATES: dict[str, RecommendationTemplate] = {
    "unsupported_claim": RecommendationTemplate(
        title="Provide evidence for unsupported {category} claims",
        action="Provide supporting evidence for the claim(s) and preserve document, page, and source references.",
        reason="Improved evidence coverage increases verification confidence and reduces unsupported-claim risk.",
        expected_impact="Higher evidence coverage and stronger claim support.",
        time_horizon=TimeHorizon.SHORT_TERM,
    ),
    "partially_verified_claim": RecommendationTemplate(
        title="Complete evidence for partially verified {category} claims",
        action="Address the specific evidence gaps identified during verification to fully substantiate the claim(s).",
        reason="Closing partial-verification gaps increases claim support and overall trust.",
        expected_impact="Movement from Partially Verified to Verified status.",
        time_horizon=TimeHorizon.SHORT_TERM,
    ),
    "numerical_mismatch": RecommendationTemplate(
        title="Reconcile numerical values in {category} claims",
        action="Reconcile the reported numerical value with the underlying source data and disclose the correct calculation basis.",
        reason="An unreconciled numerical discrepancy undermines the credibility of the disclosure.",
        expected_impact="Consistent, verifiable figures across claim and evidence.",
        time_horizon=TimeHorizon.IMMEDIATE,
    ),
    "unit_mismatch": RecommendationTemplate(
        title="Correct unit inconsistencies in {category} claims",
        action="Correct the reported unit and document the measurement basis.",
        reason="An incompatible unit prevents the claim from being verified against the underlying evidence.",
        expected_impact="Claim and evidence expressed in compatible, comparable units.",
        time_horizon=TimeHorizon.IMMEDIATE,
    ),
    "target_year_mismatch": RecommendationTemplate(
        title="Reconcile target/reporting years in {category} claims",
        action="Clarify and reconcile the target or reporting year across ESG disclosures.",
        reason="An inconsistent year makes it unclear which period the claim actually describes.",
        expected_impact="A single, consistent target/reporting year across the disclosure.",
        time_horizon=TimeHorizon.IMMEDIATE,
    ),
    "missing_provenance": RecommendationTemplate(
        title="Add traceable evidence provenance for {category} claims",
        action="Add traceable source references (document, page, and chunk identifiers) for the reported ESG information.",
        reason="Complete provenance is required to independently verify the claim.",
        expected_impact="Full document/page/chunk traceability for the underlying evidence.",
        time_horizon=TimeHorizon.SHORT_TERM,
    ),
    "vague_claim": RecommendationTemplate(
        title="Replace vague language in {category} claims with measurable objectives",
        action="Replace broad sustainability language with measurable objectives, defined metrics and target dates where applicable.",
        reason="Vague, unquantified language cannot be independently verified and reads as promotional rather than substantive.",
        expected_impact="Claims that are specific, measurable, and verifiable.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
    ),
    "absolute_claim": RecommendationTemplate(
        title="Substantiate absolute language in {category} claims",
        action="Provide measurable evidence and clearly define the scope and conditions supporting the environmental claim.",
        reason="An unqualified absolute claim (e.g. '100%', 'zero') is easily contradicted by a single exception.",
        expected_impact="Absolute claims that are fully scoped and evidenced.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
    ),
    "exaggerated_claim": RecommendationTemplate(
        title="Correct exaggerated figures in {category} claims",
        action="Correct the reported figure and disclose the underlying baseline and calculation methodology.",
        reason="The claimed figure substantially exceeds what the underlying evidence supports.",
        expected_impact="A reported figure consistent with the disclosed evidence and methodology.",
        time_horizon=TimeHorizon.IMMEDIATE,
    ),
    "contradictory_claim": RecommendationTemplate(
        title="Resolve contradictions in {category} claims",
        action="Resolve the contradiction between the claim and the evidence before publishing the ESG disclosure.",
        reason="A claim that actively conflicts with its own evidence undermines the reliability of the whole disclosure.",
        expected_impact="A claim consistent with its supporting evidence.",
        time_horizon=TimeHorizon.IMMEDIATE,
    ),
    "unsubstantiated_benefit": RecommendationTemplate(
        title="Substantiate claimed benefits in {category} claims",
        action="Provide supporting evidence for the stated environmental or social benefit.",
        reason="A stated benefit with no supporting evidence cannot be independently verified.",
        expected_impact="Benefit claims backed by source-level evidence.",
        time_horizon=TimeHorizon.SHORT_TERM,
    ),
    "missing_qualification": RecommendationTemplate(
        title="Add missing qualifying information to {category} claims",
        action="Include the qualifying information present in the underlying evidence (e.g. the baseline year).",
        reason="Omitting a known qualification changes how the figure should be interpreted.",
        expected_impact="Claims that carry the same qualifications as their underlying evidence.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
    ),
    "misleading_comparison": RecommendationTemplate(
        title="Substantiate comparisons in {category} claims",
        action="Provide a clear, substantiated basis for the comparison (e.g. the benchmark, peer group, or prior period used).",
        reason="An unsubstantiated comparison can create a misleading impression of relative performance.",
        expected_impact="Comparisons with a clearly disclosed, verifiable basis.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
    ),
    "selective_presentation": RecommendationTemplate(
        title="Present full scope of results in {category} claims",
        action="Present the full scope of results rather than a subset that may create a misleading overall impression.",
        reason="Reporting only favorable figures while omitting unfavorable ones in the same scope misrepresents overall performance.",
        expected_impact="A disclosure that reflects the full, disclosed scope of results.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
    ),
    "missing_target": RecommendationTemplate(
        title="Define target years for {category} commitments",
        action="Add an explicit target year to the stated commitment.",
        reason="A commitment without a target year cannot be tracked or verified over time.",
        expected_impact="Commitments with a clear, trackable target year.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
    ),
    "missing_metrics": RecommendationTemplate(
        title="Add measurable metrics to {category} claims",
        action="Report the claim with an explicit numeric value and unit.",
        reason="A metric or performance claim without a measurable value cannot be verified or tracked.",
        expected_impact="Metric/performance claims that carry a specific, verifiable value and unit.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
    ),
    "low_evidence_coverage": RecommendationTemplate(
        title="Improve overall evidence coverage",
        action="Establish a structured process for attaching source-level documentation, datasets, and calculation methodology to reported ESG claims.",
        reason="Low evidence coverage across the report limits how many claims can be independently verified.",
        expected_impact="A higher proportion of claims backed by matched, traceable evidence.",
        time_horizon=TimeHorizon.LONG_TERM,
    ),
    "weak_trust_component:claim_support": RecommendationTemplate(
        title="Improve overall claim support",
        action="Prioritize evidence collection for currently unsupported and partially verified claims.",
        reason="Claim support is one of the weakest components behind the overall Trust Score.",
        expected_impact="A higher claim_support component and overall Trust Score.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
    ),
    "weak_trust_component:evidence_quality": RecommendationTemplate(
        title="Improve overall evidence quality",
        action="Strengthen the authority, completeness, and source-type documentation of the evidence attached to claims.",
        reason="Evidence quality is one of the weakest components behind the overall Trust Score.",
        expected_impact="A higher evidence_quality component and overall Trust Score.",
        time_horizon=TimeHorizon.LONG_TERM,
    ),
    "weak_trust_component:consistency": RecommendationTemplate(
        title="Resolve numerical, unit, and temporal inconsistencies",
        action="Review and reconcile the numerical, unit, and temporal inconsistencies identified between claims and their evidence.",
        reason="Consistency is one of the weakest components behind the overall Trust Score.",
        expected_impact="A higher consistency component and overall Trust Score.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
    ),
    "weak_trust_component:transparency": RecommendationTemplate(
        title="Improve claim transparency",
        action="Add measurable metrics, target years, and named methodologies to claims where they are currently missing.",
        reason="Transparency is one of the weakest components behind the overall Trust Score.",
        expected_impact="A higher transparency component and overall Trust Score.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
    ),
    "weak_trust_component:greenwashing_risk": RecommendationTemplate(
        title="Reduce greenwashing risk signals",
        action="Review claims flagged with greenwashing risk signals and replace unsupported, vague, or exaggerated language with measurable, evidenced statements.",
        reason="Greenwashing risk is one of the weakest components behind the overall Trust Score.",
        expected_impact="A higher greenwashing_risk (safety) component and overall Trust Score.",
        time_horizon=TimeHorizon.MEDIUM_TERM,
    ),
    "weak_trust_component:provenance": RecommendationTemplate(
        title="Improve evidence provenance traceability",
        action="Ensure every piece of supporting evidence carries a complete document, page, and chunk reference.",
        reason="Provenance is one of the weakest components behind the overall Trust Score.",
        expected_impact="A higher provenance component and overall Trust Score.",
        time_horizon=TimeHorizon.SHORT_TERM,
    ),
}


#: A finding_type already covered by a more specific label should not also
#: produce a near-duplicate recommendation for the same claim (section 27:
#: avoid near-identical recommendations for the same underlying problem).
#: Key -> set of OTHER finding_types that, if present for the same claim,
#: suppress the key.
_SUPERSEDED_BY = {
    "numerical_mismatch": {"exaggerated_claim", "contradictory_claim"},
    "missing_provenance": {"unsupported_claim"},  # no evidence at all already implies no provenance
}


def collect_claim_findings(
    claim: Claim, verification_result: VerificationResult | None, greenwashing_result: GreenwashingResult | None,
    trust_components, config: RecommendationConfig,
) -> list[Finding]:
    findings: list[Finding] = []
    greenwashing_findings = rules_from_greenwashing(claim, greenwashing_result, trust_components)

    verification_findings = [
        rule_unsupported_claim(claim, verification_result, trust_components),
        rule_partially_verified_claim(claim, verification_result, trust_components),
        rule_numerical_mismatch(claim, verification_result, trust_components, config),
        rule_unit_mismatch(claim, verification_result, trust_components),
        rule_target_year_mismatch(claim, verification_result, trust_components),
        rule_missing_provenance(claim, verification_result, trust_components, config),
        rule_missing_target(claim, trust_components),
        rule_missing_metrics(claim, trust_components),
    ]
    present_types = {f.finding_type for f in greenwashing_findings} | {f.finding_type for f in verification_findings if f is not None}

    for rule_finding in verification_findings:
        if rule_finding is None:
            continue
        if _SUPERSEDED_BY.get(rule_finding.finding_type, set()) & (present_types - {rule_finding.finding_type}):
            continue
        findings.append(rule_finding)

    findings.extend(greenwashing_findings)
    return findings
