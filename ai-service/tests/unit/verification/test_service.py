import json

from app.core.config import EvidencePolicy
from app.core.llm import LLMGenerationError
from app.models.claim import ClaimCategory
from app.models.evidence import SourceType
from app.models.verification import VerificationStatus
from app.verification.service import VerificationService
from tests.unit.verification.conftest import (
    build_claim,
    build_evidence,
    build_retriever,
    make_manager,
    verification_config,
    verification_confidence_weights,
    verification_thresholds,
    verification_weights,
)


def _full_support_judgment(evidence_id: str) -> str:
    return json.dumps({"judgments": [{
        "evidence_id": evidence_id, "supports_claim": True, "support_level": "full",
        "supported_components": ["metric", "value", "unit", "period"], "unsupported_components": [],
        "contradictions": [], "reason": "The evidence states the same metric, value, unit and period.",
    }]})


def _no_support_judgment(evidence_id: str) -> str:
    return json.dumps({"judgments": [{
        "evidence_id": evidence_id, "supports_claim": False, "support_level": "none",
        "supported_components": [], "unsupported_components": ["metric", "value"],
        "contradictions": [], "reason": "Evidence is unrelated.",
    }]})


def _service(manager, retriever, repository, config=None):
    return VerificationService(
        retriever=retriever, repository=repository, llm_manager=manager,
        config=config or verification_config(max_schema_retries=0),
        weights=verification_weights(), confidence_weights=verification_confidence_weights(),
        thresholds=verification_thresholds(),
    )


# --- Critical tests (section 33) ---------------------------------------

def test_critical_1_exact_match_is_verified_with_high_score(tmp_path):
    claim = build_claim(claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence = build_evidence(evidence_text="Scope 1 emissions decreased by 20% in 2025.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)

    assert result.status == VerificationStatus.VERIFIED
    assert result.verification_score >= 80.0
    assert result.matched_evidence[0].evidence_id == evidence.evidence_id


def test_critical_2_wrong_numeric_value_is_not_verified(tmp_path):
    claim = build_claim(claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence = build_evidence(evidence_text="Scope 1 emissions decreased by 5% in 2025.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_no_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)

    assert result.status != VerificationStatus.VERIFIED
    assert any("numeric" in line.lower() or "value" in line.lower() for line in result.explanation)


def test_critical_3_direction_contradiction_is_not_verified(tmp_path):
    claim = build_claim(claim="Scope 1 emissions decreased by 20%.", value=20.0, unit="%")
    evidence = build_evidence(evidence_text="Scope 1 emissions increased by 20%.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_no_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)

    assert result.status != VerificationStatus.VERIFIED


def test_critical_4_wrong_company_evidence_is_unsupported(tmp_path):
    claim = build_claim(company="Company A", claim="Company A reduced emissions by 20%.", value=20.0, unit="%")
    evidence = build_evidence(company="Company B", evidence_text="Company B reduced emissions by 20%.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)

    # Company B evidence should never even be retrieved for a Company A
    # claim (Phase 5's metadata filtering), so there is no evidence at all.
    assert result.status == VerificationStatus.UNSUPPORTED


# --- Section 32 numbered test list --------------------------------------

def test_2_strong_semantic_match(tmp_path):
    claim = build_claim(claim="Scope 1 emissions decreased by 20% from the 2020 baseline.", value=20.0, unit="%")
    evidence = build_evidence(evidence_text="Scope 1 emissions decreased by 20% versus the 2020 baseline year.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.semantic > 0.3


def test_3_weak_semantic_match_is_not_verified(tmp_path):
    claim = build_claim(claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence = build_evidence(evidence_text="The board has five independent directors overseeing governance.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_no_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.status != VerificationStatus.VERIFIED


def test_6_correct_unit(tmp_path):
    claim = build_claim(claim="Scope 2 emissions were 45,000 tCO2e in 2025.", value=45000.0, unit="tCO2e")
    evidence = build_evidence(evidence_text="Scope 2 emissions were 45,000 tCO2e in 2025.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.unit == 1.0


def test_7_incorrect_unit(tmp_path):
    claim = build_claim(claim="Scope 2 emissions were 45,000 tCO2e in 2025.", value=45000.0, unit="tCO2e")
    evidence = build_evidence(evidence_text="Scope 2 emissions were 45,000 MWh in 2025.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_no_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.unit == 0.0
    assert result.status != VerificationStatus.VERIFIED


def test_8_correct_year(tmp_path):
    claim = build_claim(claim="2025 emissions decreased by 20%.", value=20.0, unit="%")
    evidence = build_evidence(evidence_text="2025 emissions decreased by 20%.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.temporal == 1.0


def test_9_incorrect_year(tmp_path):
    claim = build_claim(claim="2025 emissions decreased by 20%.", value=20.0, unit="%")
    evidence = build_evidence(evidence_text="2020 emissions decreased by 20%.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_no_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.temporal < 1.0


def test_12_category_mismatch_reduces_score_but_is_not_a_hard_reject(tmp_path):
    claim = build_claim(
        claim="Scope 1 emissions decreased by 20%.", value=20.0, unit="%", category=ClaimCategory.ENVIRONMENTAL,
    )
    evidence = build_evidence(evidence_text="Scope 1 emissions decreased by 20%.", category=ClaimCategory.SOCIAL)
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.category < 1.0
    assert "wrong_company" not in result.explanation  # category mismatch is not treated as a hard fail


def test_14_no_evidence(tmp_path):
    claim = build_claim()
    retriever, repository = build_retriever([], tmp_path)
    manager, _ = make_manager([], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.status == VerificationStatus.UNSUPPORTED
    assert result.verification_score == 0.0
    assert "No sufficiently relevant evidence was found." in result.explanation


def test_15_multiple_evidence_records_all_evaluated(tmp_path):
    claim = build_claim(claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence_a = build_evidence(evidence_id="EVD-A", evidence_text="Scope 1 emissions decreased by 20% in 2025.")
    evidence_b = build_evidence(evidence_id="EVD-B", evidence_text="Scope 1 emissions decreased by 5% in 2025.")
    retriever, repository = build_retriever([evidence_a, evidence_b], tmp_path)
    manager, _ = make_manager([
        json.dumps({"judgments": [
            {"evidence_id": "EVD-A", "supports_claim": True, "support_level": "full", "reason": "match"},
            {"evidence_id": "EVD-B", "supports_claim": False, "support_level": "none", "reason": "mismatch"},
        ]})
    ], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert len(result.matched_evidence) == 2
    assert result.status == VerificationStatus.VERIFIED  # best candidate (EVD-A) drives the outcome


def test_16_uploaded_report_evidence(tmp_path):
    claim = build_claim()
    evidence = build_evidence(source_type=SourceType.UPLOADED_REPORT)
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.matched_evidence[0].source_type == SourceType.UPLOADED_REPORT


def test_17_external_report_evidence(tmp_path):
    claim = build_claim()
    evidence = build_evidence(
        source_type=SourceType.EXTERNAL_REPORT, organization="Example Company",
        report_title="2025 Sustainability Report", source_authority="External ESG Report",
    )
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.matched_evidence[0].source_type == SourceType.EXTERNAL_REPORT


def test_18_evidence_provenance_preserved_in_matched_evidence(tmp_path):
    claim = build_claim()
    evidence = build_evidence(page_number=42, source_chunk_id="CHK-00042", report_title="2025 Report")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    match = result.matched_evidence[0]
    assert match.page_number == 42
    assert match.source_chunk_id == "CHK-00042"
    assert match.document_id == evidence.document_id
    assert match.company == evidence.company


def test_19_llm_says_supported(tmp_path):
    claim = build_claim()
    evidence = build_evidence()
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.llm_support == 1.0


def test_20_llm_says_unsupported(tmp_path):
    claim = build_claim()
    evidence = build_evidence(evidence_text="Something entirely unrelated to the claim.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_no_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.llm_support == 0.0


def test_21_llm_malformed_json_falls_back_to_neutral_signal(tmp_path):
    claim = build_claim(claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence = build_evidence(evidence_text="Scope 1 emissions decreased by 20% in 2025.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager(["not valid json {{{"], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.llm_support == 0.5
    # deterministic signals alone can still be enough to verify a strong match
    assert result.status in (VerificationStatus.VERIFIED, VerificationStatus.PARTIALLY_VERIFIED)


def test_22_llm_unavailable(tmp_path):
    claim = build_claim(claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence = build_evidence(evidence_text="Scope 1 emissions decreased by 20% in 2025.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([LLMGenerationError("simulated outage")], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.llm_support == 0.5
    assert result.confidence_score < 100.0


def test_23_retrieval_failure_produces_structured_unsupported_result(tmp_path):
    claim = build_claim()
    retriever, repository = build_retriever([], tmp_path)

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated retrieval outage")

    retriever.search = _raise
    manager, _ = make_manager([], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.status == VerificationStatus.UNSUPPORTED
    assert "retrieval failed" in result.reason.lower()


def test_24_hard_contradiction_overrides_high_similarity(tmp_path):
    claim = build_claim(claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    # Nearly identical text (high semantic/lexical score) but the number is wrong.
    evidence = build_evidence(evidence_text="Scope 1 emissions decreased by 90% in 2025.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_no_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.status != VerificationStatus.VERIFIED
    assert result.checks.numeric == 0.0


def test_25_different_year_metrics_are_not_incorrectly_conflated(tmp_path):
    claim = build_claim(claim="Scope 1 emissions in 2024 were 100 tCO2e.", value=100.0, unit="tCO2e")
    evidence = build_evidence(evidence_text="Scope 1 emissions in 2025 were 90 tCO2e.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_no_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.numeric == 0.0  # different values entirely, correctly flagged
    assert result.status != VerificationStatus.VERIFIED


def test_26_numerical_claim_without_numerical_evidence_is_not_fully_verified(tmp_path):
    claim = build_claim(claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence = build_evidence(evidence_text="Scope 1 emissions decreased significantly this year.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_no_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.checks.numeric < 1.0
    assert result.status != VerificationStatus.VERIFIED


def test_27_target_year_mismatch_is_not_verified(tmp_path):
    claim = build_claim(
        claim="We aim to achieve net zero by 2050.", value=None, unit=None, target_year=2050,
    )
    evidence = build_evidence(evidence_text="We aim to achieve net zero by 2040.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_no_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.status != VerificationStatus.VERIFIED
    assert any("target year" in line.lower() for line in result.explanation)


def test_28_direction_mismatch_is_detected(tmp_path):
    claim = build_claim(claim="Water consumption decreased.", value=None, unit=None)
    evidence = build_evidence(evidence_text="Water consumption increased this year.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_no_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.status != VerificationStatus.VERIFIED
    assert any("direction" in line.lower() for line in result.explanation)


# --- verify_claims batch behavior ---------------------------------------

def test_verify_claims_continues_after_one_claim_fails(tmp_path):
    good_claim = build_claim(claim_id="CLM-000001", claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence = build_evidence(evidence_text="Scope 1 emissions decreased by 20% in 2025.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment(evidence.evidence_id)], max_retries=0)
    service = _service(manager, retriever, repository)

    bad_claim = build_claim(claim_id="CLM-000002")
    original_search = retriever.search
    call_count = {"n": 0}

    def flaky_search(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 2:
            raise RuntimeError("simulated failure on the second claim")
        return original_search(*args, **kwargs)

    retriever.search = flaky_search

    results = service.verify_claims([good_claim, bad_claim])
    assert len(results) == 2
    assert results[0].claim_id == "CLM-000001"
    assert results[1].claim_id == "CLM-000002"
    assert results[1].status == VerificationStatus.UNSUPPORTED


# --- Data leakage protection (Phase 10 section 26) --------------------------

def test_default_policy_includes_the_claims_own_document(tmp_path):
    """The default evidence policy (INCLUDE_CURRENT_DOCUMENT) is what every
    prior phase's tests are built around: a claim IS checked against its
    own uploaded report's supporting text."""
    claim = build_claim(document_id="DOC-001", claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence = build_evidence(document_id="DOC-001", evidence_text="Scope 1 emissions decreased by 20% in 2025.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment(evidence.evidence_id)], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim)
    assert result.matched_evidence
    assert result.matched_evidence[0].document_id == "DOC-001"


def test_external_evidence_only_policy_excludes_the_claims_own_document(tmp_path):
    claim = build_claim(document_id="DOC-001", claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    own_document_evidence = build_evidence(
        evidence_id="EVD-OWN", document_id="DOC-001", evidence_text="Scope 1 emissions decreased by 20% in 2025."
    )
    external_evidence = build_evidence(
        evidence_id="EVD-EXTERNAL", document_id="DOC-999", source_type=SourceType.EXTERNAL_REPORT,
        evidence_text="Scope 1 emissions decreased by 20% in 2025.", organization="Example Company",
        report_title="Independent Report", source_authority="External ESG Report",
    )
    retriever, repository = build_retriever([own_document_evidence, external_evidence], tmp_path)
    manager, _ = make_manager([_full_support_judgment("EVD-EXTERNAL")], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim, evidence_policy=EvidencePolicy.EXTERNAL_EVIDENCE_ONLY)

    assert result.matched_evidence
    assert all(m.document_id != "DOC-001" for m in result.matched_evidence)
    assert result.matched_evidence[0].evidence_id == "EVD-EXTERNAL"


def test_external_evidence_only_falls_back_to_unsupported_when_only_own_document_evidence_exists(tmp_path):
    claim = build_claim(document_id="DOC-001", claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence = build_evidence(document_id="DOC-001", evidence_text="Scope 1 emissions decreased by 20% in 2025.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([], max_retries=0)

    result = _service(manager, retriever, repository).verify_claim(claim, evidence_policy=EvidencePolicy.EXTERNAL_EVIDENCE_ONLY)
    assert result.status == VerificationStatus.UNSUPPORTED
    assert result.matched_evidence == []


def test_evidence_policy_defaults_to_config_when_not_passed_explicitly(tmp_path):
    claim = build_claim(document_id="DOC-001", claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    evidence = build_evidence(document_id="DOC-001", evidence_text="Scope 1 emissions decreased by 20% in 2025.")
    retriever, repository = build_retriever([evidence], tmp_path)
    manager, _ = make_manager([], max_retries=0)

    config = verification_config(max_schema_retries=0, default_evidence_policy=EvidencePolicy.EXTERNAL_EVIDENCE_ONLY)
    result = _service(manager, retriever, repository, config=config).verify_claim(claim)
    assert result.status == VerificationStatus.UNSUPPORTED  # own-document evidence excluded by the config default
