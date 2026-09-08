"""Deterministic greenwashing signal detectors (sections 5-12, 22).

Every detector returns a `DetectorSignal` -- `detected`/`severity`/`details`
-- never a bare classification. These are SIGNALS, not proof: a detected
signal contributes to the weighted score (scorer.py) and is never, by
itself, sufficient to declare greenwashing. Numeric/unit/temporal/entity
comparison reuses Phase 6's `app.verification.consistency` module directly
rather than re-implementing it -- same extraction, same "never trust
Evidence.value/unit directly" guarantee.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.models.claim import Claim
from app.models.evidence import Evidence
from app.verification.consistency import (
    TextComponents,
    extract_baseline_year,
    extract_claim_components,
    extract_evidence_components,
    numeric_consistency,
    temporal_consistency,
    unit_consistency,
)


class DetectorSignal(BaseModel):
    signal: str
    detected: bool
    severity: float = Field(ge=0.0, le=1.0)
    details: str = ""


def _find_phrase(text_lower: str, phrases: tuple[str, ...]) -> str | None:
    """Word-boundary phrase match -- plain substring `in` checks would let
    a short keyword like "green" false-positive inside "greener" or
    "greenhouse", which is exactly the kind of over-triggering this module
    must avoid (a false vague/benefit signal can flip risk level)."""
    found = [p for p in phrases if re.search(rf"\b{re.escape(p)}\b", text_lower)]
    return max(found, key=len) if found else None


def _no_signal(name: str) -> DetectorSignal:
    return DetectorSignal(signal=name, detected=False, severity=0.0, details="")


# --- Vague / absolute / benefit / comparison language -------------------

_VAGUE_PHRASES = (
    "eco-friendly", "eco friendly", "environmentally friendly", "planet positive",
    "climate positive", "greener future", "better for the planet",
    "kinder to the environment", "green future", "sustainable future",
    "committed to sustainability", "green", "clean", "sustainable",
)

_ABSOLUTE_PHRASES = (
    "100% sustainable", "zero impact", "completely green", "completely sustainable",
    "completely environmentally friendly", "fully environmentally friendly",
    "fully sustainable", "carbon neutral", "zero emissions", "no environmental impact",
    "totally sustainable", "net zero", "zero waste", "entirely sustainable",
    "completely carbon neutral", "no impact on the environment",
)

_BENEFIT_KEYWORDS = (
    "reduces", "reduced", "improves", "improved", "protects", "restores",
    "eco-friendly", "environmentally friendly", "sustainable", "green",
    "planted", "conserves", "saves", "benefits the environment",
    "helps the planet", "positive impact", "gives back",
)

_COMPARISON_RE = re.compile(
    r"\b\d+%?\s+(greener|more sustainable|better)\b"
    r"|\btwice as (sustainable|green)\b"
    r"|\bindustry[- ]leading\b"
    r"|\bbest[- ]in[- ]class\b"
    r"|\bbest environmental performance\b",
    re.IGNORECASE,
)
_COMPARISON_BASIS_WORDS = ("industry average", "competitor", "peer", "benchmark", "compared to", "versus", "vs.")

_SCOPE_RE = re.compile(r"scope\s*[123]", re.IGNORECASE)
_INCREASE_WORDS = ("increas", "grew", "grow", "ris", "rose", "expand", "higher")
_DECREASE_WORDS = ("decreas", "reduc", "declin", "fell", "fall", "lower", "cut", "drop")


def detect_vague_language(claim_text: str) -> DetectorSignal:
    """A vague phrase counts only when the claim lacks its own numeric
    specificity (a number/percentage) -- a claim that's both promotional
    AND quantified isn't vague in the sense this signal means (section 5:
    "without measurable/supporting context")."""
    phrase = _find_phrase(claim_text.lower(), _VAGUE_PHRASES)
    if phrase is None:
        return _no_signal("vague_language")
    has_number = bool(re.search(r"\d", claim_text))
    if has_number:
        return _no_signal("vague_language")
    return DetectorSignal(
        signal="vague_language", detected=True, severity=0.6,
        details=f"The claim uses the promotional phrase '{phrase}' without a measurable metric, target, or timeframe.",
    )


def detect_absolute_language(claim_text: str) -> DetectorSignal:
    phrase = _find_phrase(claim_text.lower(), _ABSOLUTE_PHRASES)
    if phrase is None:
        return _no_signal("absolute_language")
    return DetectorSignal(
        signal="absolute_language", detected=True, severity=0.5,
        details=f"The claim uses absolute language ('{phrase}'), which warrants additional scrutiny of the supporting evidence.",
    )


def detect_unsupported_benefit(claim_text: str, has_evidence: bool) -> DetectorSignal:
    has_benefit_language = _find_phrase(claim_text.lower(), _BENEFIT_KEYWORDS) is not None
    if not has_benefit_language or has_evidence:
        return _no_signal("unsupported_benefit")
    return DetectorSignal(
        signal="unsupported_benefit", detected=True, severity=0.4,
        details="The claim asserts a positive environmental outcome, but no supporting evidence was found in the available information.",
    )


def detect_misleading_comparison(claim_text: str, evidence_text: str | None) -> DetectorSignal:
    match = _COMPARISON_RE.search(claim_text)
    if not match:
        return _no_signal("misleading_comparison")
    haystack = (evidence_text or "").lower()
    has_basis = any(w in haystack for w in _COMPARISON_BASIS_WORDS)
    if has_basis:
        return DetectorSignal(
            signal="misleading_comparison", detected=False, severity=0.1,
            details="A comparison basis was found in the available evidence.",
        )
    return DetectorSignal(
        signal="misleading_comparison", detected=True, severity=0.6,
        details=f"The claim makes a comparison ('{match.group(0)}') without a substantiated basis in the available evidence.",
    )


# --- Numeric/unit/temporal/direction (reusing Phase 6 consistency) ------

def detect_numerical_mismatch(
    claim_components: TextComponents, evidence_components: TextComponents, tolerance_pct: float
) -> DetectorSignal:
    score, reasons = numeric_consistency(claim_components, evidence_components, tolerance_pct)
    if "direction_contradiction" in reasons or score >= 0.99:
        return _no_signal("numerical_mismatch")
    if claim_components.value is None or evidence_components.value is None:
        return _no_signal("numerical_mismatch")
    severity = round(1.0 - score, 3)
    if severity < 0.05:
        return _no_signal("numerical_mismatch")
    return DetectorSignal(
        signal="numerical_mismatch", detected=True, severity=severity,
        details=(
            f"The claim states {claim_components.value}{claim_components.unit or ''}; "
            f"the evidence states {evidence_components.value}{evidence_components.unit or ''}."
        ),
    )


def _with_article(word: str) -> str:
    return f"an {word}" if word[:1].lower() in "aeiou" else f"a {word}"


def detect_direction_mismatch(claim_components: TextComponents, evidence_components: TextComponents) -> DetectorSignal:
    if not claim_components.direction or not evidence_components.direction:
        return _no_signal("direction_mismatch")
    if claim_components.direction == evidence_components.direction:
        return _no_signal("direction_mismatch")
    return DetectorSignal(
        signal="direction_mismatch", detected=True, severity=0.9,
        details=(
            f"The claim describes {_with_article(claim_components.direction)}, but the evidence describes "
            f"{_with_article(evidence_components.direction)} -- an opposite-direction contradiction."
        ),
    )


def detect_unit_mismatch(claim_components: TextComponents, evidence_components: TextComponents) -> DetectorSignal:
    score, reasons = unit_consistency(claim_components, evidence_components)
    if "unit_incompatible" not in reasons:
        return _no_signal("unit_mismatch")
    return DetectorSignal(
        signal="unit_mismatch", detected=True, severity=0.7,
        details=f"The claim uses unit '{claim_components.unit}' while the evidence uses '{evidence_components.unit}' -- these are not interchangeable.",
    )


def detect_target_year_mismatch(
    claim_components: TextComponents, evidence_components: TextComponents, claim_report_year: int, evidence_report_year: int | None
) -> DetectorSignal:
    _score, reasons = temporal_consistency(claim_components, evidence_components, claim_report_year, evidence_report_year)
    if "target_year_incompatible" not in reasons:
        return _no_signal("target_year_mismatch")
    return DetectorSignal(
        signal="target_year_mismatch", detected=True, severity=0.6,
        details=f"The claim states a target year of {claim_components.target_year}, but the evidence states {evidence_components.target_year}.",
    )


_PARTIAL_PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def detect_absolute_contradiction(claim_text: str, evidence_text: str) -> DetectorSignal:
    """An absolute/complete claim ("zero waste", "100% sustainable")
    contradicted by a partial figure in the evidence (e.g. "60% diverted
    from landfill") -- catches contradictions numeric extraction alone
    would miss because "zero"/"completely" aren't parsed as literal
    numbers."""
    if _find_phrase(claim_text.lower(), _ABSOLUTE_PHRASES) is None:
        return _no_signal("absolute_contradiction")
    for pct_str in _PARTIAL_PCT_RE.findall(evidence_text):
        pct = float(pct_str)
        if 1.0 <= pct <= 95.0:
            return DetectorSignal(
                signal="absolute_contradiction", detected=True, severity=0.85,
                details=(
                    f"The claim uses absolute/complete language, but the evidence states a partial "
                    f"figure of {pct_str}%, which is inconsistent with a complete outcome."
                ),
            )
    return _no_signal("absolute_contradiction")


def detect_missing_qualification(claim_text: str, evidence_text: str) -> DetectorSignal:
    evidence_baseline = extract_baseline_year(evidence_text)
    claim_baseline = extract_baseline_year(claim_text)
    if evidence_baseline and not claim_baseline:
        return DetectorSignal(
            signal="missing_qualification", detected=True, severity=0.5,
            details=f"The evidence qualifies the figure as relative to a {evidence_baseline} baseline, but the claim omits this qualification.",
        )
    return _no_signal("missing_qualification")


def detect_selective_presentation(claim_text: str, evidence_text: str) -> DetectorSignal:
    """Flags only when the evidence ITSELF supplies a clear basis: it names
    a specific scope the claim's general wording omits, and mentions
    differing directions across scopes (section 11 -- never inferred from
    outside knowledge)."""
    claim_scopes = {m.group(0).lower() for m in _SCOPE_RE.finditer(claim_text)}
    evidence_scopes = {m.group(0).lower() for m in _SCOPE_RE.finditer(evidence_text)}
    if claim_scopes or len(evidence_scopes) < 2:
        return _no_signal("selective_presentation")

    lowered = evidence_text.lower()
    has_increase = any(w in lowered for w in _INCREASE_WORDS)
    has_decrease = any(w in lowered for w in _DECREASE_WORDS)
    if not (has_increase and has_decrease):
        return _no_signal("selective_presentation")

    return DetectorSignal(
        signal="selective_presentation", detected=True, severity=0.7,
        details=(
            f"The evidence reports differing directions across {', '.join(sorted(evidence_scopes))}, "
            "but the claim does not mention this scope-specific breakdown."
        ),
    )


class DetectorReport(BaseModel):
    claim_components: TextComponents
    evidence_components: TextComponents | None = None
    vague_language: DetectorSignal
    absolute_language: DetectorSignal
    unsupported_benefit: DetectorSignal
    misleading_comparison: DetectorSignal
    numerical_mismatch: DetectorSignal
    direction_mismatch: DetectorSignal
    unit_mismatch: DetectorSignal
    target_year_mismatch: DetectorSignal
    absolute_contradiction: DetectorSignal
    missing_qualification: DetectorSignal
    selective_presentation: DetectorSignal

    def all_signals(self) -> list[DetectorSignal]:
        return [
            self.vague_language, self.absolute_language, self.unsupported_benefit,
            self.misleading_comparison, self.numerical_mismatch, self.direction_mismatch,
            self.unit_mismatch, self.target_year_mismatch, self.absolute_contradiction,
            self.missing_qualification, self.selective_presentation,
        ]

    def any_detected(self) -> bool:
        return any(s.detected for s in self.all_signals())


def run_detectors(
    claim: Claim, best_evidence: Evidence | None, numerical_tolerance_pct: float
) -> DetectorReport:
    claim_components = extract_claim_components(claim)
    has_evidence = best_evidence is not None
    evidence_text = best_evidence.evidence_text if best_evidence else None

    if best_evidence is not None:
        evidence_components = extract_evidence_components(best_evidence, claim.claim)
        numerical_mismatch = detect_numerical_mismatch(claim_components, evidence_components, numerical_tolerance_pct)
        direction_mismatch = detect_direction_mismatch(claim_components, evidence_components)
        unit_mismatch = detect_unit_mismatch(claim_components, evidence_components)
        target_year_mismatch = detect_target_year_mismatch(
            claim_components, evidence_components, claim.report_year, best_evidence.report_year
        )
        absolute_contradiction = detect_absolute_contradiction(claim.claim, evidence_text)
        missing_qualification = detect_missing_qualification(claim.claim, evidence_text)
        selective_presentation = detect_selective_presentation(claim.claim, evidence_text)
    else:
        evidence_components = None
        numerical_mismatch = _no_signal("numerical_mismatch")
        direction_mismatch = _no_signal("direction_mismatch")
        unit_mismatch = _no_signal("unit_mismatch")
        target_year_mismatch = _no_signal("target_year_mismatch")
        absolute_contradiction = _no_signal("absolute_contradiction")
        missing_qualification = _no_signal("missing_qualification")
        selective_presentation = _no_signal("selective_presentation")

    return DetectorReport(
        claim_components=claim_components,
        evidence_components=evidence_components,
        vague_language=detect_vague_language(claim.claim),
        absolute_language=detect_absolute_language(claim.claim),
        unsupported_benefit=detect_unsupported_benefit(claim.claim, has_evidence),
        misleading_comparison=detect_misleading_comparison(claim.claim, evidence_text),
        numerical_mismatch=numerical_mismatch,
        direction_mismatch=direction_mismatch,
        unit_mismatch=unit_mismatch,
        target_year_mismatch=target_year_mismatch,
        absolute_contradiction=absolute_contradiction,
        missing_qualification=missing_qualification,
        selective_presentation=selective_presentation,
    )
