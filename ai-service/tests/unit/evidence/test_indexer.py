from app.evidence.indexer import EvidenceIndexer
from app.models.evidence import Evidence, SourceType
from tests.unit.evidence.conftest import FakeEmbeddingProvider


def _evidence(evidence_id: str, text: str) -> Evidence:
    return Evidence(
        evidence_id=evidence_id, source_type=SourceType.UPLOADED_REPORT, document_id="DOC-001",
        company="Example Company", page_number=1, source_chunk_id=f"CHK-{evidence_id}",
        evidence_text=text,
    )


def test_add_many_creates_one_vector_per_record():
    indexer = EvidenceIndexer(provider=FakeEmbeddingProvider())
    indexer.add_many([
        _evidence("EVD-1", "Scope 1 emissions decreased by 18%."),
        _evidence("EVD-2", "Women represented 42% of our workforce."),
    ])
    assert len(indexer._vectors) == 2
    assert len(indexer._evidence_ids) == 2


def test_search_ranks_semantically_similar_text_higher():
    indexer = EvidenceIndexer(provider=FakeEmbeddingProvider())
    indexer.add_many([
        _evidence("EVD-1", "Scope 1 emissions decreased by 18% from the 2020 baseline."),
        _evidence("EVD-2", "The board has five independent directors."),
    ])
    results = indexer.search("Scope 1 emissions baseline reduction", top_k=2)
    assert results[0][0] == "EVD-1"
    assert results[0][1] > results[1][1]


def test_search_respects_allowed_ids_restriction():
    indexer = EvidenceIndexer(provider=FakeEmbeddingProvider())
    indexer.add_many([
        _evidence("EVD-1", "Scope 1 emissions decreased by 18%."),
        _evidence("EVD-2", "Scope 1 emissions were also mentioned here."),
    ])
    results = indexer.search("Scope 1 emissions", top_k=10, allowed_ids={"EVD-2"})
    assert [r[0] for r in results] == ["EVD-2"]


def test_search_on_empty_index_returns_no_results():
    indexer = EvidenceIndexer(provider=FakeEmbeddingProvider())
    assert indexer.search("anything", top_k=5) == []


def test_add_many_with_empty_list_is_a_noop():
    indexer = EvidenceIndexer(provider=FakeEmbeddingProvider())
    indexer.add_many([])
    assert indexer.search("anything", top_k=5) == []


def test_clear_resets_index():
    indexer = EvidenceIndexer(provider=FakeEmbeddingProvider())
    indexer.add_many([_evidence("EVD-1", "Scope 1 emissions decreased by 18%.")])
    indexer.clear()
    assert indexer.search("Scope 1 emissions", top_k=5) == []


def test_indexer_never_loads_real_model_without_use():
    # Constructing without a fake provider must not attempt any network
    # access -- the real SentenceTransformer is lazily loaded on first
    # encode() call, not at construction.
    from app.evidence.indexer import EvidenceIndexer as RealIndexer

    indexer = RealIndexer()
    assert indexer._provider._model is None
