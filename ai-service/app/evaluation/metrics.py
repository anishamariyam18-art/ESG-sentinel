"""Generic multi-class classification metrics (Phase 10 sections 27, 29).

Computes accuracy, per-label precision/recall/F1, macro-averages, and a
confusion matrix from parallel `y_true`/`y_pred` label lists -- nothing
here is specific to verification or greenwashing; both evaluation harnesses
in this package call the same functions. No metric is ever asserted as
"scientifically valid" here -- that framing belongs to the caller
(section 47).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class LabelMetrics(BaseModel):
    label: str
    support: int = Field(ge=0, description="Number of true instances of this label")
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    false_negatives: int = Field(ge=0)
    precision: float = Field(ge=0.0, le=1.0)
    recall: float = Field(ge=0.0, le=1.0)
    f1: float = Field(ge=0.0, le=1.0)


class ClassificationReport(BaseModel):
    total_cases: int = Field(ge=0)
    accuracy: float = Field(ge=0.0, le=1.0)
    macro_precision: float = Field(ge=0.0, le=1.0)
    macro_recall: float = Field(ge=0.0, le=1.0)
    macro_f1: float = Field(ge=0.0, le=1.0)
    per_label: list[LabelMetrics] = Field(default_factory=list)
    confusion_matrix: dict[str, dict[str, int]] = Field(
        default_factory=dict, description="confusion_matrix[true_label][predicted_label] = count"
    )


def _safe_div(numerator: float, denominator: float) -> float:
    return round(numerator / denominator, 4) if denominator > 0 else 0.0


def compute_confusion_matrix(y_true: list[str], y_pred: list[str], labels: list[str]) -> dict[str, dict[str, int]]:
    matrix = {true_label: {pred_label: 0 for pred_label in labels} for true_label in labels}
    for true_label, pred_label in zip(y_true, y_pred):
        matrix[true_label][pred_label] += 1
    return matrix


def compute_classification_report(y_true: list[str], y_pred: list[str], labels: list[str] | None = None) -> ClassificationReport:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must be the same length")
    if not y_true:
        return ClassificationReport(total_cases=0, accuracy=0.0, macro_precision=0.0, macro_recall=0.0, macro_f1=0.0)

    labels = labels or sorted(set(y_true) | set(y_pred))
    matrix = compute_confusion_matrix(y_true, y_pred, labels)

    correct = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    accuracy = _safe_div(correct, len(y_true))

    per_label: list[LabelMetrics] = []
    for label in labels:
        tp = matrix[label][label]
        fn = sum(matrix[label][other] for other in labels if other != label)
        fp = sum(matrix[other][label] for other in labels if other != label)
        support = tp + fn
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        per_label.append(LabelMetrics(
            label=label, support=support, true_positives=tp, false_positives=fp, false_negatives=fn,
            precision=precision, recall=recall, f1=f1,
        ))

    macro_precision = _safe_div(sum(m.precision for m in per_label), len(per_label))
    macro_recall = _safe_div(sum(m.recall for m in per_label), len(per_label))
    macro_f1 = _safe_div(sum(m.f1 for m in per_label), len(per_label))

    return ClassificationReport(
        total_cases=len(y_true), accuracy=accuracy, macro_precision=macro_precision,
        macro_recall=macro_recall, macro_f1=macro_f1, per_label=per_label, confusion_matrix=matrix,
    )
