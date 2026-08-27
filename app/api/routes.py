"""API v1 routes (Phase 10 section 18).

Every endpoint returns the project's own already-validated Pydantic models
directly (FastAPI serializes them) -- no parallel/duplicate response
schemas. `POST /analyze` runs the full pipeline synchronously (section 19:
"do not introduce unnecessary infrastructure" -- this prototype's pipeline
completes well within a single request/response cycle) and persists the
result so the GET endpoints below can serve it back by `document_id`.

Every dependency is wired via `Depends(...)` (never called directly inside
a handler) so tests can override them with `app.dependency_overrides`.
"""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.dependencies import get_pipeline_orchestrator, get_result_store
from app.api.security import validate_upload
from app.api.store import PipelineResultStore
from app.core.config import EvidencePolicy, Settings, get_settings
from app.core.exceptions import DocumentNotFoundError
from app.core.logging import get_logger
from app.models.pipeline import PipelineResult
from app.pipeline.service import PipelineOrchestrator

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1")


def _get_result_or_404(document_id: str, store: PipelineResultStore) -> PipelineResult:
    result = store.get(document_id)
    if result is None:
        raise DocumentNotFoundError(f"No analysis found for document_id={document_id!r}.")
    return result


@router.post("/analyze")
async def analyze(
    file: UploadFile = File(...),
    company: str = Form(..., min_length=1),
    report_year: int = Form(..., ge=1900, le=2100),
    evidence_policy: EvidencePolicy = Form(EvidencePolicy.INCLUDE_CURRENT_DOCUMENT),
    orchestrator: PipelineOrchestrator = Depends(get_pipeline_orchestrator),
    store: PipelineResultStore = Depends(get_result_store),
    settings: Settings = Depends(get_settings),
) -> PipelineResult:
    file_bytes = await file.read()
    safe_filename = validate_upload(file.filename, len(file_bytes), settings)

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    upload_path = settings.upload_dir / safe_filename
    upload_path.write_bytes(file_bytes)

    result = orchestrator.run(upload_path, company=company, report_year=report_year, evidence_policy=evidence_policy)
    store.save(result)
    return result


@router.get("/analysis/{document_id}")
def get_analysis(document_id: str, store: PipelineResultStore = Depends(get_result_store)) -> PipelineResult:
    return _get_result_or_404(document_id, store)


@router.get("/claims/{document_id}")
def get_claims(document_id: str, store: PipelineResultStore = Depends(get_result_store)) -> dict:
    result = _get_result_or_404(document_id, store)
    return {"document_id": document_id, "total": len(result.claims), "items": result.claims}


@router.get("/verification/{document_id}")
def get_verification(document_id: str, store: PipelineResultStore = Depends(get_result_store)) -> dict:
    result = _get_result_or_404(document_id, store)
    counts = Counter(r.status.value for r in result.verification_results)
    return {
        "document_id": document_id,
        "verified": counts.get("Verified", 0),
        "partially_verified": counts.get("Partially Verified", 0),
        "unsupported": counts.get("Unsupported", 0),
        "items": result.verification_results,
    }


@router.get("/greenwashing/{document_id}")
def get_greenwashing(document_id: str, store: PipelineResultStore = Depends(get_result_store)) -> dict:
    result = _get_result_or_404(document_id, store)
    results = result.greenwashing_results
    counts = Counter(r.greenwashing_risk.value for r in results)
    overall_score = round(sum(r.greenwashing_score for r in results) / len(results), 2) if results else 0.0
    overall_risk = "High" if counts.get("High", 0) > 0 else "Medium" if counts.get("Medium", 0) > 0 else "Low"
    return {
        "document_id": document_id,
        "overall_risk": overall_risk if results else "Unknown",
        "overall_score": overall_score,
        "high_risk": counts.get("High", 0),
        "medium_risk": counts.get("Medium", 0),
        "low_risk": counts.get("Low", 0),
        "items": results,
    }


@router.get("/trust-score/{document_id}")
def get_trust_score(document_id: str, store: PipelineResultStore = Depends(get_result_store)) -> dict:
    result = _get_result_or_404(document_id, store)
    return {"document_id": document_id, "trust_score": result.trust_score}


@router.get("/recommendations/{document_id}")
def get_recommendations(document_id: str, store: PipelineResultStore = Depends(get_result_store)) -> dict:
    result = _get_result_or_404(document_id, store)
    return {"document_id": document_id, "recommendations": result.recommendations}
