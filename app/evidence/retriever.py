"""Hybrid retrieval interface for Phase 6.

Phase 5 does NOT decide verification -- this module only answers "what
evidence exists". It exposes raw `semantic_score`/`lexical_score` per
candidate; the provisional ordering used to pick `top_k` uses
`RetrievalConfig`'s weights for a sane, non-arbitrary result set, but that
is explicitly NOT the authoritative combine/rerank step (no `final_score`
or `reranker_score` is set here -- Phase 6 owns those).

Metadata filtering ALWAYS runs first, against the repository, before any
semantic or lexical scoring happens: search only ever scores evidence that
already passed the company/document/source_type/category filters. This is
mandatory (section 19) -- evidence is never retrieved company-agnostic and
then hopefully filtered by similarity.
"""
from __future__ import annotations

from app.core.config import RetrievalConfig, get_settings
from app.core.logging import get_logger
from app.evidence.indexer import EvidenceIndexer
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.evidence.validator import compute_evidence_quality
from app.models.claim import ClaimCategory
from app.models.evidence import EvidenceMatch, SourceType

logger = get_logger(__name__)


class EvidenceRetriever:
    def __init__(
        self,
        repository: EvidenceRepository,
        indexer: EvidenceIndexer,
        lexical_index: LexicalIndex,
        retrieval_config: RetrievalConfig | None = None,
    ) -> None:
        self._repository = repository
        self._indexer = indexer
        self._lexical_index = lexical_index
        self._config = retrieval_config or get_settings().retrieval

    def search(
        self,
        query: str,
        *,
        company: str | None = None,
        document_id: str | None = None,
        exclude_document_id: str | None = None,
        report_year: int | None = None,
        source_type: SourceType | None = None,
        category: ClaimCategory | None = None,
        top_k: int | None = None,
    ) -> list[EvidenceMatch]:
        top_k = top_k or get_settings().evidence.default_top_k

        candidates = self._repository.search(
            company=company, document_id=document_id, report_year=report_year,
            source_type=source_type, category=category,
        )
        if exclude_document_id is not None:
            # Data leakage protection (Phase 10 section 26): drop candidates
            # from the document currently being analyzed so a claim can
            # never be "verified" merely by retrieving its own source text.
            candidates = [e for e in candidates if e.document_id != exclude_document_id]
        if not candidates:
            logger.info(
                "evidence_search_no_candidates",
                extra={"company": company, "document_id": document_id, "source_type": source_type},
            )
            return []

        allowed_ids = {e.evidence_id for e in candidates}
        by_id = {e.evidence_id: e for e in candidates}

        semantic_hits = dict(self._indexer.search(query, top_k=len(allowed_ids), allowed_ids=allowed_ids))
        lexical_hits = dict(self._lexical_index.search(query, top_k=len(allowed_ids), allowed_ids=allowed_ids))

        max_lexical = max(lexical_hits.values(), default=0.0)

        scored: list[tuple[float, EvidenceMatch]] = []
        for evidence_id in set(semantic_hits) | set(lexical_hits):
            evidence = by_id[evidence_id]
            semantic_score = semantic_hits.get(evidence_id, 0.0)
            lexical_score = (lexical_hits.get(evidence_id, 0.0) / max_lexical) if max_lexical > 0 else 0.0

            provisional_rank = (
                semantic_score * self._config.semantic_weight + lexical_score * self._config.lexical_weight
            )
            match = EvidenceMatch(
                evidence_id=evidence.evidence_id,
                source_type=evidence.source_type,
                company=evidence.company,
                document_id=evidence.document_id,
                report_year=evidence.report_year,
                report_title=evidence.report_title,
                page_number=evidence.page_number,
                source_chunk_id=evidence.source_chunk_id,
                evidence_text=evidence.evidence_text,
                semantic_score=round(semantic_score, 4),
                lexical_score=round(lexical_score, 4),
                quality_score=compute_evidence_quality(evidence),
            )
            scored.append((provisional_rank, match))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        results = [match for _, match in scored[:top_k]]

        logger.info(
            "evidence_search_completed",
            extra={
                "company": company, "document_id": document_id, "candidate_count": len(candidates),
                "result_count": len(results),
            },
        )
        return results
