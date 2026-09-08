from app.document.cleaner import TextCleaner, normalize_whitespace
from app.document.pdf_extractor import ExtractedPage
from app.models.document import PageExtractionStatus


def _page(page_number: int, raw_text: str) -> ExtractedPage:
    return ExtractedPage(
        document_id="DOC-TEST",
        page_number=page_number,
        source_file="test.pdf",
        extraction_status=PageExtractionStatus.OK,
        raw_text=raw_text,
    )


def test_normalize_whitespace_strips_null_chars():
    text = "Scope 1 emissions\x00 were 500 tCO2e."
    assert "\x00" not in normalize_whitespace(text)


def test_normalize_whitespace_collapses_excessive_blank_lines():
    text = "Para one.\n\n\n\n\nPara two."
    result = normalize_whitespace(text)
    assert "\n\n\n" not in result
    assert "Para one." in result and "Para two." in result


def test_normalize_whitespace_preserves_esg_numbers_and_units():
    text = (
        "Scope 1 emissions decreased by 12%.\n\n"
        "Scope 2 emissions were 45,000 tCO2e in 2025.\n\n"
        "Target year: 2030."
    )
    result = normalize_whitespace(text)
    assert "12%" in result
    assert "45,000 tCO2e" in result
    assert "Scope 1" in result and "Scope 2" in result
    assert "2030" in result


def test_repeated_header_is_detected_and_removed():
    header = "Example Company | 2025 Sustainability Report"
    pages = [
        _page(1, f"{header}\n\nIntroduction text for page one goes here."),
        _page(2, f"{header}\n\nEnvironmental content about emissions goes here."),
        _page(3, f"{header}\n\nSocial content about employees goes here."),
        _page(4, f"{header}\n\nGovernance content about the board goes here."),
        _page(5, f"{header}\n\nClosing remarks for the report go here."),
    ]
    result = TextCleaner().clean(pages)
    assert header in result.header_footer_detection.removed_headers
    for pn in range(1, 6):
        assert header not in result.cleaned_texts[pn]


def test_line_appearing_once_is_not_treated_as_header():
    pages = [
        _page(1, "Unique opening line.\n\nBody text about our environmental program."),
        _page(2, "Different opening line.\n\nBody text about our social program."),
        _page(3, "Another different opening.\n\nBody text about governance."),
        _page(4, "Yet another opening line.\n\nMore body text about targets."),
    ]
    result = TextCleaner().clean(pages)
    assert result.header_footer_detection.removed_headers == []
    assert "Unique opening line." in result.cleaned_texts[1]


def test_repeated_line_with_esg_content_is_never_removed():
    # A line that repeats across pages but carries a real metric must
    # survive even though it looks like a candidate header/footer.
    metric_line = "Scope 1 emissions: 123,456 tCO2e"
    pages = [
        _page(1, f"{metric_line}\n\nDiscussion of our climate strategy for the year."),
        _page(2, f"{metric_line}\n\nDiscussion of our energy transition plans."),
        _page(3, f"{metric_line}\n\nDiscussion of our water stewardship efforts."),
        _page(4, f"{metric_line}\n\nDiscussion of our waste reduction initiatives."),
    ]
    result = TextCleaner().clean(pages)
    assert metric_line not in result.header_footer_detection.removed_headers
    for pn in range(1, 5):
        assert metric_line in result.cleaned_texts[pn]


def test_standalone_page_number_removed_only_at_edge():
    pages = [_page(1, "17\n\nBody paragraph mentioning page 17 traffic is not here.\n\n17")]
    result = TextCleaner().clean(pages)
    cleaned = result.cleaned_texts[1]
    assert "Body paragraph mentioning page 17 traffic is not here." in cleaned
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    assert lines == ["Body paragraph mentioning page 17 traffic is not here."]


def test_header_footer_detection_requires_minimum_pages():
    pages = [
        _page(1, "Repeated Header\n\nBody one."),
        _page(2, "Repeated Header\n\nBody two."),
    ]
    result = TextCleaner().clean(pages)
    assert result.header_footer_detection.removed_headers == []
    assert "Repeated Header" in result.cleaned_texts[1]
