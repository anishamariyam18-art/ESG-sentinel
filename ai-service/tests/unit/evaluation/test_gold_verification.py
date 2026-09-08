from app.evaluation.gold_verification import GOLD_VERIFICATION_CASES, evaluate_verification_gold_set


def test_gold_set_has_a_meaningful_number_of_cases():
    assert len(GOLD_VERIFICATION_CASES) >= 20


def test_gold_set_case_ids_are_unique():
    ids = [c.case_id for c in GOLD_VERIFICATION_CASES]
    assert len(ids) == len(set(ids))


def test_evaluate_verification_gold_set_returns_a_report():
    report = evaluate_verification_gold_set()
    assert report.total_cases == len(GOLD_VERIFICATION_CASES)
    assert 0.0 <= report.accuracy <= 1.0


def test_evaluate_verification_gold_set_meets_a_minimum_accuracy_bar():
    """Regression guard, not a claim of real-world accuracy (section 47) --
    every expected label was calibrated against this deterministic-only
    harness's actual, documented behavior (see the module docstring)."""
    report = evaluate_verification_gold_set()
    assert report.accuracy >= 0.85


def test_evaluate_verification_gold_set_is_deterministic():
    report_a = evaluate_verification_gold_set()
    report_b = evaluate_verification_gold_set()
    assert report_a.accuracy == report_b.accuracy
    assert report_a.confusion_matrix == report_b.confusion_matrix
