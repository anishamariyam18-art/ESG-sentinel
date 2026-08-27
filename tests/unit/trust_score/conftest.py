from __future__ import annotations

from app.core.config import TrustRatingThresholds, TrustScoreConfig, TrustScoreWeights
from app.models.claim import Claim, ClaimCategory, ClaimType
from app.models.evidence import EvidenceMatch, SourceType
from app.models.greenwashing import GreenwashingFeatures, GreenwashingResult, GreenwashingType, RiskLevel
from app.models.verification import VerificationChecks, VerificationResult, VerificationStatus

# Reuse the generic scripted-LLM test double already built for analyzer tests.
from tests.unit.analyzer.conftest import ScriptedLLMProvider, make_manager  # noqa: F401


def trust_weights(**overrides) -> TrustScoreWeights:
    fields = dict(
        claim_support=0.30, evidence_quality=0.20, consistency=0.15,
        transparency=0.15, greenwashing_risk=0.15, provenance=0.05,
    )
    fields.update(overrides)
    return TrustScoreWeights(_env_file=None, **fields)


def trust_rating_thresholds(**overrides) -> TrustRatingThresholds:
    fields = dict(excellent_min=80.0, good_min=60.0, moderate_min=40.0)
    fields.update(overrides)
    return TrustRatingThresholds(_env_file=None, **fields)


def trust_score_config(**overrides) -> TrustScoreConfig:
    fields = dict(
        verified_credit=1.0, partially_verified_credit=0.5, unsupported_credit=0.0,
        no_greenwashing_data_default=70.0, high_risk_penalty_scale=40.0, medium_risk_penalty_scale=15.0,
        max_greenwashing_penalty=50.0, min_claims_for_full_confidence=30, enable_llm_narrative=True,
        max_schema_retries=0,
    )
    fields.update(overrides)
    return TrustScoreConfig(_env_file=None, **fields)


def build_claim(
    *, claim_id: str = "CLM-000001", document_id: str = "DOC-001", company: str = "Example Company",
    report_year: int = 2025, page_number: int = 1, section: str | None = "Environmental > Climate",
    source_chunk_id: str = "CHK-00001", claim: str = "Scope 1 emissions decreased by 20% in 2025.",
    category: ClaimCategory = ClaimCategory.ENVIRONMENTAL, claim_type: ClaimType = ClaimType.PERFORMANCE,
    value: float | None = 20.0, unit: str | None = "%", target: str | None = None, target_year: int | None = None,
    confidence: float = 0.9,
) -> Claim:
    return Claim(
        claim_id=claim_id, document_id=document_id, company=company, report_year=report_year,
        page_number=page_number, section=section, source_chunk_id=source_chunk_id, claim=claim,
        category=category, claim_type=claim_type, value=value, unit=unit, target=target, target_year=target_year,
        confidence=confidence,
    )


def build_evidence_match(
    *, evidence_id: str = "EVD-000001", document_id: str | None = "DOC-001", company: str = "Example Company",
    report_year: int | None = 2025, page_number: int | None = 1, source_chunk_id: str | None = "CHK-00001",
    evidence_text: str = "Scope 1 emissions decreased by 20% in 2025.", source_type: SourceType = SourceType.UPLOADED_REPORT,
    quality_score: float | None = 0.9, semantic_score: float = 0.9, lexical_score: float = 0.8,
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
    checks: VerificationChecks | None = None,
) -> VerificationResult:
    if matched_evidence is None:
        matched_evidence = [build_evidence_match(evidence_id=f"EVD-{claim_id}")]
    return VerificationResult(
        claim_id=claim_id, status=status, verification_score=verification_score,
        confidence_score=confidence_score, matched_evidence=matched_evidence,
        checks=checks or VerificationChecks(numeric=1.0, unit=1.0, temporal=1.0, entity=1.0, category=1.0),
    )


def build_greenwashing_result(
    *, claim_id: str = "CLM-000001", claim: str = "Scope 1 emissions decreased by 20% in 2025.",
    verification_status: VerificationStatus = VerificationStatus.VERIFIED, greenwashing_risk: RiskLevel = RiskLevel.LOW,
    greenwashing_type: list[GreenwashingType] | None = None, greenwashing_score: float = 5.0,
    confidence_score: float = 90.0,
) -> GreenwashingResult:
    return GreenwashingResult(
        claim_id=claim_id, claim=claim, verification_status=verification_status, greenwashing_risk=greenwashing_risk,
        greenwashing_type=greenwashing_type or [GreenwashingType.NO_SIGNIFICANT_SIGNAL],
        greenwashing_score=greenwashing_score, confidence_score=confidence_score,
        reason="", evidence=[], features=GreenwashingFeatures(
            evidence_support=0.9, provenance_quality=0.9, numerical_consistency=1.0, contradiction=0.0,
            vagueness=0.0, absolute_language=0.0, unsupported_benefit=0.0, missing_qualification=0.0,
            misleading_comparison=0.0,
        ), explanation=[], recommendation="",
    )
