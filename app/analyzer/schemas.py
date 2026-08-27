"""Analyzer-internal LLM response contracts.

These are intermediate shapes the LLM is asked to fill in -- not the final
cross-module `AnalyzerResult` (app.models.analyzer). Batch extraction and
summary synthesis are separate LLM calls with separate, narrower schemas so
each call only asks the model for what it can actually ground in the text
it was shown.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.analyzer import (
    NOT_FOUND,
    AnalyzerClaim,
    AnalyzerCommitment,
    AnalyzerMetric,
    AnalyzerOpportunity,
    AnalyzerRisk,
    AnalyzerTarget,
    CostingEntry,
)


class BatchExtractionResult(BaseModel):
    """What one batch (a subset of the document's chunks) yields. Multiple
    batches are merged deterministically in app.analyzer.merger -- this
    schema deliberately excludes document-level synthesized text
    (executive_summary, category summaries), which only makes sense once
    all batches are merged."""

    company_name: str = NOT_FOUND
    reporting_year: int | None = None
    industry: str = NOT_FOUND
    report_type: str = NOT_FOUND

    carbon_emissions: list[str] = Field(default_factory=list)
    water_usage: list[str] = Field(default_factory=list)
    renewable_energy: list[str] = Field(default_factory=list)
    waste_management: list[str] = Field(default_factory=list)
    net_zero_commitments: list[str] = Field(default_factory=list)
    biodiversity: list[str] = Field(default_factory=list)
    climate_actions: list[str] = Field(default_factory=list)

    women_employees: list[str] = Field(default_factory=list)
    employee_diversity: list[str] = Field(default_factory=list)
    health_and_safety: list[str] = Field(default_factory=list)
    training: list[str] = Field(default_factory=list)
    csr: list[str] = Field(default_factory=list)
    human_rights: list[str] = Field(default_factory=list)

    board_independence: list[str] = Field(default_factory=list)
    ethics: list[str] = Field(default_factory=list)
    compliance: list[str] = Field(default_factory=list)
    anti_corruption: list[str] = Field(default_factory=list)
    risk_management: list[str] = Field(default_factory=list)

    claims: list[AnalyzerClaim] = Field(default_factory=list)
    metrics: list[AnalyzerMetric] = Field(default_factory=list)
    targets: list[AnalyzerTarget] = Field(default_factory=list)
    commitments: list[AnalyzerCommitment] = Field(default_factory=list)
    risks: list[AnalyzerRisk] = Field(default_factory=list)
    opportunities: list[AnalyzerOpportunity] = Field(default_factory=list)
    costing_summary: list[CostingEntry] = Field(default_factory=list)


class SynthesisResult(BaseModel):
    """Second-stage output: short summaries grounded ONLY in the merged,
    already-extracted structured findings -- not a fresh read of the raw
    document text."""

    executive_summary: str = NOT_FOUND
    environment_summary: str = NOT_FOUND
    social_summary: str = NOT_FOUND
    governance_summary: str = NOT_FOUND
