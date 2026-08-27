from __future__ import annotations

from app.core.config import (
    GreenwashingAggregationConfig,
    GreenwashingConfidenceWeights,
    GreenwashingThresholds,
    GreenwashingWeights,
    VerificationThresholds,
)
from app.models.claim import Claim, ClaimCategory, ClaimType
from app.models.evidence import EvidenceMatch, SourceType
from app.models.verification import VerificationChecks, VerificationResult, VerificationStatus

# Reuse the generic scripted-LLM test double already built for analyzer tests.
from tests.unit.analyzer.conftest import ScriptedLLMProvider, make_manager  # noqa: F401


def greenwashing_weights(**overrides) -> GreenwashingWeights:
    fields = dict(
        lack_of_evidence_support=0.20, numerical_inconsistency=0.20, contradiction=0.20,
        vagueness=0.05, absolute_language=0.10, unsupported_benefit=0.08,
        missing_qualification=0.07, misleading_comparison=0.05, weak_provenance=0.05,
    )
    fields.update(overrides)
    return GreenwashingWeights(_env_file=None, **fields)


def greenwashing_confidence_weights(**overrides) -> GreenwashingConfidenceWeights:
    fields = dict(provenance_reliability=0.35, evidence_reliability=0.35, llm_reliability=0.30)
    fields.update(overrides)
    return GreenwashingConfidenceWeights(_env_file=None, **fields)


def greenwashing_thresholds(**overrides) -> GreenwashingThresholds:
    fields = dict(high_risk_min=60.0, medium_risk_min=30.0)
    fields.update(overrides)
    return GreenwashingThresholds(_env_file=None, **fields)


def greenwashing_aggregation(**overrides) -> GreenwashingAggregationConfig:
    fields = dict(max_high_risk_bonus=10.0, high_risk_bonus_scale=25.0, neutral_importance_weight=0.5, max_schema_retries=0)
    fields.update(overrides)
    return GreenwashingAggregationConfig(_env_file=None, **fields)


def verification_thresholds(**overrides) -> VerificationThresholds:
    fields = dict(verified_score_min=80.0, partially_verified_score_min=60.0, numerical_tolerance_pct=2.0)
    fields.update(overrides)
    return VerificationThresholds(_env_file=None, **fields)


def build_claim(
    *, claim_id: str = "CLM-000001", document_id: str = "DOC-001", company: str = "Example Company",
    report_year: int = 2025, page_number: int = 1, section: str | None = "Environmental > Climate",
    source_chunk_id: str = "CHK-00001", claim: str = "Scope 1 emissions decreased by 20% in 2025.",
    category: ClaimCategory = ClaimCategory.ENVIRONMENTAL, claim_type: ClaimType = ClaimType.PERFORMANCE,
    value: float | None = 20.0, unit: str | None = "%", target_year: int | None = None,
    confidence: float = 0.9,
) -> Claim:
    return Claim(
        claim_id=claim_id, document_id=document_id, company=company, report_year=report_year,
        page_number=page_number, section=section, source_chunk_id=source_chunk_id, claim=claim,
        category=category, claim_type=claim_type, value=value, unit=unit, target_year=target_year,
        confidence=confidence,
    )


def build_evidence_match(
    *, evidence_id: str = "EVD-000001", document_id: str | None = "DOC-001", company: str = "Example Company",
    report_year: int | None = 2025, page_number: int | None = 1, source_chunk_id: str | None = "CHK-00001",
    evidence_text: str = "Scope 1 emissions decreased by 20% in 2025.", source_type: SourceType = SourceType.UPLOADED_REPORT,
    quality_score: float = 0.9, semantic_score: float = 0.9, lexical_score: float = 0.8,
) -> EvidenceMatch:
    return EvidenceMatch(
        evidence_id=evidence_id, source_type=source_type, company=company, document_id=document_id,
        report_year=report_year, page_number=page_number, source_chunk_id=source_chunk_id,
        evidence_text=evidence_text, quality_score=quality_score, semantic_score=semantic_score,
        lexical_score=lexical_score,
    )


def build_verification_result(
    *, claim_id: str = "CLM-000001", status: VerificationStatus = VerificationStatus.VERIFIED,
    verification_score: float = 90.0, confidence_score: float = 85.0, matched_evidence: list | None = None,
) -> VerificationResult:
    return VerificationResult(
        claim_id=claim_id, status=status, verification_score=verification_score,
        confidence_score=confidence_score, matched_evidence=matched_evidence or [],
        checks=VerificationChecks(),
    )
