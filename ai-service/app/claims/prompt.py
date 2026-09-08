"""Claim extraction and classification prompts.

No Python logic lives here -- only prompt text and thin string-formatting
functions. Never a hardcoded company name: the model is told to read the
company identity (if relevant) from the supplied chunk text itself, the
same as any other fact.
"""
from __future__ import annotations

from app.analyzer.context_builder import format_batch_context
from app.models.document import DocumentChunk

_EXTRACTION_RULES = """You are an ESG claim extraction system. Follow these rules exactly:

1. Extract ONLY explicit ESG assertions that are actually stated in the text below --
   never invent a claim, never infer a claim from context that isn't written down.
2. Use ONLY the supplied text. Do not use outside knowledge about any company, industry,
   or ESG topic. Do not hardcode or assume any company name -- read it from the text if needed.
3. A claim is a factual or organizational assertion that could later be checked against
   evidence (e.g. "Scope 1 emissions decreased by 18%", "We achieved 100% renewable
   electricity", "The company has committed to net zero by 2050").
4. Do NOT extract: page numbers, headings, table-of-contents entries, navigation text,
   URLs, email addresses, copyright text, generic introductions, generic ESG definitions
   used with no specific fact, section titles, incomplete fragments, decorative text, or
   purely promotional slogans with no factual assertion.
5. Preserve the original meaning and, critically, any numerical information -- never
   summarize away a number, percentage, unit, or year. Minor whitespace cleanup is fine;
   do not paraphrase away measurable content.
6. Every claim you return MUST cite the exact `source_chunk_id` and `page_number` copied
   verbatim from the "Chunk:" and "Page:" labels above the text it came from. Never invent
   a chunk id or page number, and never attribute a claim to a chunk it didn't come from.
7. If one sentence bundles several independent factual assertions, you may return them as
   separate claim entries -- but do not split a single, logically connected statement.
8. Respond with a single JSON object only -- no markdown, no commentary, no text before or
   after the JSON.
"""

_EXTRACTION_SCHEMA = """Respond with a JSON object with exactly this shape:

{
  "candidates": [
    {"claim": "string, the claim text as stated in the source",
     "page_number": integer,
     "source_chunk_id": "string"}
  ]
}

If this batch of text contains no genuine ESG claims, return {"candidates": []}.
"""


def build_extraction_prompt(batch: list[DocumentChunk], batch_number: int, total_batches: int) -> str:
    context = format_batch_context(batch)
    return (
        f"{_EXTRACTION_RULES}\n"
        f"This is batch {batch_number} of {total_batches} from the report "
        f"(only some of the report's pages are shown in this batch).\n\n"
        f"{context}\n\n"
        f"{_EXTRACTION_SCHEMA}"
    )


_CLASSIFICATION_RULES = """You are an ESG claim classification system. For each claim below,
assign exactly one category and exactly one claim type, using ONLY the claim text given --
no outside knowledge. Follow these rules exactly:

1. category must be exactly one of: Environmental, Social, Governance, Unknown.
   Use "Unknown" ONLY if you cannot confidently determine the category from the text --
   never guess a category just to avoid "Unknown".
2. claim_type must be exactly one of: Metric, Performance, Certification, Policy,
   Commitment, Compliance, General.
   - Metric: a specific reported numerical measurement (a static reading).
   - Performance: a described change/trend in a metric (increased/decreased/improved).
   - Certification: an explicit certification or standard held (e.g. ISO 14001).
   - Policy: reference to an existing policy or guideline.
   - Commitment: an explicit future pledge or intention (not every sentence with "will").
   - Compliance: an explicit statement of complying with regulations/standards.
   - General: none of the above apply confidently.
3. confidence is your own certainty in this classification, 0.0 to 1.0 -- it is one input
   among several the system uses, not the final claim confidence.
4. reason is a short (<=20 words) explanation of why you chose this category/type.
"""


def build_classification_prompt(claim_texts: list[str]) -> str:
    numbered = "\n".join(f"{i + 1}. {text}" for i, text in enumerate(claim_texts))
    schema = """Respond with a JSON object with exactly this shape:

{
  "classifications": [
    {"index": integer (1-based, matching the numbered list above),
     "category": "Environmental|Social|Governance|Unknown",
     "claim_type": "Metric|Performance|Certification|Policy|Commitment|Compliance|General",
     "confidence": number between 0.0 and 1.0,
     "reason": "string"}
  ]
}
"""
    return f"{_CLASSIFICATION_RULES}\nClaims:\n{numbered}\n\n{schema}"
