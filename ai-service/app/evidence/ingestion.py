"""Evidence ingestion: PDF -> DocumentProcessor -> extraction -> validation
-> storage -> indexing, for both evidence layers.

- `ingest_uploaded_report`: Layer 1, ties evidence to specific claims via
  `EvidenceExtractor`.
- `ingest_external_report` / `ingest_all_external_reports`: Layer 2, every
  chunk of an external report becomes a candidate evidence record (there
  are no claims to tie it to). The SAME pipeline runs for every report --
  nothing here is company-specific.

External reports are discovered under `Settings.reports_dir`
(`data/reports/company_*/`) -- the directory structure Phase 1/2 already
established for "four company PDF reports (prototype external evidence
source)". A company's identity and report year come only from a
`manifest.json` placed next to its PDF (`{"company": ..., "report_year":
...}`); a report directory without one is skipped with a clear reason,
never given a guessed company name or fabricated year.
"""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from app.claims.classifier import deterministic_category
from app.core.config import EvidenceConfig, get_settings
from app.core.logging import get_logger, setup_logging
from app.document.pdf_extractor import PdfExtractionError
from app.document.service import DocumentProcessingService
from app.evidence.extractor import EvidenceExtractor
from app.evidence.indexer import EmbeddingProvider, EvidenceIndexer
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.evidence.validator import validate_evidence
from app.models.claim import Claim
from app.models.document import Document
from app.models.evidence import Evidence, SourceType

logger = get_logger(__name__)


class IngestionResult(BaseModel):
    document_id: str
    company: str
    source_type: SourceType
    evidence_extracted: int
    evidence_validated: int
    evidence_rejected: int
    rejected_reasons: list[str] = Field(default_factory=list)


class IngestionSummary(BaseModel):
    reports_discovered: int
    reports_ingested: int
    reports_skipped: int
    skipped_reasons: list[str] = Field(default_factory=list)
    results: list[IngestionResult] = Field(default_factory=list)


class ReportManifestEntry(BaseModel):
    company: str
    report_year: int
    report_title: str | None = None
    pdf_path: Path


def discover_reports(reports_dir: Path) -> tuple[list[ReportManifestEntry], list[str]]:
    """No hardcoded company names or logic -- every report directory is
    processed identically. Returns (entries, skip_reasons)."""
    entries: list[ReportManifestEntry] = []
    skipped: list[str] = []
    if not reports_dir.exists():
        return entries, skipped

    for company_dir in sorted(p for p in reports_dir.iterdir() if p.is_dir()):
        pdf_paths = sorted(company_dir.glob("*.pdf"))
        if not pdf_paths:
            continue
        manifest_path = company_dir / "manifest.json"
        if not manifest_path.exists():
            skipped.append(f"{company_dir.name}: no manifest.json (company/report_year unknown, not guessed)")
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            company = manifest["company"]
            report_year = int(manifest["report_year"])
            report_title = manifest.get("report_title")
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            skipped.append(f"{company_dir.name}: invalid manifest.json ({exc})")
            continue
        for pdf_path in pdf_paths:
            entries.append(
                ReportManifestEntry(company=company, report_year=report_year, report_title=report_title, pdf_path=pdf_path)
            )
    return entries, skipped


class EvidenceIngestionService:
    def __init__(
        self,
        repository: EvidenceRepository,
        indexer: EvidenceIndexer | None = None,
        lexical_index: LexicalIndex | None = None,
        config: EvidenceConfig | None = None,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._repository = repository
        self._indexer = indexer or EvidenceIndexer(provider=embedding_provider)
        self._lexical_index = lexical_index or LexicalIndex()
        self._config = config or get_settings().evidence
        self._extractor = EvidenceExtractor(embedding_provider=embedding_provider, config=self._config)

    def ingest_uploaded_report(self, document: Document, claims: list[Claim]) -> IngestionResult:
        results = self._extractor.extract_for_claims(document, claims)
        candidates = [e for r in results for e in r.evidence]
        return self._validate_and_store(document, candidates, SourceType.UPLOADED_REPORT)

    def ingest_external_report(
        self, pdf_path: Path, company: str, report_year: int, report_title: str | None = None
    ) -> IngestionResult:
        document = DocumentProcessingService().process(pdf_path, company=company, report_year=report_year)
        candidates = self._build_external_evidence(document, report_title)
        return self._validate_and_store(document, candidates, SourceType.EXTERNAL_REPORT)

    def _build_external_evidence(self, document: Document, report_title: str | None) -> list[Evidence]:
        evidence_list = []
        for chunk in document.chunks:
            if not chunk.text.strip():
                continue
            evidence_list.append(
                Evidence(
                    evidence_id=f"EVD-{document.document_id}-{chunk.chunk_id}",
                    source_type=SourceType.EXTERNAL_REPORT,
                    company=document.company,
                    document_id=document.document_id,
                    report_year=document.report_year,
                    organization=document.company,
                    report_title=report_title or document.source_filename,
                    reporting_period=str(document.report_year),
                    category=deterministic_category(chunk.text),
                    section=chunk.section,
                    page_number=chunk.page_number,
                    source_chunk_id=chunk.chunk_id,
                    evidence_text=chunk.text,
                    source_authority="External ESG Report",
                )
            )
        return evidence_list

    def _validate_and_store(
        self, document: Document, candidates: list[Evidence], source_type: SourceType
    ) -> IngestionResult:
        valid_chunk_ids = {c.chunk_id for c in document.chunks}
        validated: list[Evidence] = []
        rejected_reasons: list[str] = []
        for evidence in candidates:
            ok, reason = validate_evidence(evidence, self._config, valid_chunk_ids=valid_chunk_ids)
            if ok:
                validated.append(evidence)
            else:
                rejected_reasons.append(reason or "invalid evidence")

        self._repository.add_many(validated)
        self._indexer.add_many(validated)
        self._lexical_index.add_many(validated)

        logger.info(
            "evidence_ingested",
            extra={
                "document_id": document.document_id, "company": document.company,
                "source_type": source_type.value, "extracted": len(candidates),
                "validated": len(validated), "rejected": len(rejected_reasons),
            },
        )
        return IngestionResult(
            document_id=document.document_id, company=document.company, source_type=source_type,
            evidence_extracted=len(candidates), evidence_validated=len(validated),
            evidence_rejected=len(rejected_reasons), rejected_reasons=rejected_reasons,
        )


def ingest_all_external_reports(
    reports_dir: Path | None = None, service: EvidenceIngestionService | None = None
) -> IngestionSummary:
    settings = get_settings()
    reports_dir = reports_dir or settings.reports_dir
    service = service or EvidenceIngestionService(
        repository=EvidenceRepository(settings.evidence_dir / settings.evidence.storage_filename)
    )

    entries, skip_reasons = discover_reports(reports_dir)
    directories_with_pdfs = {entry.pdf_path.parent for entry in entries}
    reports_discovered = len(directories_with_pdfs) + len(skip_reasons)

    results: list[IngestionResult] = []
    all_skip_reasons = list(skip_reasons)
    for entry in entries:
        try:
            results.append(
                service.ingest_external_report(entry.pdf_path, entry.company, entry.report_year, entry.report_title)
            )
        except PdfExtractionError as exc:
            all_skip_reasons.append(f"{entry.pdf_path.name}: {exc}")

    return IngestionSummary(
        reports_discovered=reports_discovered,
        reports_ingested=len(results),
        reports_skipped=reports_discovered - len(results),
        skipped_reasons=all_skip_reasons,
        results=results,
    )


def main() -> None:
    setup_logging()
    summary = ingest_all_external_reports()
    print(json.dumps(summary.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
