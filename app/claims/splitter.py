"""Claim splitting.

Only splits a candidate when there is strong, conservative evidence of
multiple independent numeric/factual assertions bundled into one sentence
(the "20%, 80%, and 95%" case from the spec). A single logically connected
statement -- even a long one -- is left untouched; when in doubt, this
module does NOT split.

This is a syntactic heuristic, not semantic clause analysis: a sentence
like "Emissions decreased by 12%, which included a 500 tCO2e reduction
from efficiency programs" (an elaboration, not two independent facts) can
still be over-split, since both clauses carry a numeric marker. Building
true clause-independence detection is out of scope for a deterministic,
no-embeddings Phase 4 heuristic; downstream deduplication and human review
of extraction quality are the practical backstops.
"""
from __future__ import annotations

import re

_NUMERIC_MARKER_RE = re.compile(
    r"\d+(?:\.\d+)?\s*%|\d+(?:,\d{3})*(?:\.\d+)?\s*(?:tco2e|tonnes?|kg|mwh|gwh|kwh)",
    re.IGNORECASE,
)
# List-style commas ("A, B, and C") and semicolons, only where more text follows.
_CLAUSE_BOUNDARY_RE = re.compile(r",\s+(?:and\s+)?(?=[A-Za-z])|;\s+")
_MIN_CLAUSE_WORDS = 4


def split_candidate(text: str) -> list[str]:
    numeric_markers = _NUMERIC_MARKER_RE.findall(text)
    if len(numeric_markers) < 2:
        return [text]

    clauses = [c.strip(" ,;") for c in _CLAUSE_BOUNDARY_RE.split(text) if c.strip(" ,;")]
    if len(clauses) < 2:
        return [text]

    if any(len(clause.split()) < _MIN_CLAUSE_WORDS for clause in clauses):
        return [text]  # a resulting fragment is too short to stand alone

    clauses_with_own_number = sum(1 for c in clauses if _NUMERIC_MARKER_RE.search(c))
    if clauses_with_own_number < max(2, len(clauses) - 1):
        return [text]  # not enough clauses carry their own quantified fact

    return clauses
