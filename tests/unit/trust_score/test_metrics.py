from app.models.greenwashing import RiskLevel
from app.models.verification import VerificationStatus
from app.trust_score.metrics import compute_statistics
from tests.unit.trust_score.conftest import build_claim, build_greenwashing_result, build_verification_result


def test_statistics_counts_are_deterministic_and_exact():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(4)]
    results = [
        build_verification_result(claim_id="CLM-0", status=VerificationStatus.VERIFIED),
        build_verification_result(claim_id="CLM-1", status=VerificationStatus.VERIFIED),
        build_verification_result(claim_id="CLM-2", status=VerificationStatus.PARTIALLY_VERIFIED),
        build_verification_result(claim_id="CLM-3", status=VerificationStatus.UNSUPPORTED, matched_evidence=[]),
    ]
    greenwashing = [
        build_greenwashing_result(claim_id="CLM-0", greenwashing_risk=RiskLevel.LOW),
        build_greenwashing_result(claim_id="CLM-1", greenwashing_risk=RiskLevel.MEDIUM),
        build_greenwashing_result(claim_id="CLM-2", greenwashing_risk=RiskLevel.HIGH),
    ]
    stats = compute_statistics(claims, results, greenwashing)

    assert stats.total_claims == 4
    assert stats.verified_claims == 2
    assert stats.partially_verified_claims == 1
    assert stats.unsupported_claims == 1
    assert stats.low_greenwashing_claims == 1
    assert stats.medium_greenwashing_claims == 1
    assert stats.high_greenwashing_claims == 1
    assert stats.verification_coverage == 100.0  # every claim has a result
    assert stats.evidence_coverage == 75.0  # 3 of 4 claims have matched evidence
    assert stats.provenance_coverage == 75.0  # 3 of 4 have complete evidence provenance


def test_statistics_empty_claims_gives_zero_not_a_crash():
    stats = compute_statistics([], [], [])
    assert stats.total_claims == 0
    assert stats.evidence_coverage == 0.0
    assert stats.verification_coverage == 0.0
    assert stats.provenance_coverage == 0.0


def test_statistics_claim_without_verification_result_excluded_from_coverage():
    claims = [build_claim(claim_id="CLM-0"), build_claim(claim_id="CLM-1")]
    results = [build_verification_result(claim_id="CLM-0", status=VerificationStatus.VERIFIED)]
    stats = compute_statistics(claims, results, [])
    assert stats.verification_coverage == 50.0
    assert stats.evidence_coverage == 50.0
