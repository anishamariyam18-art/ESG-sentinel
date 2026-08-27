from app.evidence.repository import EvidenceRepository
from app.models.claim import ClaimCategory
from app.models.evidence import Evidence, SourceType


def _evidence(**overrides) -> Evidence:
    fields = dict(
        evidence_id="EVD-000001", source_type=SourceType.UPLOADED_REPORT, document_id="DOC-001",
        company="Company A", report_year=2025, page_number=1, source_chunk_id="CHK-00001",
        category=ClaimCategory.ENVIRONMENTAL, evidence_text="Company A reduced emissions by 20%.",
    )
    fields.update(overrides)
    return Evidence(**fields)


def test_add_and_get(tmp_repository):
    evidence = _evidence()
    tmp_repository.add(evidence)
    fetched = tmp_repository.get("EVD-000001")
    assert fetched is not None
    assert fetched.evidence_text == evidence.evidence_text


def test_get_missing_returns_none(tmp_repository):
    assert tmp_repository.get("EVD-999999") is None


def test_add_many(tmp_repository):
    tmp_repository.add_many([_evidence(evidence_id="EVD-000001"), _evidence(evidence_id="EVD-000002")])
    assert tmp_repository.count() == 2


def test_add_with_same_id_overwrites(tmp_repository):
    tmp_repository.add(_evidence(evidence_text="Original text."))
    tmp_repository.add(_evidence(evidence_text="Updated text."))
    assert tmp_repository.count() == 1
    assert tmp_repository.get("EVD-000001").evidence_text == "Updated text."


def test_search_filters_by_company(tmp_repository):
    tmp_repository.add_many([
        _evidence(evidence_id="EVD-000001", company="Company A", document_id="DOC-A"),
        _evidence(evidence_id="EVD-000002", company="Company B", document_id="DOC-B"),
    ])
    results = tmp_repository.search(company="Company A")
    assert len(results) == 1
    assert results[0].company == "Company A"


def test_search_filters_by_document_id(tmp_repository):
    tmp_repository.add_many([
        _evidence(evidence_id="EVD-000001", document_id="DOC-A"),
        _evidence(evidence_id="EVD-000002", document_id="DOC-B"),
    ])
    assert len(tmp_repository.search(document_id="DOC-A")) == 1


def test_search_filters_by_source_type(tmp_repository):
    tmp_repository.add_many([
        _evidence(evidence_id="EVD-000001", source_type=SourceType.UPLOADED_REPORT),
        Evidence(
            evidence_id="EVD-000002", source_type=SourceType.EXTERNAL_REPORT, company="Company A",
            organization="Company A", report_title="Report", report_year=2025, page_number=1,
            document_id="DOC-002", evidence_text="External evidence text here.",
            source_authority="External ESG Report",
        ),
    ])
    assert len(tmp_repository.search(source_type=SourceType.UPLOADED_REPORT)) == 1
    assert len(tmp_repository.search(source_type=SourceType.EXTERNAL_REPORT)) == 1


def test_search_filters_by_category_and_report_year(tmp_repository):
    tmp_repository.add_many([
        _evidence(evidence_id="EVD-000001", category=ClaimCategory.ENVIRONMENTAL, report_year=2024),
        _evidence(evidence_id="EVD-000002", category=ClaimCategory.SOCIAL, report_year=2025),
    ])
    assert len(tmp_repository.search(category=ClaimCategory.SOCIAL)) == 1
    assert len(tmp_repository.search(report_year=2024)) == 1


def test_list_by_document_company_and_source_type(tmp_repository):
    tmp_repository.add(_evidence())
    assert len(tmp_repository.list_by_document("DOC-001")) == 1
    assert len(tmp_repository.list_by_company("Company A")) == 1
    assert len(tmp_repository.list_by_source_type(SourceType.UPLOADED_REPORT)) == 1


def test_delete_document_removes_only_that_documents_records(tmp_repository):
    tmp_repository.add_many([
        _evidence(evidence_id="EVD-000001", document_id="DOC-A"),
        _evidence(evidence_id="EVD-000002", document_id="DOC-B"),
    ])
    deleted = tmp_repository.delete_document("DOC-A")
    assert deleted == 1
    assert tmp_repository.count() == 1
    assert tmp_repository.get("EVD-000002") is not None


def test_count_with_filters(tmp_repository):
    tmp_repository.add_many([
        _evidence(evidence_id="EVD-000001", company="Company A"),
        _evidence(evidence_id="EVD-000002", company="Company B"),
    ])
    assert tmp_repository.count(company="Company A") == 1
    assert tmp_repository.count() == 2


def test_stats_aggregates_by_company_document_source_type_category(tmp_repository):
    tmp_repository.add_many([
        _evidence(evidence_id="EVD-000001", company="Company A", document_id="DOC-A", category=ClaimCategory.ENVIRONMENTAL),
        _evidence(evidence_id="EVD-000002", company="Company A", document_id="DOC-A", category=ClaimCategory.SOCIAL),
        _evidence(evidence_id="EVD-000003", company="Company B", document_id="DOC-B", category=ClaimCategory.ENVIRONMENTAL),
    ])
    stats = tmp_repository.stats()
    assert stats.total_records == 3
    assert stats.companies == {"Company A": 2, "Company B": 1}
    assert stats.documents == {"DOC-A": 2, "DOC-B": 1}
    assert stats.source_types == {"uploaded_report": 3}
    assert stats.categories == {"Environmental": 2, "Social": 1}


def test_empty_repository_stats(tmp_repository):
    stats = tmp_repository.stats()
    assert stats.total_records == 0
    assert stats.companies == {}


def test_reload_reflects_disk_state(tmp_path):
    repo_a = EvidenceRepository(tmp_path / "evidence_store.json")
    repo_a.add(_evidence())

    repo_b = EvidenceRepository(tmp_path / "evidence_store.json")
    assert repo_b.count() == 1

    repo_a.add(_evidence(evidence_id="EVD-000002"))
    assert repo_b.count() == 1  # repo_b hasn't reloaded yet
    repo_b.reload()
    assert repo_b.count() == 2


def test_persistence_survives_across_instances(tmp_path):
    path = tmp_path / "evidence_store.json"
    EvidenceRepository(path).add(_evidence())
    reloaded = EvidenceRepository(path)
    assert reloaded.count() == 1
    assert reloaded.get("EVD-000001").evidence_text == "Company A reduced emissions by 20%."


def test_missing_storage_file_starts_empty(tmp_path):
    repo = EvidenceRepository(tmp_path / "does_not_exist.json")
    assert repo.count() == 0
    assert repo.all() == []


def test_list_by_document_for_unknown_document_returns_empty(tmp_repository):
    tmp_repository.add(_evidence())
    assert tmp_repository.list_by_document("DOC-DOES-NOT-EXIST") == []


def test_delete_document_for_unknown_document_returns_zero(tmp_repository):
    tmp_repository.add(_evidence())
    assert tmp_repository.delete_document("DOC-DOES-NOT-EXIST") == 0
    assert tmp_repository.count() == 1


def test_corrupt_record_in_storage_does_not_break_reload(tmp_path):
    import json

    path = tmp_path / "evidence_store.json"
    good = _evidence().model_dump(mode="json")
    bad = {"evidence_id": "EVD-BAD", "source_type": "not_a_real_source_type"}
    path.write_text(json.dumps([good, bad]), encoding="utf-8")

    repo = EvidenceRepository(path)
    assert repo.count() == 1
    assert repo.get("EVD-000001") is not None
    assert repo.stats().failed_record_count == 1
