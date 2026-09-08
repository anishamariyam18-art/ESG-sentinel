import pytest

from app.document.pdf_extractor import PdfExtractionError, PdfExtractor, compute_document_id
from app.models.document import PageExtractionStatus


def test_pdf_opens_and_extracts_all_pages(esg_report_pdf):
    result = PdfExtractor().extract(esg_report_pdf)
    assert len(result.pages) == 6


def test_page_count_matches_metadata(esg_report_pdf):
    result = PdfExtractor().extract(esg_report_pdf)
    assert result.metadata.page_count == 6
    assert len(result.pages) == result.metadata.page_count


def test_every_page_gets_sequential_page_number(esg_report_pdf):
    result = PdfExtractor().extract(esg_report_pdf)
    assert [p.page_number for p in result.pages] == [1, 2, 3, 4, 5, 6]


def test_empty_page_is_preserved_not_discarded(empty_page_pdf):
    result = PdfExtractor().extract(empty_page_pdf)
    assert len(result.pages) == 2
    assert result.pages[0].extraction_status == PageExtractionStatus.EMPTY
    assert result.pages[0].raw_text == ""
    assert result.pages[1].extraction_status == PageExtractionStatus.OK


def test_raw_text_is_preserved(esg_report_pdf):
    result = PdfExtractor().extract(esg_report_pdf)
    page_2 = result.pages[1]
    assert "Scope 1 emissions decreased by 12%" in page_2.raw_text
    assert "45,000 tCO2e" in page_2.raw_text


def test_every_extracted_page_carries_document_id_and_source_file(esg_report_pdf):
    result = PdfExtractor().extract(esg_report_pdf)
    for page in result.pages:
        assert page.document_id == result.document_id
        assert page.source_file == "esg_report.pdf"


def test_same_pdf_bytes_produce_same_document_id(esg_report_pdf):
    result_a = PdfExtractor().extract(esg_report_pdf)
    result_b = PdfExtractor().extract(esg_report_pdf)
    assert result_a.document_id == result_b.document_id
    assert result_a.file_hash == result_b.file_hash


def test_different_pdfs_produce_different_document_ids(esg_report_pdf, other_pdf):
    result_a = PdfExtractor().extract(esg_report_pdf)
    result_b = PdfExtractor().extract(other_pdf)
    assert result_a.document_id != result_b.document_id


def test_compute_document_id_is_deterministic_and_content_sensitive():
    id_a, hash_a = compute_document_id(b"identical bytes")
    id_b, hash_b = compute_document_id(b"identical bytes")
    id_c, hash_c = compute_document_id(b"different bytes")
    assert id_a == id_b
    assert hash_a == hash_b
    assert id_a != id_c
    assert hash_a != hash_c


def test_extract_raises_on_missing_file(tmp_path):
    with pytest.raises(PdfExtractionError):
        PdfExtractor().extract(tmp_path / "does_not_exist.pdf")


def test_extract_raises_on_non_pdf_bytes():
    with pytest.raises(PdfExtractionError):
        PdfExtractor().extract_bytes(b"this is not a pdf", source_file="fake.pdf")


def test_extract_raises_on_empty_bytes():
    with pytest.raises(PdfExtractionError):
        PdfExtractor().extract_bytes(b"", source_file="empty.pdf")


def test_metadata_missing_fields_represented_as_none(esg_report_pdf):
    result = PdfExtractor().extract(esg_report_pdf)
    # Synthetically generated PDFs carry no author/title -- must not be fabricated.
    assert result.metadata.author is None
    assert result.metadata.title is None
