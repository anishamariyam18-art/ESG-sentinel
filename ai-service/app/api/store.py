"""Pipeline result storage (section 22): the simplest reliable storage this
prototype already uses elsewhere -- one JSON file per document, exactly the
pattern `EvidenceRepository` already established, so nothing new is
introduced beyond a second instance of a pattern that's already tested and
working.
"""
from __future__ import annotations

from pathlib import Path
from threading import RLock

from app.core.logging import get_logger
from app.models.pipeline import PipelineResult

logger = get_logger(__name__)


class PipelineResultStore:
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _path(self, document_id: str) -> Path:
        return self._output_dir / f"{document_id}.json"

    def save(self, result: PipelineResult) -> None:
        with self._lock:
            self._path(result.document_id).write_text(result.model_dump_json(indent=2), encoding="utf-8")
        logger.info("pipeline_result_stored", extra={"document_id": result.document_id})

    def get(self, document_id: str) -> PipelineResult | None:
        path = self._path(document_id)
        if not path.exists():
            return None
        return PipelineResult.model_validate_json(path.read_text(encoding="utf-8"))

    def exists(self, document_id: str) -> bool:
        return self._path(document_id).exists()
