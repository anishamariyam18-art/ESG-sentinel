"""Multi-report evidence corpus tests (Phase 10 sections 40-41).

Self-contained (tmp_path + a `FakeEmbeddingProvider`, consistent with every
other test in this suite -- no network, no real model download) rather than
depending on the actual populated `data/reports/company_{1..4}/` sample
corpus, so this test stays deterministic regardless of what real sample
data happens to be on disk. `scripts/generate_sample_reports.py` populates
that real corpus separately for manual/demonstration use.

Section 40: the system must not assume any one company is always the
evidence source -- retrieval must work correctly across a corpus spanning
multiple companies and reporting years.

Section 41 (CRITICAL): a claim must never be marked Verified merely because
some OTHER company's report contains semantically similar wording. Company
scoping is enforced by `EvidenceRetriever`/`EvidenceRepository` metadata
filtering (mandatory since Phase 5); this test proves it holds using a
genuine multi-company corpus, not just a 2-record synthetic pair.
"""
from __future__ import annotations

from app.document.service import DocumentProcessingService
from app.evidence.indexer import EvidenceIndexer
from app.evidence.ingestion import EvidenceIngestionService
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.evidence.retriever import EvidenceRetriever
from app.models.claim import Claim, ClaimCategory, ClaimType
from app.models.verification import VerificationStatus
from app.verification.service import VerificationService
from tests.unit.analyzer.conftest import make_manager
from tests.unit.document.conftest import _build_pdf
from tests.unit.evidence.conftest import FakeEmbeddingProvider
from tests.unit.verification.conftest import verification_config, verification_confidence_weights, verification_thresholds, verification_weights

_COMPANIES = [
    ("Aurora Materials Inc.", 2024, "Scope 1 emissions decreased by 15% from the 2021 baseline."),
    ("Meridian Foods Co.", 2025, "Women held 38% of management positions in 2025."),
    ("Northwind Energy Corp.", 2023, "Independent directors held 75% of board seats in 2023."),
    ("Cobalt Textiles Ltd.", 2025, "Textile waste sent to landfill decreased by 30% in 2025."),
]


def _build_corpus(tmp_path):
    """Ingests 4 distinct fictional companies' reports as external evidence,
    exactly the multi-report architecture `app.evidence.ingestion` supports
    -- nothing here is company-specific logic."""
    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    embedding_provider = FakeEmbeddingProvider()
    indexer = EvidenceIndexer(provider=embedding_provider)
    lexical_index = LexicalIndex()
    ingestion_service = EvidenceIngestionService(
        repository=repository, indexer=indexer, lexical_index=lexical_index, embedding_provider=embedding_provider,
    )

    for i, (company, report_year, fact_sentence) in enumerate(_COMPANIES):
        header = f"{company} | {report_year} ESG Report"
        pdf_path = _build_pdf(tmp_path / f"report_{i}.pdf", [[header, "Environmental", fact_sentence]])
        ingestion_service.ingest_external_report(pdf_path, company=company, report_year=report_year)

    retriever = EvidenceRetriever(repository=repository, indexer=indexer, lexical_index=lexical_index)
    return retriever, repository


# --- Section 40: retrieval works across the whole corpus --------------------

def test_40_retrieval_works_for_every_company_in_the_corpus(tmp_path):
    retriever, _ = _build_corpus(tmp_path)
    for company, _report_year, fact_sentence in _COMPANIES:
        results = retriever.search(fact_sentence, company=company)
        assert results, f"expected evidence for {company}"
        assert all(r.company == company for r in results)


def test_40_corpus_contains_multiple_companies_and_years(tmp_path):
    _, repository = _build_corpus(tmp_path)
    stats = repository.stats()
    assert len(stats.companies) == 4
    assert stats.total_records == 4


# --- Section 41 (CRITICAL): cross-document / cross-company isolation -------

def test_41_claim_from_uningested_company_is_not_verified_via_another_companys_evidence(tmp_path):
    """A brand-new company (not in the corpus at all) makes a claim with
    wording nearly identical to Aurora Materials' -- it must NOT be
    verified just because a semantically similar sentence exists for a
    different company."""
    retriever, repository = _build_corpus(tmp_path)

    claim = Claim(
        claim_id="CLM-000001", document_id="DOC-NEWCO", company="Zephyr Robotics Co.", report_year=2025,
        page_number=1, source_chunk_id="CHK-00001", claim="Scope 1 emissions decreased by 15% from the 2021 baseline.",
        category=ClaimCategory.ENVIRONMENTAL, claim_type=ClaimType.PERFORMANCE, value=15.0, unit="%", confidence=0.9,
    )
    manager, _ = make_manager([], max_retries=0)
    service = VerificationService(
        retriever=retriever, repository=repository, llm_manager=manager,
        config=verification_config(max_schema_retries=0), weights=verification_weights(),
        confidence_weights=verification_confidence_weights(), thresholds=verification_thresholds(),
    )

    result = service.verify_claim(claim)
    assert result.status == VerificationStatus.UNSUPPORTED
    assert result.matched_evidence == []


def test_41_claim_is_verified_only_against_its_own_companys_evidence(tmp_path):
    """Sanity check: the SAME wording, attributed to the CORRECT company,
    does retrieve that company's own evidence -- proving the isolation in
    the test above is about company scoping, not a broken retriever."""
    retriever, repository = _build_corpus(tmp_path)

    claim = Claim(
        claim_id="CLM-000001", document_id="DOC-AURORA", company="Aurora Materials Inc.", report_year=2024,
        page_number=1, source_chunk_id="CHK-00001", claim="Scope 1 emissions decreased by 15% from the 2021 baseline.",
        category=ClaimCategory.ENVIRONMENTAL, claim_type=ClaimType.PERFORMANCE, value=15.0, unit="%", confidence=0.9,
    )
    manager, _ = make_manager([], max_retries=0)
    service = VerificationService(
        retriever=retriever, repository=repository, llm_manager=manager,
        config=verification_config(max_schema_retries=0), weights=verification_weights(),
        confidence_weights=verification_confidence_weights(), thresholds=verification_thresholds(),
    )

    result = service.verify_claim(claim)
    assert result.matched_evidence
    assert all(m.company == "Aurora Materials Inc." for m in result.matched_evidence)


def test_41_entity_consistency_company_filter_beats_pure_text_similarity(tmp_path):
    """Section 42: metadata (company) filtering must run BEFORE similarity
    scoring -- a claim attributed to the wrong company must never surface
    another company's textually-identical evidence, no matter how high the
    semantic similarity would otherwise be."""
    retriever, _ = _build_corpus(tmp_path)

    # Identical text to Meridian Foods' own evidence, but queried under a
    # different company name entirely -- the metadata filter must exclude
    # Meridian's record before similarity scoring ever runs, regardless of
    # how textually similar it is to the query.
    results = retriever.search("Women held 38% of management positions in 2025.", company="Aurora Materials Inc.")
    assert all(r.company == "Aurora Materials Inc." for r in results)
    assert not any(r.evidence_text.startswith("Women held 38%") for r in results)
