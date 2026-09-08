"""ESG Recommendation contract (Phase 9).

Every `Recommendation` MUST trace back to concrete upstream findings --
`source_claim_ids` and/or `source_findings` -- never generic ESG advice
unrelated to the analyzed report (section 5/6: "if a recommendation has no
identifiable source finding, do not generate it"). The deterministic rule
engine (`app.recommendations.rules`) is always what decides `category`,
`priority`, and which problem->action mapping fires; an optional LLM may
only improve wording (section 23).
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RecommendationPriority(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class RecommendationCategory(str, Enum):
    ENVIRONMENTAL = "Environmental"
    SOCIAL = "Social"
    GOVERNANCE = "Governance"
    CROSS_CUTTING = "Cross-cutting"


class TimeHorizon(str, Enum):
    IMMEDIATE = "Immediate"
    SHORT_TERM = "Short-term"
    MEDIUM_TERM = "Medium-term"
    LONG_TERM = "Long-term"


class Recommendation(BaseModel):
    recommendation_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    problem: str = Field(min_length=1)
    source_claim_ids: list[str] = Field(default_factory=list)
    source_findings: list[str] = Field(default_factory=list)
    category: RecommendationCategory
    priority: RecommendationPriority
    priority_score: float = Field(ge=0.0, le=100.0)
    action: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    expected_impact: str = Field(min_length=1)
    time_horizon: TimeHorizon
    explanation: str = Field(min_length=1)


class PriorityAction(BaseModel):
    """The highest-impact recommendations, surfaced separately (section 30)
    so a consumer doesn't have to re-sort the full `recommendations` list."""

    recommendation_id: str = Field(min_length=1)
    priority: RecommendationPriority
    action: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class RecommendationResult(BaseModel):
    document_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    overall_assessment: str = Field(default="")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)
    priority_actions: list[PriorityAction] = Field(default_factory=list)
    implementation_areas: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
