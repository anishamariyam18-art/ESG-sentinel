import pytest
from pydantic import ValidationError

from app.models.greenwashing import (
    GreenwashingFeatures,
    GreenwashingReport,
    GreenwashingResult,
    GreenwashingType,
    RiskLevel,
)
from app.models.verification import VerificationStatus


def _features(**overrides) -> GreenwashingFeatures:
    fields = dict(
        evidence_support=0.42, provenance_quality=0.5, numerical_consistency=0.0,
        contradiction=1.0, vagueness=0.3, absolute_language=0.0,
        unsupported_benefit=0.0, missing_qualification=0.0, misleading_comparison=0.0,
    )
    fields.update(overrides)
    return GreenwashingFeatures(**fields)


def test_greenwashing_result_multi_label_type_list():
    result = GreenwashingResult(
        claim_id="CLM-000001", claim="We reduced emissions by 80%.",
        verification_status=VerificationStatus.UNSUPPORTED, greenwashing_risk=RiskLevel.HIGH,
        greenwashing_type=[GreenwashingType.EXAGGERATED_CLAIM, GreenwashingType.ABSOLUTE_CLAIM],
        greenwashing_score=82.0, confidence_score=90.0, features=_features(),
        reason="The claimed reduction exceeds what the evidence supports.",
        explanation=["The claim states an 80% reduction.", "The evidence reports a 20% reduction."],
    )
    assert len(result.greenwashing_type) == 2
    assert GreenwashingType.EXAGGERATED_CLAIM in result.greenwashing_type


def test_supported_claim_gets_no_significant_signal():
    result = GreenwashingResult(
        claim_id="CLM-000001", claim="Scope 1 emissions decreased by 20%.",
        verification_status=VerificationStatus.VERIFIED, greenwashing_risk=RiskLevel.LOW,
        greenwashing_type=[GreenwashingType.NO_SIGNIFICANT_SIGNAL],
        greenwashing_score=5.0, confidence_score=90.0, features=_features(contradiction=0.0),
    )
    assert result.greenwashing_type == [GreenwashingType.NO_SIGNIFICANT_SIGNAL]


def test_greenwashing_score_bounded_zero_to_hundred():
    with pytest.raises(ValidationError):
        GreenwashingResult(
            claim_id="CLM-000001", claim="text", verification_status=VerificationStatus.UNSUPPORTED,
            greenwashing_risk=RiskLevel.LOW, greenwashing_score=150.0, confidence_score=50.0,
            features=_features(),
        )


def test_greenwashing_features_bounded():
    with pytest.raises(ValidationError):
        _features(evidence_support=1.5)


def test_greenwashing_result_rejects_invalid_risk_level():
    with pytest.raises(ValidationError):
        GreenwashingResult(
            claim_id="CLM-000001", claim="text", verification_status=VerificationStatus.UNSUPPORTED,
            greenwashing_risk="Severe", greenwashing_score=50.0, confidence_score=50.0,
            features=_features(),
        )


def test_greenwashing_report_aggregates_claims():
    claim_result = GreenwashingResult(
        claim_id="CLM-000001", claim="text", verification_status=VerificationStatus.VERIFIED,
        greenwashing_risk=RiskLevel.LOW, greenwashing_type=[GreenwashingType.NO_SIGNIFICANT_SIGNAL],
        greenwashing_score=5.0, confidence_score=90.0, features=_features(contradiction=0.0),
    )
    report = GreenwashingReport(
        total_claims=1, low_risk=1, medium_risk=0, high_risk=0,
        overall_risk=RiskLevel.LOW, overall_score=5.0, claims=[claim_result],
    )
    assert report.total_claims == 1
    assert report.claims[0].claim_id == "CLM-000001"
