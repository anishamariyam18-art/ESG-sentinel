import pytest

from app.evaluation.metrics import compute_classification_report, compute_confusion_matrix


def test_perfect_predictions_give_accuracy_1():
    y_true = ["A", "B", "A", "B"]
    y_pred = ["A", "B", "A", "B"]
    report = compute_classification_report(y_true, y_pred)
    assert report.accuracy == 1.0
    assert report.macro_f1 == 1.0


def test_all_wrong_predictions_give_accuracy_0():
    y_true = ["A", "A", "A"]
    y_pred = ["B", "B", "B"]
    report = compute_classification_report(y_true, y_pred, labels=["A", "B"])
    assert report.accuracy == 0.0


def test_confusion_matrix_counts_are_exact():
    y_true = ["A", "A", "B", "B"]
    y_pred = ["A", "B", "B", "B"]
    matrix = compute_confusion_matrix(y_true, y_pred, labels=["A", "B"])
    assert matrix["A"]["A"] == 1
    assert matrix["A"]["B"] == 1
    assert matrix["B"]["B"] == 2
    assert matrix["B"]["A"] == 0


def test_per_label_precision_recall_f1():
    # Label "A": 2 true instances, predicted correctly once (recall 0.5),
    # predicted "A" twice total with 1 correct (precision 0.5).
    y_true = ["A", "A", "B", "B"]
    y_pred = ["A", "B", "A", "B"]
    report = compute_classification_report(y_true, y_pred, labels=["A", "B"])
    label_a = next(m for m in report.per_label if m.label == "A")
    assert label_a.support == 2
    assert label_a.precision == 0.5
    assert label_a.recall == 0.5
    assert label_a.f1 == 0.5


def test_empty_input_gives_zero_report_not_a_crash():
    report = compute_classification_report([], [])
    assert report.total_cases == 0
    assert report.accuracy == 0.0


def test_mismatched_lengths_raise():
    with pytest.raises(ValueError):
        compute_classification_report(["A"], ["A", "B"])


def test_labels_inferred_when_not_provided():
    report = compute_classification_report(["X", "Y"], ["X", "X"])
    labels = {m.label for m in report.per_label}
    assert labels == {"X", "Y"}
