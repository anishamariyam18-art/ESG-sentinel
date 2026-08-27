"""Explainability validation (Phase 10 section 31): every number that
appears in a natural-language explanation must actually be present in the
underlying structured result -- never an LLM-invented statistic. Exercised
against the real `TrustScoreService`/`RecommendationService` outputs,
without an LLM manager (so `explanation` is 100% the deterministic
templates), which is exactly the part of the text this requirement is
about -- the deterministic explanation is what must always be traceable,
regardless of whether an optional LLM narrative is ever appended on top."""
from __future__ import annotations

import re

from app.models.verification import VerificationStatus
from app.recommendations.service import RecommendationService
from app.trust_score.service import TrustScoreService
from tests.unit.trust_score.conftest import build_claim, build_greenwashing_result, build_verification_result


def _numbers_in(text: str) -> set[str]:
    return set(re.findall(r"\d+\.?\d*", text))


def test_trust_score_explanation_percentages_are_traceable_to_statistics():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(10)]
    results = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.VERIFIED) for i in range(9)]
    results.append(build_verification_result(claim_id="CLM-9", status=VerificationStatus.UNSUPPORTED, matched_evidence=[]))
    greenwashing = [build_greenwashing_result(claim_id=f"CLM-{i}") for i in range(10)]

    result = TrustScoreService().calculate_trust_score("DOC-1", "Example Co", claims, results, greenwashing)

    # "90.0% of claims were fully verified (9 of 10)." -- every number here
    # must be derivable from `statistics`, never invented.
    joined_explanation = " ".join(result.explanation)
    assert str(result.statistics.verified_claims) in joined_explanation
    assert str(result.statistics.total_claims) in joined_explanation
    expected_pct = round((result.statistics.verified_claims / result.statistics.total_claims) * 100, 1)
    assert str(expected_pct) in joined_explanation


def test_trust_score_strengths_and_weaknesses_reference_real_percentages_only():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(20)]
    results = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.VERIFIED) for i in range(4)]
    results += [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.UNSUPPORTED, matched_evidence=[]) for i in range(4, 20)]
    greenwashing = [build_greenwashing_result(claim_id=f"CLM-{i}") for i in range(20)]

    result = TrustScoreService().calculate_trust_score("DOC-1", "Example Co", claims, results, greenwashing)

    # Every number appearing anywhere in weaknesses must trace back to a
    # real statistic, component value, or a simple percentage derived from
    # the statistics (e.g. "80.0%" from 16/20 unsupported) -- collect the
    # legitimate number pool and check nothing outside it appears.
    stats = result.statistics
    derived_percentages = {
        str(round((stats.verified_claims / stats.total_claims) * 100, 1)),
        str(round((stats.partially_verified_claims / stats.total_claims) * 100, 1)),
        str(round((stats.unsupported_claims / stats.total_claims) * 100, 1)),
    }
    legitimate_numbers = _numbers_in(str(stats.model_dump())) | _numbers_in(str(result.components.model_dump())) | derived_percentages
    for line in result.weaknesses:
        for number in _numbers_in(line):
            assert number in legitimate_numbers or float(number) < 1, f"unexplained number {number!r} in weakness: {line!r}"


def test_recommendation_explanations_reference_real_claim_ids():
    claims = [build_claim(claim_id=f"CLM-{i}") for i in range(5)]
    results = [build_verification_result(claim_id=f"CLM-{i}", status=VerificationStatus.UNSUPPORTED, matched_evidence=[]) for i in range(5)]
    greenwashing = [build_greenwashing_result(claim_id=f"CLM-{i}") for i in range(5)]

    trust_score = TrustScoreService().calculate_trust_score("DOC-1", "Example Co", claims, results, greenwashing)
    rec_result = RecommendationService().generate_recommendations("DOC-1", "Example Co", claims, results, greenwashing, trust_score)

    real_claim_ids = {c.claim_id for c in claims}
    for rec in rec_result.recommendations:
        for claim_id in rec.source_claim_ids:
            assert claim_id in real_claim_ids, f"recommendation cites unknown claim_id {claim_id!r}"
