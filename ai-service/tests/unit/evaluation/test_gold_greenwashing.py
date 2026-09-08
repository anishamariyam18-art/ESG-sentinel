from app.evaluation.gold_greenwashing import GOLD_GREENWASHING_CASES, evaluate_greenwashing_gold_set


def test_gold_set_has_a_meaningful_number_of_cases():
    assert len(GOLD_GREENWASHING_CASES) >= 10


def test_gold_set_case_ids_are_unique():
    ids = [c.case_id for c in GOLD_GREENWASHING_CASES]
    assert len(ids) == len(set(ids))


def test_gold_set_covers_every_required_category():
    """Section 29 requires: no signal, vague, exaggerated, contradictory,
    unsupported environmental benefit, absolute."""
    from app.models.greenwashing import GreenwashingType

    covered = {c.expected_primary_type for c in GOLD_GREENWASHING_CASES}
    required = {
        GreenwashingType.NO_SIGNIFICANT_SIGNAL, GreenwashingType.VAGUE_CLAIM, GreenwashingType.EXAGGERATED_CLAIM,
        GreenwashingType.CONTRADICTORY_CLAIM, GreenwashingType.UNSUBSTANTIATED_BENEFIT, GreenwashingType.ABSOLUTE_CLAIM,
    }
    assert required <= covered


def test_evaluate_greenwashing_gold_set_returns_a_report():
    report = evaluate_greenwashing_gold_set()
    assert report.total_cases == len(GOLD_GREENWASHING_CASES)
    assert 0.0 <= report.accuracy <= 1.0


def test_evaluate_greenwashing_gold_set_meets_a_minimum_accuracy_bar():
    report = evaluate_greenwashing_gold_set()
    assert report.accuracy >= 0.85


def test_evaluate_greenwashing_gold_set_is_deterministic():
    report_a = evaluate_greenwashing_gold_set()
    report_b = evaluate_greenwashing_gold_set()
    assert report_a.accuracy == report_b.accuracy
    assert report_a.confusion_matrix == report_b.confusion_matrix


def test_unsupported_alone_does_not_default_to_a_greenwashing_label():
    """Section 14: Unsupported != Greenwashing. G003 has no vague/absolute/
    exaggerated/contradictory signal at all -- only the explicit
    'Unsupported Environmental Claim' label, never a generic one."""
    from app.models.greenwashing import GreenwashingType

    case = next(c for c in GOLD_GREENWASHING_CASES if c.case_id == "G003")
    assert case.expected_primary_type == GreenwashingType.UNSUPPORTED_ENVIRONMENTAL_CLAIM
