"""BM25 lexical index over evidence text.

Exists specifically because pure semantic similarity can miss exact
technical/numerical terminology ("Scope 1", "tCO2e", "water withdrawal")
that matters a great deal for ESG verification but doesn't always dominate
an embedding's similarity signal.
"""
from __future__ import annotations

import re

from app.core.logging import get_logger
from app.models.evidence import Evidence

logger = get_logger(__name__)

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?%?")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


class LexicalIndex:
    """BM25 index. `evidence_id`s and their tokenized text are kept in
    parallel lists; the BM25 model is rebuilt on every mutation (cheap at
    prototype scale -- documented as a limitation for very large corpora)."""

    def __init__(self) -> None:
        self._evidence_ids: list[str] = []
        self._corpus: list[list[str]] = []
        self._bm25 = None

    def add_many(self, evidence_list: list[Evidence]) -> None:
        for evidence in evidence_list:
            self._evidence_ids.append(evidence.evidence_id)
            self._corpus.append(tokenize(evidence.evidence_text))
        self._rebuild()

    def clear(self) -> None:
        self._evidence_ids = []
        self._corpus = []
        self._bm25 = None

    def _rebuild(self) -> None:
        if not self._corpus:
            self._bm25 = None
            return
        from rank_bm25 import BM25Okapi

        self._bm25 = BM25Okapi(self._corpus)

    def search(
        self, query: str, top_k: int, allowed_ids: set[str] | None = None
    ) -> list[tuple[str, float]]:
        """Returns (evidence_id, score) pairs, highest first. When
        `allowed_ids` is given, scoring never considers evidence outside
        that set -- restriction happens before scoring, not as a
        post-filter (section 19)."""
        if self._bm25 is None:
            return []

        scores = self._bm25.get_scores(tokenize(query))
        pairs = [
            (evidence_id, float(score))
            for evidence_id, score in zip(self._evidence_ids, scores)
            if allowed_ids is None or evidence_id in allowed_ids
        ]
        pairs.sort(key=lambda item: item[1], reverse=True)
        return pairs[:top_k]
