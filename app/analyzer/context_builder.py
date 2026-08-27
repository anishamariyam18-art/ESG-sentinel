"""Controlled context-building for large reports.

A multi-hundred-page ESG report is never sent to the model as one
unstructured blob. Chunks are grouped into character- and count-bounded
batches, in document order, and each batch is rendered with explicit
chunk/page/section labels so the model's output can cite exactly where a
fact came from.
"""
from __future__ import annotations

from app.models.document import DocumentChunk


def build_batches(
    chunks: list[DocumentChunk], max_batch_chars: int, max_chunks_per_batch: int
) -> list[list[DocumentChunk]]:
    """Greedily groups chunks (already in document order) into batches
    respecting both a character budget and a chunk-count ceiling. A single
    chunk is never split across batches; an unusually large chunk that
    alone exceeds max_batch_chars is still placed in its own batch rather
    than dropped."""
    batches: list[list[DocumentChunk]] = []
    current: list[DocumentChunk] = []
    current_chars = 0

    for chunk in chunks:
        chunk_chars = len(chunk.text)
        would_exceed_chars = current and (current_chars + chunk_chars) > max_batch_chars
        would_exceed_count = len(current) >= max_chunks_per_batch

        if would_exceed_chars or would_exceed_count:
            batches.append(current)
            current = []
            current_chars = 0

        current.append(chunk)
        current_chars += chunk_chars

    if current:
        batches.append(current)

    return batches


def format_batch_context(batch: list[DocumentChunk]) -> str:
    """Renders a batch as explicitly labeled chunk/page/section blocks so
    the model can cite `source_chunk_id`/`page_number` in its output."""
    blocks = []
    for chunk in batch:
        blocks.append(
            "DOCUMENT INFORMATION\n\n"
            f"Chunk:\n{chunk.chunk_id}\n\n"
            f"Page:\n{chunk.page_number}\n\n"
            f"Section:\n{chunk.section or 'Unknown'}\n\n"
            f"Text:\n{chunk.text}"
        )
    return "\n\n---\n\n".join(blocks)
