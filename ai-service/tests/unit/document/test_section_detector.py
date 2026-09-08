from app.document.section_detector import SectionDetector, UNKNOWN_SECTION


def test_unknown_text_never_crashes_and_returns_unknown():
    detector = SectionDetector()
    sections = detector.assign_sections([(1, "Some arbitrary paragraph with no known keywords at all.")])
    assert sections[1] == UNKNOWN_SECTION


def test_category_only_heading_detected():
    detector = SectionDetector()
    heading = detector.detect_page_heading("Environmental\n\nA short intro paragraph follows here.")
    assert heading == "Environmental"


def test_category_and_subsection_heading_detected():
    detector = SectionDetector()
    heading = detector.detect_page_heading("Environmental\n\nGHG Emissions\n\nBody text about emissions.")
    assert heading == "Environmental > GHG Emissions"


def test_section_carries_forward_when_no_new_heading_found():
    detector = SectionDetector()
    pages = [
        (1, "Environmental\n\nClimate\n\nDiscussion of climate strategy."),
        (2, "Continued discussion with no heading on this page at all, just body text."),
        (3, "More continued discussion, still no heading line present here."),
    ]
    sections = detector.assign_sections(pages)
    assert sections[1] == "Environmental > Climate"
    assert sections[2] == "Environmental > Climate"
    assert sections[3] == "Environmental > Climate"


def test_no_heading_ever_detected_stays_unknown_for_all_pages():
    detector = SectionDetector()
    pages = [(1, "Cover page text."), (2, "More generic front matter."), (3, "Table of contents.")]
    sections = detector.assign_sections(pages)
    assert all(s == UNKNOWN_SECTION for s in sections.values())


def test_short_wrapped_continuation_line_does_not_falsely_match_keyword():
    # Regression: a wrapped line from a multi-line paragraph ("...across
    # environmental, social, and governance dimensions.") must not be
    # mistaken for an "Environmental" heading merely because it's short
    # and contains the word "environmental".
    text = (
        "Introduction\n\n"
        "This report summarizes our 2025 ESG performance across\n"
        "environmental, social, and governance dimensions."
    )
    detector = SectionDetector()
    assert detector.detect_page_heading(text) is None


def test_long_body_line_never_treated_as_heading():
    detector = SectionDetector()
    long_line = "Environmental " + ("performance data " * 10)
    heading = detector.detect_page_heading(long_line)
    assert heading is None


def test_only_known_keywords_ever_produce_a_section_never_invented():
    detector = SectionDetector()
    heading = detector.detect_page_heading("Miscellaneous Appendix Notes\n\nSome text.")
    assert heading is None


def test_sections_are_never_fabricated_outside_keyword_map():
    from app.document.section_detector import SECTION_KEYWORDS

    known_sections = {
        f"{category} > {subsection}" for category, subs in SECTION_KEYWORDS.items() for subsection in subs
    } | set(SECTION_KEYWORDS.keys()) | {UNKNOWN_SECTION}

    detector = SectionDetector()
    pages = [
        (1, "Environmental\n\nClimate\n\nBody."),
        (2, "Random unrelated content."),
        (3, "Governance\n\nEthics\n\nBody about ethics."),
    ]
    sections = detector.assign_sections(pages)
    assert set(sections.values()) <= known_sections
