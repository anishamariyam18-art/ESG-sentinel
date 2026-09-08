from __future__ import annotations

from app.core.config import RecommendationConfig, RecommendationPriorityWeights, RecommendationThresholds
from app.models.claim import Claim, ClaimCategory, ClaimType
from app.models.evidence import EvidenceMatch, SourceType
from app.models.greenwashing import GreenwashingFeatures, GreenwashingResult, GreenwashingType, RiskLevel
from app.models.trust import TrustRating, TrustScore, TrustScoreComponents, TrustScoreStatistics
from app.models.verification import VerificationChecks, VerificationResult, VerificationStatus

# Reuse the generic scripted-LLM test double already built for analyzer tests.
from tests.unit.analyzer.conftest import ScriptedLLMProvider, make_manager  # noqa: F401


def recommendation_priority_weights(**overrides) -> RecommendationPriorityWeights:
    fields = dict(severity=0.30, affected_claims=0.20, verification_impact=0.15, greenwashing_risk=0.15, trust_impact=0.10, claim_importance=0.10)
    fields.update(overrides)
    return RecommendationPriorityWeights(_env_file=None, **fields)


def recommendation_thresholds(**overrides) -> RecommendationThresholds:
    fields = dict(high_priority_min=70.0, medium_priority_min=40.0)
    fields.update(overrides)
    return RecommendationThresholds(_env_file=None, **fields)


def recommendation_config(**overrides) -> RecommendationConfig:
    fields = dict(
        max_recommendations=10, max_priority_actions=5, max_source_findings_per_recommendation=5,
        numerical_mismatch_threshold=0.8, provenance_completeness_threshold=0.5, weak_component_threshold=60.0,
        low_evidence_coverage_threshold=70.0, affected_claims_full_credit=10, enable_llm_synthesis=True,
        max_schema_retries=0,
    )
    fields.update(overrides)
    return RecommendationConfig(_env_file=None, **fields)


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
    confidence_score: float = 90.0, explanation: list[str] | None = None,
) -> GreenwashingResult:
    return GreenwashingResult(
        claim_id=claim_id, claim=claim, verification_status=verification_status, greenwashing_risk=greenwashing_risk,
        greenwashing_type=greenwashing_type or [GreenwashingType.NO_SIGNIFICANT_SIGNAL],
        greenwashing_score=greenwashing_score, confidence_score=confidence_score,
        reason="", evidence=[], features=GreenwashingFeatures(
            evidence_support=0.9, provenance_quality=0.9, numerical_consistency=1.0, contradiction=0.0,
            vagueness=0.0, absolute_language=0.0, unsupported_benefit=0.0, missing_qualification=0.0,
            misleading_comparison=0.0,
        ), explanation=explanation or [], recommendation="",
    )


def build_trust_score(
    *, document_id: str = "DOC-001", company: str = "Example Company", trust_score: float = 80.0,
    rating: TrustRating = TrustRating.GOOD, confidence: float = 80.0,
    claim_support: float = 80.0, evidence_quality: float = 80.0, consistency: float = 80.0,
    transparency: float = 80.0, greenwashing_risk: float = 80.0, provenance: float = 80.0,
    total_claims: int = 10, verified_claims: int = 8, partially_verified_claims: int = 1, unsupported_claims: int = 1,
    high_greenwashing_claims: int = 0, medium_greenwashing_claims: int = 0, low_greenwashing_claims: int = 10,
    evidence_coverage: float = 90.0, verification_coverage: float = 100.0, provenance_coverage: float = 90.0,
    strengths: list[str] | None = None, weaknesses: list[str] | None = None, limitations: list[str] | None = None,
) -> TrustScore:
    return TrustScore(
        document_id=document_id, company=company, trust_score=trust_score, rating=rating, confidence=confidence,
        components=TrustScoreComponents(
            claim_support=claim_support, evidence_quality=evidence_quality, consistency=consistency,
            transparency=transparency, greenwashing_risk=greenwashing_risk, provenance=provenance,
        ),
        statistics=TrustScoreStatistics(
            total_claims=total_claims, verified_claims=verified_claims, partially_verified_claims=partially_verified_claims,
            unsupported_claims=unsupported_claims, high_greenwashing_claims=high_greenwashing_claims,
            medium_greenwashing_claims=medium_greenwashing_claims, low_greenwashing_claims=low_greenwashing_claims,
            evidence_coverage=evidence_coverage, verification_coverage=verification_coverage, provenance_coverage=provenance_coverage,
        ),
        explanation=["Sample explanation."], strengths=strengths or [], weaknesses=weaknesses or [],
        limitations=limitations or [],
    )
