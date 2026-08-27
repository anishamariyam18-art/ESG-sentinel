"""Greenwashing detection contract.

`greenwashing_type` is a MULTI-LABEL list, not a single classification --
a claim can simultaneously be, say, both an Absolute Claim and a Vague
Claim. `NO_SIGNIFICANT_SIGNAL` is the explicit "nothing detected" value; a
normal, fully-supported claim gets exactly `["No Significant Greenwashing
Signal"]`, never an empty list standing in for "unknown".

Critically: `Unsupported` verification status does NOT automatically mean
greenwashing. `features` holds the measurable signals the deterministic
scorer actually used, so `explanation` can never be generated without the
inputs that justify it -- and the score can be audited component by
component rather than trusted as an opaque number.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.models.evidence import EvidenceMatch
from app.models.verification import VerificationStatus


class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class GreenwashingType(str, Enum):
    UNSUPPORTED_ENVIRONMENTAL_CLAIM = "Unsupported Environmental Claim"
    MISLEADING_CLAIM = "Misleading Claim"
    EXAGGERATED_CLAIM = "Exaggerated Claim"
    VAGUE_CLAIM = "Vague Claim"
    ABSOLUTE_CLAIM = "Absolute Claim"
    UNSUBSTANTIATED_BENEFIT = "Unsubstantiated Benefit"
    CONTRADICTORY_CLAIM = "Contradictory Claim"
    SELECTIVE_PRESENTATION = "Selective Presentation"
    MISLEADING_COMPARISON = "Misleading Comparison"
    MISSING_QUALIFICATION = "Missing Qualification"
    NO_SIGNIFICANT_SIGNAL = "No Significant Greenwashing Signal"


class GreenwashingFeatures(BaseModel):
    """One float (0.0-1.0) per deterministic signal (section 16). The
    first two are "protective" (their absence, i.e. 1 - value, is what
    increases risk); the rest are risk-increasing signals directly."""

    evidence_support: float = Field(ge=0.0, le=1.0)
    provenance_quality: float = Field(ge=0.0, le=1.0)
    numerical_consistency: float = Field(ge=0.0, le=1.0)
    contradiction: float = Field(ge=0.0, le=1.0)
    vagueness: float = Field(ge=0.0, le=1.0)
    absolute_language: float = Field(ge=0.0, le=1.0)
    unsupported_benefit: float = Field(ge=0.0, le=1.0)
    missing_qualification: float = Field(ge=0.0, le=1.0)
    misleading_comparison: float = Field(ge=0.0, le=1.0)


class GreenwashingResult(BaseModel):
    claim_id: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    verification_status: VerificationStatus
    greenwashing_risk: RiskLevel
    greenwashing_type: list[GreenwashingType] = Field(default_factory=list)
    greenwashing_score: float = Field(ge=0.0, le=100.0)
    confidence_score: float = Field(ge=0.0, le=100.0)
    reason: str = ""
    evidence: list[EvidenceMatch] = Field(default_factory=list)
    features: GreenwashingFeatures
    explanation: list[str] = Field(default_factory=list)
    recommendation: str = ""


class GreenwashingReport(BaseModel):
    """Report-level aggregation (section 25) -- computed from claim-level
    results, never requested directly from the LLM."""

    total_claims: int = Field(ge=0)
    low_risk: int = Field(ge=0)
    medium_risk: int = Field(ge=0)
    high_risk: int = Field(ge=0)
    overall_risk: RiskLevel
    overall_score: float = Field(ge=0.0, le=100.0)
    claims: list[GreenwashingResult] = Field(default_factory=list)
