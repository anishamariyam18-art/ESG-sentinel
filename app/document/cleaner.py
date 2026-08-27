"""Conservative text cleaning.

Only strips extraction artifacts we can be confident about: null/control
characters, excessive blank lines, standalone page-number lines at a page's
very top/bottom edge, and lines that repeat across most pages in the same
top/bottom position (headers/footers). Never touches percentages, monetary
values, units, dates, ESG terminology, or numeric content -- and any
candidate header/footer line that looks like it might carry ESG content is
left alone rather than removed.
"""
from __future__ import annotations

import re
from collections import defaultdict

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.document.pdf_extractor import ExtractedPage

logger = get_logger(__name__)

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MULTI_BLANK_LINES_RE = re.compile(r"\n{3,}")

_PAGE_NUMBER_RE = re.compile(r"(page\s+)?\d{1,4}(\s+of\s+\d{1,4})?", re.IGNORECASE)
_PAGE_NUMBER_DASH_RE = re.compile(r"[-–—]\s*\d{1,4}\s*[-–—]")
_DIGIT_RUN_RE = re.compile(r"\d+")

_ESG_MARKERS = (
    "scope 1", "scope 2", "scope 3", "tco2e", "co2e", "ghg", "emission",
    "target", "%", "percent", "renewable", "water", "waste", "biodiversity",
)

_EDGE_ZONE_LINES = 2
_MIN_PAGES_FOR_HEADER_DETECTION = 4
_MIN_REPETITION_RATIO = 0.6
_MAX_CANDIDATE_LINE_LENGTH = 100


class HeaderFooterDetectionResult(BaseModel):
    removed_headers: list[str] = Field(default_factory=list)
    removed_footers: list[str] = Field(default_factory=list)


class CleaningResult(BaseModel):
    cleaned_texts: dict[int, str] = Field(default_factory=dict)
    header_footer_detection: HeaderFooterDetectionResult = Field(
        default_factory=HeaderFooterDetectionResult
    )


def normalize_whitespace(text: str) -> str:
    """Control-character and blank-line normalization only. Never touches
    numbers, units, or intra-line spacing (which may carry table structure)."""
    text = _CONTROL_CHARS_RE.sub("", text)
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = _MULTI_BLANK_LINES_RE.sub("\n\n", text)
    return text.strip("\n")


def _is_standalone_page_number(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return bool(_PAGE_NUMBER_RE.fullmatch(stripped)) or bool(_PAGE_NUMBER_DASH_RE.fullmatch(stripped))


def _strip_standalone_page_numbers(text: str) -> str:
    """Removes a page-number-only line, but only when it is the very first
    or very last non-blank line -- never from the body of the page."""
    lines = text.split("\n")
    non_blank_indices = [i for i, line in enumerate(lines) if line.strip()]
    if not non_blank_indices:
        return text

    edge_indices = {non_blank_indices[0], non_blank_indices[-1]}
    for i in edge_indices:
        if _is_standalone_page_number(lines[i]):
            lines[i] = ""
    return "\n".join(lines)


def _normalize_key(line: str) -> str:
    return _DIGIT_RUN_RE.sub("#", line.strip().lower())


def _looks_like_esg_content(line: str) -> bool:
    lowered = line.lower()
    if len(line) > _MAX_CANDIDATE_LINE_LENGTH:
        return True
    if any(marker in lowered for marker in _ESG_MARKERS):
        return True
    large_numbers = [int(n) for n in _DIGIT_RUN_RE.findall(line) if len(n) >= 3]
    if any(n >= 100 and not (1900 <= n <= 2100) for n in large_numbers):
        return True
    return False


class TextCleaner:
    """Applies conservative whitespace normalization plus document-wide
    repeated header/footer detection."""

    def clean(self, pages: list[ExtractedPage]) -> CleaningResult:
        normalized = {p.page_number: normalize_whitespace(p.raw_text) for p in pages}
        normalized = {pn: _strip_standalone_page_numbers(text) for pn, text in normalized.items()}

        cleaned_texts, detection = self._strip_repeated_headers_footers(normalized)

        logger.info(
            "text_cleaned",
            extra={
                "pages_cleaned": len(cleaned_texts),
                "removed_header_variants": len(detection.removed_headers),
                "removed_footer_variants": len(detection.removed_footers),
            },
        )
        return CleaningResult(cleaned_texts=cleaned_texts, header_footer_detection=detection)

    def _strip_repeated_headers_footers(
        self, page_texts: dict[int, str]
    ) -> tuple[dict[int, str], HeaderFooterDetectionResult]:
        page_numbers = sorted(page_texts)
        if len(page_numbers) < _MIN_PAGES_FOR_HEADER_DETECTION:
            return dict(page_texts), HeaderFooterDetectionResult()

        page_lines = {pn: page_texts[pn].split("\n") for pn in page_numbers}
        page_non_blank = {
            pn: [i for i, line in enumerate(lines) if line.strip()]
            for pn, lines in page_lines.items()
        }

        top_groups: dict[str, dict] = defaultdict(lambda: {"positions": set(), "examples": set()})
        bottom_groups: dict[str, dict] = defaultdict(lambda: {"positions": set(), "examples": set()})

        for pn in page_numbers:
            indices = page_non_blank[pn]
            lines = page_lines[pn]
            top_idx = indices[:_EDGE_ZONE_LINES]
            bottom_idx = indices[-_EDGE_ZONE_LINES:] if len(indices) > _EDGE_ZONE_LINES else []

            for i in top_idx:
                line = lines[i]
                if _looks_like_esg_content(line):
                    continue
                key = _normalize_key(line)
                if not key:
                    continue
                top_groups[key]["positions"].add((pn, i))
                top_groups[key]["examples"].add(line.strip())

            for i in bottom_idx:
                if i in top_idx:
                    continue
                line = lines[i]
                if _looks_like_esg_content(line):
                    continue
                key = _normalize_key(line)
                if not key:
                    continue
                bottom_groups[key]["positions"].add((pn, i))
                bottom_groups[key]["examples"].add(line.strip())

        total_pages = len(page_numbers)
        min_pages_hit = max(_MIN_PAGES_FOR_HEADER_DETECTION, round(total_pages * _MIN_REPETITION_RATIO))

        header_keys = {k for k, v in top_groups.items() if len({pn for pn, _ in v["positions"]}) >= min_pages_hit}
        footer_keys = {k for k, v in bottom_groups.items() if len({pn for pn, _ in v["positions"]}) >= min_pages_hit}

        removed_headers = sorted({ex for k in header_keys for ex in top_groups[k]["examples"]})
        removed_footers = sorted({ex for k in footer_keys for ex in bottom_groups[k]["examples"]})

        # Only remove lines at the exact edge positions that matched a
        # qualifying key -- never elsewhere on the page, even if the same
        # text coincidentally recurs in the body.
        positions_to_clear: set[tuple[int, int]] = set()
        for k in header_keys:
            positions_to_clear |= top_groups[k]["positions"]
        for k in footer_keys:
            positions_to_clear |= bottom_groups[k]["positions"]

        cleaned: dict[int, str] = {}
        for pn in page_numbers:
            lines = list(page_lines[pn])
            for i in range(len(lines)):
                if (pn, i) in positions_to_clear:
                    lines[i] = ""
            cleaned[pn] = "\n".join(lines).strip("\n")
            cleaned[pn] = _MULTI_BLANK_LINES_RE.sub("\n\n", cleaned[pn])

        return cleaned, HeaderFooterDetectionResult(
            removed_headers=removed_headers, removed_footers=removed_footers
        )
