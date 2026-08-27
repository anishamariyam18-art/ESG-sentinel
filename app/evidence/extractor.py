"""Primary-report (Layer 1) evidence extraction: Document + Claims -> Evidence.

Never uses the claim text itself as evidence -- every Evidence record's
`evidence_text` is an actual chunk of the source document. Each claim
always gets an evidence candidate from its own `source_chunk_id` (and any
`source_references`, for claims spanning multiple chunks) since that's
literally where Phase 4 extracted it from; additional *corroborating*
chunks elsewhere in the same document are added only if they score above
`EvidenceConfig.corroboration_similarity_threshold` on an ephemeral,
per-call semantic+lexical index scoped to just this document (never the
persistent evidence store -- that's populated afterward, from the
validated results, by app.evidence.ingestion).

A claim with no usable source chunk gets `evidence_found=False` and an
empty evidence list -- never a fabricated placeholder record.
"""
from __future__ import annotations

from app.core.config import EvidenceConfig, get_settings
from app.core.logging import get_logger
from app.evidence.indexer import EmbeddingProvider, EvidenceIndexer
from app.evidence.lexical import LexicalIndex
from app.models.claim import Claim, ClaimCategory
from app.models.document import Document, DocumentChunk
from app.models.evidence import ClaimEvidenceResult, Evidence, SourceType

logger = get_logger(__name__)

_PSEUDO_PREFIX = "__corroboration__"


def _pseudo_evidence_id(chunk_id: str) -> str:
    return f"{_PSEUDO_PREFIX}{chunk_id}"


def _build_pseudo_evidence(chunk: DocumentChunk) -> Evidence:
    """A throwaway Evidence wrapper around a chunk, used only to reuse the
    tested EvidenceIndexer/LexicalIndex search machinery for corroboration
    search. Never validated, stored, or returned to callers."""
    return Evidence(
        evidence_id=_pseudo_evidence_id(chunk.chunk_id),
        source_type=SourceType.UPLOADED_REPORT,
        company=chunk.company,
        document_id=chunk.document_id,
        report_year=chunk.report_year,
        section=chunk.section,
        page_number=chunk.page_number,
        source_chunk_id=chunk.chunk_id,
        evidence_text=chunk.text,
    )


class EvidenceExtractor:
    def __init__(
        self, embedding_provider: EmbeddingProvider | None = None, config: EvidenceConfig | None = None
    ) -> None:
        self._embedding_provider = embedding_provider
        self._config = config or get_settings().evidence
        self._counter = 0

    def extract_for_claims(self, document: Document, claims: list[Claim]) -> list[ClaimEvidenceResult]:
        if not claims:
            return []
        chunk_by_id = {c.chunk_id: c for c in document.chunks}

        indexer: EvidenceIndexer | None = None
        lexical_index: LexicalIndex | None = None
        allowed_ids: set[str] = set()
        if document.chunks and self._config.max_corroborating_chunks_per_claim > 0:
            pseudo_evidence = [_build_pseudo_evidence(c) for c in document.chunks]
            indexer = EvidenceIndexer(provider=self._embedding_provider)
            lexical_index = LexicalIndex()
            indexer.add_many(pseudo_evidence)
            lexical_index.add_many(pseudo_evidence)
            allowed_ids = {e.evidence_id for e in pseudo_evidence}

        results: list[ClaimEvidenceResult] = []
        for claim in claims:
            candidate_chunk_ids = self._own_chunk_ids(claim, chunk_by_id)
            if indexer is not None and lexical_index is not None:
                candidate_chunk_ids += self._corroborating_chunk_ids(
                    claim, indexer, lexical_index, allowed_ids, exclude=set(candidate_chunk_ids)
                )

            claim_evidence = [
                self._build_evidence(document, claim, chunk_by_id[chunk_id]) for chunk_id in candidate_chunk_ids
            ]
            results.append(
                ClaimEvidenceResult(
                    claim_id=claim.claim_id, evidence_found=bool(claim_evidence), evidence=claim_evidence
                )
            )

        found = sum(1 for r in results if r.evidence_found)
        logger.info(
            "evidence_extracted_for_claims",
            extra={"document_id": document.document_id, "claim_count": len(claims), "claims_with_evidence": found},
        )
        return results

    def _own_chunk_ids(self, claim: Claim, chunk_by_id: dict[str, DocumentChunk]) -> list[str]:
        ids: list[str] = []
        if claim.source_chunk_id in chunk_by_id:
            ids.append(claim.source_chunk_id)
        for ref in claim.source_references:
            if ref.chunk_id in chunk_by_id and ref.chunk_id not in ids:
                ids.append(ref.chunk_id)
        return ids

    def _corroborating_chunk_ids(
        self,
        claim: Claim,
        indexer: EvidenceIndexer,
        lexical_index: LexicalIndex,
        allowed_ids: set[str],
        exclude: set[str],
    ) -> list[str]:
        budget = self._config.max_corroborating_chunks_per_claim
        pool_size = len(allowed_ids)
        semantic_hits = indexer.search(claim.claim, top_k=pool_size, allowed_ids=allowed_ids)
        lexical_hits = lexical_index.search(claim.claim, top_k=pool_size, allowed_ids=allowed_ids)

        max_lexical = max((score for _, score in lexical_hits), default=0.0)
        combined: dict[str, float] = {}
        for evidence_id, score in semantic_hits:
            combined[evidence_id] = max(combined.get(evidence_id, 0.0), score)
        for evidence_id, score in lexical_hits:
            normalized = score / max_lexical if max_lexical > 0 else 0.0
            combined[evidence_id] = max(combined.get(evidence_id, 0.0), normalized)

        found: list[str] = []
        for evidence_id, score in sorted(combined.items(), key=lambda item: item[1], reverse=True):
            if score < self._config.corroboration_similarity_threshold:
                break
            chunk_id = evidence_id[len(_PSEUDO_PREFIX):]
            if chunk_id in exclude or chunk_id in found:
                continue
            found.append(chunk_id)
            if len(found) >= budget:
                break
        return found

    def _build_evidence(self, document: Document, claim: Claim, chunk: DocumentChunk) -> Evidence:
        self._counter += 1
        return Evidence(
            evidence_id=f"EVD-{document.document_id}-{self._counter:06d}",
            source_type=SourceType.UPLOADED_REPORT,
            document_id=document.document_id,
            company=document.company,
            report_year=document.report_year,
            category=claim.category if claim.category != ClaimCategory.UNKNOWN else None,
            section=chunk.section,
            page_number=chunk.page_number,
            source_chunk_id=chunk.chunk_id,
            evidence_text=chunk.text,
            metric_name=claim.metric_name,
            value=claim.value,
            unit=claim.unit,
            target_year=claim.target_year,
            source_authority="Uploaded ESG Report",
        )
