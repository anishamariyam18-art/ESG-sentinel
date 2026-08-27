from app.models.greenwashing import GreenwashingType, RiskLevel
from app.models.trust import TrustScoreComponents
from app.models.verification import VerificationChecks, VerificationStatus
from app.recommendations.rules import (
    collect_claim_findings,
    rule_low_evidence_coverage,
    rule_missing_metrics,
    rule_missing_provenance,
    rule_missing_target,
    rule_numerical_mismatch,
    rule_partially_verified_claim,
    rule_target_year_mismatch,
    rule_unit_mismatch,
    rule_unsupported_claim,
    rule_weak_trust_components,
    rules_from_greenwashing,
)
from tests.unit.recommendations.conftest import (
    build_claim,
    build_evidence_match,
    build_greenwashing_result,
    build_trust_score,
    build_verification_result,
    recommendation_config,
)

_TRUST_COMPONENTS = TrustScoreComponents(claim_support=80, evidence_quality=80, consistency=80, transparency=80, greenwashing_risk=80, provenance=80)


# --- 1: Unsupported claim ---------------------------------------------------

def test_1_unsupported_claim_generates_finding():
    claim = build_claim()
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED)
    finding = rule_unsupported_claim(claim, vr, _TRUST_COMPONENTS)
    assert finding is not None
    assert finding.finding_type == "unsupported_claim"
    assert finding.claim_id == claim.claim_id


def test_unsupported_claim_rule_does_not_fire_for_verified():
    claim = build_claim()
    vr = build_verification_result(status=VerificationStatus.VERIFIED)
    assert rule_unsupported_claim(claim, vr, _TRUST_COMPONENTS) is None


def test_unsupported_claim_rule_does_not_fire_without_verification_result():
    claim = build_claim()
    assert rule_unsupported_claim(claim, None, _TRUST_COMPONENTS) is None


# --- Partially verified ------------------------------------------------------

def test_partially_verified_claim_generates_finding():
    claim = build_claim()
    vr = build_verification_result(status=VerificationStatus.PARTIALLY_VERIFIED)
    finding = rule_partially_verified_claim(claim, vr, _TRUST_COMPONENTS)
    assert finding is not None
    assert finding.finding_type == "partially_verified_claim"


# --- 2: Numerical mismatch --------------------------------------------------

def test_2_numerical_mismatch_generates_finding():
    claim = build_claim(claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    vr = build_verification_result(checks=VerificationChecks(numeric=0.1, unit=1.0, temporal=1.0, entity=1.0, category=1.0))
    finding = rule_numerical_mismatch(claim, vr, _TRUST_COMPONENTS, recommendation_config())
    assert finding is not None
    assert finding.finding_type == "numerical_mismatch"
    assert finding.severity > 0.5


def test_numerical_mismatch_does_not_fire_within_tolerance():
    claim = build_claim()
    vr = build_verification_result(checks=VerificationChecks(numeric=0.95, unit=1.0, temporal=1.0, entity=1.0, category=1.0))
    assert rule_numerical_mismatch(claim, vr, _TRUST_COMPONENTS, recommendation_config()) is None


# --- 3: Unit mismatch --------------------------------------------------------

def test_3_unit_mismatch_generates_finding():
    claim = build_claim()
    vr = build_verification_result(checks=VerificationChecks(numeric=1.0, unit=0.0, temporal=1.0, entity=1.0, category=1.0))
    finding = rule_unit_mismatch(claim, vr, _TRUST_COMPONENTS)
    assert finding is not None
    assert finding.finding_type == "unit_mismatch"


def test_unit_mismatch_does_not_fire_when_units_compatible():
    claim = build_claim()
    vr = build_verification_result(checks=VerificationChecks(numeric=1.0, unit=1.0, temporal=1.0, entity=1.0, category=1.0))
    assert rule_unit_mismatch(claim, vr, _TRUST_COMPONENTS) is None


# --- 4: Target-year mismatch -------------------------------------------------

def test_4_target_year_mismatch_generates_finding():
    claim = build_claim()
    vr = build_verification_result(checks=VerificationChecks(numeric=1.0, unit=1.0, temporal=0.0, entity=1.0, category=1.0))
    finding = rule_target_year_mismatch(claim, vr, _TRUST_COMPONENTS)
    assert finding is not None
    assert finding.finding_type == "target_year_mismatch"


# --- 5-8: Greenwashing-derived rules -----------------------------------------

def test_5_vague_claim_generates_finding():
    claim = build_claim(claim="We are committed to a greener future.")
    gw = build_greenwashing_result(greenwashing_type=[GreenwashingType.VAGUE_CLAIM], greenwashing_risk=RiskLevel.MEDIUM, greenwashing_score=40.0)
    findings = rules_from_greenwashing(claim, gw, _TRUST_COMPONENTS)
    assert any(f.finding_type == "vague_claim" for f in findings)


def test_6_absolute_claim_generates_finding():
    claim = build_claim(claim="100% environmentally friendly.")
    gw = build_greenwashing_result(greenwashing_type=[GreenwashingType.ABSOLUTE_CLAIM], greenwashing_risk=RiskLevel.MEDIUM, greenwashing_score=45.0)
    findings = rules_from_greenwashing(claim, gw, _TRUST_COMPONENTS)
    assert any(f.finding_type == "absolute_claim" for f in findings)


def test_7_exaggerated_claim_generates_finding():
    claim = build_claim(claim="We reduced emissions by 80%.", value=80.0, unit="%")
    gw = build_greenwashing_result(greenwashing_type=[GreenwashingType.EXAGGERATED_CLAIM], greenwashing_risk=RiskLevel.HIGH, greenwashing_score=75.0)
    findings = rules_from_greenwashing(claim, gw, _TRUST_COMPONENTS)
    assert any(f.finding_type == "exaggerated_claim" for f in findings)


def test_8_contradictory_claim_generates_finding():
    claim = build_claim()
    gw = build_greenwashing_result(greenwashing_type=[GreenwashingType.CONTRADICTORY_CLAIM], greenwashing_risk=RiskLevel.HIGH, greenwashing_score=80.0)
    findings = rules_from_greenwashing(claim, gw, _TRUST_COMPONENTS)
    assert any(f.finding_type == "contradictory_claim" for f in findings)


def test_no_significant_signal_generates_no_findings():
    claim = build_claim()
    gw = build_greenwashing_result(greenwashing_type=[GreenwashingType.NO_SIGNIFICANT_SIGNAL])
    assert rules_from_greenwashing(claim, gw, _TRUST_COMPONENTS) == []


# --- 9: Missing provenance ---------------------------------------------------

def test_9_missing_provenance_generates_finding():
    claim = build_claim()
    evidence = build_evidence_match(document_id=None, page_number=None, source_chunk_id=None)
    vr = build_verification_result(matched_evidence=[evidence])
    finding = rule_missing_provenance(claim, vr, _TRUST_COMPONENTS, recommendation_config())
    assert finding is not None
    assert finding.finding_type == "missing_provenance"


def test_missing_provenance_does_not_fire_with_complete_evidence():
    claim = build_claim()
    vr = build_verification_result()  # default evidence has full provenance
    assert rule_missing_provenance(claim, vr, _TRUST_COMPONENTS, recommendation_config()) is None


# --- Missing target / missing metrics ---------------------------------------

def test_missing_target_generates_finding_for_commitment_without_target_year():
    from app.models.claim import ClaimType
    claim = build_claim(claim_type=ClaimType.COMMITMENT, target_year=None)
    finding = rule_missing_target(claim, _TRUST_COMPONENTS)
    assert finding is not None
    assert finding.finding_type == "missing_target"


def test_missing_target_does_not_fire_for_non_commitment_claims():
    finding = rule_missing_target(build_claim(), _TRUST_COMPONENTS)  # default PERFORMANCE type
    assert finding is None


def test_missing_metrics_generates_finding_for_metric_claim_without_value():
    from app.models.claim import ClaimType
    claim = build_claim(claim_type=ClaimType.METRIC, value=None, unit=None)
    finding = rule_missing_metrics(claim, _TRUST_COMPONENTS)
    assert finding is not None
    assert finding.finding_type == "missing_metrics"


# --- 11: Weak trust components -----------------------------------------------

def test_11_weak_trust_component_generates_finding_sorted_weakest_first():
    trust_score = build_trust_score(consistency=40.0, claim_support=45.0, greenwashing_risk=35.0, evidence_quality=70.0, transparency=65.0, provenance=80.0)
    findings = rule_weak_trust_components(trust_score, recommendation_config(weak_component_threshold=60.0))
    types = [f.finding_type for f in findings]
    assert types == ["weak_trust_component:greenwashing_risk", "weak_trust_component:consistency", "weak_trust_component:claim_support"]


def test_weak_trust_component_does_not_fire_for_strong_components():
    trust_score = build_trust_score(claim_support=90, evidence_quality=90, consistency=90, transparency=90, greenwashing_risk=90, provenance=90)
    assert rule_weak_trust_components(trust_score, recommendation_config(weak_component_threshold=60.0)) == []


# --- Low evidence coverage ---------------------------------------------------

def test_low_evidence_coverage_generates_finding():
    trust_score = build_trust_score(evidence_coverage=30.0)
    finding = rule_low_evidence_coverage(trust_score, recommendation_config(low_evidence_coverage_threshold=70.0))
    assert finding is not None
    assert finding.finding_type == "low_evidence_coverage"


def test_low_evidence_coverage_does_not_fire_when_coverage_is_strong():
    trust_score = build_trust_score(evidence_coverage=95.0)
    assert rule_low_evidence_coverage(trust_score, recommendation_config(low_evidence_coverage_threshold=70.0)) is None


# --- 12: Traceability --------------------------------------------------------

def test_12_all_findings_are_traceable_to_a_claim_id_or_are_report_level():
    claim = build_claim()
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED)
    findings = collect_claim_findings(claim, vr, None, _TRUST_COMPONENTS, recommendation_config())
    assert all(f.claim_id == claim.claim_id for f in findings)


# --- Deduplication of overlapping numeric/exaggerated findings --------------

def test_numerical_mismatch_suppressed_when_greenwashing_already_flags_exaggerated():
    claim = build_claim(claim="We reduced emissions by 80%.", value=80.0, unit="%")
    vr = build_verification_result(checks=VerificationChecks(numeric=0.1, unit=1.0, temporal=1.0, entity=1.0, category=1.0))
    gw = build_greenwashing_result(greenwashing_type=[GreenwashingType.EXAGGERATED_CLAIM], greenwashing_risk=RiskLevel.HIGH, greenwashing_score=75.0)
    findings = collect_claim_findings(claim, vr, gw, _TRUST_COMPONENTS, recommendation_config())
    types = [f.finding_type for f in findings]
    assert "exaggerated_claim" in types
    assert "numerical_mismatch" not in types  # superseded, not duplicated
