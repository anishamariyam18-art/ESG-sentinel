"""Phase 10 section 46 final demonstration.

Runs the complete orchestrated pipeline against a REAL sample PDF
(`data/reports/company_1/`) and the REAL, already-ingested multi-report
evidence corpus (`data/evidence/evidence_store.json`, real SentenceTransformer
embeddings -- not a fake/mocked embedding provider).

HONESTY NOTE (section 47): no GEMINI_API_KEY is configured in this
environment, so the Analyzer/Claims/Verification-judgment/Greenwashing-
judgment LLM calls use the SAME scripted-response test double this entire
project's automated test suite uses (`tests/unit/analyzer/conftest.py`'s
`ScriptedLLMProvider`) -- clearly labeled below, never presented as a live
Gemini call. Everything else (PDF extraction, chunking, evidence retrieval
against the real corpus with real embeddings, the deterministic
verification/greenwashing/trust-score/recommendation logic, and all
timings) is completely real, not simulated.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.llm import LLMConfig, LLMManager
from app.evidence.indexer import EvidenceIndexer
from app.evidence.lexical import LexicalIndex
from app.evidence.repository import EvidenceRepository
from app.pipeline.service import PipelineOrchestrator
from tests.unit.analyzer.conftest import ScriptedLLMProvider, batch_json, synthesis_json
from tests.unit.claims.conftest import extraction_batch_json


def main() -> None:
    settings = get_settings()
    pdf_path = settings.reports_dir / "company_1" / "company_1_esg_report.pdf"
    manifest = json.loads((settings.reports_dir / "company_1" / "manifest.json").read_text(encoding="utf-8"))
    company = manifest["company"]
    report_year = manifest["report_year"]

    print("=" * 70)
    print("PHASE 10 END-TO-END DEMONSTRATION")
    print("=" * 70)
    print(f"PDF: {pdf_path}")
    print(f"Company (from manifest, not inferred): {company}")
    print(f"Report year (from manifest): {report_year}")
    print()

    repository = EvidenceRepository(settings.evidence_dir / settings.evidence.storage_filename)
    print(f"Real evidence corpus loaded: {repository.count()} record(s) "
          f"across {len(repository.stats().companies)} companies")

    print("Building real semantic (SentenceTransformer) + lexical (BM25) indexes "
          "from the existing corpus (this loads a real embedding model)...")
    t0 = time.monotonic()
    indexer = EvidenceIndexer()
    lexical_index = LexicalIndex()
    existing = repository.all()
    indexer.add_many(existing)
    lexical_index.add_many(existing)
    print(f"  -> indexed in {time.monotonic() - t0:.2f}s")
    print()

    # Scripted LLM (see module docstring: no GEMINI_API_KEY in this
    # environment). The claim intentionally overstates the report (80%
    # claimed vs the report's actual 15%) to demonstrate the greenwashing
    # and trust-score pathways, not just the "everything passes" path.
    print("NOTE: No GEMINI_API_KEY is configured in this environment -- the")
    print("LLM calls below use the same scripted test double the automated")
    print("test suite uses, NOT a live Gemini call. See tests/integration/")
    print("test_analyzer_live_gemini.py for the one live-Gemini test (skipped")
    print("without credentials).")
    print()

    responses = [
        batch_json(company_name=company, reporting_year=report_year),
        synthesis_json(),
        extraction_batch_json([
            {"claim": "We reduced Scope 1 emissions by 80% in 2024.", "page_number": 2, "source_chunk_id": "PLACEHOLDER"},
        ]),
        json.dumps({"judgments": [{
            "evidence_id": "PLACEHOLDER", "supports_claim": False, "support_level": "none",
            "supported_components": [], "unsupported_components": ["value"],
            "contradictions": ["Evidence states 15%, claim states 80%."],
            "reason": "The evidence reports a smaller reduction than claimed.",
        }]}),
        json.dumps({
            "risk_assessment": "high",
            "reasoning": ["The claimed reduction substantially exceeds what the underlying evidence reports."],
            "intent_assumed": False,
        }),
    ]

    # Resolve the real chunk_id/evidence_id so the scripted responses line up
    # with the real document once it's processed.
    from app.document.service import DocumentProcessingService

    probe = DocumentProcessingService().process(pdf_path, company=company, report_year=report_year)
    env_chunk = next(c for c in probe.chunks if "15%" in c.text)
    responses[2] = extraction_batch_json([
        {"claim": "We reduced Scope 1 emissions by 80% in 2024.", "page_number": env_chunk.page_number, "source_chunk_id": env_chunk.chunk_id}
    ])

    llm_manager = LLMManager(ScriptedLLMProvider(responses), config=LLMConfig(_env_file=None, max_retries=0))

    orchestrator = PipelineOrchestrator(
        repository=repository, indexer=indexer, lexical_index=lexical_index, llm_manager=llm_manager,
    )

    print("Running the full pipeline...")
    started = time.monotonic()
    result = orchestrator.run(pdf_path, company=company, report_year=report_year)
    total_time = time.monotonic() - started

    print()
    print("-" * 70)
    print("RESULTS")
    print("-" * 70)
    print(f"document_id: {result.document_id}")
    print(f"pipeline_status: {result.pipeline_status}")
    print(f"claim count: {len(result.claims)}")
    for claim in result.claims:
        print(f"  - [{claim.claim_id}] \"{claim.claim}\" (page {claim.page_number})")

    print(f"evidence retrieval: {sum(len(v.matched_evidence) for v in result.verification_results)} matched evidence record(s)")

    verified = sum(1 for v in result.verification_results if v.status.value == "Verified")
    partial = sum(1 for v in result.verification_results if v.status.value == "Partially Verified")
    unsupported = sum(1 for v in result.verification_results if v.status.value == "Unsupported")
    print(f"verification distribution: Verified={verified}, Partially Verified={partial}, Unsupported={unsupported}")

    high = sum(1 for g in result.greenwashing_results if g.greenwashing_risk.value == "High")
    medium = sum(1 for g in result.greenwashing_results if g.greenwashing_risk.value == "Medium")
    low = sum(1 for g in result.greenwashing_results if g.greenwashing_risk.value == "Low")
    print(f"greenwashing distribution: High={high}, Medium={medium}, Low={low}")
    for gw in result.greenwashing_results:
        print(f"  - [{gw.claim_id}] risk={gw.greenwashing_risk.value} score={gw.greenwashing_score} types={[t.value for t in gw.greenwashing_type]}")

    if result.trust_score:
        print(f"Trust Score: {result.trust_score.trust_score} ({result.trust_score.rating.value}), confidence={result.trust_score.confidence}")
        print(f"  components: {result.trust_score.components.model_dump()}")

    if result.recommendations:
        print(f"recommendations: {len(result.recommendations.recommendations)}")
        for rec in result.recommendations.recommendations:
            print(f"  - [{rec.priority.value}] {rec.title}")

    print()
    print(f"stage_timings: {json.dumps(result.stage_timings, indent=2)}")
    print(f"TOTAL PROCESSING TIME: {total_time:.3f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
