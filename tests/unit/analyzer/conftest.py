from __future__ import annotations

import json

import pytest

from app.core.config import AnalyzerConfidenceWeights, AnalyzerConfig, LLMConfig
from app.core.llm import LLMGenerationError, LLMManager
from app.models.document import Document, DocumentChunk, PdfMetadata, ProcessingStatistics


class ScriptedLLMProvider:
    """Test double for LLMProvider -- returns scripted responses in order,
    one per call to generate_text, regardless of json_mode. No network."""

    def __init__(self, responses: list[str | Exception]):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def generate_text(self, prompt, *, json_mode, temperature):
        self.calls.append({"prompt": prompt, "json_mode": json_mode, "temperature": temperature})
        if not self.responses:
            raise LLMGenerationError("ScriptedLLMProvider: ran out of scripted responses")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def health_check(self):
        return True


def make_manager(responses: list[str | Exception], max_retries: int = 1) -> tuple[LLMManager, ScriptedLLMProvider]:
    provider = ScriptedLLMProvider(responses)
    manager = LLMManager(provider, config=LLMConfig(_env_file=None, max_retries=max_retries))
    return manager, provider


def analyzer_config(**overrides) -> AnalyzerConfig:
    fields = dict(max_batch_chars=100000, max_chunks_per_batch=100)
    fields.update(overrides)
    return AnalyzerConfig(_env_file=None, **fields)


def confidence_weights() -> AnalyzerConfidenceWeights:
    return AnalyzerConfidenceWeights(_env_file=None)


def build_document(n_chunks: int, text: str = "Scope 1 emissions decreased by 12%.") -> Document:
    chunks = [
        DocumentChunk(
            chunk_id=f"CHK-{i:05d}", document_id="DOC-001", company="Example Company",
            report_year=2025, page_number=i, section="Environmental > Climate", text=text,
        )
        for i in range(1, n_chunks + 1)
    ]
    return Document(
        document_id="DOC-001", company="Example Company", report_year=2025,
        source_filename="report.pdf", file_hash="a" * 64, total_pages=n_chunks,
        metadata=PdfMetadata(page_count=n_chunks), chunks=chunks,
        processing_statistics=ProcessingStatistics(
            page_count=n_chunks, pages_with_text=n_chunks, pages_without_text=0,
            pages_with_errors=0, chunk_count=n_chunks,
        ),
    )


def batch_json(**overrides) -> str:
    payload = {
        "company_name": "Not Found", "reporting_year": None, "industry": "Not Found", "report_type": "Not Found",
        "carbon_emissions": [], "water_usage": [], "renewable_energy": [], "waste_management": [],
        "net_zero_commitments": [], "biodiversity": [], "climate_actions": [],
        "women_employees": [], "employee_diversity": [], "health_and_safety": [], "training": [],
        "csr": [], "human_rights": [],
        "board_independence": [], "ethics": [], "compliance": [], "anti_corruption": [], "risk_management": [],
        "claims": [], "metrics": [], "targets": [], "commitments": [], "risks": [], "opportunities": [],
        "costing_summary": [],
    }
    payload.update(overrides)
    return json.dumps(payload)


def synthesis_json(**overrides) -> str:
    payload = {
        "executive_summary": "Not Found", "environment_summary": "Not Found",
        "social_summary": "Not Found", "governance_summary": "Not Found",
    }
    payload.update(overrides)
    return json.dumps(payload)


@pytest.fixture
def small_document() -> Document:
    return build_document(2)
