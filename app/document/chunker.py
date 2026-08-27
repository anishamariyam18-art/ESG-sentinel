"""Page-aware, paragraph-aware, section-aware chunking.

Chunks never cross a page boundary (page_number provenance must stay
unambiguous). Within a page, paragraphs are greedily merged up to a
configurable target size; a paragraph that alone exceeds the configured
maximum is further split on sentence boundaries (and, as a last resort, on
whitespace) so no chunk is dropped or silently truncated.
"""
from __future__ import annotations

import re

from app.core.config import ChunkingConfig
from app.core.logging import get_logger
from app.models.document import DocumentChunk

logger = get_logger(__name__)

_PARAGRAPH_RE = re.compile(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", re.DOTALL)
_SENTENCE_GAP_RE = re.compile(r"(?<=[.!?])\s+")

_Span = tuple[int, int]


def _find_paragraph_spans(text: str) -> list[_Span]:
    return [(m.start(), m.end()) for m in _PARAGRAPH_RE.finditer(text)]


def _find_sentence_spans(text: str) -> list[_Span]:
    """Splits on whitespace immediately following sentence-ending
    punctuation. Linear-time (no backtracking risk on punctuation-sparse
    text, unlike a lazy `.*?[.!?]` pattern)."""
    spans: list[_Span] = []
    cursor = 0
    for m in _SENTENCE_GAP_RE.finditer(text):
        if m.start() > cursor:
            spans.append((cursor, m.start()))
        cursor = m.end()
    if cursor < len(text) and text[cursor:].strip():
        spans.append((cursor, len(text)))
    return spans


def _hard_split(text: str, base_offset: int, max_chars: int) -> list[_Span]:
    """Last-resort splitter for a single unit with no usable sentence
    boundaries. Cuts on the last whitespace inside the window when
    possible, never mid-word if a whitespace is available."""
    spans: list[_Span] = []
    cursor = 0
    length = len(text)
    while cursor < length:
        end = min(cursor + max_chars, length)
        if end < length:
            split_at = text.rfind(" ", cursor, end)
            if split_at > cursor:
                end = split_at
        spans.append((base_offset + cursor, base_offset + end))
        cursor = end
        while cursor < length and text[cursor] == " ":
            cursor += 1
    return spans


def _greedy_merge(
    text: str, unit_spans: list[_Span], target_chars: int, max_chars: int, min_chars: int
) -> list[_Span]:
    """Merges consecutive unit spans (paragraphs or sentences) into chunks
    up to target_chars, never exceeding max_chars, and folds a too-small
    trailing chunk into its predecessor when possible."""
    chunks: list[_Span] = []
    buffer_start: int | None = None
    buffer_end: int | None = None

    def buffer_len() -> int:
        return 0 if buffer_start is None else buffer_end - buffer_start

    for start, end in unit_spans:
        unit_len = end - start

        if unit_len > max_chars:
            if buffer_start is not None:
                chunks.append((buffer_start, buffer_end))
                buffer_start = buffer_end = None
            sub_spans = _find_sentence_spans(text[start:end])
            if not sub_spans:
                chunks.extend(_hard_split(text[start:end], start, max_chars))
            else:
                absolute = [(start + s, start + e) for s, e in sub_spans]
                chunks.extend(_greedy_merge(text, absolute, target_chars, max_chars, min_chars))
            continue

        if buffer_start is None:
            buffer_start, buffer_end = start, end
            continue

        candidate_len = end - buffer_start
        if candidate_len <= target_chars:
            buffer_end = end
        else:
            chunks.append((buffer_start, buffer_end))
            buffer_start, buffer_end = start, end

    if buffer_start is not None:
        if chunks and (buffer_end - buffer_start) < min_chars:
            prev_start, prev_end = chunks[-1]
            if (buffer_end - prev_start) <= max_chars:
                chunks[-1] = (prev_start, buffer_end)
            else:
                chunks.append((buffer_start, buffer_end))
        else:
            chunks.append((buffer_start, buffer_end))

    return chunks


class DocumentChunker:
    def chunk_page(
        self,
        document_id: str,
        company: str,
        report_year: int,
        page_number: int,
        section: str | None,
        cleaned_text: str,
        config: ChunkingConfig,
        start_index: int = 1,
    ) -> list[DocumentChunk]:
        text = cleaned_text
        if not text.strip():
            return []

        paragraph_spans = _find_paragraph_spans(text)
        if not paragraph_spans:
            return []

        chunk_spans = _greedy_merge(
            text, paragraph_spans, config.target_chunk_chars, config.max_chunk_chars, config.min_chunk_chars
        )

        chunks: list[DocumentChunk] = []
        for offset, (start, end) in enumerate(chunk_spans):
            chunk_text = text[start:end].strip()
            if not chunk_text:
                continue
            chunk_index = start_index + offset
            chunks.append(
                DocumentChunk(
                    chunk_id=f"{document_id}-P{page_number:04d}-C{chunk_index:03d}",
                    document_id=document_id,
                    company=company,
                    report_year=report_year,
                    page_number=page_number,
                    section=section,
                    text=chunk_text,
                    start_char=start,
                    end_char=end,
                )
            )
        return chunks
