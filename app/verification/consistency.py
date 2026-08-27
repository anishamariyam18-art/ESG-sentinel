"""Deterministic claim-vs-evidence consistency checks (sections 4-12, 18).

Every check here returns a float in [0.0, 1.0], not a bare bool -- so the
weighted scoring in scorer.py can reflect "how consistent", not just
"consistent or not". `run_consistency_checks` additionally collects hard-
fail reasons (section 18): conditions a high weighted score must never be
allowed to override.

Critical design point: evidence components are re-extracted independently
from `evidence.evidence_text`, never trusted from `Evidence.value`/`unit`/
`target_year`. For uploaded-report evidence, Phase 5's extractor copies
those fields straight from the claim that produced the record -- comparing
a claim's value against a copy of itself would trivially "match" every
time and defeat the entire point of numerical verification (section 6's
literal test case: claim says 20%, evidence says 5%, this MUST be caught).
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from app.claims.classifier import NumericInfo, extract_numeric_info, extract_target_info
from app.core.config import VerificationThresholds
from app.models.claim import Claim, ClaimCategory
from app.models.evidence import Evidence

_DECREASE_WORDS = ("decreas", "reduc", "declin", "fell", "fall", "lower", "cut", "drop", "shrink")
_INCREASE_WORDS = ("increas", "grew", "grow", "ris", "rose", "expand", "higher", "improv", "gain")

_BASELINE_YEAR_RE = re.compile(
    r"\b((?:19|20)\d{2})\s+baseline\b|\bbaseline\s+(?:year\s+)?(?:of\s+)?((?:19|20)\d{2})\b",
    re.IGNORECASE,
)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")


def _normalize_unit(unit: str | None) -> str | None:
    return unit.strip().lower() if unit else None


def _normalize_company(company: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", company.lower())


def detect_direction(text: str) -> str | None:
    """Returns "decrease", "increase", or None if absent/ambiguous (both
    or neither present) -- never guessed."""
    lowered = text.lower()
    has_decrease = any(w in lowered for w in _DECREASE_WORDS)
    has_increase = any(w in lowered for w in _INCREASE_WORDS)
    if has_decrease and not has_increase:
        return "decrease"
    if has_increase and not has_decrease:
        return "increase"
    return None


def extract_baseline_year(text: str) -> int | None:
    match = _BASELINE_YEAR_RE.search(text)
    if not match:
        return None
    year = int(match.group(1) or match.group(2))
    return year if 1900 <= year <= 2100 else None


class TextComponents(BaseModel):
    """Structured components extracted from a single piece of text (claim
    or evidence) -- section 4/5. Never invents a missing component: an
    absent field stays None."""

    entity: str
    metric: str | None = None
    direction: str | None = None
    value: float | None = None
    unit: str | None = None
    measurement_year: int | None = None
    baseline_year: int | None = None
    target_year: int | None = None
    category: ClaimCategory | None = None


def extract_claim_components(claim: Claim) -> TextComponents:
    baseline_year = extract_baseline_year(claim.claim)
    measurement_year = _extract_measurement_year(claim.claim, baseline_year, claim.target_year)
    return TextComponents(
        entity=claim.company,
        metric=claim.metric_name,
        direction=detect_direction(claim.claim),
        value=claim.value,
        unit=claim.unit,
        measurement_year=measurement_year,
        baseline_year=baseline_year,
        target_year=claim.target_year,
        category=claim.category,
    )


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")


def _split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if s.strip()]


def _most_relevant_segment(evidence_text: str, claim_text: str) -> str:
    """An evidence chunk (page-aware, per Phase 2) commonly bundles several
    distinct sentences/facts. Numeric/temporal extraction must operate on
    the sentence actually relevant to this claim, not the whole chunk --
    otherwise a chunk containing both a Scope 1 AND a Scope 2 figure looks
    numerically ambiguous even when the claim only concerns one of them.
    Picked deterministically by token overlap with the claim text, never a
    guess at which number matters."""
    sentences = _split_sentences(evidence_text)
    if len(sentences) <= 1:
        return evidence_text
    from app.evidence.lexical import tokenize

    claim_tokens = set(tokenize(claim_text))
    if not claim_tokens:
        return evidence_text
    return max(sentences, key=lambda s: len(claim_tokens & set(tokenize(s))))


def extract_evidence_components(evidence: Evidence, claim_text: str) -> TextComponents:
    """Independently re-derives numeric/temporal facts from the evidence
    text itself -- see module docstring for why this must never reuse
    `Evidence.value`/`unit`/`target_year` directly. Extraction runs on the
    sentence within the evidence chunk most relevant to `claim_text` (see
    `_most_relevant_segment`), not the whole chunk indiscriminately."""
    segment = _most_relevant_segment(evidence.evidence_text, claim_text)
    numeric: NumericInfo = extract_numeric_info(segment)
    _, target_year = extract_target_info(segment)
    baseline_year = extract_baseline_year(segment)
    measurement_year = _extract_measurement_year(segment, baseline_year, target_year)
    return TextComponents(
        entity=evidence.company,
        metric=numeric.metric_name,
        direction=detect_direction(segment),
        value=numeric.value,
        unit=numeric.unit,
        measurement_year=measurement_year,
        baseline_year=baseline_year,
        target_year=target_year,
        category=evidence.category,
    )


def _extract_measurement_year(text: str, baseline_year: int | None, target_year: int | None) -> int | None:
    """A bare year mentioned in the text that is neither the baseline nor
    the target year -- e.g. the "2025" in "2025 emissions decreased by
    20%." Returns the first such year, or None if every year found is
    already accounted for as baseline/target (or none is present)."""
    for year_str in _YEAR_RE.findall(text):
        year = int(year_str)
        if year != baseline_year and year != target_year:
            return year
    return None


class ConsistencyResult(BaseModel):
    numeric: float
    unit: float
    temporal: float
    entity: float
    category: float
    hard_fail_reasons: list[str] = []
    notes: list[str] = []


def numeric_consistency(claim: TextComponents, evidence: TextComponents, tolerance_pct: float) -> tuple[float, list[str]]:
    """Returns (score, hard_fail_reasons). Direction is folded in here: a
    claim/evidence pair with opposite stated directions is always a hard
    numeric contradiction, independent of how close the values happen to be."""
    reasons: list[str] = []

    if claim.direction and evidence.direction and claim.direction != evidence.direction:
        reasons.append("direction_contradiction")
        return 0.0, reasons

    if claim.value is None:
        return 1.0, reasons  # claim asserts no specific number -- nothing to contradict
    if evidence.value is None:
        return 0.3, reasons  # evidence doesn't state a comparable number -- weak, not zero

    if claim.unit and evidence.unit and _normalize_unit(claim.unit) != _normalize_unit(evidence.unit):
        return 0.0, reasons  # incompatible units -- unit_consistency() reports this separately too

    if claim.value == 0:
        deviation_pct = 0.0 if evidence.value == 0 else 100.0
    else:
        deviation_pct = abs(claim.value - evidence.value) / abs(claim.value) * 100

    if deviation_pct <= tolerance_pct:
        return 1.0, reasons
    if deviation_pct > tolerance_pct * 5:
        reasons.append("numeric_contradiction")
        return 0.0, reasons
    return max(0.0, 1.0 - (deviation_pct / (tolerance_pct * 5))), reasons


def unit_consistency(claim: TextComponents, evidence: TextComponents) -> tuple[float, list[str]]:
    if claim.unit is None:
        return 1.0, []
    if evidence.unit is None:
        return 0.5, []
    if _normalize_unit(claim.unit) == _normalize_unit(evidence.unit):
        return 1.0, []
    return 0.0, ["unit_incompatible"]


def temporal_consistency(
    claim: TextComponents, evidence: TextComponents, claim_report_year: int, evidence_report_year: int | None
) -> tuple[float, list[str]]:
    reasons: list[str] = []

    if claim.measurement_year is not None and evidence.measurement_year is not None:
        score = 1.0 if claim.measurement_year == evidence.measurement_year else 0.2
    else:
        score = 1.0 if evidence_report_year is None or claim_report_year == evidence_report_year else 0.6

    if claim.baseline_year and evidence.baseline_year and claim.baseline_year != evidence.baseline_year:
        score = min(score, 0.3)

    if claim.target_year and evidence.target_year and claim.target_year != evidence.target_year:
        score = min(score, 0.3)
        reasons.append("target_year_incompatible")

    return score, reasons


def entity_consistency(claim_company: str, evidence_company: str) -> tuple[float, list[str]]:
    if _normalize_company(claim_company) == _normalize_company(evidence_company):
        return 1.0, []
    return 0.0, ["wrong_company"]


def category_consistency(claim_category: ClaimCategory, evidence_category: ClaimCategory | None) -> float:
    if evidence_category is None or claim_category == ClaimCategory.UNKNOWN:
        return 0.7  # unknown on either side -- don't punish harshly, but not full credit
    return 1.0 if claim_category == evidence_category else 0.4  # never a hard fail (section 12)


def lexical_similarity(text_a: str, text_b: str) -> float:
    """Token-overlap (Jaccard) similarity -- a single-pair comparison, so
    BM25's corpus-relative IDF isn't meaningful here; reuses the same
    tokenizer as the lexical index so "Scope 1"/"tCO2e"-style terms count."""
    from app.evidence.lexical import tokenize

    tokens_a, tokens_b = set(tokenize(text_a)), set(tokenize(text_b))
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)


def run_consistency_checks(
    claim: Claim, evidence: Evidence, thresholds: VerificationThresholds
) -> tuple[ConsistencyResult, TextComponents, TextComponents]:
    claim_components = extract_claim_components(claim)
    evidence_components = extract_evidence_components(evidence, claim.claim)

    entity_score, entity_reasons = entity_consistency(claim.company, evidence.company)
    numeric_score, numeric_reasons = numeric_consistency(
        claim_components, evidence_components, thresholds.numerical_tolerance_pct
    )
    unit_score, unit_reasons = unit_consistency(claim_components, evidence_components)
    temporal_score, temporal_reasons = temporal_consistency(
        claim_components, evidence_components, claim.report_year, evidence.report_year
    )
    category_score = category_consistency(claim.category, evidence.category)

    hard_fail_reasons = entity_reasons + numeric_reasons + unit_reasons + temporal_reasons

    result = ConsistencyResult(
        numeric=numeric_score, unit=unit_score, temporal=temporal_score,
        entity=entity_score, category=category_score, hard_fail_reasons=hard_fail_reasons,
    )
    return result, claim_components, evidence_components
