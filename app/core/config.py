"""Central configuration for ESG Sentinel AI Services.

All tunables (model names, thresholds, scoring weights) live here so that
every module reads from one documented source instead of hardcoding values.
Nothing here fabricates behavior -- values are defaults that later phases
are expected to override via environment variables as they are evaluated.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class RetrievalConfig(BaseSettings):
    """Hybrid retrieval tuning. Documented here, overridable via env vars
    prefixed RETRIEVAL__ (e.g. RETRIEVAL__TOP_K=10)."""

    model_config = SettingsConfigDict(env_prefix="RETRIEVAL__", extra="ignore")

    top_k: int = Field(default=5, ge=1, description="Evidence records returned per claim")
    lexical_weight: float = Field(default=0.4, ge=0.0, le=1.0)
    semantic_weight: float = Field(default=0.6, ge=0.0, le=1.0)
    rerank_enabled: bool = True
    min_final_score: float = Field(
        default=0.0, ge=0.0, description="Below this, an evidence match is discarded"
    )


class EvidenceConfig(BaseSettings):
    """Evidence extraction/indexing tuning (Phase 5). Documented here,
    overridable via env vars prefixed EVIDENCE__."""

    model_config = SettingsConfigDict(env_prefix="EVIDENCE__", extra="ignore")

    corroboration_similarity_threshold: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Minimum retrieval score for a non-source chunk to be added as "
        "additional (corroborating) evidence for a claim",
    )
    max_corroborating_chunks_per_claim: int = Field(
        default=2, ge=0, description="Cap on extra evidence chunks beyond the claim's own source chunk"
    )
    default_top_k: int = Field(default=10, gt=0, description="Default EvidenceRetriever.search() top_k")
    min_evidence_text_length: int = Field(
        default=10, gt=0, description="Evidence text shorter than this is rejected as not meaningfully useful"
    )
    storage_filename: str = Field(default="evidence_store.json")


class ChunkingConfig(BaseSettings):
    """Section/paragraph/page-aware chunking tuning. Documented here,
    overridable via env vars prefixed CHUNKING__ (e.g. CHUNKING__TARGET_CHUNK_CHARS=800)."""

    model_config = SettingsConfigDict(env_prefix="CHUNKING__", extra="ignore")

    target_chunk_chars: int = Field(
        default=1000, gt=0, description="Preferred chunk size; paragraphs are merged up to this"
    )
    max_chunk_chars: int = Field(
        default=1600, gt=0, description="Hard ceiling; oversized paragraphs are split at this size"
    )
    min_chunk_chars: int = Field(
        default=150, ge=0, description="Trailing remainder below this is merged into the prior chunk"
    )

    @field_validator("max_chunk_chars")
    @classmethod
    def validate_max_gte_target(cls, v: int, info) -> int:
        target = info.data.get("target_chunk_chars")
        if target is not None and v < target:
            raise ValueError("max_chunk_chars must be >= target_chunk_chars")
        return v


class LLMConfig(BaseSettings):
    """LLM call tuning shared by every module that goes through
    `app.core.llm.LLMManager`. Documented here, overridable via env vars
    prefixed LLM__ (e.g. LLM__MAX_RETRIES=3)."""

    model_config = SettingsConfigDict(env_prefix="LLM__", extra="ignore")

    max_retries: int = Field(default=2, ge=0, description="Retries after the first attempt")
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    request_timeout_seconds: int = Field(default=60, gt=0)


class AnalyzerConfig(BaseSettings):
    """Batching tuning for the ESG Analyzer. Documented here, overridable
    via env vars prefixed ANALYZER__ (e.g. ANALYZER__MAX_BATCH_CHARS=8000)."""

    model_config = SettingsConfigDict(env_prefix="ANALYZER__", extra="ignore")

    max_batch_chars: int = Field(
        default=12000, gt=0, description="Character budget for chunk context per LLM batch"
    )
    max_chunks_per_batch: int = Field(default=40, gt=0)
    max_schema_retries: int = Field(
        default=1, ge=0,
        description="Extra full re-generations when JSON is syntactically valid but fails "
        "AnalyzerResult schema validation. Separate from LLMConfig.max_retries (which "
        "covers pure JSON-syntax recovery inside a single generate_json call) so the two "
        "retry budgets don't compound multiplicatively.",
    )


class AnalyzerConfidenceWeights(BaseSettings):
    """Weighting for the analyzer's deterministic confidence score. Must
    sum to 1.0 so component contributions stay interpretable -- never a
    number requested directly from the LLM."""

    model_config = SettingsConfigDict(
        env_prefix="ANALYZER_CONFIDENCE__", extra="ignore", protected_namespaces=()
    )

    source_coverage: float = Field(default=0.25, ge=0.0, le=1.0)
    extraction_completeness: float = Field(default=0.20, ge=0.0, le=1.0)
    structured_field_availability: float = Field(default=0.25, ge=0.0, le=1.0)
    model_response_validity: float = Field(default=0.20, ge=0.0, le=1.0)
    parsing_quality: float = Field(default=0.10, ge=0.0, le=1.0)

    @field_validator("parsing_quality")
    @classmethod
    def validate_weights_sum(cls, v: float, info) -> float:
        values = info.data
        total = (
            values.get("source_coverage", 0)
            + values.get("extraction_completeness", 0)
            + values.get("structured_field_availability", 0)
            + values.get("model_response_validity", 0)
            + v
        )
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"AnalyzerConfidenceWeights must sum to 1.0, got {total:.4f}")
        return v


class ClaimsConfig(BaseSettings):
    """Batching and thresholds for exhaustive ESG claim extraction.
    Documented here, overridable via env vars prefixed CLAIMS__."""

    model_config = SettingsConfigDict(env_prefix="CLAIMS__", extra="ignore")

    max_batch_chars: int = Field(
        default=12000, gt=0, description="Character budget for chunk context per LLM batch"
    )
    max_chunks_per_batch: int = Field(default=40, gt=0)
    max_schema_retries: int = Field(
        default=1, ge=0, description="Extra full re-generations on JSON/schema failure per batch"
    )
    min_claim_length: int = Field(
        default=15, gt=0, description="Candidates shorter than this are rejected as fragments"
    )
    near_duplicate_similarity_threshold: float = Field(
        default=0.85, ge=0.0, le=1.0,
        description="Normalized-text similarity ratio above which two claims with compatible "
        "metric/value/unit/year metadata are treated as near-duplicates",
    )
    max_classification_batch_size: int = Field(
        default=25, gt=0, description="Ambiguous claims sent to the LLM classifier per call"
    )


class ClaimConfidenceWeights(BaseSettings):
    """Weighting for the deterministic claim confidence score. Must sum to
    1.0. An LLM-reported classification confidence is only ONE input signal
    here (classification_certainty) -- never used directly as the claim's
    confidence."""

    model_config = SettingsConfigDict(
        env_prefix="CLAIM_CONFIDENCE__", extra="ignore", protected_namespaces=()
    )

    esg_relevance: float = Field(default=0.20, ge=0.0, le=1.0)
    provenance_completeness: float = Field(default=0.20, ge=0.0, le=1.0)
    classification_certainty: float = Field(default=0.25, ge=0.0, le=1.0)
    numerical_clarity: float = Field(default=0.20, ge=0.0, le=1.0)
    claim_completeness: float = Field(default=0.15, ge=0.0, le=1.0)

    @field_validator("claim_completeness")
    @classmethod
    def validate_weights_sum(cls, v: float, info) -> float:
        values = info.data
        total = (
            values.get("esg_relevance", 0)
            + values.get("provenance_completeness", 0)
            + values.get("classification_certainty", 0)
            + values.get("numerical_clarity", 0)
            + v
        )
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"ClaimConfidenceWeights must sum to 1.0, got {total:.4f}")
        return v


class VerificationThresholds(BaseSettings):
    """Status thresholds for the verification engine, on the same 0-100
    scale as `VerificationResult.verification_score`. These are starting
    points to be tuned against evaluation data (Phase 13), never tuned
    solely to maximize 'Verified' outcomes. Hard-fail conditions (wrong
    company, explicit contradictions, ...) can still force a lower status
    than the score alone would suggest -- see app.verification.scorer."""

    model_config = SettingsConfigDict(env_prefix="VERIFICATION__", extra="ignore")

    verified_score_min: float = Field(default=80.0, ge=0.0, le=100.0)
    partially_verified_score_min: float = Field(default=60.0, ge=0.0, le=100.0)
    numerical_tolerance_pct: float = Field(
        default=2.0, ge=0.0, description="Allowed percentage deviation for numeric matches"
    )

    @field_validator("partially_verified_score_min")
    @classmethod
    def validate_thresholds_ordered(cls, v: float, info) -> float:
        verified_min = info.data.get("verified_score_min")
        if verified_min is not None and v > verified_min:
            raise ValueError("partially_verified_score_min must be <= verified_score_min")
        return v


class VerificationWeights(BaseSettings):
    """Weighting for the deterministic verification score (section 17).
    Must sum to 1.0. The LLM's structured judgment contributes only the
    `llm_support` component -- never the whole score."""

    model_config = SettingsConfigDict(env_prefix="VERIFICATION_WEIGHTS__", extra="ignore")

    semantic: float = Field(default=0.15, ge=0.0, le=1.0)
    lexical: float = Field(default=0.10, ge=0.0, le=1.0)
    numeric: float = Field(default=0.20, ge=0.0, le=1.0)
    unit: float = Field(default=0.10, ge=0.0, le=1.0)
    temporal: float = Field(default=0.10, ge=0.0, le=1.0)
    entity: float = Field(default=0.10, ge=0.0, le=1.0)
    category: float = Field(default=0.05, ge=0.0, le=1.0)
    llm_support: float = Field(default=0.15, ge=0.0, le=1.0)
    provenance: float = Field(default=0.05, ge=0.0, le=1.0)

    @field_validator("provenance")
    @classmethod
    def validate_weights_sum(cls, v: float, info) -> float:
        values = info.data
        total = (
            values.get("semantic", 0) + values.get("lexical", 0) + values.get("numeric", 0)
            + values.get("unit", 0) + values.get("temporal", 0) + values.get("entity", 0)
            + values.get("category", 0) + values.get("llm_support", 0) + v
        )
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"VerificationWeights must sum to 1.0, got {total:.4f}")
        return v


class VerificationConfidenceWeights(BaseSettings):
    """Weighting for the verification *confidence* score -- "how reliable
    is this decision?", deliberately separate from verification_score
    ("how strongly is the claim supported?"). Must sum to 1.0."""

    model_config = SettingsConfigDict(env_prefix="VERIFICATION_CONFIDENCE__", extra="ignore")

    provenance_quality: float = Field(default=0.30, ge=0.0, le=1.0)
    signal_agreement: float = Field(default=0.25, ge=0.0, le=1.0)
    llm_reliability: float = Field(default=0.25, ge=0.0, le=1.0)
    low_ambiguity: float = Field(default=0.20, ge=0.0, le=1.0)

    @field_validator("low_ambiguity")
    @classmethod
    def validate_weights_sum(cls, v: float, info) -> float:
        values = info.data
        total = values.get("provenance_quality", 0) + values.get("signal_agreement", 0) + values.get("llm_reliability", 0) + v
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"VerificationConfidenceWeights must sum to 1.0, got {total:.4f}")
        return v


class EvidencePolicy(str, Enum):
    """Which document(s) a claim's evidence retrieval is allowed to draw
    from (Phase 10 section 26 -- data leakage protection).

    INCLUDE_CURRENT_DOCUMENT: search the claim's own uploaded report
    together with any other ingested evidence (external reports, etc). This
    is this project's default: Phase 5's Layer-1 evidence extraction exists
    specifically so a claim can be checked against the detailed supporting
    passage elsewhere in the SAME report (e.g. a summary claim vs. the
    underlying table) -- that is the primary verification target this
    pipeline was designed and tested around, not a leakage artifact.

    EXTERNAL_EVIDENCE_ONLY: excludes the claim's own document_id from
    retrieval entirely, so verification can only draw on independently
    ingested evidence from OTHER documents. Use this for genuine
    cross-report corroboration analysis or evaluation, where retrieving the
    original claim's own source text back at itself would trivially and
    artificially inflate verification performance."""

    INCLUDE_CURRENT_DOCUMENT = "include_current_document"
    EXTERNAL_EVIDENCE_ONLY = "external_evidence_only"


class VerificationConfig(BaseSettings):
    """Retrieval/reranking/LLM-judgment tuning for the verification engine.
    Documented here, overridable via env vars prefixed VERIFICATION_ENGINE__."""

    model_config = SettingsConfigDict(env_prefix="VERIFICATION_ENGINE__", extra="ignore")

    candidates_per_claim: int = Field(
        default=5, gt=0, description="Evidence candidates retrieved per claim before reranking"
    )
    max_llm_judgment_candidates: int = Field(
        default=3, gt=0, description="Top-ranked candidates actually sent to the LLM for judgment"
    )
    uploaded_report_priority_bonus: float = Field(
        default=0.05, ge=0.0, le=1.0,
        description="Small reranking bonus for source_type=uploaded_report (section 20)",
    )
    max_schema_retries: int = Field(default=1, ge=0)
    default_evidence_policy: EvidencePolicy = EvidencePolicy.INCLUDE_CURRENT_DOCUMENT


class GreenwashingThresholds(BaseSettings):
    """Risk-level cutoffs for greenwashing_score, on the same 0-100 scale
    as the score itself (section 17). A hard-signal combination (explicit
    contradiction, an absolute claim actively contradicted by evidence)
    can still force High regardless of where the score alone would land --
    see app.greenwashing.scorer."""

    model_config = SettingsConfigDict(env_prefix="GREENWASHING__", extra="ignore")

    high_risk_min: float = Field(default=60.0, ge=0.0, le=100.0)
    medium_risk_min: float = Field(default=30.0, ge=0.0, le=100.0)

    @field_validator("medium_risk_min")
    @classmethod
    def validate_thresholds_ordered(cls, v: float, info) -> float:
        high_min = info.data.get("high_risk_min")
        if high_min is not None and v > high_min:
            raise ValueError("medium_risk_min must be <= high_risk_min")
        return v


class GreenwashingWeights(BaseSettings):
    """Weighting for the deterministic greenwashing score (section 16).
    Must sum to 1.0. `lack_of_evidence_support`/`weak_provenance` are the
    *inverse* of the corresponding GreenwashingFeatures values (their
    absence is what increases risk); the rest apply directly. Per section
    16: contradiction and numerical mismatch carry the largest weights
    ("should strongly increase risk"), vagueness the smallest ("should have
    a smaller effect")."""

    model_config = SettingsConfigDict(env_prefix="GREENWASHING_WEIGHTS__", extra="ignore")

    lack_of_evidence_support: float = Field(default=0.20, ge=0.0, le=1.0)
    numerical_inconsistency: float = Field(default=0.20, ge=0.0, le=1.0)
    contradiction: float = Field(default=0.20, ge=0.0, le=1.0)
    vagueness: float = Field(default=0.05, ge=0.0, le=1.0)
    absolute_language: float = Field(default=0.10, ge=0.0, le=1.0)
    unsupported_benefit: float = Field(default=0.08, ge=0.0, le=1.0)
    missing_qualification: float = Field(default=0.07, ge=0.0, le=1.0)
    misleading_comparison: float = Field(default=0.05, ge=0.0, le=1.0)
    weak_provenance: float = Field(default=0.05, ge=0.0, le=1.0)

    @field_validator("weak_provenance")
    @classmethod
    def validate_weights_sum(cls, v: float, info) -> float:
        values = info.data
        total = (
            values.get("lack_of_evidence_support", 0) + values.get("numerical_inconsistency", 0)
            + values.get("contradiction", 0) + values.get("vagueness", 0)
            + values.get("absolute_language", 0) + values.get("unsupported_benefit", 0)
            + values.get("missing_qualification", 0) + values.get("misleading_comparison", 0) + v
        )
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"GreenwashingWeights must sum to 1.0, got {total:.4f}")
        return v


class GreenwashingConfidenceWeights(BaseSettings):
    """Weighting for the greenwashing *confidence* score -- "how reliable
    is this determination?", separate from greenwashing_score itself. Must
    sum to 1.0."""

    model_config = SettingsConfigDict(env_prefix="GREENWASHING_CONFIDENCE__", extra="ignore")

    provenance_reliability: float = Field(default=0.35, ge=0.0, le=1.0)
    evidence_reliability: float = Field(default=0.35, ge=0.0, le=1.0)
    llm_reliability: float = Field(default=0.30, ge=0.0, le=1.0)

    @field_validator("llm_reliability")
    @classmethod
    def validate_weights_sum(cls, v: float, info) -> float:
        values = info.data
        total = values.get("provenance_reliability", 0) + values.get("evidence_reliability", 0) + v
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"GreenwashingConfidenceWeights must sum to 1.0, got {total:.4f}")
        return v


class GreenwashingAggregationConfig(BaseSettings):
    """Report-level aggregation tuning (section 26): claim importance is
    used to weight the importance-weighted average so one trivial claim
    can't dominate the report; a small, capped bonus based on the fraction
    of high-risk claims keeps a report with many high-risk claims from
    being diluted down by many low-risk ones."""

    model_config = SettingsConfigDict(env_prefix="GREENWASHING_AGGREGATION__", extra="ignore")

    max_high_risk_bonus: float = Field(default=10.0, ge=0.0, le=100.0)
    high_risk_bonus_scale: float = Field(default=25.0, ge=0.0)
    neutral_importance_weight: float = Field(default=0.5, gt=0.0, le=1.0)
    max_schema_retries: int = Field(default=1, ge=0)


class TrustScoreWeights(BaseSettings):
    """Weighting for the 6 deterministic Trust Score components (Phase 8
    section 11) -- claim support, evidence quality, consistency,
    transparency, greenwashing risk, provenance. Must sum to 1.0 so
    component contributions stay interpretable. These are starting weights
    only, per the spec -- never scattered as bare numbers throughout
    app/trust_score/."""

    model_config = SettingsConfigDict(env_prefix="TRUST_WEIGHTS__", extra="ignore")

    claim_support: float = Field(default=0.30, ge=0.0, le=1.0)
    evidence_quality: float = Field(default=0.20, ge=0.0, le=1.0)
    consistency: float = Field(default=0.15, ge=0.0, le=1.0)
    transparency: float = Field(default=0.15, ge=0.0, le=1.0)
    greenwashing_risk: float = Field(default=0.15, ge=0.0, le=1.0)
    provenance: float = Field(default=0.05, ge=0.0, le=1.0)

    @field_validator("provenance")
    @classmethod
    def validate_weights_sum(cls, v: float, info) -> float:
        values = info.data
        total = (
            values.get("claim_support", 0)
            + values.get("evidence_quality", 0)
            + values.get("consistency", 0)
            + values.get("transparency", 0)
            + values.get("greenwashing_risk", 0)
            + v
        )
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"TrustScoreWeights must sum to 1.0, got {total:.4f}")
        return v


class TrustRatingThresholds(BaseSettings):
    """Configurable rating-label cutoffs (section 3), on the same 0-100
    scale as `trust_score`. Descriptive mapping from the spec: >=excellent_min
    ("100: very strong" / "80-99: strong"), >=good_min ("60-79: moderate
    trust"), >=moderate_min ("40-59: low/moderate trust"), below
    moderate_min ("0-39: low trust")."""

    model_config = SettingsConfigDict(env_prefix="TRUST_RATING__", extra="ignore")

    excellent_min: float = Field(default=80.0, ge=0.0, le=100.0)
    good_min: float = Field(default=60.0, ge=0.0, le=100.0)
    moderate_min: float = Field(default=40.0, ge=0.0, le=100.0)

    @field_validator("moderate_min")
    @classmethod
    def validate_thresholds_ordered(cls, v: float, info) -> float:
        excellent_min = info.data.get("excellent_min")
        good_min = info.data.get("good_min")
        if excellent_min is not None and good_min is not None and not (excellent_min >= good_min >= v):
            raise ValueError("TrustRatingThresholds must satisfy excellent_min >= good_min >= moderate_min")
        return v


class TrustScoreConfig(BaseSettings):
    """Non-weight Trust Score tuning (section 28: "do not scatter numeric
    weights/constants throughout the code"). `*_credit` values are the
    per-claim contribution (0.0-1.0) each verification status earns toward
    `claim_support` (section 5). The greenwashing-component penalty scales
    implement section 9's "documented aggregation formula, not a simple
    100 - greenwashing_score subtraction". `min_claims_for_full_confidence`
    is the sample-size scale used by `confidence` (section 14) -- a report
    with at least this many claims gets full sample-size credit; fewer
    claims scale confidence down proportionally, never the trust_score
    itself (section 15: score and confidence are always separate)."""

    model_config = SettingsConfigDict(env_prefix="TRUST_SCORE__", extra="ignore")

    verified_credit: float = Field(default=1.0, ge=0.0, le=1.0)
    partially_verified_credit: float = Field(default=0.5, ge=0.0, le=1.0)
    unsupported_credit: float = Field(default=0.0, ge=0.0, le=1.0)

    no_greenwashing_data_default: float = Field(
        default=70.0, ge=0.0, le=100.0,
        description="greenwashing_risk component when no GreenwashingResult was supplied at all -- a documented neutral default, never fabricated as 'no risk'.",
    )
    high_risk_penalty_scale: float = Field(default=40.0, ge=0.0)
    medium_risk_penalty_scale: float = Field(default=15.0, ge=0.0)
    max_greenwashing_penalty: float = Field(default=50.0, ge=0.0, le=100.0)

    min_claims_for_full_confidence: int = Field(default=30, ge=1)

    enable_llm_narrative: bool = True
    max_schema_retries: int = Field(default=1, ge=0)


class RecommendationPriorityWeights(BaseSettings):
    """Weighting for the deterministic recommendation priority score
    (section 8). Must sum to 1.0. The LLM is never consulted for this
    score (section 23: "LLM must not change priority scores")."""

    model_config = SettingsConfigDict(env_prefix="RECOMMENDATION_PRIORITY__", extra="ignore")

    severity: float = Field(default=0.30, ge=0.0, le=1.0)
    affected_claims: float = Field(default=0.20, ge=0.0, le=1.0)
    verification_impact: float = Field(default=0.15, ge=0.0, le=1.0)
    greenwashing_risk: float = Field(default=0.15, ge=0.0, le=1.0)
    trust_impact: float = Field(default=0.10, ge=0.0, le=1.0)
    claim_importance: float = Field(default=0.10, ge=0.0, le=1.0)

    @field_validator("claim_importance")
    @classmethod
    def validate_weights_sum(cls, v: float, info) -> float:
        values = info.data
        total = (
            values.get("severity", 0) + values.get("affected_claims", 0) + values.get("verification_impact", 0)
            + values.get("greenwashing_risk", 0) + values.get("trust_impact", 0) + v
        )
        if not (0.99 <= total <= 1.01):
            raise ValueError(f"RecommendationPriorityWeights must sum to 1.0, got {total:.4f}")
        return v


class RecommendationThresholds(BaseSettings):
    """Priority-level cutoffs for `priority_score`, on the same 0-100 scale
    as the score itself (section 7)."""

    model_config = SettingsConfigDict(env_prefix="RECOMMENDATION_THRESHOLDS__", extra="ignore")

    high_priority_min: float = Field(default=70.0, ge=0.0, le=100.0)
    medium_priority_min: float = Field(default=40.0, ge=0.0, le=100.0)

    @field_validator("medium_priority_min")
    @classmethod
    def validate_thresholds_ordered(cls, v: float, info) -> float:
        high_min = info.data.get("high_priority_min")
        if high_min is not None and v > high_min:
            raise ValueError("RecommendationThresholds must satisfy high_priority_min >= medium_priority_min")
        return v


class RecommendationConfig(BaseSettings):
    """Non-weight recommendation-engine tuning (section 29: "these limits
    must be configurable"). `weak_component_threshold` is the Trust Score
    component cutoff (0-100) below which a component-improvement
    recommendation is generated (section 13). `numerical_mismatch_threshold`
    is the `VerificationChecks.numeric` cutoff (0-1, lower means a bigger
    mismatch) below which a numerical-mismatch finding fires --
    `unit`/`temporal` checks only ever degrade below 1.0 on an actual
    incompatibility (Phase 6), so those two are compared directly against
    1.0 rather than needing their own configurable threshold."""

    model_config = SettingsConfigDict(env_prefix="RECOMMENDATIONS__", extra="ignore")

    max_recommendations: int = Field(default=10, ge=1)
    max_priority_actions: int = Field(default=5, ge=1)
    max_source_findings_per_recommendation: int = Field(default=5, ge=1)

    numerical_mismatch_threshold: float = Field(default=0.8, ge=0.0, le=1.0)
    provenance_completeness_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    weak_component_threshold: float = Field(default=60.0, ge=0.0, le=100.0)
    low_evidence_coverage_threshold: float = Field(default=70.0, ge=0.0, le=100.0)
    affected_claims_full_credit: int = Field(
        default=10, ge=1, description="Number of affected claims at which the priority score's affected-claims factor reaches full (1.0) credit.",
    )

    enable_llm_synthesis: bool = True
    max_schema_retries: int = Field(default=1, ge=0)


class Settings(BaseSettings):
    """Top-level application settings, loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Environment ---
    environment: Literal["development", "test", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # --- LLM provider (Gemini) ---
    gemini_api_key: SecretStr | None = None
    gemini_model_name: str = "gemini-3.6-flash"

    # --- Embedding / reranking models ---
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    cross_encoder_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    # --- Upload handling ---
    upload_dir: Path = PROJECT_ROOT / "uploads"
    max_upload_size_mb: int = Field(default=25, gt=0)
    allowed_upload_extensions: tuple[str, ...] = (".pdf",)

    # --- Data directories ---
    data_dir: Path = PROJECT_ROOT / "data"
    reports_dir: Path = PROJECT_ROOT / "data" / "reports"
    evidence_dir: Path = PROJECT_ROOT / "data" / "evidence"
    processed_dir: Path = PROJECT_ROOT / "data" / "processed"
    indexes_dir: Path = PROJECT_ROOT / "data" / "indexes"
    evaluation_dir: Path = PROJECT_ROOT / "data" / "evaluation"
    outputs_dir: Path = PROJECT_ROOT / "data" / "outputs"

    # --- Sub-configs (documented, independently overridable) ---
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = Field(default_factory=RetrievalConfig)
    verification_thresholds: VerificationThresholds = Field(
        default_factory=VerificationThresholds
    )
    llm: LLMConfig = Field(default_factory=LLMConfig)
    analyzer: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    analyzer_confidence_weights: AnalyzerConfidenceWeights = Field(
        default_factory=AnalyzerConfidenceWeights
    )
    claims: ClaimsConfig = Field(default_factory=ClaimsConfig)
    claim_confidence_weights: ClaimConfidenceWeights = Field(default_factory=ClaimConfidenceWeights)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)
    verification_weights: VerificationWeights = Field(default_factory=VerificationWeights)
    verification_confidence_weights: VerificationConfidenceWeights = Field(
        default_factory=VerificationConfidenceWeights
    )
    greenwashing_thresholds: GreenwashingThresholds = Field(default_factory=GreenwashingThresholds)
    greenwashing_weights: GreenwashingWeights = Field(default_factory=GreenwashingWeights)
    greenwashing_confidence_weights: GreenwashingConfidenceWeights = Field(
        default_factory=GreenwashingConfidenceWeights
    )
    greenwashing_aggregation: GreenwashingAggregationConfig = Field(
        default_factory=GreenwashingAggregationConfig
    )
    trust_score_weights: TrustScoreWeights = Field(default_factory=TrustScoreWeights)
    trust_rating_thresholds: TrustRatingThresholds = Field(default_factory=TrustRatingThresholds)
    trust_score_config: TrustScoreConfig = Field(default_factory=TrustScoreConfig)
    recommendation_priority_weights: RecommendationPriorityWeights = Field(default_factory=RecommendationPriorityWeights)
    recommendation_thresholds: RecommendationThresholds = Field(default_factory=RecommendationThresholds)
    recommendation_config: RecommendationConfig = Field(default_factory=RecommendationConfig)


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a process-wide cached Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
