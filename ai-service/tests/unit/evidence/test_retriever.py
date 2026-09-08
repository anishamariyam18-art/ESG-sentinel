from app.evidence.indexer import EvidenceIndexer
from app.evidence.lexical import LexicalIndex
from app.evidence.retriever import EvidenceRetriever
from app.models.evidence import Evidence, SourceType
from tests.unit.evidence.conftest import FakeEmbeddingProvider


def _evidence(evidence_id, company, document_id, text, source_type=SourceType.UPLOADED_REPORT, **overrides):
    fields = dict(
        evidence_id=evidence_id, source_type=source_type, company=company, document_id=document_id,
        page_number=1, source_chunk_id=f"CHK-{evidence_id}", evidence_text=text,
    )
    fields.update(overrides)
    return Evidence(**fields)


def _retriever(repository):
    indexer = EvidenceIndexer(provider=FakeEmbeddingProvider())
    lexical_index = LexicalIndex()
    all_evidence = repository.all()
    indexer.add_many(all_evidence)
    lexical_index.add_many(all_evidence)
    return EvidenceRetriever(repository=repository, indexer=indexer, lexical_index=lexical_index)


def test_search_returns_results_with_both_scores(tmp_repository):
    tmp_repository.add(_evidence("EVD-1", "Company A", "DOC-A", "Scope 1 emissions decreased by 18%."))
    retriever = _retriever(tmp_repository)

    results = retriever.search("Scope 1 emissions", company="Company A")
    assert len(results) == 1
    assert results[0].semantic_score >= 0.0
    assert results[0].lexical_score >= 0.0
    assert results[0].quality_score is not None


def test_search_never_returns_other_companies_evidence(tmp_repository):
    # Mandatory cross-company isolation test (Phase 5 section 28).
    tmp_repository.add(_evidence("EVD-A", "Company A", "DOC-A", "Company A reduced emissions by 20%."))
    tmp_repository.add(_evidence("EVD-B", "Company B", "DOC-B", "Company B reduced emissions by 20%."))
    retriever = _retriever(tmp_repository)

    results = retriever.search("reduced emissions by 20%", company="Company A")

    assert len(results) == 1
    assert results[0].evidence_id == "EVD-A"
    assert results[0].company == "Company A"
    assert all(r.company == "Company A" for r in results)


def test_search_filters_by_document_id(tmp_repository):
    tmp_repository.add(_evidence("EVD-1", "Company A", "DOC-A", "Scope 1 emissions decreased by 18%."))
    tmp_repository.add(_evidence("EVD-2", "Company A", "DOC-B", "Scope 1 emissions decreased by 18%."))
    retriever = _retriever(tmp_repository)

    results = retriever.search("Scope 1 emissions", document_id="DOC-A")
    assert {r.evidence_id for r in results} == {"EVD-1"}


def test_search_filters_by_source_type(tmp_repository):
    tmp_repository.add(_evidence("EVD-1", "Company A", "DOC-A", "Scope 1 emissions decreased by 18%."))
    tmp_repository.add(_evidence(
        "EVD-2", "Company A", "DOC-B", "Scope 1 emissions decreased by 18%.",
        source_type=SourceType.EXTERNAL_REPORT, organization="Company A", report_title="Report",
        report_year=2025, page_number=1, source_authority="External ESG Report",
    ))
    retriever = _retriever(tmp_repository)

    results = retriever.search("Scope 1 emissions", source_type=SourceType.UPLOADED_REPORT)
    assert {r.evidence_id for r in results} == {"EVD-1"}


def test_search_on_empty_database_returns_no_results(tmp_repository):
    retriever = _retriever(tmp_repository)
    assert retriever.search("anything", company="Company A") == []


def test_search_with_no_matching_company_returns_empty(tmp_repository):
    tmp_repository.add(_evidence("EVD-1", "Company A", "DOC-A", "Scope 1 emissions decreased by 18%."))
    retriever = _retriever(tmp_repository)
    assert retriever.search("Scope 1 emissions", company="Company C (does not exist)") == []


def test_search_respects_top_k(tmp_repository):
    for i in range(5):
        tmp_repository.add(_evidence(f"EVD-{i}", "Company A", "DOC-A", f"Scope 1 emissions decreased by {i}%."))
    retriever = _retriever(tmp_repository)
    results = retriever.search("Scope 1 emissions", company="Company A", top_k=2)
    assert len(results) == 2


def test_missing_document_id_filter_returns_no_results(tmp_repository):
    tmp_repository.add(_evidence("EVD-1", "Company A", "DOC-A", "Scope 1 emissions decreased by 18%."))
    retriever = _retriever(tmp_repository)
    assert retriever.search("Scope 1 emissions", document_id="DOC-DOES-NOT-EXIST") == []


def test_exclude_document_id_removes_the_current_document_evidence(tmp_repository):
    """Phase 10 section 26: data leakage protection -- a claim's own
    document's evidence must be excludable so verification can't trivially
    match a claim against its own source text."""
    tmp_repository.add(_evidence("EVD-1", "Company A", "DOC-A", "Scope 1 emissions decreased by 20%."))
    tmp_repository.add(_evidence(
        "EVD-2", "Company A", "DOC-B", "Scope 1 emissions decreased by 20%.",
        source_type=SourceType.EXTERNAL_REPORT, organization="Company A", report_title="Report",
        report_year=2025, page_number=1, source_authority="External ESG Report",
    ))
    retriever = _retriever(tmp_repository)

    results = retriever.search("Scope 1 emissions decreased by 20%", company="Company A", exclude_document_id="DOC-A")
    assert {r.evidence_id for r in results} == {"EVD-2"}
    assert all(r.document_id != "DOC-A" for r in results)


def test_exclude_document_id_none_keeps_default_behavior(tmp_repository):
    tmp_repository.add(_evidence("EVD-1", "Company A", "DOC-A", "Scope 1 emissions decreased by 20%."))
    retriever = _retriever(tmp_repository)
    results = retriever.search("Scope 1 emissions decreased by 20%", company="Company A")
    assert {r.evidence_id for r in results} == {"EVD-1"}
