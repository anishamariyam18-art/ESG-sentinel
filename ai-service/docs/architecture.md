# ESG Sentinel AI Services — Architecture

This document describes each stage of the pipeline in detail: input,
output, model/technology, purpose, failure handling, and evaluation. See
[README.md](../README.md) for setup, configuration, and running
instructions; this file is the module-by-module reference.

## Pipeline

```
PDF
 ↓
Document Ingestion (app/document/ingestion.py)
 ↓
PDF/Text Extraction + Cleaning + Section Detection + Chunking (app/document/)
 ↓
Analyzer (app/analyzer/)
 ↓
Claim Extraction, Validation, Splitting, Deduplication, Classification (app/claims/)
 ↓
Evidence Extraction, Storage, Indexing, Retrieval (app/evidence/)
 ↓
Verification (app/verification/)
 ↓
Greenwashing Detection (app/greenwashing/)
 ↓
Trust Score (app/trust_score/)
 ↓
Recommendations (app/recommendations/)
 ↓
Final Assessment (app/models/pipeline.py::PipelineResult, orchestrated by app/pipeline/service.py)
 ↓
API Response (app/api/)
```

Every arrow above is a real Pydantic-model boundary (`app/models/`) — no
undocumented dictionaries cross module boundaries, and `app/pipeline/
service.py::PipelineOrchestrator.run` is the single place that wires every
stage together in this exact order.

---

## Document Ingestion

**Files:** `app/document/ingestion.py`

**Input:** PDF file path or bytes, `company`, `report_year` (caller-supplied
— never inferred from PDF content at this stage).

**Output:** `DocumentIngestionRecord` — `document_id`
(`DOC-<sha256[:16]>`, deterministic, content-only), `source_filename`,
`file_hash` (full SHA-256), `upload_timestamp` (ISO-8601 UTC), `page_count`,
`pages_with_text`, `extraction_status` (`ok`/`partial`), and the full
`Document`.

**Model/Technology:** PyMuPDF (`app/document/pdf_extractor.py`), wrapped by
`DocumentProcessingService` (Phase 2) — no LLM.

**Purpose:** Turn an uploaded PDF into a page-aware, provenance-complete
`Document` before any analysis happens.

**Failure handling:** A PDF that cannot be opened, or a PDF with zero pages
of usable text, raises `DocumentExtractionError` (`EXTRACTION_FAILED`,
HTTP 422) — extraction never silently continues with empty text.

**Evaluation:** Deterministic — extraction status is exact, not estimated.

---

## Text Cleaning, Section Detection, Chunking

**Files:** `app/document/cleaner.py`, `app/document/section_detector.py`,
`app/document/chunker.py`

**Input:** Raw per-page extracted text.

**Output:** Cleaned per-page text, per-page section labels, paragraph-aware
`DocumentChunk`s (never crossing a page boundary).

**Model/Technology:** Rule-based (control-character stripping, repeated
header/footer detection, a fixed E/S/G section-heading keyword list). No
LLM, no ML model.

**Purpose:** Produce clean, structurally addressable text chunks that later
claims and evidence records can point back to.

**Failure handling:** Best-effort, never raises — an unrecognized section
defaults to `"Unknown"` rather than a guess.

**Evaluation:** Covered by Phase 2's unit/integration tests (determinism,
page/chunk provenance survival).

---

## Analyzer

**Files:** `app/analyzer/`

**Input:** `Document` (Phase 2).

**Output:** `AnalyzerResult` — report-level metadata, category breakdowns,
provenance-tagged metrics/targets/commitments/risks/opportunities/costing
entries, executive summary.

**Model/Technology:** Gemini (`app.core.llm.LLMManager` → `GeminiProvider`,
the only file touching `google.generativeai`), batched per
`AnalyzerConfig.max_batch_chars`/`max_chunks_per_batch`.

**Purpose:** Structured, source-grounded extraction of report-level ESG
findings; not exhaustive claim extraction (that's the next stage).

**Failure handling:** A batch that never produces valid JSON after
`max_schema_retries` is excluded (with the reason recorded in
`AnalyzerResult.errors`); if every batch fails, `AnalyzerError` propagates
(`ANALYZER_OUTPUT_INVALID`, HTTP 502 at the API layer) rather than
returning a fabricated result.

**Evaluation:** Deterministic confidence score (`app/analyzer/confidence.py`)
from source coverage, extraction completeness, batch success rate, and JSON
parsing health — never requested from the LLM.

---

## Claim Extraction, Refinement, Classification

**Files:** `app/claims/`

**Input:** `Document` + `AnalyzerResult` (context only — claims are always
re-derived from the original chunks, never synthesized purely from the
analyzer's summary).

**Output:** `ClaimExtractionResult` — a validated `Claim` list, each
carrying full provenance (`document_id`, `page_number`, `source_chunk_id`,
`source_references` for claims spanning multiple chunks).

**Model/Technology:** Gemini for candidate extraction and ambiguous-case
classification; deterministic rules (`app/claims/validator.py`,
`classifier.py`, `splitter.py`, `deduplicator.py`) for everything else.

**Purpose:** Candidate Extraction → Validation → Cleaning → Splitting →
Classification → Deduplication → Final Claims — exhaustive, not just the
"important" claims.

**Failure handling:** A batch that never produces valid JSON raises
`ClaimExtractionBatchError`; total failure raises `ClaimExtractionError`
(`CLAIM_EXTRACTION_FAILED`, HTTP 502). Provenance is never lost during
splitting — a split claim's parent chunk/page stays attached to every
resulting claim.

**Evaluation:** Deterministic confidence score
(`app/claims/classifier.py::compute_claim_confidence`) from ESG relevance,
provenance completeness, classification certainty, numerical clarity, and
completeness.

---

## Evidence Database

**Files:** `app/evidence/`

**Input:** `Document` + `Claim`s (Layer 1, `uploaded_report`) or a PDF +
`manifest.json` (Layer 2, `external_report`, via
`app/evidence/ingestion.py::ingest_external_report`/`ingest_all_external_reports`).

**Output:** `Evidence` records, persisted to `data/evidence/evidence_store.json`
(one JSON file, `EvidenceRepository`), indexed in-memory by
`EvidenceIndexer` (SentenceTransformer embeddings) and `LexicalIndex`
(BM25).

**Model/Technology:** `sentence-transformers/all-MiniLM-L6-v2` (default,
configurable) for semantic embeddings; `rank-bm25` for lexical scoring.

**Purpose:** A company-agnostic, multi-document, multi-report evidence
corpus. `SourceType` is always explicit
(`uploaded_report`/`external_report`/`government`/`regulatory`/`filing`/
`dataset`/`XBRL`) — an uploaded company ESG report is never mislabeled as
government evidence; `government`/`regulatory`/`filing`/`dataset` are
schema-ready but actively rejected by `app/evidence/validator.py` until a
real authoritative source is wired in (section 25's "experimental corpus
vs. authoritative evidence" distinction). `data/reports/company_{1..4}/`
holds 4 CLEARLY FICTIONAL, synthetically generated sample companies
(`scripts/generate_sample_reports.py`) spanning different reporting years
and E/S/G emphases — never real company facts, and nothing in the ingestion
code is specific to any one of them (section 9-10).

**Failure handling:** A report directory without a `manifest.json` is
skipped with a clear reason, never given a guessed company/year. A PDF that
fails extraction is recorded in `skipped_reasons`, never silently dropped.

**Evaluation:** Mandatory cross-company isolation test
(`tests/unit/evidence/test_security_cross_company.py`), plus the Phase 10
multi-report/cross-document tests below.

---

## Evidence Retrieval

**Files:** `app/evidence/retriever.py`

**Input:** Query text + `company`, optional `document_id`/
`exclude_document_id`/`report_year`/`source_type`/`category` filters.

**Output:** `EvidenceMatch` list, each carrying `semantic_score`,
`lexical_score`, `quality_score`, and full provenance (`document_id`,
`page_number`, `source_chunk_id`, `company`) — evidence is never returned
without provenance.

**Model/Technology:** Metadata filtering (via `EvidenceRepository.search`)
always runs BEFORE semantic/lexical scoring — a claim can never surface
another company's evidence merely because of high text similarity
(section 41-42, "entity consistency"; verified directly by
`tests/integration/test_multi_report_corpus.py`).

**Purpose:** "What evidence exists?" only — never decides
Verified/Partially Verified/Unsupported (that's Phase 6's job).

**Failure handling:** An empty/missing evidence database returns `[]`, not
an exception; `EvidenceRetriever.search`'s `top_k` is configurable
(`EvidenceConfig.default_top_k`).

**Evaluation:** `tests/unit/evidence/test_retriever.py`.

---

## Data Leakage Protection

**Files:** `app/core/config.py::EvidencePolicy`, `app/evidence/retriever.py`,
`app/verification/service.py`

Two documented modes:

- **`include_current_document`** (project default): a claim is checked
  against its own uploaded report's evidence AND any other ingested
  evidence. This is the mode every one of this project's 9 analysis phases
  was designed and tested around — Phase 5's Layer-1 evidence extraction
  exists specifically so a summary claim can be checked against the
  detailed passage elsewhere in the SAME report.
- **`external_evidence_only`**: excludes the claim's own `document_id`
  from retrieval entirely, so verification can only draw on independently
  ingested evidence. Use this for genuine cross-report corroboration or
  evaluation, where retrieving a claim's own source text back at itself
  would trivially and artificially inflate verification performance.

Section 26 names `external_evidence_only` as the recommended *production*
default; this prototype implements it as a fully supported, tested,
first-class option (`VerificationService.verify_claim(claim,
evidence_policy=...)`, `POST /api/v1/analyze`'s `evidence_policy` form
field) but keeps `include_current_document` as the actual default, since
flipping it would silently invalidate the "verify a report's claims
against its own disclosures" behavior every prior phase's tests assume,
without any test having exposed a defect in that behavior. Documented here
rather than silently decided either way.

---

## Verification

**Files:** `app/verification/`

**Input:** `Claim` + the evidence corpus (via `EvidenceRetriever`).

**Output:** `VerificationResult` — canonical status
`Verified`/`Partially Verified`/`Unsupported` (one representation only, no
`Supported`/`Partially Supported` variants), `verification_score` (0-100),
`confidence_score` (0-100, deliberately independent), per-signal `checks`,
`matched_evidence`, `explanation`.

**Model/Technology:** Deterministic consistency checks
(`app/verification/consistency.py` — numeric/unit/temporal/entity/category,
never trusting `Evidence.value`/`unit` directly, always re-extracting from
text) + Gemini for evidence judgment (`app/verification/judge.py`,
contributes only the `llm_support` signal) + a documented weighted formula
(`app/verification/scorer.py`).

**Purpose:** Compare the CLAIM against its MATCHED EVIDENCE — never trusts
semantic similarity alone (section 12). A claim stating "80%" against
evidence stating "20%" is caught by `numeric_consistency`'s hard-fail
detection regardless of how semantically similar the two sentences read.

**Failure handling:** `wrong_company` and an LLM-reported explicit
contradiction force `Unsupported` outright; a numeric/direction
contradiction, incompatible unit, or incompatible target year caps the
result at `Partially Verified` even with an otherwise-high score. Retrieval
failure or LLM unavailability never crashes verification — both fall back
to a documented, structured `Unsupported`/neutral-signal result.

**Evaluation:** `app/evaluation/gold_verification.py` — a 21-case synthetic
gold set evaluated against the deterministic consistency-checking core
(numeric matches/mismatches, unit mismatches, direction contradictions,
target-year mismatches, vague claims, wrong-company evidence). See that
module's docstring for exactly what is and isn't exercised (no live LLM
call is made).

---

## Greenwashing Detection

**Files:** `app/greenwashing/`

**Input:** `Claim` + `VerificationResult` (which already carries matched
evidence) — nothing independently re-searched.

**Output:** `GreenwashingResult` — multi-label `greenwashing_type` (up to 11
simultaneous signals, or `No Significant Greenwashing Signal`),
`greenwashing_risk` (`Low`/`Medium`/`High`), `greenwashing_score` (0-100),
`features`, `explanation`, `recommendation`.

**Model/Technology:** 11 deterministic signal detectors
(`app/greenwashing/detector.py` — vague/absolute/exaggerated/contradictory/
unsupported-benefit/misleading-comparison/missing-qualification/selective-
presentation, reusing Phase 6's consistency extraction for the numeric/
unit/temporal/direction signals) + a documented weighted score
(`app/greenwashing/scorer.py`) + Gemini for advisory-only reasoning
(`app/greenwashing/judge.py`, never controls the type list or score).

**Purpose:** `Unsupported` verification status is explicitly NOT treated as
greenwashing by itself (section 14) — the type list only ever includes
`Unsupported Environmental Claim` alongside a concrete signal that was
actually detected. Intent is never inferred: an LLM reasoning line
asserting "intentionally deceived" is filtered out even if the LLM
self-reports otherwise.

**Failure handling:** A claim analysis failure returns a structured
Low-risk result explaining what went wrong — uncertainty is never
fabricated as risk.

**Evaluation:** `app/evaluation/gold_greenwashing.py` — a 14-case synthetic
gold set covering every category section 29 requires (no signal, vague,
exaggerated, contradictory, unsupported benefit, absolute), evaluated
against the real, already-100%-deterministic classification logic
(no LLM involved at all, since the LLM never controls this classification
in production either).

---

## Trust Score

**Files:** `app/trust_score/`

**Input:** `Claim`s + `VerificationResult`s + `GreenwashingResult`s
(+ optionally `AnalyzerResult`, for context/logging only).

**Output:** `TrustScore` — `trust_score` (0-100), `rating`
(`Excellent`/`Good`/`Moderate`/`Low`), `confidence` (0-100, deliberately
separate from the score), 6 `components`, `statistics`, `explanation`,
`strengths`, `weaknesses`, `limitations`.

**Model/Technology:** 100% deterministic weighted formula
(`app/trust_score/scorer.py` — claim_support, evidence_quality,
consistency, transparency, greenwashing_risk, provenance) + an optional
Gemini-generated narrative appended to `explanation` only (never the
score).

**Purpose:** "How well-supported and internally consistent is the ESG
information?" — never `verified_claims / total_claims * 100` (too
simplistic per section 30); always the full weighted combination of all 6
components.

**Failure handling:** Works with zero LLM configuration — the LLM manager
is never auto-constructed, and any narrative failure is caught and logged,
never propagated. A zero-claim report returns `trust_score=0`,
`confidence=0`, with an honest "no claims were available" explanation
rather than a fabricated score.

**Evaluation:** `tests/unit/evaluation/test_trust_score_validation.py` —
same-input-same-score determinism, and the 4 monotonicity properties
section 30 names directly (worse verification → lower score; more
contradiction → lower consistency; higher greenwashing risk → lower score;
better evidence support → higher score), exercised against the real
production `TrustScoreService`.

---

## Recommendations

**Files:** `app/recommendations/`

**Input:** `Claim`s + `VerificationResult`s + `GreenwashingResult`s +
`TrustScore`.

**Output:** `RecommendationResult` — `overall_assessment`, `strengths`,
`weaknesses` (both reused verbatim from `TrustScore`, never re-derived),
`recommendations` (each with `source_claim_ids`, `source_findings`,
`category`, `priority`, `priority_score`, `action`, `reason`,
`expected_impact`, `time_horizon`, `explanation`), `priority_actions`,
`implementation_areas`, `limitations`.

**Model/Technology:** ~19 deterministic `IF <finding> THEN <Finding>` rules
(`app/recommendations/rules.py`) + a documented weighted priority formula
with a hard-signal override (`app/recommendations/prioritizer.py`) +
template-based recommendation text (`FINDING_TEMPLATES`) + optional Gemini
narrative appended to `overall_assessment` only.

**Purpose:** Every recommendation traces back to at least one concrete
`Finding`; a finding_type with zero supporting findings never produces a
recommendation (section 6). Never "Improve ESG." — every action names the
specific problem category (e.g. "Reconcile numerical values in
Environmental claims").

**Failure handling:** Works with zero LLM configuration, same pattern as
Trust Score. Output is capped (`max_recommendations`/`max_priority_actions`,
both configurable) and deduplicated by `(finding_type, category)` grouping
so 10 similar findings produce one recommendation, not ten.

**Evaluation:** Phase 9's own critical-test suite (4 exact scenarios from
the original spec) plus `tests/unit/evaluation/test_explainability_validation.py`
(every claim_id cited in a recommendation is checked against the real
claim list).

---

## Final Assessment & API

**Files:** `app/pipeline/service.py::PipelineOrchestrator`, `app/api/`

`PipelineOrchestrator.run` is the only place all 9 stages are wired
together; each stage's failure is caught individually and turned into a
`PipelineResult` with `pipeline_status` (`completed`/`partial`/`failed`)
and a stage-attributed `errors` list, rather than a bare exception —
whatever was already computed is preserved and returned. `stage_timings`
records wall-clock seconds per stage.

`app/api/routes.py` exposes this synchronously (section 19 — this
prototype's pipeline comfortably completes within one request; no queue/
worker infrastructure was added for a workload that doesn't need it):

- `POST /api/v1/analyze` — upload a PDF, run the full pipeline, persist
  and return the result.
- `GET /api/v1/analysis/{document_id}` — the full stored `PipelineResult`.
- `GET /api/v1/claims/{document_id}`, `/verification/{document_id}`,
  `/greenwashing/{document_id}`, `/trust-score/{document_id}`,
  `/recommendations/{document_id}` — per-stage views of the same stored
  result.
- `GET /health`, `GET /ready` — liveness and dependency readiness.

Every `PipelineStageError` becomes `{"error": {"code", "message", "stage"}}`
at a documented HTTP status (`app/core/exceptions.py`); any other exception
is logged internally with its full traceback and never leaks details to
the client (`app/api/errors.py`).

Results are stored one JSON file per `document_id`
(`app/api/store.py::PipelineResultStore`, `data/outputs/`) — the same
"one JSON file per record" pattern `EvidenceRepository` already uses.
