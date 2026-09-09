"""Shared singletons for the API layer (section 36: centralized
configuration/wiring).

`EvidenceRepository` persists to JSON; `EvidenceIndexer`/`LexicalIndex` are
in-memory only, so on process startup they're rebuilt from whatever the
repository already has on disk -- otherwise a server restart would silently
lose semantic/lexical searchability of previously-ingested evidence even
though the metadata itself is still there.
"""
from __future__ import annotations

from app.core.config import get_settings
from app.core.llm import LLMManager, get_llm_manager
from app.core.logging import get_logger
from app.evidence.indexer import EmbeddingProvider, EvidenceIndexer, SentenceTransformerProvider
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.evidence.retriever import EvidenceRetriever
from app.pipeline.service import PipelineOrchestrator
from app.api.store import PipelineResultStore

logger = get_logger(__name__)

_repository: EvidenceRepository | None = None
_embedding_provider: EmbeddingProvider | None = None
_indexer: EvidenceIndexer | None = None
_lexical_index: LexicalIndex | None = None
_retriever: EvidenceRetriever | None = None
_result_store: PipelineResultStore | None = None
_orchestrator: PipelineOrchestrator | None = None


def get_evidence_repository() -> EvidenceRepository:
    global _repository
    if _repository is None:
        settings = get_settings()
        _repository = EvidenceRepository(settings.evidence_dir / settings.evidence.storage_filename)
    return _repository


def get_embedding_provider() -> EmbeddingProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = SentenceTransformerProvider()
    return _embedding_provider


def get_evidence_indexes() -> tuple[EvidenceIndexer, LexicalIndex]:
    global _indexer, _lexical_index
    if _indexer is None or _lexical_index is None:
        _indexer = EvidenceIndexer(provider=get_embedding_provider())
        _lexical_index = LexicalIndex()

        existing = get_evidence_repository().all()

        if existing:
            _indexer.add_many(existing)
            _lexical_index.add_many(existing)

            logger.info(
                "evidence_indexes_rebuilt_from_repository",
                extra={"count": len(existing)},
            )

    return _indexer, _lexical_index


def get_evidence_retriever() -> EvidenceRetriever:
    global _retriever

    if _retriever is None:
        indexer, lexical_index = get_evidence_indexes()

        _retriever = EvidenceRetriever(
            repository=get_evidence_repository(),
            indexer=indexer,
            lexical_index=lexical_index,
        )

    return _retriever


def get_result_store() -> PipelineResultStore:
    global _result_store

    if _result_store is None:
        _result_store = PipelineResultStore(
            get_settings().outputs_dir
        )

    return _result_store


def get_pipeline_llm_manager() -> LLMManager | None:
    """Returns None (rather than raising) when no Gemini API key is
    configured, so `/health`/`/ready` and read-only GET endpoints keep
    working without one -- only POST /analyze actually needs an LLM."""
    try:
        return get_llm_manager()
    except Exception:  # noqa: BLE001 -- absence of a key must not crash dependency wiring
        return None


def get_pipeline_orchestrator() -> PipelineOrchestrator:
    global _orchestrator

    if _orchestrator is None:
        indexer, lexical_index = get_evidence_indexes()

        _orchestrator = PipelineOrchestrator(
            repository=get_evidence_repository(),
            indexer=indexer,
            lexical_index=lexical_index,
            retriever=get_evidence_retriever(),
            llm_manager=get_pipeline_llm_manager(),
            embedding_provider=get_embedding_provider(),
        )

    return _orchestrator


def reset_dependencies_for_testing() -> None:
    """Test-only: clears every singleton so a test can inject fakes."""
    global _repository, _embedding_provider, _indexer, _lexical_index
    global _retriever, _result_store, _orchestrator

    _repository = None
    _embedding_provider = None
    _indexer = None
    _lexical_index = None
    _retriever = None
    _result_store = None
    _orchestrator = None