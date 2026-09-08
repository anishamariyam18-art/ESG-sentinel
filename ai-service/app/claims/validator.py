"""Deterministic claim validation and cleaning.

Two checkpoints, matching the pipeline's two validation stages:

- `is_structurally_valid_candidate` runs on raw LLM candidate text, before
  any further processing -- a cheap filter for obvious non-claims (headings,
  TOC entries, URLs, boilerplate, fragments) so the rest of the pipeline
  never wastes effort on them.
- `validate_final_claim` runs on a fully constructed `Claim`, right before
  it's allowed into deduplication -- confirms provenance is real (the cited
  chunk actually exists in this document) and the claim is ESG-relevant,
  the two things Pydantic's field validation alone cannot check.

Cleaning is intentionally minimal: whitespace normalization only, per the
"never unnecessarily rewrite a claim" rule.
"""
from __future__ import annotations

import re

from app.core.config import ClaimsConfig
from app.models.claim import Claim, ClaimCategory

_WHITESPACE_RE = re.compile(r"\s+")

_NON_CLAIM_EXACT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"table\s+of\s+contents",
        r"about\s+this\s+report",
        r"contents",
        r"appendix(\s+[a-z0-9]+)?",
        r"environmental",
        r"social",
        r"governance",
        r"introduction",
        r"executive\s+summary",
        r"see\s+page\s+\d+",
        r"page\s+\d+(\s+of\s+\d+)?",
        r"\(?c\)?\s*\d{4}.*all\s+rights\s+reserved",
    )
]
_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_MIN_WORD_COUNT = 3

#: Single source of truth for ESG category keywords -- shared with
#: app.claims.classifier.deterministic_category so the two never drift out
#: of sync with each other.
ESG_CATEGORY_KEYWORDS: dict[ClaimCategory, tuple[str, ...]] = {
    ClaimCategory.ENVIRONMENTAL: (
        "emission", "climate", "energy", "renewable", "water", "waste",
        "biodiversity", "pollution", "carbon", "ghg", "scope 1", "scope 2",
        "scope 3", "tco2e", "environmental",
    ),
    ClaimCategory.SOCIAL: (
        "employee", "workforce", "diversity", "inclusion", "health", "safety",
        "training", "human rights", "communit", "customer", "supplier", "labor",
        "labour", "social",
    ),
    ClaimCategory.GOVERNANCE: (
        # Deliberately excludes bare "policy"/"policies"/"compliance" --
        # those describe a claim *type* (see classifier._POLICY_KEYWORDS /
        # _COMPLIANCE_KEYWORDS) and appear across all three categories
        # (e.g. "environmental policy", "human rights policy"), so
        # including them here would falsely flag most policy/compliance
        # statements as category-ambiguous regardless of actual domain.
        "board", "ethics", "corruption", "risk management",
        "governance", "audit", "cybersecurity", "whistleblow", "oversight",
    ),
}

#: Cross-cutting ESG signal words that don't determine a single category
#: (certifications, policies, and compliance statements exist in all three
#: categories -- see the note above) but DO indicate a claim is ESG-related
#: for the relevance check. Kept separate from ESG_CATEGORY_KEYWORDS so
#: category disambiguation is never affected by them.
_GENERAL_ESG_SIGNAL_KEYWORDS = (
    "certified", "certification", "certif", "iso 1", "iso 2", "iso 3",
    "iso 4", "iso 5", "leed", "policy", "policies", "compliance", "comply",
    "compliant", "sustainab", "esg",
)
_ALL_ESG_KEYWORDS = tuple(
    kw for kws in ESG_CATEGORY_KEYWORDS.values() for kw in kws
) + _GENERAL_ESG_SIGNAL_KEYWORDS


def clean_claim_text(text: str) -> str:
    """Whitespace normalization only -- never rewrites wording."""
    return _WHITESPACE_RE.sub(" ", text).strip()


def is_structurally_valid_candidate(text: str, config: ClaimsConfig) -> tuple[bool, str | None]:
    stripped = text.strip()
    if not stripped:
        return False, "Empty claim text"
    if len(stripped) < config.min_claim_length:
        return False, f"Claim text shorter than minimum length ({config.min_claim_length} chars)"
    if len(stripped.split()) < _MIN_WORD_COUNT:
        return False, "Claim text has fewer than the minimum number of words"
    if _URL_RE.search(stripped):
        return False, "Claim text is a URL, not a claim"
    if _EMAIL_RE.search(stripped):
        return False, "Claim text is an email address, not a claim"
    for pattern in _NON_CLAIM_EXACT_PATTERNS:
        if pattern.fullmatch(stripped.strip(".:")):
            return False, f"Claim text matches a known non-claim pattern: '{stripped}'"
    if not is_esg_relevant(stripped):
        return False, "Claim text does not appear ESG-relevant (no matching E/S/G keyword)"
    return True, None


def is_esg_relevant(text: str) -> bool:
    """Deterministic keyword-based relevance check -- a second, independent
    filter on top of the LLM's own judgement (defense in depth per the
    'do not depend entirely on an LLM' rule). Intentionally permissive:
    only used to catch candidates that clearly have no ESG grounding at
    all, not to second-guess borderline classification calls."""
    lowered = text.lower()
    return any(keyword in lowered for keyword in _ALL_ESG_KEYWORDS)


def esg_relevance_score(text: str) -> float:
    """0.0-1.0 signal for confidence scoring: 0.0 with no keyword grounding
    at all, rising with each additional distinct ESG keyword hit (more
    grounding language = clearer relevance), capped at 1.0."""
    lowered = text.lower()
    hit_count = sum(1 for keyword in _ALL_ESG_KEYWORDS if keyword in lowered)
    if hit_count == 0:
        return 0.0
    return min(1.0, 0.5 + 0.15 * hit_count)


def validate_final_claim(claim: Claim, valid_chunk_ids: set[str]) -> tuple[bool, str | None]:
    if claim.source_chunk_id not in valid_chunk_ids:
        return False, f"source_chunk_id '{claim.source_chunk_id}' was not found in this document (fabricated provenance)"
    for ref in claim.source_references:
        if ref.chunk_id not in valid_chunk_ids:
            return False, f"additional source reference '{ref.chunk_id}' was not found in this document"
    if not is_esg_relevant(claim.claim):
        return False, "Claim text is not ESG-relevant"
    if not (0.0 <= claim.confidence <= 1.0):
        return False, "Confidence out of range"
    return True, None
