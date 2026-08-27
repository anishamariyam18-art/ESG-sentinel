import json

from app.evidence.ingestion import (
    EvidenceIngestionService,
    discover_reports,
    ingest_all_external_reports,
)
from app.evidence.repository import EvidenceRepository
from app.models.evidence import SourceType
from tests.unit.document.conftest import _build_pdf
from tests.unit.evidence.conftest import FakeEmbeddingProvider, build_claim, build_document, evidence_config


def _write_report(base_dir, company_slug, company, report_year, report_title=None):
    company_dir = base_dir / company_slug
    company_dir.mkdir(parents=True, exist_ok=True)
    header = f"{company} | {report_year} Sustainability Report"
    pages = [
        [header, "Environmental", "Climate",
         f"{company} reported Scope 1 emissions of 100,000 tCO2e in {report_year}.\n"
         f"{company} reduced emissions by 15% from the prior year."],
    ]
    pdf_path = _build_pdf(company_dir / "report.pdf", pages)
    if report_title is not None or True:
        manifest = {"company": company, "report_year": report_year}
        if report_title:
            manifest["report_title"] = report_title
        (company_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pdf_path


def test_discover_reports_finds_manifested_reports(tmp_path):
    _write_report(tmp_path, "company_a", "Company A", 2025)
    _write_report(tmp_path, "company_b", "Company B", 2024)

    entries, skipped = discover_reports(tmp_path)
    assert len(entries) == 2
    assert skipped == []
    companies = {e.company for e in entries}
    assert companies == {"Company A", "Company B"}


def test_discover_reports_skips_directory_without_manifest(tmp_path):
    company_dir = tmp_path / "company_c"
    company_dir.mkdir()
    _build_pdf(company_dir / "report.pdf", [["Header", "Some content here."]])

    entries, skipped = discover_reports(tmp_path)
    assert entries == []
    assert len(skipped) == 1
    assert "no manifest.json" in skipped[0]


def test_discover_reports_skips_directory_with_invalid_manifest(tmp_path):
    company_dir = tmp_path / "company_d"
    company_dir.mkdir()
    _build_pdf(company_dir / "report.pdf", [["Header", "Some content here."]])
    (company_dir / "manifest.json").write_text("not valid json", encoding="utf-8")

    entries, skipped = discover_reports(tmp_path)
    assert entries == []
    assert len(skipped) == 1


def test_discover_reports_ignores_directories_without_pdfs(tmp_path):
    (tmp_path / "empty_dir").mkdir()
    entries, skipped = discover_reports(tmp_path)
    assert entries == []
    assert skipped == []


def test_discover_reports_never_hardcodes_company_names(tmp_path):
    _write_report(tmp_path, "some_random_dir_name", "Totally Custom Company Name", 2025)
    entries, _ = discover_reports(tmp_path)
    assert entries[0].company == "Totally Custom Company Name"


def _service(tmp_path):
    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    return EvidenceIngestionService(
        repository=repository, config=evidence_config(), embedding_provider=FakeEmbeddingProvider()
    ), repository


def test_ingest_external_report_stores_validated_evidence(tmp_path):
    pdf_path = _write_report(tmp_path / "reports", "company_a", "Company A", 2025)
    service, repository = _service(tmp_path)

    result = service.ingest_external_report(pdf_path, "Company A", 2025)

    assert result.source_type == SourceType.EXTERNAL_REPORT
    assert result.evidence_validated > 0
    assert result.evidence_rejected == 0
    stored = repository.list_by_document(result.document_id)
    assert len(stored) == result.evidence_validated
    assert all(e.source_type == SourceType.EXTERNAL_REPORT for e in stored)
    assert all(e.organization == "Company A" for e in stored)
    assert all(e.report_title for e in stored)


def test_ingest_uploaded_report_ties_evidence_to_claims(tmp_path):
    document = build_document(["Scope 1 emissions decreased by 18% from the 2020 baseline."])
    claim = build_claim(source_chunk_id="CHK-00001", page_number=1)
    service, repository = _service(tmp_path)

    result = service.ingest_uploaded_report(document, [claim])

    assert result.source_type == SourceType.UPLOADED_REPORT
    assert result.evidence_validated == 1
    stored = repository.list_by_document(document.document_id)
    assert len(stored) == 1
    assert stored[0].source_chunk_id == "CHK-00001"


def test_four_report_ingestion_interface_processes_all_discovered_reports(tmp_path):
    reports_dir = tmp_path / "reports"
    for i, company in enumerate(["Company A", "Company B", "Company C", "Company D"], start=1):
        _write_report(reports_dir, f"company_{i}", company, 2025)

    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    service = EvidenceIngestionService(
        repository=repository, config=evidence_config(), embedding_provider=FakeEmbeddingProvider()
    )
    summary = ingest_all_external_reports(reports_dir=reports_dir, service=service)

    assert summary.reports_discovered == 4
    assert summary.reports_ingested == 4
    assert summary.reports_skipped == 0
    companies = {r.company for r in summary.results}
    assert companies == {"Company A", "Company B", "Company C", "Company D"}
    assert repository.count() > 0
    stats = repository.stats()
    assert len(stats.companies) == 4


def test_ingestion_summary_reports_skipped_reports_without_fabricating(tmp_path):
    reports_dir = tmp_path / "reports"
    _write_report(reports_dir, "company_a", "Company A", 2025)
    no_manifest_dir = reports_dir / "company_b"
    no_manifest_dir.mkdir(parents=True)
    _build_pdf(no_manifest_dir / "report.pdf", [["Header", "Some content here."]])

    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    service = EvidenceIngestionService(
        repository=repository, config=evidence_config(), embedding_provider=FakeEmbeddingProvider()
    )
    summary = ingest_all_external_reports(reports_dir=reports_dir, service=service)

    assert summary.reports_discovered == 2
    assert summary.reports_ingested == 1
    assert summary.reports_skipped == 1
    assert any("no manifest.json" in reason for reason in summary.skipped_reasons)


def test_empty_reports_directory_ingests_nothing(tmp_path):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    service = EvidenceIngestionService(
        repository=repository, config=evidence_config(), embedding_provider=FakeEmbeddingProvider()
    )
    summary = ingest_all_external_reports(reports_dir=reports_dir, service=service)
    assert summary.reports_discovered == 0
    assert summary.reports_ingested == 0
    assert repository.count() == 0
