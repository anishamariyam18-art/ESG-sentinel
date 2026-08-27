from app.claims.classifier import (
    ClaimClassifier,
    classify_deterministic,
    compute_claim_confidence,
    deterministic_category,
    deterministic_claim_type,
    extract_numeric_info,
    extract_target_info,
)
from app.models.claim import ClaimCategory, ClaimType
from tests.unit.claims.conftest import classification_batch_json, claims_config, confidence_weights, make_manager


def test_environmental_metric_classified_deterministically():
    result = classify_deterministic("Scope 1 emissions decreased by 20% from the 2020 baseline.")
    assert result is not None
    assert result.category == ClaimCategory.ENVIRONMENTAL
    assert result.claim_type == ClaimType.PERFORMANCE


def test_commitment_classified_deterministically():
    result = classify_deterministic("We aim to achieve net zero emissions by 2050.")
    assert result is not None
    assert result.category == ClaimCategory.ENVIRONMENTAL
    assert result.claim_type == ClaimType.COMMITMENT


def test_social_metric_classified_deterministically():
    result = classify_deterministic("Women represented 42% of our global workforce.")
    assert result is not None
    assert result.category == ClaimCategory.SOCIAL
    assert result.claim_type == ClaimType.METRIC


def test_governance_claim_category_is_preserved_even_if_type_is_general():
    category = deterministic_category("The board has five independent directors.")
    assert category == ClaimCategory.GOVERNANCE


def test_certification_claim_type_detected_deterministically():
    # "ISO 14001 certified" has no E/S/G category keyword by itself, so the
    # *type* resolves deterministically while category is left for the LLM
    # fallback -- classify_deterministic only returns a result when BOTH
    # resolve, so it correctly returns None here.
    assert deterministic_claim_type("Our facility is ISO 14001 certified.") == ClaimType.CERTIFICATION
    assert classify_deterministic("Our facility is ISO 14001 certified.") is None


def test_policy_claim_classified_deterministically():
    result = classify_deterministic("We maintain an environmental policy covering all operations.")
    assert result is not None
    assert result.claim_type == ClaimType.POLICY


def test_compliance_claim_classified_deterministically():
    result = classify_deterministic("We comply with applicable environmental regulations in all regions.")
    assert result is not None
    assert result.claim_type == ClaimType.COMPLIANCE


def test_ambiguous_text_has_no_confident_deterministic_category():
    # No environmental/social/governance keyword at all.
    assert deterministic_category("We opened three new offices this year.") is None


def test_ambiguous_claim_type_without_number_or_keyword():
    assert deterministic_claim_type("We continue to prioritize sustainability across the business.") is None


def test_extract_numeric_info_preserves_value_and_unit():
    info = extract_numeric_info("Scope 1 emissions decreased by 18%.")
    assert info.value == 18
    assert info.unit == "%"


def test_extract_numeric_info_preserves_mass_unit():
    info = extract_numeric_info("Scope 2 emissions were 45,000 tCO2e in 2025.")
    assert info.value == 45000
    assert info.unit == "tCO2e"


def test_extract_numeric_info_does_not_guess_when_multiple_numbers_present():
    info = extract_numeric_info("Emissions fell from 100 tCO2e to 90 tCO2e this year.")
    assert info.value is None
    assert info.unit is None


def test_extract_target_year_from_by_phrase():
    target_text, target_year = extract_target_info("We aim to achieve net zero emissions by 2050.")
    assert target_year == 2050
    assert target_text is not None


def test_extract_target_year_ignores_baseline_year():
    # "by 18%" and "2020 baseline" must NOT be misread as a 2020 target.
    target_text, target_year = extract_target_info(
        "Scope 1 emissions decreased by 18% from the 2020 baseline."
    )
    assert target_year is None
    assert target_text is None


def test_compute_claim_confidence_bounded_zero_to_one():
    from app.claims.classifier import NumericInfo

    confidence = compute_claim_confidence(
        claim_text="Scope 1 emissions decreased by 18%.", provenance_complete=True,
        classification_confidence=0.9, numeric_info=NumericInfo(value=18, unit="%"),
        claim_type=ClaimType.PERFORMANCE, weights=confidence_weights(),
    )
    assert 0.0 <= confidence <= 1.0


def test_compute_claim_confidence_lower_when_numeric_expected_but_missing():
    from app.claims.classifier import NumericInfo

    with_number = compute_claim_confidence(
        claim_text="Scope 1 emissions decreased by 18%.", provenance_complete=True,
        classification_confidence=0.9, numeric_info=NumericInfo(value=18, unit="%"),
        claim_type=ClaimType.METRIC, weights=confidence_weights(),
    )
    without_number = compute_claim_confidence(
        claim_text="Scope 1 emissions decreased significantly.", provenance_complete=True,
        classification_confidence=0.9, numeric_info=NumericInfo(), claim_type=ClaimType.METRIC,
        weights=confidence_weights(),
    )
    assert without_number < with_number


def test_llm_fallback_used_for_ambiguous_claim():
    manager, provider = make_manager(
        [classification_batch_json([
            {"index": 1, "category": "Social", "claim_type": "General", "confidence": 0.7, "reason": "test"}
        ])],
        max_retries=0,
    )
    classifier = ClaimClassifier(manager, claims_config(max_schema_retries=0))
    results = classifier.classify(["We opened three new offices this year."], "DOC-001")
    assert results[0].category == ClaimCategory.SOCIAL
    assert len(provider.calls) == 1


def test_deterministic_claims_never_trigger_an_llm_call():
    manager, provider = make_manager([], max_retries=0)
    classifier = ClaimClassifier(manager, claims_config(max_schema_retries=0))
    results = classifier.classify(["Scope 1 emissions decreased by 20%."], "DOC-001")
    assert results[0].category == ClaimCategory.ENVIRONMENTAL
    assert provider.calls == []


def test_llm_classification_failure_falls_back_to_unknown_honestly():
    manager, _ = make_manager(["not json {{{"], max_retries=0)
    classifier = ClaimClassifier(manager, claims_config(max_schema_retries=0))
    results = classifier.classify(["We opened three new offices this year."], "DOC-001")
    assert results[0].category == ClaimCategory.UNKNOWN
    assert results[0].claim_type == ClaimType.GENERAL
    assert results[0].confidence == 0.0
