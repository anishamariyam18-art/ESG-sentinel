"""Analyzer prompts.

No Python logic lives here -- only prompt text and thin string-formatting
functions that assemble it from already-computed context. All extraction
rules (source-only, no fabrication, "Not Found"/[] conventions) are stated
here in plain language for the model; they are separately, deterministically
enforced by Pydantic validation and the merge/confidence logic in Python.
"""
from __future__ import annotations

from app.analyzer.context_builder import format_batch_context
from app.models.document import DocumentChunk

_SOURCE_ONLY_RULES = """You are an ESG report analysis system. You must follow these rules exactly:

1. Use ONLY the text provided below. Never use outside knowledge about this
   company, industry, or ESG topics in general.
2. Never guess or infer information that is not explicitly stated in the
   provided text (company name, industry, reporting year, metrics, targets,
   commitments, risks, opportunities, financial figures).
3. If a field is not explicitly supported by the provided text, use the
   exact string "Not Found" for text fields or an empty list [] for list
   fields. Do not leave a field out and do not guess a plausible value.
4. Distinguish carefully between:
   - a metric: a specific reported numerical measurement,
   - a target: an explicitly stated future goal with a metric/value/year,
   - a commitment: an explicit pledge or stated future action (not every
     ESG-sounding sentence is a commitment),
   - a risk: a risk the report itself explicitly names,
   - an opportunity: an opportunity the report itself explicitly names,
   - a general/promotional statement: none of the above -- do not force
     it into one of these categories.
5. Every metric, target, commitment, risk, opportunity, and costing entry
   MUST cite the exact chunk id and page number it came from, copied
   verbatim from the "Chunk:" and "Page:" labels above the text it was
   found in. Never invent a chunk id or page number.
6. Respond with a single JSON object only -- no markdown, no commentary,
   no text before or after the JSON.
"""


def build_batch_prompt(batch: list[DocumentChunk], batch_number: int, total_batches: int) -> str:
    context = format_batch_context(batch)
    schema = """Respond with a JSON object with exactly these keys:

{
  "company_name": "string or 'Not Found'",
  "reporting_year": integer or null,
  "industry": "string or 'Not Found'",
  "report_type": "string or 'Not Found'",

  "carbon_emissions": ["string", ...], "water_usage": [...], "renewable_energy": [...],
  "waste_management": [...], "net_zero_commitments": [...], "biodiversity": [...], "climate_actions": [...],

  "women_employees": [...], "employee_diversity": [...], "health_and_safety": [...],
  "training": [...], "csr": [...], "human_rights": [...],

  "board_independence": [...], "ethics": [...], "compliance": [...],
  "anti_corruption": [...], "risk_management": [...],

  "claims": [{"claim": "string", "category": "Environmental|Social|Governance or null",
              "page_number": integer or null, "source_chunk_id": "string or null"}],
  "metrics": [{"metric_name": "string", "value": number or null, "unit": "string or null",
               "reporting_year": integer or null, "page_number": integer, "source_chunk_id": "string"}],
  "targets": [{"target": "string", "metric": "string or null", "target_value": number or null,
               "unit": "string or null", "baseline_year": integer or null, "target_year": integer or null,
               "page_number": integer, "source_chunk_id": "string"}],
  "commitments": [{"commitment": "string", "category": "Environmental|Social|Governance or null",
                    "page_number": integer, "source_chunk_id": "string"}],
  "risks": [{"risk": "string", "page_number": integer, "source_chunk_id": "string"}],
  "opportunities": [{"opportunity": "string", "page_number": integer, "source_chunk_id": "string"}],
  "costing_summary": [{"amount": number, "currency": "string", "description": "string",
                        "year": integer or null, "page_number": integer, "source_chunk_id": "string"}]
}

The category breakdown lists (carbon_emissions, women_employees, board_independence, etc.) hold
short, source-grounded statements -- not fabricated generic ESG language. Every list defaults to [].
"""
    return (
        f"{_SOURCE_ONLY_RULES}\n"
        f"This is batch {batch_number} of {total_batches} from the report "
        f"(only some of the report's pages are shown in this batch; do not assume "
        f"information from pages you cannot see).\n\n"
        f"{context}\n\n"
        f"{schema}"
    )


def build_synthesis_prompt(
    company_name: str,
    environment_findings: dict,
    social_findings: dict,
    governance_findings: dict,
    top_metrics: list[str],
    top_targets: list[str],
    top_commitments: list[str],
) -> str:
    return f"""{_SOURCE_ONLY_RULES}
You are given the ESG findings already extracted from a report (not the raw report text).
Write concise summaries using ONLY the information below -- do not add facts that are not
present here.

Company: {company_name}

Environmental findings: {environment_findings}
Social findings: {social_findings}
Governance findings: {governance_findings}
Key metrics: {top_metrics}
Key targets: {top_targets}
Key commitments: {top_commitments}

Respond with a JSON object with exactly these keys:
{{
  "executive_summary": "a concise summary, maximum approximately 150 words, using only the findings above, or 'Not Found' if the findings above are empty",
  "environment_summary": "a concise summary of the environmental findings above, or 'Not Found' if empty",
  "social_summary": "a concise summary of the social findings above, or 'Not Found' if empty",
  "governance_summary": "a concise summary of the governance findings above, or 'Not Found' if empty"
}}
"""
