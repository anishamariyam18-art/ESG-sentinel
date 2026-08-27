from app.models.trust import TrustRating, TrustScoreComponents, TrustScoreStatistics
from app.trust_score.explainability import build_explanation, build_limitations, build_strengths, build_weaknesses
from tests.unit.trust_score.conftest import trust_score_config


def _stats(**overrides):
    fields = dict(
        total_claims=100, verified_claims=90, partially_verified_claims=5, unsupported_claims=5,
        high_greenwashing_claims=0, medium_greenwashing_claims=2, low_greenwashing_claims=98,
        evidence_coverage=92.0, verification_coverage=100.0, provenance_coverage=88.0,
    )
    fields.update(overrides)
    return TrustScoreStatistics(**fields)


def _components(**overrides):
    fields = dict(claim_support=85.0, evidence_quality=88.0, consistency=90.0, transparency=80.0, greenwashing_risk=92.0, provenance=85.0)
    fields.update(overrides)
    return TrustScoreComponents(**fields)


# --- 21: Explanation matches actual statistics ----------------------------

def test_21_explanation_mentions_exact_verified_partial_unsupported_counts():
    stats = _stats(total_claims=100, verified_claims=90, partially_verified_claims=5, unsupported_claims=5)
    lines = build_explanation(stats, _components(), TrustRating.EXCELLENT)
    joined = " ".join(lines)
    assert "90" in joined and "verified" in joined.lower()
    assert "5" in joined
    assert "partially verified" in joined.lower()
    assert "unsupported" in joined.lower()


def test_explanation_empty_claims_says_so_and_does_not_crash():
    stats = _stats(total_claims=0, verified_claims=0, partially_verified_claims=0, unsupported_claims=0,
                    high_greenwashing_claims=0, medium_greenwashing_claims=0, low_greenwashing_claims=0,
                    evidence_coverage=0, verification_coverage=0, provenance_coverage=0)
    lines = build_explanation(stats, _components(claim_support=0, evidence_quality=0, consistency=0, transparency=0, greenwashing_risk=0, provenance=0), TrustRating.LOW)
    assert lines
    assert "no esg claims" in lines[0].lower()


def test_explanation_mentions_high_greenwashing_when_present():
    stats = _stats(high_greenwashing_claims=3)
    lines = build_explanation(stats, _components(), TrustRating.MODERATE)
    joined = " ".join(lines)
    assert "3" in joined and "high" in joined.lower()


# --- 22: Strengths from actual metrics -------------------------------------

def test_22_strengths_reflect_high_verification_rate():
    stats = _stats(total_claims=100, verified_claims=95)
    strengths = build_strengths(stats, _components(consistency=90))
    assert any("95" in s or "verified" in s.lower() for s in strengths)


def test_strengths_are_empty_when_nothing_is_strong():
    stats = _stats(
        total_claims=100, verified_claims=10, partially_verified_claims=10, unsupported_claims=80,
        high_greenwashing_claims=20, medium_greenwashing_claims=30, low_greenwashing_claims=50,
        evidence_coverage=20.0, verification_coverage=100.0, provenance_coverage=15.0,
    )
    strengths = build_strengths(stats, _components(consistency=30, transparency=20))
    assert strengths == []


# --- 23: Weaknesses from actual metrics -------------------------------------

def test_23_weaknesses_reflect_high_unsupported_rate():
    stats = _stats(total_claims=100, verified_claims=40, partially_verified_claims=20, unsupported_claims=40)
    weaknesses = build_weaknesses(stats, _components(consistency=90, transparency=90))
    assert any("40" in w and "unsupported" in w.lower() for w in weaknesses)


def test_weaknesses_flag_high_greenwashing_claims():
    stats = _stats(high_greenwashing_claims=5)
    weaknesses = build_weaknesses(stats, _components())
    assert any("5" in w and "high" in w.lower() for w in weaknesses)


def test_weaknesses_are_empty_when_there_are_no_claims():
    """A component's arithmetic default (0.0 for an unmeasured signal)
    must never be reported as a discovered weakness."""
    stats = _stats(total_claims=0, verified_claims=0, partially_verified_claims=0, unsupported_claims=0,
                    high_greenwashing_claims=0, medium_greenwashing_claims=0, low_greenwashing_claims=0,
                    evidence_coverage=0.0, verification_coverage=0.0, provenance_coverage=0.0)
    weaknesses = build_weaknesses(stats, _components(claim_support=0, evidence_quality=0, consistency=0, transparency=0, greenwashing_risk=0, provenance=0))
    assert weaknesses == []


def test_weaknesses_are_empty_when_nothing_is_weak():
    stats = _stats(
        total_claims=100, verified_claims=95, partially_verified_claims=5, unsupported_claims=0,
        high_greenwashing_claims=0, medium_greenwashing_claims=0, low_greenwashing_claims=100,
        evidence_coverage=98.0, verification_coverage=100.0, provenance_coverage=95.0,
    )
    weaknesses = build_weaknesses(stats, _components(consistency=95, transparency=95))
    assert weaknesses == []


# --- 24: Limitations from actual missing data -------------------------------

def test_24_limitations_flag_small_sample():
    stats = _stats(total_claims=3, verified_claims=3, partially_verified_claims=0, unsupported_claims=0,
                    evidence_coverage=100.0, verification_coverage=100.0, provenance_coverage=100.0)
    limitations = build_limitations(stats, trust_score_config(min_claims_for_full_confidence=30))
    assert any("3" in l and ("claim" in l.lower()) for l in limitations)


def test_limitations_never_assert_fraud_or_deception():
    stats = _stats(total_claims=100, verified_claims=10, partially_verified_claims=10, unsupported_claims=80)
    limitations = build_limitations(stats, trust_score_config())
    joined = " ".join(limitations).lower()
    assert "fraud" not in joined or "not a finding of fraud" in joined
    assert "deceiv" not in joined or "not" in joined


def test_limitations_flag_incomplete_evidence_and_provenance_coverage():
    stats = _stats(evidence_coverage=60.0, provenance_coverage=50.0)
    limitations = build_limitations(stats, trust_score_config())
    joined = " ".join(limitations).lower()
    assert "evidence" in joined
    assert "provenance" in joined
