from app.analyzer.context_builder import build_batches, format_batch_context
from app.models.document import DocumentChunk


def _chunk(index: int, page: int, text: str, section: str | None = "Environmental") -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"CHK-{index:05d}", document_id="DOC-001", company="Example Company",
        report_year=2025, page_number=page, section=section, text=text,
    )


def test_build_batches_respects_char_budget():
    chunks = [_chunk(i, i, "x" * 100) for i in range(1, 11)]
    batches = build_batches(chunks, max_batch_chars=350, max_chunks_per_batch=100)
    assert sum(len(b) for b in batches) == 10
    for batch in batches[:-1]:
        assert sum(len(c.text) for c in batch) <= 350


def test_build_batches_respects_chunk_count_ceiling():
    chunks = [_chunk(i, i, "short") for i in range(1, 11)]
    batches = build_batches(chunks, max_batch_chars=100000, max_chunks_per_batch=3)
    assert all(len(b) <= 3 for b in batches)
    assert sum(len(b) for b in batches) == 10


def test_build_batches_never_splits_a_single_oversized_chunk():
    huge_chunk = _chunk(1, 1, "x" * 5000)
    chunks = [huge_chunk, _chunk(2, 2, "small")]
    batches = build_batches(chunks, max_batch_chars=1000, max_chunks_per_batch=10)
    assert any(len(b) == 1 and b[0].chunk_id == "CHK-00001" for b in batches)
    assert sum(len(b) for b in batches) == 2


def test_build_batches_preserves_document_order():
    chunks = [_chunk(i, i, "text") for i in range(1, 6)]
    batches = build_batches(chunks, max_batch_chars=8, max_chunks_per_batch=1)
    flattened = [c.chunk_id for batch in batches for c in batch]
    assert flattened == [c.chunk_id for c in chunks]


def test_build_batches_empty_input_returns_no_batches():
    assert build_batches([], max_batch_chars=1000, max_chunks_per_batch=10) == []


def test_format_batch_context_includes_chunk_page_section_and_text():
    chunk = _chunk(1, 17, "Scope 1 emissions decreased by 12%.", section="Environmental > Climate")
    context = format_batch_context([chunk])
    assert "CHK-00001" in context
    assert "17" in context
    assert "Environmental > Climate" in context
    assert "Scope 1 emissions decreased by 12%." in context


def test_format_batch_context_joins_multiple_chunks():
    chunks = [_chunk(1, 1, "First chunk text."), _chunk(2, 2, "Second chunk text.")]
    context = format_batch_context(chunks)
    assert "First chunk text." in context
    assert "Second chunk text." in context
    assert context.index("First chunk text.") < context.index("Second chunk text.")
