"""Hybrid claim classification: deterministic rules first, LLM only for
genuinely ambiguous cases (section 18). Also owns deterministic numeric/
target extraction (section 15/16) and the documented claim confidence
methodology (section 20) -- an LLM-reported classification confidence is
only one input signal, never the final claim confidence.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field, ValidationError

from app.claims.prompt import build_classification_prompt
from app.claims.validator import ESG_CATEGORY_KEYWORDS, esg_relevance_score, is_esg_relevant
from app.core.config import ClaimConfidenceWeights, ClaimsConfig
from app.core.llm import LLMGenerationError, LLMJsonError, LLMManager
from app.core.logging import get_logger
from app.models.claim import ClaimCategory, ClaimType

logger = get_logger(__name__)

# --- Claim-type deterministic signals ---
_CERTIFICATION_KEYWORDS = ("certified", "certification", "iso 1", "iso 2", "iso 5", "leed", "certif")
_COMMITMENT_PHRASES = (
    "will achieve", "plans to", "plan to", "committed to", "commits to",
    "aims to", "aim to", "intends to", "intend to", "pledged to",
    "pledges to", "targeting",
)
_COMPLIANCE_KEYWORDS = ("comply", "compliant", "compliance with", "adhere to", "in accordance with", "adherence to")
_POLICY_KEYWORDS = ("policy", "policies", "guideline")
_CHANGE_VERBS = (
    "decreased", "decrease", "increased", "increase", "reduced", "reduction",
    "improved", "declined", "grew", "growth", "rose", "fell", "cut", "lowered",
    "raised", "expanded",
)
_HAS_DIGIT_RE = re.compile(r"\d")

# --- Numeric extraction ---
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_MASS_RE = re.compile(
    r"(\d+(?:,\d{3})*(?:\.\d+)?)\s*(tCO2e|tonnes?|kg|MWh|GWh|kWh|liters?|litres?)", re.IGNORECASE
)
_COUNT_RE = re.compile(
    r"(\d+(?:,\d{3})*)\s+(employees|people|staff|workers|members|directors|hours)", re.IGNORECASE
)
_KNOWN_METRIC_PHRASES = (
    "scope 1 emissions", "scope 2 emissions", "scope 3 emissions", "ghg emissions",
    "renewable energy", "renewable electricity", "water usage", "water consumption",
    "waste", "training hours", "women", "board independence", "independent directors",
)

_TARGET_YEAR_RE = re.compile(
    r"\bby\s+(?:the\s+year\s+)?((?:19|20)\d{2})\b"
    r"|\btarget(?:ing)?\s+(?:of\s+|for\s+)?(?:the\s+year\s+)?((?:19|20)\d{2})\b",
    re.IGNORECASE,
)


class ClassificationResult(BaseModel):
    category: ClaimCategory
    claim_type: ClaimType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class NumericInfo(BaseModel):
    metric_name: str | None = None
    value: float | None = None
    unit: str | None = None


def _parse_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def extract_numeric_info(text: str) -> NumericInfo:
    """Deterministic numeric extraction. If more than one distinct numeric
    fact is present (splitting should normally have separated these, but a
    candidate may still slip through with two numbers), value/unit are left
    unset rather than guessing which one is "the" value."""
    matches: list[tuple[float, str]] = []
    matches += [(_parse_number(v), "%") for v in _PERCENT_RE.findall(text)]
    matches += [(_parse_number(v), unit) for v, unit in _MASS_RE.findall(text)]
    matches += [(_parse_number(v), unit.lower()) for v, unit in _COUNT_RE.findall(text)]

    if len(matches) != 1:
        return NumericInfo()

    value, unit = matches[0]
    lowered = text.lower()
    metric_name = next((phrase for phrase in _KNOWN_METRIC_PHRASES if phrase in lowered), None)
    return NumericInfo(metric_name=metric_name, value=value, unit=unit)


def extract_target_info(text: str) -> tuple[str | None, int | None]:
    """Returns (target_text, target_year). target_text mirrors the claim
    text verbatim (never rewritten) when a target-context year is found."""
    match = _TARGET_YEAR_RE.search(text)
    if not match:
        return None, None
    year = int(match.group(1) or match.group(2))
    if not (1900 <= year <= 2100):
        return None, None
    return text.strip(), year


def deterministic_category(text: str) -> ClaimCategory | None:
    lowered = text.lower()
    hits = {
        category: sum(1 for kw in keywords if kw in lowered)
        for category, keywords in ESG_CATEGORY_KEYWORDS.items()
    }
    matching = [c for c, count in hits.items() if count > 0]
    if len(matching) == 1:
        return matching[0]
    return None  # zero or multiple categories matched -- ambiguous, don't guess


def deterministic_claim_type(text: str) -> ClaimType | None:
    lowered = text.lower()
    if any(kw in lowered for kw in _CERTIFICATION_KEYWORDS):
        return ClaimType.CERTIFICATION
    if any(kw in lowered for kw in _COMMITMENT_PHRASES):
        return ClaimType.COMMITMENT
    if any(kw in lowered for kw in _COMPLIANCE_KEYWORDS):
        return ClaimType.COMPLIANCE
    if any(kw in lowered for kw in _POLICY_KEYWORDS):
        return ClaimType.POLICY

    has_number = bool(_HAS_DIGIT_RE.search(text))
    has_change_verb = any(v in lowered for v in _CHANGE_VERBS)
    if has_change_verb and has_number:
        return ClaimType.PERFORMANCE
    if has_number:
        return ClaimType.METRIC
    return None  # ambiguous -- don't guess


def classify_deterministic(text: str) -> ClassificationResult | None:
    """Returns a confident classification only when BOTH category and
    claim_type are unambiguous by rule; otherwise None (caller falls back
    to the LLM for this claim)."""
    category = deterministic_category(text)
    claim_type = deterministic_claim_type(text)
    if category is None or claim_type is None:
        return None
    return ClassificationResult(
        category=category, claim_type=claim_type, confidence=0.9,
        reason="Matched deterministic category and claim-type rules.",
    )


class ClaimClassifier:
    def __init__(self, llm_manager: LLMManager, config: ClaimsConfig) -> None:
        self._llm = llm_manager
        self._config = config

    def classify(self, texts: list[str], document_id: str) -> list[ClassificationResult]:
        """Classifies every text: deterministic rule first, then LLM in
        batches for whatever remains ambiguous. Order-preserving."""
        results: list[ClassificationResult | None] = [classify_deterministic(t) for t in texts]
        ambiguous_indices = [i for i, r in enumerate(results) if r is None]

        for start in range(0, len(ambiguous_indices), self._config.max_classification_batch_size):
            batch_indices = ambiguous_indices[start : start + self._config.max_classification_batch_size]
            batch_texts = [texts[i] for i in batch_indices]
            batch_results = self._classify_via_llm(batch_texts, document_id)
            for i, result in zip(batch_indices, batch_results):
                results[i] = result

        return [r if r is not None else _unknown_fallback() for r in results]

    def _classify_via_llm(self, texts: list[str], document_id: str) -> list[ClassificationResult]:
        prompt = build_classification_prompt(texts)
        attempts = self._config.max_schema_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                raw_json, _ = self._llm.generate_json(prompt)
            except (LLMJsonError, LLMGenerationError) as exc:
                last_error = exc
                logger.warning(
                    "claim_classification_call_failed",
                    extra={"document_id": document_id, "attempt": attempt},
                )
                continue

            try:
                parsed = _LLMClassificationBatch.model_validate(raw_json)
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "claim_classification_schema_invalid",
                    extra={"document_id": document_id, "attempt": attempt},
                )
                continue

            by_index = {item.index: item for item in parsed.classifications}
            return [
                ClassificationResult(
                    category=by_index[i + 1].category,
                    claim_type=by_index[i + 1].claim_type,
                    confidence=by_index[i + 1].confidence,
                    reason=by_index[i + 1].reason,
                )
                if (i + 1) in by_index
                else _unknown_fallback()
                for i in range(len(texts))
            ]

        logger.warning(
            "claim_classification_failed_using_fallback",
            extra={"document_id": document_id, "error": str(last_error), "claim_count": len(texts)},
        )
        return [_unknown_fallback() for _ in texts]


class _LLMClassificationItem(BaseModel):
    index: int = Field(ge=1)
    category: ClaimCategory
    claim_type: ClaimType
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = ""


class _LLMClassificationBatch(BaseModel):
    classifications: list[_LLMClassificationItem] = Field(default_factory=list)


def _unknown_fallback() -> ClassificationResult:
    return ClassificationResult(
        category=ClaimCategory.UNKNOWN, claim_type=ClaimType.GENERAL, confidence=0.0,
        reason="Could not be confidently classified by rules or the LLM; defaulted honestly to Unknown/General.",
    )


def compute_claim_confidence(
    claim_text: str,
    provenance_complete: bool,
    classification_confidence: float,
    numeric_info: NumericInfo,
    claim_type: ClaimType,
    weights: ClaimConfidenceWeights,
) -> float:
    """Documented, deterministic confidence -- an LLM-reported
    classification confidence contributes only the classification_certainty
    component, never the whole score."""
    relevance = esg_relevance_score(claim_text) if is_esg_relevant(claim_text) else 0.0

    numeric_expected = claim_type in (ClaimType.METRIC, ClaimType.PERFORMANCE)
    if not numeric_expected:
        numerical_clarity = 1.0  # no number required for this claim type
    elif numeric_info.value is not None and numeric_info.unit is not None:
        numerical_clarity = 1.0
    else:
        numerical_clarity = 0.3  # expected a clear number but didn't get one

    word_count = len(claim_text.split())
    claim_completeness = min(1.0, word_count / 6) if word_count > 0 else 0.0

    score = (
        relevance * weights.esg_relevance
        + (1.0 if provenance_complete else 0.0) * weights.provenance_completeness
        + classification_confidence * weights.classification_certainty
        + numerical_clarity * weights.numerical_clarity
        + claim_completeness * weights.claim_completeness
    )
    return round(min(1.0, max(0.0, score)), 3)
