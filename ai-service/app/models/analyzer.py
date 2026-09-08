"""Contract for the ESG Analyzer module output.

The analyzer must use only the supplied report. Missing string fields are
represented explicitly as "Not Found"; missing list fields as []. Never a
fabricated value.

Metrics/targets/commitments/risks/opportunities/costing entries carry
mandatory page/chunk provenance (they always come from a specific chunk the
model was shown); `AnalyzerClaim` -- the analyzer's high-level, non-
exhaustive claims, distinct from Phase 4's dedicated claim extractor -- may
have it only "where possible". `additional_references` preserves further
occurrences of the same item found in other chunks (e.g. the same metric
repeated in a summary table and in body text) without collapsing them into
a single, provenance-losing entry.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.models.claim import ClaimCategory
from app.models.provenance import SourceReference

NOT_FOUND = "Not Found"


class AnalyzerMetric(BaseModel):
    metric_name: str = Field(min_length=1)
    value: float | None = None
    unit: str | None = None
    reporting_year: int | None = None
    page_number: int = Field(ge=1)
    source_chunk_id: str = Field(min_length=1)
    additional_references: list[SourceReference] = Field(default_factory=list)


class AnalyzerTarget(BaseModel):
    target: str = Field(min_length=1)
    metric: str | None = None
    target_value: float | None = None
    unit: str | None = None
    baseline_year: int | None = None
    target_year: int | None = None
    page_number: int = Field(ge=1)
    source_chunk_id: str = Field(min_length=1)
    additional_references: list[SourceReference] = Field(default_factory=list)


class AnalyzerCommitment(BaseModel):
    commitment: str = Field(min_length=1)
    category: ClaimCategory | None = None
    page_number: int = Field(ge=1)
    source_chunk_id: str = Field(min_length=1)
    additional_references: list[SourceReference] = Field(default_factory=list)


class AnalyzerRisk(BaseModel):
    risk: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    source_chunk_id: str = Field(min_length=1)
    additional_references: list[SourceReference] = Field(default_factory=list)


class AnalyzerOpportunity(BaseModel):
    opportunity: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    source_chunk_id: str = Field(min_length=1)
    additional_references: list[SourceReference] = Field(default_factory=list)


class CostingEntry(BaseModel):
    amount: float
    currency: str = Field(min_length=1)
    description: str = Field(min_length=1)
    year: int | None = None
    page_number: int = Field(ge=1)
    source_chunk_id: str = Field(min_length=1)
    additional_references: list[SourceReference] = Field(default_factory=list)


class AnalyzerClaim(BaseModel):
    """A concise, high-level claim surfaced by the analyzer for summary
    purposes -- NOT exhaustive claim extraction (that's Phase 4)."""

    claim: str = Field(min_length=1)
    category: ClaimCategory | None = None
    page_number: int | None = Field(default=None, ge=1)
    source_chunk_id: str | None = None


class EnvironmentAnalysis(BaseModel):
    summary: str = NOT_FOUND
    carbon_emissions: list[str] = Field(default_factory=list)
    water_usage: list[str] = Field(default_factory=list)
    renewable_energy: list[str] = Field(default_factory=list)
    waste_management: list[str] = Field(default_factory=list)
    net_zero_commitments: list[str] = Field(default_factory=list)
    biodiversity: list[str] = Field(default_factory=list)
    climate_actions: list[str] = Field(default_factory=list)


class SocialAnalysis(BaseModel):
    summary: str = NOT_FOUND
    women_employees: list[str] = Field(default_factory=list)
    employee_diversity: list[str] = Field(default_factory=list)
    health_and_safety: list[str] = Field(default_factory=list)
    training: list[str] = Field(default_factory=list)
    csr: list[str] = Field(default_factory=list)
    human_rights: list[str] = Field(default_factory=list)


class GovernanceAnalysis(BaseModel):
    summary: str = NOT_FOUND
    board_independence: list[str] = Field(default_factory=list)
    ethics: list[str] = Field(default_factory=list)
    compliance: list[str] = Field(default_factory=list)
    anti_corruption: list[str] = Field(default_factory=list)
    risk_management: list[str] = Field(default_factory=list)


class ConfidenceBreakdown(BaseModel):
    """Documented, deterministic confidence methodology -- never a number
    requested directly from the LLM. Weights live in
    app.core.config.AnalyzerConfidenceWeights."""

    model_config = ConfigDict(protected_namespaces=())

    source_coverage: float = Field(ge=0.0, le=1.0)
    extraction_completeness: float = Field(ge=0.0, le=1.0)
    structured_field_availability: float = Field(ge=0.0, le=1.0)
    model_response_validity: float = Field(ge=0.0, le=1.0)
    parsing_quality: float = Field(ge=0.0, le=1.0)


class AnalyzerResult(BaseModel):
    document_id: str = Field(min_length=1)
    company_name: str = NOT_FOUND
    reporting_year: int | None = None
    industry: str = NOT_FOUND
    report_type: str = NOT_FOUND

    executive_summary: str = NOT_FOUND

    environment: EnvironmentAnalysis = Field(default_factory=EnvironmentAnalysis)
    social: SocialAnalysis = Field(default_factory=SocialAnalysis)
    governance: GovernanceAnalysis = Field(default_factory=GovernanceAnalysis)

    claims: list[AnalyzerClaim] = Field(default_factory=list)
    metrics: list[AnalyzerMetric] = Field(default_factory=list)
    targets: list[AnalyzerTarget] = Field(default_factory=list)
    commitments: list[AnalyzerCommitment] = Field(default_factory=list)
    risks: list[AnalyzerRisk] = Field(default_factory=list)
    opportunities: list[AnalyzerOpportunity] = Field(default_factory=list)
    costing_summary: list[CostingEntry] = Field(default_factory=list)

    confidence: float = Field(ge=0.0, le=1.0)
    confidence_breakdown: ConfidenceBreakdown | None = None
    source_references: list[SourceReference] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
