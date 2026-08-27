"""ESG Trust Score contract (Phase 8).

`trust_score` is always computed deterministically from `components` by
`app.trust_score.scorer` -- never requested directly from an LLM (section
24: the LLM may only phrase an optional natural-language narrative onto
`explanation`, never calculate or override the numerical score or any
other field here). `confidence` is a deliberately separate number from
`trust_score`: "how well-supported and internally consistent is the ESG
information?" vs. "how reliable is this computed score given the available
data?" (section 14) -- a report with very few claims can have a high
`trust_score` and a low `confidence` at the same time.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class TrustRating(str, Enum):
    EXCELLENT = "Excellent"
    GOOD = "Good"
    MODERATE = "Moderate"
    LOW = "Low"


class TrustScoreComponents(BaseModel):
    """Six independently computed 0-100 components (section 4). Each is
    oriented so a HIGHER value always means MORE trustworthy -- including
    `greenwashing_risk`, which despite its name holds the inverse-of-risk
    ("greenwashing safety") contribution: 100 means no greenwashing signal
    was detected across the assessed claims, 0 means severe, widespread
    risk. Keeping every component on the same "higher is better" scale is
    what lets `calculate_final_score` combine them with a single weighted
    sum (section 11)."""

    claim_support: float = Field(ge=0.0, le=100.0)
    evidence_quality: float = Field(ge=0.0, le=100.0)
    consistency: float = Field(ge=0.0, le=100.0)
    transparency: float = Field(ge=0.0, le=100.0)
    greenwashing_risk: float = Field(ge=0.0, le=100.0)
    provenance: float = Field(ge=0.0, le=100.0)


class TrustScoreStatistics(BaseModel):
    """Deterministic report statistics (section 17)."""

    total_claims: int = Field(ge=0)
    verified_claims: int = Field(ge=0)
    partially_verified_claims: int = Field(ge=0)
    unsupported_claims: int = Field(ge=0)
    high_greenwashing_claims: int = Field(ge=0)
    medium_greenwashing_claims: int = Field(ge=0)
    low_greenwashing_claims: int = Field(ge=0)
    evidence_coverage: float = Field(ge=0.0, le=100.0, description="% of claims with at least one matched evidence record")
    verification_coverage: float = Field(ge=0.0, le=100.0, description="% of claims that received a VerificationResult at all")
    provenance_coverage: float = Field(ge=0.0, le=100.0, description="% of claims whose best evidence carries complete document/page/chunk/evidence-id provenance")


class TrustScore(BaseModel):
    document_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    trust_score: float = Field(ge=0.0, le=100.0)
    rating: TrustRating
    confidence: float = Field(ge=0.0, le=100.0)
    components: TrustScoreComponents
    statistics: TrustScoreStatistics
    explanation: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
