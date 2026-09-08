from app.evidence.lexical import LexicalIndex, tokenize
from app.models.evidence import Evidence, SourceType


def _evidence(evidence_id: str, text: str) -> Evidence:
    return Evidence(
        evidence_id=evidence_id, source_type=SourceType.UPLOADED_REPORT, document_id="DOC-001",
        company="Example Company", page_number=1, source_chunk_id=f"CHK-{evidence_id}",
        evidence_text=text,
    )


def test_tokenize_preserves_scope_numbers_and_units():
    tokens = tokenize("Scope 1 emissions were 45,000 tCO2e in 2025.")
    assert "scope" in tokens
    assert "1" in tokens
    assert "tco2e" in tokens


def test_tokenize_preserves_percent_sign():
    tokens = tokenize("Renewable electricity reached 68%.")
    assert "68%" in tokens


def test_search_ranks_relevant_document_higher():
    index = LexicalIndex()
    index.add_many([
        _evidence("EVD-1", "Scope 1 emissions decreased by 18% from the 2020 baseline."),
        _evidence("EVD-2", "The board has five independent directors."),
        _evidence("EVD-3", "Employee training hours totaled 45,000 in 2025."),
    ])
    results = index.search("Scope 1 emissions baseline", top_k=3)
    assert results[0][0] == "EVD-1"


def test_search_respects_allowed_ids_restriction():
    index = LexicalIndex()
    index.add_many([
        _evidence("EVD-1", "Scope 1 emissions decreased by 18% from the 2020 baseline."),
        _evidence("EVD-2", "Scope 1 emissions were also mentioned here for comparison."),
    ])
    results = index.search("Scope 1 emissions", top_k=10, allowed_ids={"EVD-2"})
    assert [r[0] for r in results] == ["EVD-2"]


def test_search_on_empty_index_returns_no_results():
    index = LexicalIndex()
    assert index.search("anything", top_k=5) == []


def test_clear_resets_index():
    index = LexicalIndex()
    index.add_many([_evidence("EVD-1", "Scope 1 emissions decreased by 18%.")])
    index.clear()
    assert index.search("Scope 1 emissions", top_k=5) == []
