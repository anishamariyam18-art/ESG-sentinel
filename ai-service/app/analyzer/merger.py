"""Deterministic merge and deduplication of per-batch extraction results.

Deduplication uses normalized-text equality (case/whitespace-insensitive),
never bare string equality and never embedding similarity (that machinery
belongs to Phase 5/6) -- a conservative middle ground that won't merge two
genuinely different statements just because they're phrased alike, and
won't miss an exact repeat just because of whitespace differences.

A "duplicate" always means the same fact reported again (same metric name +
unit + reporting_year + value, etc.) -- when a repeated statement carries a
*different* value for the same metric/year, that is a contradiction, not a
duplicate, and both are kept as separate entries rather than one silently
overwriting the other.
"""
from __future__ import annotations

import re
from typing import Callable, TypeVar

from app.analyzer.schemas import BatchExtractionResult
from app.models.analyzer import (
    NOT_FOUND,
    AnalyzerClaim,
    AnalyzerCommitment,
    AnalyzerMetric,
    AnalyzerOpportunity,
    AnalyzerRisk,
    AnalyzerTarget,
    CostingEntry,
    EnvironmentAnalysis,
    GovernanceAnalysis,
    SocialAnalysis,
    SourceReference,
)

T = TypeVar("T")


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def dedupe_text_list(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if not item or not item.strip():
            continue
        key = _normalize(item)
        if key in seen:
            continue
        seen.add(key)
        result.append(item.strip())
    return result


def _dedupe_provenance(items: list[T], key_fn: Callable[[T], tuple]) -> list[T]:
    merged: dict[tuple, T] = {}
    for item in items:
        key = key_fn(item)
        if key not in merged:
            merged[key] = item
            continue

        existing = merged[key]
        page_number = getattr(item, "page_number", None)
        chunk_id = getattr(item, "source_chunk_id", None)
        if not chunk_id or page_number is None:
            continue

        already_present = existing.source_chunk_id == chunk_id or any(
            ref.chunk_id == chunk_id for ref in existing.additional_references
        )
        if already_present:
            continue

        new_refs = [*existing.additional_references, SourceReference(chunk_id=chunk_id, page_number=page_number)]
        merged[key] = existing.model_copy(update={"additional_references": new_refs})

    return list(merged.values())


def merge_report_info(batches: list[BatchExtractionResult]) -> tuple[str, int | None, str, str]:
    """First non-'Not Found' value wins per field, in batch order."""
    company_name, reporting_year, industry, report_type = NOT_FOUND, None, NOT_FOUND, NOT_FOUND
    for batch in batches:
        if company_name == NOT_FOUND and batch.company_name != NOT_FOUND:
            company_name = batch.company_name
        if reporting_year is None and batch.reporting_year is not None:
            reporting_year = batch.reporting_year
        if industry == NOT_FOUND and batch.industry != NOT_FOUND:
            industry = batch.industry
        if report_type == NOT_FOUND and batch.report_type != NOT_FOUND:
            report_type = batch.report_type
    return company_name, reporting_year, industry, report_type


def merge_environment(batches: list[BatchExtractionResult]) -> EnvironmentAnalysis:
    return EnvironmentAnalysis(
        carbon_emissions=dedupe_text_list([x for b in batches for x in b.carbon_emissions]),
        water_usage=dedupe_text_list([x for b in batches for x in b.water_usage]),
        renewable_energy=dedupe_text_list([x for b in batches for x in b.renewable_energy]),
        waste_management=dedupe_text_list([x for b in batches for x in b.waste_management]),
        net_zero_commitments=dedupe_text_list([x for b in batches for x in b.net_zero_commitments]),
        biodiversity=dedupe_text_list([x for b in batches for x in b.biodiversity]),
        climate_actions=dedupe_text_list([x for b in batches for x in b.climate_actions]),
    )


def merge_social(batches: list[BatchExtractionResult]) -> SocialAnalysis:
    return SocialAnalysis(
        women_employees=dedupe_text_list([x for b in batches for x in b.women_employees]),
        employee_diversity=dedupe_text_list([x for b in batches for x in b.employee_diversity]),
        health_and_safety=dedupe_text_list([x for b in batches for x in b.health_and_safety]),
        training=dedupe_text_list([x for b in batches for x in b.training]),
        csr=dedupe_text_list([x for b in batches for x in b.csr]),
        human_rights=dedupe_text_list([x for b in batches for x in b.human_rights]),
    )


def merge_governance(batches: list[BatchExtractionResult]) -> GovernanceAnalysis:
    return GovernanceAnalysis(
        board_independence=dedupe_text_list([x for b in batches for x in b.board_independence]),
        ethics=dedupe_text_list([x for b in batches for x in b.ethics]),
        compliance=dedupe_text_list([x for b in batches for x in b.compliance]),
        anti_corruption=dedupe_text_list([x for b in batches for x in b.anti_corruption]),
        risk_management=dedupe_text_list([x for b in batches for x in b.risk_management]),
    )


def merge_claims(batches: list[BatchExtractionResult]) -> list[AnalyzerClaim]:
    all_claims = [c for b in batches for c in b.claims]
    return _dedupe_provenance(all_claims, key_fn=lambda c: (_normalize(c.claim),))


def merge_metrics(batches: list[BatchExtractionResult]) -> list[AnalyzerMetric]:
    all_metrics = [m for b in batches for m in b.metrics]
    return _dedupe_provenance(
        all_metrics,
        key_fn=lambda m: (_normalize(m.metric_name), m.unit, m.reporting_year, m.value),
    )


def merge_targets(batches: list[BatchExtractionResult]) -> list[AnalyzerTarget]:
    all_targets = [t for b in batches for t in b.targets]
    return _dedupe_provenance(
        all_targets,
        key_fn=lambda t: (
            _normalize(t.target), t.metric and _normalize(t.metric),
            t.target_value, t.unit, t.baseline_year, t.target_year,
        ),
    )


def merge_commitments(batches: list[BatchExtractionResult]) -> list[AnalyzerCommitment]:
    all_commitments = [c for b in batches for c in b.commitments]
    return _dedupe_provenance(all_commitments, key_fn=lambda c: (_normalize(c.commitment),))


def merge_risks(batches: list[BatchExtractionResult]) -> list[AnalyzerRisk]:
    all_risks = [r for b in batches for r in b.risks]
    return _dedupe_provenance(all_risks, key_fn=lambda r: (_normalize(r.risk),))


def merge_opportunities(batches: list[BatchExtractionResult]) -> list[AnalyzerOpportunity]:
    all_opportunities = [o for b in batches for o in b.opportunities]
    return _dedupe_provenance(all_opportunities, key_fn=lambda o: (_normalize(o.opportunity),))


def merge_costing(batches: list[BatchExtractionResult]) -> list[CostingEntry]:
    all_costing = [c for b in batches for c in b.costing_summary]
    return _dedupe_provenance(
        all_costing,
        key_fn=lambda c: (c.amount, c.currency, c.year, _normalize(c.description)),
    )


def collect_source_references(*groups: list) -> list[SourceReference]:
    """Union of every chunk a merged item (or one of its additional
    occurrences) actually cites, deduplicated by chunk id."""
    refs: dict[str, SourceReference] = {}
    for group in groups:
        for item in group:
            chunk_id = getattr(item, "source_chunk_id", None)
            page_number = getattr(item, "page_number", None)
            if chunk_id and page_number is not None and chunk_id not in refs:
                refs[chunk_id] = SourceReference(chunk_id=chunk_id, page_number=page_number)
            for ref in getattr(item, "additional_references", []):
                if ref.chunk_id not in refs:
                    refs[ref.chunk_id] = ref
    return list(refs.values())
