import pytest

from app.claims.extractor import ClaimExtractionBatchError, ClaimExtractor
from app.models.document import DocumentChunk
from tests.unit.claims.conftest import claims_config, extraction_batch_json, make_manager


def _chunk(i: int) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"CHK-{i:05d}", document_id="DOC-001", company="Example Company", report_year=2025,
        page_number=i, section="Environmental > Climate", text="Scope 1 emissions decreased by 12%.",
    )


def test_extract_batch_returns_candidates_with_provenance():
    manager, _ = make_manager([
        extraction_batch_json([
            {"claim": "Scope 1 emissions decreased by 12%.", "page_number": 1, "source_chunk_id": "CHK-00001"}
        ])
    ])
    extractor = ClaimExtractor(manager, claims_config(max_schema_retries=0))
    candidates, repair_count = extractor.extract_batch("DOC-001", [_chunk(1)], 1, 1)
    assert len(candidates) == 1
    assert candidates[0].page_number == 1
    assert candidates[0].source_chunk_id == "CHK-00001"
    assert repair_count == 0


def test_extract_batch_handles_empty_candidates():
    manager, _ = make_manager([extraction_batch_json([])])
    extractor = ClaimExtractor(manager, claims_config(max_schema_retries=0))
    candidates, _ = extractor.extract_batch("DOC-001", [_chunk(1)], 1, 1)
    assert candidates == []


def test_extract_batch_raises_on_unparseable_json_after_retries():
    manager, _ = make_manager(["not json {{{"], max_retries=0)
    extractor = ClaimExtractor(manager, claims_config(max_schema_retries=0))
    with pytest.raises(ClaimExtractionBatchError):
        extractor.extract_batch("DOC-001", [_chunk(1)], 1, 1)


def test_extract_batch_raises_when_schema_invalid():
    bad_json = extraction_batch_json([{"claim": "text only, missing page/chunk"}])
    manager, _ = make_manager([bad_json], max_retries=0)
    extractor = ClaimExtractor(manager, claims_config(max_schema_retries=0))
    with pytest.raises(ClaimExtractionBatchError):
        extractor.extract_batch("DOC-001", [_chunk(1)], 1, 1)


def test_extract_batch_tracks_json_repair_count():
    manager, _ = make_manager([
        "```json\n" + extraction_batch_json([
            {"claim": "Scope 1 emissions decreased by 12%.", "page_number": 1, "source_chunk_id": "CHK-00001"}
        ]) + "\n```"
    ])
    extractor = ClaimExtractor(manager, claims_config(max_schema_retries=0))
    _, repair_count = extractor.extract_batch("DOC-001", [_chunk(1)], 1, 1)
    assert repair_count == 1
