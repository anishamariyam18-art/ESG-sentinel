from app.core.config import ChunkingConfig
from app.document.chunker import DocumentChunker


def _config(**overrides) -> ChunkingConfig:
    fields = dict(target_chunk_chars=1000, max_chunk_chars=1600, min_chunk_chars=150)
    fields.update(overrides)
    return ChunkingConfig(_env_file=None, **fields)


def test_empty_text_produces_no_chunks():
    chunks = DocumentChunker().chunk_page(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=1, section="Environmental", cleaned_text="   \n\n  ",
        config=_config(),
    )
    assert chunks == []


def test_every_chunk_has_required_provenance_fields():
    text = "Paragraph one about emissions.\n\nParagraph two about targets."
    chunks = DocumentChunker().chunk_page(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=7, section="Environmental > Climate", cleaned_text=text,
        config=_config(),
    )
    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.document_id == "DOC-001"
        assert chunk.page_number == 7
        assert chunk.text.strip() != ""
        assert chunk.chunk_id.startswith("DOC-001-P0007-")


def test_chunk_ids_are_unique_across_pages():
    chunker = DocumentChunker()
    text = "Paragraph about emissions.\n\nParagraph about targets."
    chunks_page_1 = chunker.chunk_page(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=1, section=None, cleaned_text=text, config=_config(),
    )
    chunks_page_2 = chunker.chunk_page(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=2, section=None, cleaned_text=text, config=_config(),
    )
    all_ids = [c.chunk_id for c in chunks_page_1 + chunks_page_2]
    assert len(all_ids) == len(set(all_ids))


def test_small_target_produces_more_chunks_than_large_target():
    paragraphs = "\n\n".join(f"This is paragraph number {i} discussing ESG topic {i}." for i in range(20))
    small = DocumentChunker().chunk_page(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=1, section=None, cleaned_text=paragraphs,
        config=_config(target_chunk_chars=80, max_chunk_chars=160, min_chunk_chars=20),
    )
    large = DocumentChunker().chunk_page(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=1, section=None, cleaned_text=paragraphs,
        config=_config(target_chunk_chars=5000, max_chunk_chars=6000, min_chunk_chars=20),
    )
    assert len(small) > len(large)
    assert len(large) == 1


def test_oversized_paragraph_is_split_and_never_exceeds_max_chars():
    huge_sentence_paragraph = " ".join(f"Sentence number {i} about ESG performance." for i in range(200))
    chunks = DocumentChunker().chunk_page(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=1, section=None, cleaned_text=huge_sentence_paragraph,
        config=_config(target_chunk_chars=200, max_chunk_chars=300, min_chunk_chars=50),
    )
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.text) <= 300


def test_chunking_never_drops_meaningful_content():
    text = (
        "Scope 1 emissions decreased by 12% compared to the prior year.\n\n"
        "Scope 2 emissions were 45,000 tCO2e in 2025.\n\n"
        "The company has committed to net zero emissions by 2050."
    )
    chunks = DocumentChunker().chunk_page(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=1, section=None, cleaned_text=text, config=_config(),
    )
    combined = " ".join(c.text for c in chunks)
    assert "12%" in combined
    assert "45,000 tCO2e" in combined
    assert "net zero emissions by 2050" in combined


def test_start_and_end_char_are_valid_offsets_into_source_text():
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    chunks = DocumentChunker().chunk_page(
        document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=1, section=None, cleaned_text=text,
        config=_config(target_chunk_chars=15, max_chunk_chars=20, min_chunk_chars=5),
    )
    for chunk in chunks:
        assert 0 <= chunk.start_char <= chunk.end_char <= len(text)
        assert chunk.text in text
