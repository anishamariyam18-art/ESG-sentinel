import json

from app.verification.judge import EvidenceJudge, judgment_to_score
from tests.unit.verification.conftest import build_claim, build_evidence, make_manager, verification_config


def _judgment_json(judgments: list[dict]) -> str:
    return json.dumps({"judgments": judgments})


def test_llm_says_supported():
    evidence = build_evidence()
    manager, _ = make_manager([
        _judgment_json([{
            "evidence_id": "EVD-000001", "supports_claim": True, "support_level": "full",
            "supported_components": ["metric", "value", "unit"], "unsupported_components": [],
            "contradictions": [], "reason": "Evidence matches the claim.",
        }])
    ], max_retries=0)
    judge = EvidenceJudge(manager, verification_config(max_schema_retries=0))

    judgments = judge.judge(build_claim(), [evidence])
    assert judgments["EVD-000001"].supports_claim is True
    assert judgments["EVD-000001"].support_level == "full"
    assert judgment_to_score(judgments["EVD-000001"]) == 1.0


def test_llm_says_unsupported():
    evidence = build_evidence(evidence_text="The board has five independent directors.")
    manager, _ = make_manager([
        _judgment_json([{
            "evidence_id": "EVD-000001", "supports_claim": False, "support_level": "none",
            "supported_components": [], "unsupported_components": ["metric", "value"],
            "contradictions": [], "reason": "Evidence is about a different topic.",
        }])
    ], max_retries=0)
    judge = EvidenceJudge(manager, verification_config(max_schema_retries=0))

    judgments = judge.judge(build_claim(), [evidence])
    assert judgments["EVD-000001"].supports_claim is False
    assert judgment_to_score(judgments["EVD-000001"]) == 0.0


def test_llm_reports_explicit_contradiction_forces_zero_score_even_if_support_level_partial():
    evidence = build_evidence(evidence_text="Emissions decreased by 5%.")
    manager, _ = make_manager([
        _judgment_json([{
            "evidence_id": "EVD-000001", "supports_claim": False, "support_level": "partial",
            "supported_components": ["metric"], "unsupported_components": ["value"],
            "contradictions": ["Evidence states 5%, claim states 20%."], "reason": "Value mismatch.",
        }])
    ], max_retries=0)
    judge = EvidenceJudge(manager, verification_config(max_schema_retries=0))

    judgments = judge.judge(build_claim(), [evidence])
    assert judgment_to_score(judgments["EVD-000001"]) == 0.0


def test_llm_malformed_json_returns_empty_dict_not_fabricated():
    evidence = build_evidence()
    manager, _ = make_manager(["not valid json {{{"], max_retries=0)
    judge = EvidenceJudge(manager, verification_config(max_schema_retries=0))

    judgments = judge.judge(build_claim(), [evidence])
    assert judgments == {}


def test_llm_unavailable_returns_empty_dict():
    from app.core.llm import LLMGenerationError

    evidence = build_evidence()
    manager, _ = make_manager([LLMGenerationError("simulated outage")], max_retries=0)
    judge = EvidenceJudge(manager, verification_config(max_schema_retries=0))

    judgments = judge.judge(build_claim(), [evidence])
    assert judgments == {}


def test_judgment_to_score_missing_judgment_is_neutral_default():
    assert judgment_to_score(None) == 0.5


def test_judge_with_no_candidates_returns_empty_dict_without_calling_llm():
    manager, provider = make_manager([], max_retries=0)
    judge = EvidenceJudge(manager, verification_config(max_schema_retries=0))
    assert judge.judge(build_claim(), []) == {}
    assert provider.calls == []


def test_judge_ignores_judgment_for_unknown_evidence_id():
    evidence = build_evidence(evidence_id="EVD-REAL")
    manager, _ = make_manager([
        _judgment_json([
            {"evidence_id": "EVD-REAL", "supports_claim": True, "support_level": "full", "reason": "ok"},
            {"evidence_id": "EVD-FABRICATED", "supports_claim": True, "support_level": "full", "reason": "should be dropped"},
        ])
    ], max_retries=0)
    judge = EvidenceJudge(manager, verification_config(max_schema_retries=0))

    judgments = judge.judge(build_claim(), [evidence])
    assert set(judgments.keys()) == {"EVD-REAL"}
