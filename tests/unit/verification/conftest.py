from __future__ import annotations

from app.core.config import (
    VerificationConfidenceWeights,
    VerificationConfig,
    VerificationThresholds,
    VerificationWeights,
)
from app.evidence.indexer import EvidenceIndexer
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.evidence.retriever import EvidenceRetriever
from app.models.claim import Claim, ClaimCategory, ClaimType
from app.models.evidence import Evidence, SourceType

# Reuse test doubles already built for analyzer/evidence tests.
from tests.unit.analyzer.conftest import ScriptedLLMProvider, make_manager  # noqa: F401
from tests.unit.evidence.conftest import FakeEmbeddingProvider  # noqa: F401


def verification_config(**overrides) -> VerificationConfig:
    fields = dict(
        candidates_per_claim=5, max_llm_judgment_candidates=3,
        uploaded_report_priority_bonus=0.05, max_schema_retries=0,
    )
    fields.update(overrides)
    return VerificationConfig(_env_file=None, **fields)


def verification_weights(**overrides) -> VerificationWeights:
    fields = dict(
        semantic=0.15, lexical=0.10, numeric=0.20, unit=0.10, temporal=0.10,
        entity=0.10, category=0.05, llm_support=0.15, provenance=0.05,
    )
    fields.update(overrides)
    return VerificationWeights(_env_file=None, **fields)


def verification_confidence_weights(**overrides) -> VerificationConfidenceWeights:
    fields = dict(provenance_quality=0.30, signal_agreement=0.25, llm_reliability=0.25, low_ambiguity=0.20)
    fields.update(overrides)
    return VerificationConfidenceWeights(_env_file=None, **fields)


def verification_thresholds(**overrides) -> VerificationThresholds:
    fields = dict(verified_score_min=80.0, partially_verified_score_min=60.0, numerical_tolerance_pct=2.0)
    fields.update(overrides)
    return VerificationThresholds(_env_file=None, **fields)


def build_claim(
    *, claim_id: str = "CLM-000001", document_id: str = "DOC-001", company: str = "Example Company",
    report_year: int = 2025, page_number: int = 1, section: str | None = "Environmental > Climate",
    source_chunk_id: str = "CHK-00001", claim: str = "Scope 1 emissions decreased by 20% in 2025.",
    category: ClaimCategory = ClaimCategory.ENVIRONMENTAL, claim_type: ClaimType = ClaimType.PERFORMANCE,
    value: float | None = 20.0, unit: str | None = "%", target_year: int | None = None,
    confidence: float = 0.9,
) -> Claim:
    return Claim(
        claim_id=claim_id, document_id=document_id, company=company, report_year=report_year,
        page_number=page_number, section=section, source_chunk_id=source_chunk_id, claim=claim,
        category=category, claim_type=claim_type, value=value, unit=unit, target_year=target_year,
        confidence=confidence,
    )


def build_evidence(
    *, evidence_id: str = "EVD-000001", document_id: str | None = "DOC-001", company: str = "Example Company",
    report_year: int | None = 2025, page_number: int | None = 1, section: str | None = "Environmental > Climate",
    source_chunk_id: str | None = "CHK-00001", evidence_text: str = "Scope 1 emissions decreased by 20% in 2025.",
    category: ClaimCategory | None = ClaimCategory.ENVIRONMENTAL, source_type: SourceType = SourceType.UPLOADED_REPORT,
    source_authority: str | None = "Uploaded ESG Report", organization: str | None = None,
    report_title: str | None = None,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id, source_type=source_type, document_id=document_id, company=company,
        report_year=report_year, page_number=page_number, section=section, source_chunk_id=source_chunk_id,
        category=category, evidence_text=evidence_text, source_authority=source_authority,
        organization=organization, report_title=report_title,
    )


def build_retriever(evidence_list: list[Evidence], tmp_path) -> tuple[EvidenceRetriever, EvidenceRepository]:
    """tmp_path is the standard pytest fixture, passed through by the
    calling test -- a real (temp-file-backed) EvidenceRepository, not a
    bypassed/fake one, so repository.get() behaves exactly as it would in
    production."""
    repository = EvidenceRepository(tmp_path / "evidence_store.json")
    repository.add_many(evidence_list)

    provider = FakeEmbeddingProvider()
    indexer = EvidenceIndexer(provider=provider)
    lexical_index = LexicalIndex()
    indexer.add_many(evidence_list)
    lexical_index.add_many(evidence_list)
    retriever = EvidenceRetriever(repository=repository, indexer=indexer, lexical_index=lexical_index)
    return retriever, repository
