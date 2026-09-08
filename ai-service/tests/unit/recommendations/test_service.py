import json

from app.core.llm import LLMGenerationError
from app.models.claim import ClaimCategory, ClaimType
from app.models.greenwashing import GreenwashingType, RiskLevel
from app.models.recommendation import RecommendationPriority
from app.models.verification import VerificationChecks, VerificationStatus
from app.recommendations.service import RecommendationService
from tests.unit.recommendations.conftest import (
    build_claim,
    build_evidence_match,
    build_greenwashing_result,
    build_trust_score,
    build_verification_result,
    make_manager,
    recommendation_config,
    recommendation_priority_weights,
    recommendation_thresholds,
)


def _make_service(llm_manager=None, **config_overrides):
    return RecommendationService(
        llm_manager=llm_manager, priority_weights=recommendation_priority_weights(),
        thresholds=recommendation_thresholds(), config=recommendation_config(**config_overrides),
    )


# --- Critical test 32 --------------------------------------------------------

def test_critical_32_focuses_on_unsupported_consistency_and_greenwashing():
    claims = [build_claim(claim_id=f"CLM-{i:03d}") for i in range(100)]
    results = []
    for i in range(60):
        results.append(build_verification_result(claim_id=f"CLM-{i:03d}", status=VerificationStatus.VERIFIED))
    for i in range(60, 85):
        results.append(build_verification_result(
            claim_id=f"CLM-{i:03d}", status=VerificationStatus.PARTIALLY_VERIFIED,
            checks=VerificationChecks(numeric=0.5, unit=1.0, temporal=1.0, entity=0.5, category=1.0),
        ))
    for i in range(85, 100):
        results.append(build_verification_result(claim_id=f"CLM-{i:03d}", status=VerificationStatus.UNSUPPORTED, matched_evidence=[]))

    greenwashing = (
        [build_greenwashing_result(claim_id=f"CLM-{i:03d}", greenwashing_risk=RiskLevel.HIGH, greenwashing_score=80.0,
                                    greenwashing_type=[GreenwashingType.CONTRADICTORY_CLAIM]) for i in range(5)]
        + [build_greenwashing_result(claim_id=f"CLM-{i:03d}", greenwashing_risk=RiskLevel.MEDIUM, greenwashing_score=45.0,
                                      greenwashing_type=[GreenwashingType.VAGUE_CLAIM]) for i in range(5, 25)]
        + [build_greenwashing_result(claim_id=f"CLM-{i:03d}", greenwashing_risk=RiskLevel.LOW, greenwashing_score=5.0) for i in range(25, 100)]
    )
    trust_score = build_trust_score(
        trust_score=55.0, consistency=40.0, claim_support=50.0, greenwashing_risk=55.0, evidence_quality=60.0,
        transparency=65.0, provenance=70.0,
        total_claims=100, verified_claims=60, partially_verified_claims=25, unsupported_claims=15,
        high_greenwashing_claims=5, medium_greenwashing_claims=20, low_greenwashing_claims=75,
        evidence_coverage=85.0, provenance_coverage=80.0,
    )

    service = _make_service()
    result = service.generate_recommendations("DOC-001", "Example Company", claims, results, greenwashing, trust_score)

    finding_types = {rec.title for rec in result.recommendations}
    joined_actions = " ".join(rec.action for rec in result.recommendations).lower()
    assert any("unsupported" in t.lower() for t in finding_types)
    assert any("consistency" in t.lower() or "reconcile" in t.lower() for t in finding_types)
    assert "contradiction" in joined_actions or "vague" in joined_actions or "reconcile" in joined_actions
    assert "improve esg" not in joined_actions
    assert all(rec.source_claim_ids or rec.category.value == "Cross-cutting" for rec in result.recommendations)


# --- Critical test 33 --------------------------------------------------------

def test_critical_33_near_perfect_report_gives_few_recommendations():
    claims = [build_claim(claim_id=f"CLM-{i:03d}") for i in range(100)]
    results = [build_verification_result(claim_id=f"CLM-{i:03d}", status=VerificationStatus.VERIFIED) for i in range(95)]
    results += [build_verification_result(claim_id=f"CLM-{i:03d}", status=VerificationStatus.PARTIALLY_VERIFIED,
                                           checks=VerificationChecks(numeric=0.9, unit=1.0, temporal=1.0, entity=0.9, category=1.0))
                for i in range(95, 99)]
    results += [build_verification_result(claim_id="CLM-099", status=VerificationStatus.UNSUPPORTED, matched_evidence=[])]
    greenwashing = [build_greenwashing_result(claim_id=f"CLM-{i:03d}") for i in range(100)]
    trust_score = build_trust_score(
        trust_score=92.0, claim_support=96.0, evidence_quality=95.0, consistency=97.0, transparency=95.0,
        greenwashing_risk=98.0, provenance=95.0,
        total_claims=100, verified_claims=95, partially_verified_claims=4, unsupported_claims=1,
        high_greenwashing_claims=0, medium_greenwashing_claims=0, low_greenwashing_claims=100,
        evidence_coverage=99.0, provenance_coverage=98.0,
    )

    service = _make_service()
    result = service.generate_recommendations("DOC-001", "Example Company", claims, results, greenwashing, trust_score)

    assert len(result.recommendations) <= 2
    assert all(rec.priority != RecommendationPriority.HIGH for rec in result.recommendations)


# --- Critical test 34 --------------------------------------------------------

def test_critical_34_exaggerated_claim_references_the_discrepancy():
    claim = build_claim(claim="Emissions decreased by 80%.", value=80.0, unit="%")
    vr = build_verification_result(
        status=VerificationStatus.PARTIALLY_VERIFIED,
        checks=VerificationChecks(numeric=0.2, unit=1.0, temporal=1.0, entity=1.0, category=1.0),
    )
    gw = build_greenwashing_result(
        claim="Emissions decreased by 80%.", greenwashing_risk=RiskLevel.HIGH, greenwashing_score=75.0,
        greenwashing_type=[GreenwashingType.EXAGGERATED_CLAIM],
        explanation=["The claim states 80.0%; the evidence states 20.0%."],
    )
    trust_score = build_trust_score(total_claims=1, verified_claims=0, partially_verified_claims=1, unsupported_claims=0)

    service = _make_service()
    result = service.generate_recommendations("DOC-001", "Example Company", [claim], [vr], [gw], trust_score)

    exaggerated = [rec for rec in result.recommendations if "exaggerated" in rec.title.lower() or "correct" in rec.action.lower()]
    assert exaggerated
    rec = exaggerated[0]
    assert claim.claim_id in rec.source_claim_ids
    assert "80" in " ".join(rec.source_findings) or "80" in rec.explanation


# --- Critical test 35 --------------------------------------------------------

def test_critical_35_vague_claim_recommends_measurable_language():
    claim = build_claim(claim="We are committed to a greener future.", value=None, unit=None, claim_type=ClaimType.GENERAL)
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, matched_evidence=[])
    gw = build_greenwashing_result(
        claim="We are committed to a greener future.", greenwashing_risk=RiskLevel.MEDIUM, greenwashing_score=40.0,
        greenwashing_type=[GreenwashingType.VAGUE_CLAIM],
    )
    trust_score = build_trust_score(total_claims=1, verified_claims=0, partially_verified_claims=0, unsupported_claims=1)

    service = _make_service()
    result = service.generate_recommendations("DOC-001", "Example Company", [claim], [vr], [gw], trust_score)

    vague = [rec for rec in result.recommendations if "vague" in rec.title.lower() or "measurable objectives" in rec.action.lower()]
    assert vague
    assert vague[0].action == (
        "Replace broad sustainability language with measurable objectives, defined metrics and target dates where applicable."
    )


# --- 13: Deduplication / grouping -------------------------------------------

def test_13_ten_unsupported_claims_produce_one_grouped_recommendation():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(10)]
    results = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.UNSUPPORTED, matched_evidence=[]) for i in range(10)]
    trust_score = build_trust_score(total_claims=10, verified_claims=0, partially_verified_claims=0, unsupported_claims=10)

    service = _make_service()
    result = service.generate_recommendations("DOC-001", "Example Company", claims, results, [], trust_score)

    unsupported_recs = [rec for rec in result.recommendations if rec.title.lower().startswith("provide evidence")]
    assert len(unsupported_recs) == 1
    assert set(unsupported_recs[0].source_claim_ids) == {f"CLM-{i}" for i in range(10)}


# --- 21/29: Maximum recommendation limit ------------------------------------

def test_21_maximum_recommendation_limit_is_respected():
    claims = [build_claim(claim_id=f"CLM-{i}", category=ClaimCategory.ENVIRONMENTAL) for i in range(30)]
    results = []
    checks_variants = [
        VerificationChecks(numeric=0.1, unit=1.0, temporal=1.0, entity=1.0, category=1.0),
        VerificationChecks(numeric=1.0, unit=0.0, temporal=1.0, entity=1.0, category=1.0),
        VerificationChecks(numeric=1.0, unit=1.0, temporal=0.0, entity=1.0, category=1.0),
    ]
    for i in range(30):
        results.append(build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.PARTIALLY_VERIFIED, checks=checks_variants[i % 3]))
    trust_score = build_trust_score(
        claim_support=30, evidence_quality=30, consistency=20, transparency=20, greenwashing_risk=30, provenance=20,
        total_claims=30, verified_claims=0, partially_verified_claims=30, unsupported_claims=0, evidence_coverage=20.0,
    )
    service = _make_service(max_recommendations=4)
    result = service.generate_recommendations("DOC-001", "Example Company", claims, results, [], trust_score)
    assert len(result.recommendations) <= 4


# --- 22/30: Maximum priority-action limit -----------------------------------

def test_22_maximum_priority_action_limit_is_respected():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(30)]
    results = []
    checks_variants = [
        VerificationChecks(numeric=0.1, unit=1.0, temporal=1.0, entity=1.0, category=1.0),
        VerificationChecks(numeric=1.0, unit=0.0, temporal=1.0, entity=1.0, category=1.0),
        VerificationChecks(numeric=1.0, unit=1.0, temporal=0.0, entity=1.0, category=1.0),
    ]
    for i in range(30):
        results.append(build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.PARTIALLY_VERIFIED, checks=checks_variants[i % 3]))
    trust_score = build_trust_score(consistency=20, total_claims=30, partially_verified_claims=30, verified_claims=0, unsupported_claims=0)
    service = _make_service(max_recommendations=10, max_priority_actions=2)
    result = service.generate_recommendations("DOC-001", "Example Company", claims, results, [], trust_score)
    assert len(result.priority_actions) <= 2


# --- 20: Empty findings produce a valid result -------------------------------

def test_20_empty_claims_produce_a_valid_result():
    trust_score = build_trust_score(total_claims=0, verified_claims=0, partially_verified_claims=0, unsupported_claims=0, evidence_coverage=0.0, provenance_coverage=0.0)
    service = _make_service()
    result = service.generate_recommendations("DOC-001", "Example Company", [], [], [], trust_score)
    assert result.recommendations == []
    assert result.priority_actions == []
    assert result.document_id == "DOC-001"


# --- 15/16/17: LLM never controls the deterministic result ------------------

def test_15_llm_failure_uses_deterministic_fallback():
    claim = build_claim()
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, matched_evidence=[])
    trust_score = build_trust_score(total_claims=1, verified_claims=0, partially_verified_claims=0, unsupported_claims=1)

    manager, provider = make_manager(["not valid json {{{"], max_retries=0)
    service = _make_service(llm_manager=manager)
    result = service.generate_recommendations("DOC-001", "Example Company", [claim], [vr], [], trust_score)
    assert result.recommendations
    assert result.overall_assessment


def test_16_17_llm_cannot_alter_scores_or_invent_recommendations():
    claim = build_claim()
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, matched_evidence=[])
    trust_score = build_trust_score(total_claims=1, verified_claims=0, partially_verified_claims=0, unsupported_claims=1)

    manager_ok, _ = make_manager([json.dumps({"narrative": ["Everything is fabricated and fraudulent."]})], max_retries=0)
    service_a = _make_service(llm_manager=manager_ok)
    service_b = _make_service(llm_manager=None)

    result_a = service_a.generate_recommendations("DOC-001", "Example Company", [claim], [vr], [], trust_score)
    result_b = service_b.generate_recommendations("DOC-001", "Example Company", [claim], [vr], [], trust_score)

    assert [r.priority_score for r in result_a.recommendations] == [r.priority_score for r in result_b.recommendations]
    assert [r.priority for r in result_a.recommendations] == [r.priority for r in result_b.recommendations]
    assert len(result_a.recommendations) == len(result_b.recommendations)


def test_no_llm_call_when_manager_not_supplied():
    claim = build_claim()
    vr = build_verification_result(status=VerificationStatus.VERIFIED)
    trust_score = build_trust_score()
    service = _make_service(llm_manager=None)
    result = service.generate_recommendations("DOC-001", "Example Company", [claim], [vr], [], trust_score)
    assert result.overall_assessment


def test_llm_narrative_appended_on_success():
    claim = build_claim()
    vr = build_verification_result(status=VerificationStatus.UNSUPPORTED, matched_evidence=[])
    trust_score = build_trust_score(total_claims=1, verified_claims=0, partially_verified_claims=0, unsupported_claims=1)
    manager, provider = make_manager([json.dumps({"narrative": ["The report shows a small number of unsupported claims."]})], max_retries=0)
    service = _make_service(llm_manager=manager)
    result = service.generate_recommendations("DOC-001", "Example Company", [claim], [vr], [], trust_score)
    assert "small number of unsupported claims" in result.overall_assessment
    assert len(provider.calls) == 1


# --- 18/19: Strengths/weaknesses based on actual metrics --------------------

def test_18_19_strengths_and_weaknesses_come_from_trust_score():
    trust_score = build_trust_score(
        strengths=["90% of claims were verified against source-level evidence."],
        weaknesses=["10% of claims were unsupported by available evidence."],
    )
    service = _make_service()
    result = service.generate_recommendations("DOC-001", "Example Company", [], [], [], trust_score)
    assert result.strengths == ["90% of claims were verified against source-level evidence."]
    assert result.weaknesses == ["10% of claims were unsupported by available evidence."]


# --- Traceability: every recommendation has source claim ids or is report-level ---

def test_every_recommendation_is_traceable():
    claims = [build_claim(claim_id="CLM-0"), build_claim(claim_id="CLM-1")]
    results = [
        build_verification_result(claim_id="CLM-0", status=VerificationStatus.UNSUPPORTED, matched_evidence=[]),
        build_verification_result(claim_id="CLM-1", status=VerificationStatus.VERIFIED),
    ]
    trust_score = build_trust_score(consistency=30, total_claims=2, verified_claims=1, partially_verified_claims=0, unsupported_claims=1)
    service = _make_service()
    result = service.generate_recommendations("DOC-001", "Example Company", claims, results, [], trust_score)
    for rec in result.recommendations:
        assert rec.source_claim_ids or rec.category.value == "Cross-cutting"
        assert rec.source_findings
