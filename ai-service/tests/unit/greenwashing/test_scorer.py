from app.greenwashing.detector import run_detectors
from app.greenwashing.scorer import (
    build_features,
    compute_greenwashing_confidence,
    compute_greenwashing_score,
    derive_hard_signals,
    determine_greenwashing_types,
    determine_risk_level,
    estimate_claim_importance,
)
from app.models.claim import ClaimType
from app.models.evidence import EvidenceMatch, SourceType
from app.models.greenwashing import GreenwashingFeatures, GreenwashingType, RiskLevel
from app.models.verification import VerificationStatus
from tests.unit.greenwashing.conftest import (
    build_claim,
    build_evidence_match,
    greenwashing_confidence_weights,
    greenwashing_thresholds,
    greenwashing_weights,
)


def _features(**overrides) -> GreenwashingFeatures:
    fields = dict(
        evidence_support=0.9, provenance_quality=0.9, numerical_consistency=1.0, contradiction=0.0,
        vagueness=0.0, absolute_language=0.0, unsupported_benefit=0.0, missing_qualification=0.0,
        misleading_comparison=0.0,
    )
    fields.update(overrides)
    return GreenwashingFeatures(**fields)


def test_score_is_low_for_clean_features():
    score = compute_greenwashing_score(_features(), greenwashing_weights())
    assert score < 30.0


def test_score_is_high_for_strong_contradiction():
    score = compute_greenwashing_score(
        _features(evidence_support=0.1, numerical_consistency=0.0, contradiction=1.0, provenance_quality=0.1),
        greenwashing_weights(),
    )
    assert score >= 60.0


def test_vague_language_alone_has_smaller_effect_than_contradiction():
    vague_score = compute_greenwashing_score(_features(vagueness=1.0), greenwashing_weights())
    contradiction_score = compute_greenwashing_score(_features(contradiction=1.0), greenwashing_weights())
    assert vague_score < contradiction_score


def test_high_verification_quality_reduces_score():
    high_support = compute_greenwashing_score(_features(evidence_support=0.95), greenwashing_weights())
    low_support = compute_greenwashing_score(_features(evidence_support=0.1), greenwashing_weights())
    assert high_support < low_support


def test_determine_risk_level_thresholds():
    thresholds = greenwashing_thresholds()
    assert determine_risk_level(10.0, [], thresholds) == RiskLevel.LOW
    assert determine_risk_level(45.0, [], thresholds) == RiskLevel.MEDIUM
    assert determine_risk_level(75.0, [], thresholds) == RiskLevel.HIGH


def test_severe_hard_signal_forces_high_even_with_low_score():
    risk = determine_risk_level(10.0, ["explicit_contradiction"], greenwashing_thresholds())
    assert risk == RiskLevel.HIGH


def test_one_weak_signal_does_not_force_high():
    # A single, non-severe detected signal must not, by itself, push risk to High.
    score = compute_greenwashing_score(_features(vagueness=0.6), greenwashing_weights())
    risk = determine_risk_level(score, [], greenwashing_thresholds())
    assert risk != RiskLevel.HIGH


def test_determine_greenwashing_types_no_signal_for_clean_claim():
    claim = build_claim(claim="Scope 1 emissions decreased by 20%.", value=20.0, unit="%")
    evidence = build_evidence_match(evidence_text="Scope 1 emissions decreased by 20%.")
    report = run_detectors(claim, _match_to_evidence(evidence), 2.0)
    types = determine_greenwashing_types(report, VerificationStatus.VERIFIED)
    assert types == [GreenwashingType.NO_SIGNIFICANT_SIGNAL]


def test_determine_greenwashing_types_exaggerated():
    claim = build_claim(claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    evidence = build_evidence_match(evidence_text="Scope 1 emissions decreased by 20%.")
    report = run_detectors(claim, _match_to_evidence(evidence), 2.0)
    types = determine_greenwashing_types(report, VerificationStatus.UNSUPPORTED)
    assert GreenwashingType.EXAGGERATED_CLAIM in types


def test_determine_greenwashing_types_unsupported_adds_unsupported_type():
    claim = build_claim(claim="Scope 1 emissions decreased by 20%.", value=20.0, unit="%")
    report = run_detectors(claim, None, 2.0)
    types = determine_greenwashing_types(report, VerificationStatus.UNSUPPORTED)
    assert GreenwashingType.UNSUPPORTED_ENVIRONMENTAL_CLAIM in types


def test_compute_confidence_lower_when_llm_unavailable():
    with_llm = compute_greenwashing_confidence(_features(), True, greenwashing_confidence_weights())
    without_llm = compute_greenwashing_confidence(_features(), False, greenwashing_confidence_weights())
    assert without_llm < with_llm


def test_estimate_claim_importance_quantitative_metric_is_high():
    claim = build_claim(value=20.0, unit="%")
    importance = estimate_claim_importance(claim, neutral_weight=0.5)
    assert importance > 0.5


def test_estimate_claim_importance_falls_back_to_neutral():
    claim = build_claim(value=None, unit=None, target_year=None, claim_type=ClaimType.GENERAL)
    importance = estimate_claim_importance(claim, neutral_weight=0.5)
    assert importance == 0.5


def test_estimate_claim_importance_commitment_type():
    claim = build_claim(value=None, unit=None, claim_type=ClaimType.COMMITMENT, target_year=2050)
    importance = estimate_claim_importance(claim, neutral_weight=0.5)
    assert importance > 0.5


def _match_to_evidence(match: EvidenceMatch):
    from app.models.evidence import Evidence

    return Evidence(
        evidence_id=match.evidence_id, source_type=match.source_type, company=match.company,
        document_id=match.document_id, report_year=match.report_year, page_number=match.page_number,
        source_chunk_id=match.source_chunk_id, evidence_text=match.evidence_text,
    )
