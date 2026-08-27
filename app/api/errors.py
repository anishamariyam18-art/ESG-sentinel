"""Centralized API error handling (Phase 10 section 20).

Every `PipelineStageError` becomes the documented
`{"error": {"code", "message", "stage"}}` JSON shape at its own documented
HTTP status code. Any other, unanticipated exception is logged internally
with its full traceback (`logger.exception`) and turned into a generic 500
response that never leaks the traceback or exception internals to the
client.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import PipelineStageError
from app.core.logging import get_logger

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PipelineStageError)
    async def _pipeline_stage_error_handler(request: Request, exc: PipelineStageError) -> JSONResponse:
        logger.warning(
            "api_pipeline_stage_error",
            extra={"path": str(request.url.path), "code": exc.code, "stage": exc.stage, "error": exc.message},
        )
        return JSONResponse(status_code=exc.status_code, content=exc.to_dict())

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("api_unhandled_exception", extra={"path": str(request.url.path)})
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred.", "stage": "unknown"}},
        )
