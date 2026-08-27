from fastapi.testclient import TestClient

from main import app


def test_health_endpoint_reports_healthy():
    """Phase 10 section 35 specifies this exact response shape --
    superseding Phase 1's placeholder {"status": "ok", "version": ...}."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "esg-sentinel"


def test_ready_endpoint_reports_dependency_checks():
    client = TestClient(app)
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert "ready" in body
    assert "evidence_repository" in body["checks"]
    assert "gemini_api_key_configured" in body["checks"]
