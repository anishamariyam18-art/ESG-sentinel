import json

from app.greenwashing.detector import run_detectors
from app.greenwashing.judge import GreenwashingJudge
from app.models.evidence import Evidence, SourceType
from tests.unit.greenwashing.conftest import (
    build_claim,
    build_verification_result,
    greenwashing_aggregation,
    make_manager,
)


def _evidence(text, **overrides):
    fields = dict(
        evidence_id="EVD-000001", source_type=SourceType.UPLOADED_REPORT, document_id="DOC-001",
        company="Example Company", report_year=2025, page_number=1, source_chunk_id="CHK-00001",
        evidence_text=text,
    )
    fields.update(overrides)
    return Evidence(**fields)


def _judgment_json(**overrides) -> str:
    payload = {"risk_assessment": "high", "reasoning": ["Large numerical discrepancy detected."], "intent_assumed": False}
    payload.update(overrides)
    return json.dumps(payload)


def test_judge_returns_structured_judgment():
    claim = build_claim(claim="We reduced Scope 1 emissions by 80%.", value=80.0, unit="%")
    evidence = _evidence("Scope 1 emissions decreased by 20%.")
    report = run_detectors(claim, evidence, 2.0)
    vr = build_verification_result()

    manager, _ = make_manager([_judgment_json()], max_retries=0)
    judge = GreenwashingJudge(manager, greenwashing_aggregation(max_schema_retries=0))

    judgment = judge.judge(claim, vr, evidence, report)
    assert judgment is not None
    assert judgment.risk_assessment == "high"
    assert judgment.reasoning


def test_judge_malformed_json_returns_none():
    claim = build_claim()
    report = run_detectors(claim, None, 2.0)
    vr = build_verification_result()

    manager, _ = make_manager(["not valid json {{{"], max_retries=0)
    judge = GreenwashingJudge(manager, greenwashing_aggregation(max_schema_retries=0))

    assert judge.judge(claim, vr, None, report) is None


def test_judge_llm_unavailable_returns_none():
    from app.core.llm import LLMGenerationError

    claim = build_claim()
    report = run_detectors(claim, None, 2.0)
    vr = build_verification_result()

    manager, _ = make_manager([LLMGenerationError("simulated outage")], max_retries=0)
    judge = GreenwashingJudge(manager, greenwashing_aggregation(max_schema_retries=0))

    assert judge.judge(claim, vr, None, report) is None


def test_judge_discards_reasoning_if_intent_assumed():
    claim = build_claim()
    report = run_detectors(claim, None, 2.0)
    vr = build_verification_result()

    manager, _ = make_manager(
        [_judgment_json(reasoning=["The company intentionally deceived investors."], intent_assumed=True)],
        max_retries=0,
    )
    judge = GreenwashingJudge(manager, greenwashing_aggregation(max_schema_retries=0))

    judgment = judge.judge(claim, vr, None, report)
    assert judgment is not None
    assert judgment.reasoning == []
    assert judgment.intent_assumed is True
