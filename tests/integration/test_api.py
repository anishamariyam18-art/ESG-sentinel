"""API layer tests (Phase 10 sections 18-20, 32, 35).

Drives the real FastAPI app through `TestClient`, with only the pipeline's
LLM/embedding dependencies swapped for scripted/fake test doubles (the same
pattern every other integration test in this suite uses) via FastAPI's
`dependency_overrides` -- routing, validation, error handling, and storage
are all exercised for real.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import main
from app.api.dependencies import get_pipeline_orchestrator, get_result_store
from app.api.store import PipelineResultStore
from app.core.config import get_settings, Settings
from app.evidence.indexer import EvidenceIndexer
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.pipeline.service import PipelineOrchestrator
from tests.unit.analyzer.conftest import batch_json, make_manager, synthesis_json
from tests.unit.claims.conftest import extraction_batch_json
from tests.unit.document.conftest import _build_pdf
from tests.unit.evidence.conftest import FakeEmbeddingProvider


@pytest.fixture
def esg_report_pdf(tmp_path):
    header = "Example Company | 2025 Sustainability Report"
    pages = [
        [header, "Introduction", "This report summarizes our 2025 ESG performance."],
        [header, "Environmental", "Climate", "Scope 1 emissions decreased by 20% from the 2020 baseline."],
    ]
    return _build_pdf(tmp_path / "esg_report.pdf", pages)


@pytest.fixture
def api_client(tmp_path, esg_report_pdf):
    from app.document.service import DocumentProcessingService

    probe_document = DocumentProcessingService().process(esg_report_pdf, company="Example Company", report_year=2025)
    env_chunk = next(c for c in probe_document.chunks if "20%" in c.text)

    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    embedding_provider = FakeEmbeddingProvider()
    indexer = EvidenceIndexer(provider=embedding_provider)
    lexical_index = LexicalIndex()

    judgment = json.dumps({"judgments": [{
        "evidence_id": "PLACEHOLDER", "supports_claim": True, "support_level": "full",
        "supported_components": ["metric", "value", "unit", "period"], "unsupported_components": [],
        "contradictions": [], "reason": "The evidence matches the claim.",
    }]})
    manager, provider = make_manager(
        [
            batch_json(company_name="Example Company", reporting_year=2025),
            synthesis_json(),
            extraction_batch_json([{"claim": "Scope 1 emissions decreased by 20%.", "page_number": env_chunk.page_number, "source_chunk_id": env_chunk.chunk_id}]),
            judgment,
        ],
        max_retries=0,
    )
    orchestrator = PipelineOrchestrator(
        repository=repository, indexer=indexer, lexical_index=lexical_index,
        llm_manager=manager, embedding_provider=embedding_provider,
    )
    store = PipelineResultStore(tmp_path / "outputs")
    test_settings = Settings(_env_file=None, upload_dir=tmp_path / "uploads")

    main.app.dependency_overrides[get_pipeline_orchestrator] = lambda: orchestrator
    main.app.dependency_overrides[get_result_store] = lambda: store
    main.app.dependency_overrides[get_settings] = lambda: test_settings

    # raise_server_exceptions=False so an unhandled 500 comes back as a
    # normal response body (to assert on) instead of re-raising in the test
    # process -- matches how a real deployed server behaves for a client.
    client = TestClient(main.app, raise_server_exceptions=False)
    yield client, store
    main.app.dependency_overrides.clear()


# --- Health / readiness ------------------------------------------------------

def test_health_endpoint():
    client = TestClient(main.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ready_endpoint_reports_checks():
    client = TestClient(main.app)
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert "ready" in body
    assert "evidence_repository" in body["checks"]


# --- POST /analyze -----------------------------------------------------------

def test_analyze_runs_the_full_pipeline_and_returns_completed(api_client, esg_report_pdf):
    client, _store = api_client
    with open(esg_report_pdf, "rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("esg_report.pdf", f, "application/pdf")},
            data={"company": "Example Company", "report_year": "2025"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["pipeline_status"] == "completed"
    assert body["document_id"]
    assert len(body["claims"]) == 1
    assert body["trust_score"] is not None
    assert body["recommendations"] is not None


def test_analyze_rejects_non_pdf_file(api_client):
    client, _store = api_client
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("report.txt", b"not a pdf", "text/plain")},
        data={"company": "Example Company", "report_year": "2025"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UPLOAD"


def test_analyze_rejects_empty_file(api_client):
    client, _store = api_client
    response = client.post(
        "/api/v1/analyze",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        data={"company": "Example Company", "report_year": "2025"},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UPLOAD"


def test_analyze_rejects_path_traversal_filename(api_client, esg_report_pdf):
    client, _store = api_client
    with open(esg_report_pdf, "rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("../../evil.pdf", f, "application/pdf")},
            data={"company": "Example Company", "report_year": "2025"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_UPLOAD"


def test_analyze_rejects_a_pdf_with_no_usable_text(api_client, tmp_path):
    client, _store = api_client
    blank_pdf = _build_pdf(tmp_path / "blank.pdf", [[]])
    with open(blank_pdf, "rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("blank.pdf", f, "application/pdf")},
            data={"company": "Example Company", "report_year": "2025"},
        )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "EXTRACTION_FAILED"


def test_analyze_rejects_report_year_zero(api_client, esg_report_pdf):
    """Regression test: report_year=0 (e.g. Swagger UI's default
    placeholder left unfilled) previously reached deep pydantic models
    (DocumentPage requires 1900 <= report_year <= 2100) uncaught, crashing
    with a raw ValidationError and an opaque 500. Must now be rejected at
    the request-validation boundary with a clean 422."""
    client, _store = api_client
    with open(esg_report_pdf, "rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("esg_report.pdf", f, "application/pdf")},
            data={"company": "Example Company", "report_year": "0"},
        )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "report_year"]


def test_analyze_rejects_report_year_out_of_range(api_client, esg_report_pdf):
    client, _store = api_client
    with open(esg_report_pdf, "rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("esg_report.pdf", f, "application/pdf")},
            data={"company": "Example Company", "report_year": "3000"},
        )
    assert response.status_code == 422


def test_analyze_rejects_empty_company(api_client, esg_report_pdf):
    client, _store = api_client
    with open(esg_report_pdf, "rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("esg_report.pdf", f, "application/pdf")},
            data={"company": "", "report_year": "2025"},
        )
    assert response.status_code == 422


def test_analyze_returns_a_clear_error_when_no_llm_is_configured(api_client, esg_report_pdf, tmp_path):
    """Regression test for the opaque 500 previously seen with no
    GEMINI_API_KEY configured: this must be a clear, typed 503, not a
    generic INTERNAL_ERROR."""
    client, store = api_client
    repository = EvidenceRepository(tmp_path / "evidence_store_no_llm.json")
    embedding_provider = FakeEmbeddingProvider()
    indexer = EvidenceIndexer(provider=embedding_provider)
    lexical_index = LexicalIndex()
    orchestrator_without_llm = PipelineOrchestrator(
        repository=repository, indexer=indexer, lexical_index=lexical_index,
        llm_manager=None, embedding_provider=embedding_provider,
    )
    main.app.dependency_overrides[get_pipeline_orchestrator] = lambda: orchestrator_without_llm

    with open(esg_report_pdf, "rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("esg_report.pdf", f, "application/pdf")},
            data={"company": "Example Company", "report_year": "2025"},
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"


# --- GET endpoints ------------------------------------------------------------

def _analyze(client, pdf_path) -> dict:
    with open(pdf_path, "rb") as f:
        response = client.post(
            "/api/v1/analyze",
            files={"file": ("esg_report.pdf", f, "application/pdf")},
            data={"company": "Example Company", "report_year": "2025"},
        )
    assert response.status_code == 200
    return response.json()


def test_get_analysis_returns_the_stored_result(api_client, esg_report_pdf):
    client, _store = api_client
    analyzed = _analyze(client, esg_report_pdf)
    response = client.get(f"/api/v1/analysis/{analyzed['document_id']}")
    assert response.status_code == 200
    assert response.json()["document_id"] == analyzed["document_id"]


def test_get_analysis_404_for_unknown_document(api_client):
    client, _store = api_client
    response = client.get("/api/v1/analysis/DOC-DOES-NOT-EXIST")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


def test_get_claims_returns_total_and_items(api_client, esg_report_pdf):
    client, _store = api_client
    analyzed = _analyze(client, esg_report_pdf)
    response = client.get(f"/api/v1/claims/{analyzed['document_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1


def test_get_verification_returns_status_counts(api_client, esg_report_pdf):
    client, _store = api_client
    analyzed = _analyze(client, esg_report_pdf)
    response = client.get(f"/api/v1/verification/{analyzed['document_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["verified"] + body["partially_verified"] + body["unsupported"] == 1


def test_get_greenwashing_returns_overall_risk(api_client, esg_report_pdf):
    client, _store = api_client
    analyzed = _analyze(client, esg_report_pdf)
    response = client.get(f"/api/v1/greenwashing/{analyzed['document_id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["overall_risk"] in ("Low", "Medium", "High")
    assert len(body["items"]) == 1


def test_get_trust_score_returns_the_stored_score(api_client, esg_report_pdf):
    client, _store = api_client
    analyzed = _analyze(client, esg_report_pdf)
    response = client.get(f"/api/v1/trust-score/{analyzed['document_id']}")
    assert response.status_code == 200
    assert response.json()["trust_score"]["document_id"] == analyzed["document_id"]


def test_get_recommendations_returns_the_stored_recommendations(api_client, esg_report_pdf):
    client, _store = api_client
    analyzed = _analyze(client, esg_report_pdf)
    response = client.get(f"/api/v1/recommendations/{analyzed['document_id']}")
    assert response.status_code == 200
    assert response.json()["recommendations"]["document_id"] == analyzed["document_id"]


# --- Error handling never leaks a traceback ---------------------------------

def test_unhandled_exception_never_leaks_a_traceback(api_client, monkeypatch):
    client, store = api_client

    def _boom(document_id):
        raise RuntimeError("simulated internal failure with a secret detail")

    monkeypatch.setattr(store, "get", _boom)
    response = client.get("/api/v1/analysis/DOC-ANYTHING")
    assert response.status_code == 500
    body = response.json()
    assert "secret detail" not in json.dumps(body)
    assert body["error"]["code"] == "INTERNAL_ERROR"
