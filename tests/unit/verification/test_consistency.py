from app.models.claim import ClaimCategory
from app.models.evidence import Evidence, SourceType
from app.verification.consistency import (
    category_consistency,
    detect_direction,
    entity_consistency,
    extract_baseline_year,
    extract_claim_components,
    extract_evidence_components,
    lexical_similarity,
    numeric_consistency,
    run_consistency_checks,
    temporal_consistency,
    unit_consistency,
)
from tests.unit.verification.conftest import build_claim, build_evidence, verification_thresholds


def test_detect_direction_decrease():
    assert detect_direction("Emissions decreased by 20%.") == "decrease"


def test_detect_direction_increase():
    assert detect_direction("Emissions increased by 20%.") == "increase"


def test_detect_direction_ambiguous_returns_none():
    assert detect_direction("Emissions changed this year.") is None


def test_detect_direction_both_present_returns_none():
    assert detect_direction("Emissions decreased in one region but increased in another.") is None


def test_extract_baseline_year():
    assert extract_baseline_year("Scope 1 emissions decreased by 18% from the 2020 baseline.") == 2020


def test_extract_baseline_year_absent():
    assert extract_baseline_year("Scope 1 emissions decreased by 18%.") is None


def test_extract_claim_components_never_invents_missing_fields():
    claim = build_claim(claim="Scope 1 emissions decreased by 20% in 2025.", value=20.0, unit="%")
    components = extract_claim_components(claim)
    assert components.entity == "Example Company"
    assert components.value == 20.0
    assert components.unit == "%"
    assert components.direction == "decrease"
    assert components.baseline_year is None  # not mentioned in this claim text


def test_extract_evidence_components_independently_derives_value_not_from_evidence_fields():
    # Evidence.value is deliberately left unset here -- extraction must come
    # from evidence_text, never trust a pre-populated (possibly claim-copied) field.
    evidence = build_evidence(evidence_text="Scope 1 emissions decreased by 5% in 2025.")
    components = extract_evidence_components(evidence, "")
    assert components.value == 5.0
    assert components.unit == "%"
    assert components.direction == "decrease"


def test_numeric_consistency_exact_match_scores_full():
    claim_components = extract_claim_components(build_claim(value=20.0, unit="%"))
    evidence_components = extract_evidence_components(build_evidence(evidence_text="Emissions decreased by 20%."), "")
    score, reasons = numeric_consistency(claim_components, evidence_components, tolerance_pct=2.0)
    assert score == 1.0
    assert reasons == []


def test_numeric_consistency_large_deviation_is_hard_fail():
    claim_components = extract_claim_components(build_claim(claim="Emissions decreased by 20%.", value=20.0, unit="%"))
    evidence_components = extract_evidence_components(build_evidence(evidence_text="Emissions decreased by 5%."), "")
    score, reasons = numeric_consistency(claim_components, evidence_components, tolerance_pct=2.0)
    assert score == 0.0
    assert "numeric_contradiction" in reasons


def test_numeric_consistency_direction_contradiction_is_hard_fail_regardless_of_value():
    claim_components = extract_claim_components(build_claim(claim="Emissions decreased by 20%.", value=20.0, unit="%"))
    evidence_components = extract_evidence_components(build_evidence(evidence_text="Emissions increased by 20%."), "")
    score, reasons = numeric_consistency(claim_components, evidence_components, tolerance_pct=2.0)
    assert score == 0.0
    assert "direction_contradiction" in reasons


def test_numeric_consistency_claim_without_value_is_not_penalized():
    claim_components = extract_claim_components(
        build_claim(claim="The company has committed to net zero.", value=None, unit=None)
    )
    evidence_components = extract_evidence_components(build_evidence(evidence_text="No numbers here at all."), "")
    score, reasons = numeric_consistency(claim_components, evidence_components, tolerance_pct=2.0)
    assert score == 1.0


def test_numeric_consistency_missing_evidence_value_is_weak_not_zero():
    claim_components = extract_claim_components(build_claim(value=20.0, unit="%"))
    evidence_components = extract_evidence_components(build_evidence(evidence_text="Emissions decreased significantly."), "")
    score, _ = numeric_consistency(claim_components, evidence_components, tolerance_pct=2.0)
    assert 0.0 < score < 1.0


def test_unit_consistency_matching_units():
    claim_components = extract_claim_components(build_claim(value=20.0, unit="%"))
    evidence_components = extract_evidence_components(build_evidence(evidence_text="Emissions decreased by 20%."), "")
    score, reasons = unit_consistency(claim_components, evidence_components)
    assert score == 1.0
    assert reasons == []


def test_unit_consistency_incompatible_units():
    claim_components = extract_claim_components(build_claim(claim="Emissions decreased by 20%.", value=20.0, unit="%"))
    evidence_components = extract_evidence_components(
        build_evidence(evidence_text="Emissions decreased by 20 tCO2e."), ""
    )
    score, reasons = unit_consistency(claim_components, evidence_components)
    assert score == 0.0
    assert "unit_incompatible" in reasons


def test_temporal_consistency_matching_measurement_year():
    claim_components = extract_claim_components(build_claim(claim="2025 emissions decreased by 20%.", value=20.0, unit="%"))
    evidence_components = extract_evidence_components(build_evidence(evidence_text="2025 emissions decreased by 20%."), "")
    score, _ = temporal_consistency(claim_components, evidence_components, 2025, 2025)
    assert score == 1.0


def test_temporal_consistency_mismatched_measurement_year():
    claim_components = extract_claim_components(build_claim(claim="2025 emissions decreased by 20%.", value=20.0, unit="%"))
    evidence_components = extract_evidence_components(build_evidence(evidence_text="2020 emissions decreased by 20%."), "")
    score, _ = temporal_consistency(claim_components, evidence_components, 2025, 2020)
    assert score < 1.0


def test_temporal_consistency_target_year_mismatch_is_hard_fail():
    claim_components = extract_claim_components(
        build_claim(claim="We aim to achieve net zero by 2050.", value=None, unit=None, target_year=2050)
    )
    evidence_components = extract_evidence_components(
        build_evidence(evidence_text="We aim to achieve net zero by 2040."), ""
    )
    score, reasons = temporal_consistency(claim_components, evidence_components, 2025, 2025)
    assert score < 1.0
    assert "target_year_incompatible" in reasons


def test_entity_consistency_same_company():
    score, reasons = entity_consistency("Company A", "Company A")
    assert score == 1.0
    assert reasons == []


def test_entity_consistency_different_company_is_hard_fail():
    score, reasons = entity_consistency("Company A", "Company B")
    assert score == 0.0
    assert "wrong_company" in reasons


def test_entity_consistency_case_and_punctuation_insensitive():
    score, _ = entity_consistency("Company A, Inc.", "company a inc")
    assert score == 1.0


def test_category_consistency_match():
    assert category_consistency(ClaimCategory.ENVIRONMENTAL, ClaimCategory.ENVIRONMENTAL) == 1.0


def test_category_consistency_mismatch_is_not_zero_and_not_a_hard_fail():
    score = category_consistency(ClaimCategory.ENVIRONMENTAL, ClaimCategory.SOCIAL)
    assert 0.0 < score < 1.0


def test_category_consistency_unknown_evidence_category_is_not_punished_harshly():
    score = category_consistency(ClaimCategory.ENVIRONMENTAL, None)
    assert score >= 0.5


def test_lexical_similarity_identical_text():
    assert lexical_similarity("Scope 1 emissions decreased by 20%.", "Scope 1 emissions decreased by 20%.") == 1.0


def test_lexical_similarity_unrelated_text_is_low():
    score = lexical_similarity("Scope 1 emissions decreased by 20%.", "The board has five independent directors.")
    assert score < 0.3


def test_run_consistency_checks_never_trusts_evidence_value_field_directly():
    # Evidence.value is set to match the CLAIM's value (as Phase 5's
    # extractor does for a claim's own source chunk), but evidence_text
    # states a DIFFERENT number -- the text must win, catching the
    # discrepancy rather than trusting the (possibly stale/copied) field.
    claim = build_claim(claim="Emissions decreased by 20%.", value=20.0, unit="%")
    evidence = Evidence(
        evidence_id="EVD-000001", source_type=SourceType.UPLOADED_REPORT, document_id="DOC-001",
        company="Example Company", report_year=2025, page_number=1, source_chunk_id="CHK-00001",
        evidence_text="Emissions decreased by 5% this year.",
        value=20.0, unit="%",  # copied from the claim by Phase 5's extractor -- must NOT be trusted
    )
    result, _, _ = run_consistency_checks(claim, evidence, verification_thresholds())
    assert result.numeric == 0.0
    assert "numeric_contradiction" in result.hard_fail_reasons
