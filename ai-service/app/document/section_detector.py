"""Conservative ESG section detection.

Only recognizes a fixed, documented set of section keywords -- it never
invents a section name. A page is assigned a section only when a short,
heading-like line near the top of the page matches a known keyword;
otherwise the previously detected section carries forward (reports
typically don't repeat the section heading on every page), and if nothing
has ever been detected, the section is explicitly "Unknown".
"""
from __future__ import annotations

import re

from app.core.logging import get_logger

logger = get_logger(__name__)

UNKNOWN_SECTION = "Unknown"

_HEADING_ZONE_LINES = 5
_MAX_HEADING_LINE_LENGTH = 60

# Ordered longest-phrase-first within each category so e.g. "GHG Emissions"
# beats a lone "emissions" match.
SECTION_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "Environmental": {
        "Climate": ["climate change", "climate"],
        "GHG Emissions": [
            "ghg emissions", "greenhouse gas emissions", "scope 1 emissions",
            "scope 2 emissions", "scope 3 emissions", "emissions",
        ],
        "Energy": ["renewable energy", "energy"],
        "Water": ["water stewardship", "water"],
        "Waste": ["waste management", "waste"],
        "Biodiversity": ["biodiversity"],
    },
    "Social": {
        "Employees": ["our employees", "our people", "workforce", "employees"],
        "Health and Safety": ["health and safety", "occupational health"],
        "Human Rights": ["human rights"],
        "Diversity": ["diversity, equity and inclusion", "diversity and inclusion", "diversity"],
        "Community": ["community engagement", "community"],
    },
    "Governance": {
        "Board": ["board of directors", "board composition", "board"],
        "Ethics": ["business ethics", "code of conduct", "ethics"],
        "Compliance": ["regulatory compliance", "compliance"],
        "Risk Management": ["risk management"],
    },
}

_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "Environmental": ["environmental", "environment"],
    "Social": ["social"],
    "Governance": ["governance", "corporate governance"],
}

_ALL_SUBSECTION_PHRASES: list[tuple[str, str, str]] = sorted(
    (
        (phrase, category, subsection)
        for category, subsections in SECTION_KEYWORDS.items()
        for subsection, phrases in subsections.items()
        for phrase in phrases
    ),
    key=lambda item: len(item[0]),
    reverse=True,
)

_ALL_CATEGORY_PHRASES: list[tuple[str, str]] = sorted(
    ((phrase, category) for category, phrases in _CATEGORY_KEYWORDS.items() for phrase in phrases),
    key=lambda item: len(item[0]),
    reverse=True,
)


def _matches_whole_phrase(line_lower: str, phrase: str) -> bool:
    return re.search(rf"\b{re.escape(phrase)}\b", line_lower) is not None


def _detect_heading_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_LINE_LENGTH:
        return None
    lowered = stripped.lower()

    for phrase, category, subsection in _ALL_SUBSECTION_PHRASES:
        if _matches_whole_phrase(lowered, phrase):
            return f"{category} > {subsection}"

    for phrase, category in _ALL_CATEGORY_PHRASES:
        if _matches_whole_phrase(lowered, phrase):
            return category

    return None


class SectionDetector:
    def detect_page_heading(self, cleaned_text: str) -> str | None:
        """Returns a section string only if a heading-like paragraph near
        the top of this page matches a known keyword; otherwise None.

        Only considers paragraphs that stand alone as a single line (no
        internal line wrap) -- a short *wrapped continuation line* of a
        multi-line paragraph (e.g. "environmental, social, and governance
        dimensions." wrapped from a longer sentence) looks identical to a
        heading once naively split on "\\n", so heading candidates are
        drawn from paragraph (blank-line-separated block) boundaries
        instead, where a true heading is reliably its own single-line
        block."""
        paragraphs = [p for p in re.split(r"\n\s*\n", cleaned_text) if p.strip()]
        candidates = [
            p for p in paragraphs[:_HEADING_ZONE_LINES] if "\n" not in p.strip()
        ]  # multi-line paragraph bodies are never standalone headings

        matches = [m for m in (_detect_heading_line(p) for p in candidates) if m]
        if not matches:
            return None

        # A subsection match ("Category > Sub") is more specific than a
        # bare category match and wins even if the category heading
        # appears first in reading order (e.g. "Environmental" then
        # "GHG Emissions" as two separate heading lines).
        for match in matches:
            if " > " in match:
                return match
        return matches[0]

    def assign_sections(self, pages: list[tuple[int, str]]) -> dict[int, str]:
        """`pages` is a list of (page_number, cleaned_text). Returns a
        section per page_number, carrying the last detected section forward
        and defaulting to "Unknown" until one is ever detected."""
        current = UNKNOWN_SECTION
        result: dict[int, str] = {}
        for page_number, text in sorted(pages, key=lambda item: item[0]):
            heading = self.detect_page_heading(text)
            if heading:
                current = heading
            result[page_number] = current

        detected_count = sum(1 for s in result.values() if s != UNKNOWN_SECTION)
        logger.info(
            "sections_assigned",
            extra={"page_count": len(result), "pages_with_known_section": detected_count},
        )
        return result
