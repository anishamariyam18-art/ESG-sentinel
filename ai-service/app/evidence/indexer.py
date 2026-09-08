"""Semantic embedding index over evidence text.

`SentenceTransformerProvider` is the only place that imports
`sentence_transformers` -- the model is swappable via constructor
injection (`EvidenceIndexer(provider=...)`), the same pattern used for the
LLM abstraction in app.core.llm, so tests never need to download a real
model or hit the network.
"""
from __future__ import annotations

import math
from typing import Protocol

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.evidence import Evidence

logger = get_logger(__name__)


class EmbeddingProvider(Protocol):
    def encode(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerProvider:
    """The only file/class that touches sentence_transformers. Lazily
    loads the model on first use, not at construction, so simply creating
    an (unused) EvidenceIndexer never triggers a model download."""

    def __init__(self, model_name: str | None = None) -> None:
        self._model_name = model_name or get_settings().embedding_model_name
        self._model = None

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            logger.info("embedding_model_loading", extra={"model_name": self._model_name})
            self._model = SentenceTransformer(self._model_name)
        vectors = self._model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
        return vectors.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class EvidenceIndexer:
    """Holds one embedding vector per indexed evidence record, alongside
    its evidence_id, so metadata never gets separated from its vector."""

    def __init__(self, provider: EmbeddingProvider | None = None) -> None:
        self._provider = provider or SentenceTransformerProvider()
        self._evidence_ids: list[str] = []
        self._vectors: list[list[float]] = []

    def add_many(self, evidence_list: list[Evidence]) -> None:
        if not evidence_list:
            return
        vectors = self._provider.encode([e.evidence_text for e in evidence_list])
        for evidence, vector in zip(evidence_list, vectors):
            self._evidence_ids.append(evidence.evidence_id)
            self._vectors.append(vector)
        logger.info("evidence_embedded", extra={"count": len(evidence_list)})

    def clear(self) -> None:
        self._evidence_ids = []
        self._vectors = []

    def search(
        self, query: str, top_k: int, allowed_ids: set[str] | None = None
    ) -> list[tuple[str, float]]:
        """Returns (evidence_id, cosine_similarity) pairs, highest first.
        Restriction to `allowed_ids` happens before scoring is used to pick
        the top_k, never as a post-filter (section 19)."""
        if not self._vectors:
            return []
        (query_vector,) = self._provider.encode([query])

        pairs = [
            (evidence_id, cosine_similarity(query_vector, vector))
            for evidence_id, vector in zip(self._evidence_ids, self._vectors)
            if allowed_ids is None or evidence_id in allowed_ids
        ]
        pairs.sort(key=lambda item: item[1], reverse=True)
        return pairs[:top_k]
