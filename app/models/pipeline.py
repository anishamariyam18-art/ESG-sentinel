"""End-to-end pipeline result and reproducibility metadata.

`ProcessingMetadata` records exactly what produced a `PipelineResult` --
model names/versions, embedding model, retrieval configuration, thresholds,
and scoring weights actually used -- so a run can be reproduced or audited
later without guessing what configuration was active at the time.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.analyzer import AnalyzerResult
from app.models.claim import Claim
from app.models.greenwashing import GreenwashingResult
from app.models.recommendation import RecommendationResult
from app.models.trust import TrustScore
from app.models.verification import VerificationResult


class ProcessingMetadata(BaseModel):
    document_hash: str = Field(min_length=1)
    processing_timestamp: str = Field(min_length=1, description="ISO-8601 UTC timestamp")
    llm_model_name: str | None = None
    llm_model_version: str | None = None
    embedding_model_name: str | None = None
    cross_encoder_model_name: str | None = None
    retrieval_config: dict = Field(default_factory=dict)
    verification_thresholds: dict = Field(default_factory=dict)
    trust_score_weights: dict = Field(default_factory=dict)


class PipelineResult(BaseModel):
    document_id: str = Field(min_length=1)
    company: str = Field(min_length=1)
    report_year: int = Field(ge=1900, le=2100)

    #: "completed" (every stage ran), "partial" (a later stage failed but
    #: earlier stages' results are still present and usable), or "failed"
    #: (a stage failed before any usable result existed) -- section 17.
    pipeline_status: str = "pending"

    analyzer_result: AnalyzerResult | None = None
    claims: list[Claim] = Field(default_factory=list)
    verification_results: list[VerificationResult] = Field(default_factory=list)
    greenwashing_results: list[GreenwashingResult] = Field(default_factory=list)
    trust_score: TrustScore | None = None
    recommendations: RecommendationResult | None = None

    #: Wall-clock seconds per stage (section 34) -- e.g.
    #: {"extraction": 0.4, "analyzer": 2.1, "claims": 1.8, ...}.
    stage_timings: dict[str, float] = Field(default_factory=dict)

    processing_metadata: ProcessingMetadata | None = None
    errors: list[str] = Field(default_factory=list)
