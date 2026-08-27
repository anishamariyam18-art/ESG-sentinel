"""Evidence storage: a clean repository abstraction over a JSON-backed
store.

JSON is deliberately the only storage format for this prototype -- the
point of the `EvidenceRepository` interface is that nothing else in the
codebase touches the file directly, so swapping this for SQLite or another
backend later only requires a new implementation of the same methods, not
call-site changes throughout the codebase.
"""
from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from pydantic import BaseModel, Field

from app.core.logging import get_logger
from app.models.claim import ClaimCategory
from app.models.evidence import Evidence, SourceType

logger = get_logger(__name__)


class EvidenceStats(BaseModel):
    total_records: int = 0
    companies: dict[str, int] = Field(default_factory=dict)
    documents: dict[str, int] = Field(default_factory=dict)
    source_types: dict[str, int] = Field(default_factory=dict)
    categories: dict[str, int] = Field(default_factory=dict)
    indexed_chunk_count: int = 0
    failed_record_count: int = 0


class EvidenceRepository:
    """In-memory index backed by a single JSON file, guarded by a lock so
    concurrent calls within one process don't corrupt the in-memory state
    (this does NOT provide cross-process locking -- acceptable for a
    single-process prototype, a documented limitation for later)."""

    def __init__(self, storage_path: Path):
        self._storage_path = Path(storage_path)
        self._lock = RLock()
        self._records: dict[str, Evidence] = {}
        self._failed_record_count = 0
        self.reload()

    # --- persistence -----------------------------------------------------

    def reload(self) -> None:
        """Re-reads the store from disk, discarding any in-memory state.
        Safe to call any time evidence data changes externally."""
        with self._lock:
            self._records = {}
            self._failed_record_count = 0
            if not self._storage_path.exists():
                return
            raw = json.loads(self._storage_path.read_text(encoding="utf-8") or "[]")
            for entry in raw:
                try:
                    evidence = Evidence.model_validate(entry)
                    self._records[evidence.evidence_id] = evidence
                except Exception as exc:  # noqa: BLE001 -- a corrupt record must not break the whole load
                    self._failed_record_count += 1
                    logger.warning("evidence_record_load_failed", extra={"error": str(exc)})
        logger.info(
            "evidence_repository_reloaded",
            extra={"record_count": len(self._records), "failed_record_count": self._failed_record_count},
        )

    def _persist(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [e.model_dump(mode="json") for e in self._records.values()]
        self._storage_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    # --- writes ------------------------------------------------------------

    def add(self, evidence: Evidence) -> None:
        """Adds (or overwrites, if `evidence_id` already exists) a single
        record and persists immediately."""
        with self._lock:
            self._records[evidence.evidence_id] = evidence
            self._persist()

    def add_many(self, evidence_list: list[Evidence]) -> None:
        if not evidence_list:
            return
        with self._lock:
            for evidence in evidence_list:
                self._records[evidence.evidence_id] = evidence
            self._persist()
        logger.info("evidence_added", extra={"count": len(evidence_list)})

    def delete_document(self, document_id: str) -> int:
        """Removes every record for a given document_id. Returns the
        number of records removed."""
        with self._lock:
            to_delete = [eid for eid, e in self._records.items() if e.document_id == document_id]
            for eid in to_delete:
                del self._records[eid]
            if to_delete:
                self._persist()
        return len(to_delete)

    # --- reads ---------------------------------------------------------

    def get(self, evidence_id: str) -> Evidence | None:
        with self._lock:
            return self._records.get(evidence_id)

    def all(self) -> list[Evidence]:
        with self._lock:
            return list(self._records.values())

    def search(
        self,
        *,
        company: str | None = None,
        document_id: str | None = None,
        report_year: int | None = None,
        source_type: SourceType | None = None,
        category: ClaimCategory | None = None,
        section: str | None = None,
    ) -> list[Evidence]:
        """Metadata-only filtering -- no text/semantic matching here. This
        is the filter step that MUST run before any semantic/lexical
        scoring (see app.evidence.retriever), never the other way around."""
        with self._lock:
            candidates = list(self._records.values())

        def matches(e: Evidence) -> bool:
            if company is not None and e.company != company:
                return False
            if document_id is not None and e.document_id != document_id:
                return False
            if report_year is not None and e.report_year != report_year:
                return False
            if source_type is not None and e.source_type != source_type:
                return False
            if category is not None and e.category != category:
                return False
            if section is not None and e.section != section:
                return False
            return True

        return [e for e in candidates if matches(e)]

    def list_by_document(self, document_id: str) -> list[Evidence]:
        return self.search(document_id=document_id)

    def list_by_company(self, company: str) -> list[Evidence]:
        return self.search(company=company)

    def list_by_source_type(self, source_type: SourceType) -> list[Evidence]:
        return self.search(source_type=source_type)

    def count(self, **filters) -> int:
        return len(self.search(**filters))

    def stats(self) -> EvidenceStats:
        with self._lock:
            records = list(self._records.values())
            failed = self._failed_record_count

        companies: dict[str, int] = {}
        documents: dict[str, int] = {}
        source_types: dict[str, int] = {}
        categories: dict[str, int] = {}
        for e in records:
            companies[e.company] = companies.get(e.company, 0) + 1
            if e.document_id:
                documents[e.document_id] = documents.get(e.document_id, 0) + 1
            source_types[e.source_type.value] = source_types.get(e.source_type.value, 0) + 1
            if e.category:
                categories[e.category.value] = categories.get(e.category.value, 0) + 1

        return EvidenceStats(
            total_records=len(records), companies=companies, documents=documents,
            source_types=source_types, categories=categories,
            indexed_chunk_count=len({e.source_chunk_id for e in records if e.source_chunk_id}),
            failed_record_count=failed,
        )
