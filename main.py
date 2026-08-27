"""ESG Sentinel AI Services entrypoint.

Phase 10: application bootstrap, settings, logging, and the full business
API (`app.api.routes`) wired in -- document upload/analysis, and per-stage
result retrieval (claims, verification, greenwashing, trust score,
recommendations).
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import router as api_router
from app.api.errors import register_exception_handlers
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging

settings = get_settings()
setup_logging(level=settings.log_level)
logger = get_logger(__name__)

app = FastAPI(
    title="ESG Sentinel AI Services",
    description="Research-oriented ESG claim extraction, verification, greenwashing, trust scoring, and recommendation pipeline.",
    version="1.0.0",
)

# No authentication/session cookies exist anywhere in this prototype, so an
# open CORS policy carries no credential-leak risk -- it exists purely so
# the Swagger UI (or any browser-based client/tool) can call this API from
# a different origin (e.g. a forwarded dev-tunnel port) without the browser
# blocking the request.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router)


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "service": "esg-sentinel",
        "environment": settings.environment,
        "version": "1.0.0",
    }


@app.get("/ready")
def ready() -> dict:
    """Verifies critical dependencies are reachable -- never raises; a
    dependency failure is reported as `ready: false` with a reason, not a
    500, so a health-check caller gets a clear answer either way. Only the
    evidence repository gates readiness -- the Gemini API key is reported
    for visibility but doesn't block readiness, since every GET endpoint
    and even POST /analyze's deterministic stages work without one."""
    try:
        from app.api.dependencies import get_evidence_repository

        get_evidence_repository()
        repository_ok = True
    except Exception:  # noqa: BLE001 -- readiness check must never raise
        repository_ok = False

    checks = {"evidence_repository": repository_ok, "gemini_api_key_configured": settings.gemini_api_key is not None}
    return {"ready": repository_ok, "checks": checks}


if __name__ == "__main__":
    import uvicorn

    logger.info("starting_server", extra={"environment": settings.environment})
    uvicorn.run(app, host="127.0.0.1", port=8000)
