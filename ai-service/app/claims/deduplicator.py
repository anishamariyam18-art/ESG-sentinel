"""Exact and near-duplicate claim detection.

Exact duplicates are found by normalized-text + metric-identity equality.
Near duplicates use text-similarity (difflib -- no embedding model is wired
up until Phase 5/6) gated by metadata compatibility: two claims are only
ever considered duplicates of each other if their category, unit,
reporting year, and target year don't contradict, and any numeric values
present are equal. A repeated measurement with a different value or a
different year is always kept as a separate claim, never merged away.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.core.config import ClaimsConfig
from app.core.logging import get_logger
from app.models.claim import Claim, ClaimCategory
from app.models.provenance import SourceReference

logger = get_logger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text.strip().lower())


def _exact_key(claim: Claim) -> tuple:
    return (
        _normalize(claim.claim),
        claim.category,
        claim.metric_name and _normalize(claim.metric_name),
        claim.value,
        claim.unit,
        claim.report_year,
        claim.target_year,
    )


def _metadata_compatible(a: Claim, b: Claim) -> bool:
    """Two claims are only duplicate candidates if their measurable
    metadata doesn't contradict -- different values/years/units for the
    same claim are NOT duplicates, they're separate legitimate facts."""
    if a.category != b.category:
        return False
    if a.value is not None and b.value is not None and a.value != b.value:
        return False
    if a.unit is not None and b.unit is not None and a.unit != b.unit:
        return False
    if a.report_year != b.report_year:
        return False
    if a.target_year is not None and b.target_year is not None and a.target_year != b.target_year:
        return False
    return True


def _text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _merge_into(primary: Claim, duplicate: Claim) -> Claim:
    existing_chunk_ids = {primary.source_chunk_id} | {r.chunk_id for r in primary.source_references}
    if duplicate.source_chunk_id in existing_chunk_ids:
        return primary
    new_refs = [
        *primary.source_references,
        SourceReference(
            chunk_id=duplicate.source_chunk_id, page_number=duplicate.page_number, section=duplicate.section
        ),
    ]
    return primary.model_copy(update={"source_references": new_refs})


def deduplicate_claims(claims: list[Claim], config: ClaimsConfig) -> list[Claim]:
    """Exact pass first (cheap, precise), then a near-duplicate pass
    bucketed by category to keep pairwise comparisons bounded rather than
    O(n^2) over the whole claim list."""
    exact_groups: dict[tuple, Claim] = {}
    order: list[tuple] = []
    for claim in claims:
        key = _exact_key(claim)
        if key not in exact_groups:
            exact_groups[key] = claim
            order.append(key)
        else:
            exact_groups[key] = _merge_into(exact_groups[key], claim)
    exact_deduped = [exact_groups[k] for k in order]

    buckets: dict[ClaimCategory, list[Claim]] = {}
    for claim in exact_deduped:
        buckets.setdefault(claim.category, []).append(claim)

    final: list[Claim] = []
    for bucket in buckets.values():
        kept: list[Claim] = []
        for claim in bucket:
            merged = False
            for i, existing in enumerate(kept):
                if not _metadata_compatible(existing, claim):
                    continue
                if _text_similarity(existing.claim, claim.claim) >= config.near_duplicate_similarity_threshold:
                    kept[i] = _merge_into(existing, claim)
                    merged = True
                    break
            if not merged:
                kept.append(claim)
        final.extend(kept)

    logger.info("claims_deduplicated", extra={"input_count": len(claims), "output_count": len(final)})
    return final
