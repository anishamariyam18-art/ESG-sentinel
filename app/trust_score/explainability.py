"""Trust Score explainable-AI output (sections 18-23).

Every line returned here traces back to an actual computed statistic or
component -- nothing is a generic compliment, an invented weakness, or a
claim of fraud/deception. Missing data is always described as a coverage
gap, never as evidence of wrongdoing (section 23).
"""
from __future__ import annotations

from app.core.config import TrustScoreConfig
from app.models.trust import TrustRating, TrustScoreComponents, TrustScoreStatistics


def _pct(count: int, total: int) -> float:
    return round((count / total) * 100, 2) if total > 0 else 0.0


def build_explanation(
    stats: TrustScoreStatistics, components: TrustScoreComponents, rating: TrustRating
) -> list[str]:
    lines: list[str] = []
    total = stats.total_claims
    if total == 0:
        lines.append("No ESG claims were available to assess.")
        return lines

    lines.append(f"{_pct(stats.verified_claims, total)}% of claims were fully verified ({stats.verified_claims} of {total}).")
    lines.append(f"{_pct(stats.partially_verified_claims, total)}% were partially verified ({stats.partially_verified_claims} of {total}).")
    lines.append(f"{_pct(stats.unsupported_claims, total)}% were unsupported by available evidence ({stats.unsupported_claims} of {total}).")
    lines.append(f"Evidence coverage: {stats.evidence_coverage}% of claims had matched evidence.")
    lines.append(f"Provenance coverage: {stats.provenance_coverage}% of claims had complete document/page/chunk/evidence-id provenance.")

    if stats.high_greenwashing_claims > 0:
        lines.append(f"{stats.high_greenwashing_claims} claim(s) carried a High greenwashing risk signal.")
    elif stats.medium_greenwashing_claims > 0:
        lines.append(f"{stats.medium_greenwashing_claims} claim(s) carried a Medium greenwashing risk signal; greenwashing risk overall was moderate.")
    else:
        lines.append("Greenwashing risk across assessed claims was low.")

    if components.consistency < 70.0:
        lines.append("Several claims showed numerical, unit, temporal, or entity inconsistencies against their matched evidence.")
    else:
        lines.append("Claims were generally consistent with their matched evidence on number, unit, timeframe, and entity.")

    lines.append(f"Overall rating: {rating.value} (combining claim support, evidence quality, consistency, transparency, greenwashing risk, and provenance).")
    return lines


def build_strengths(stats: TrustScoreStatistics, components: TrustScoreComponents) -> list[str]:
    strengths: list[str] = []
    total = stats.total_claims
    if total > 0 and stats.verified_claims / total >= 0.7:
        strengths.append(f"{_pct(stats.verified_claims, total)}% of claims were verified against source-level evidence.")
    if stats.provenance_coverage >= 70.0:
        strengths.append(f"Most evidence retained complete page-level and chunk-level provenance ({stats.provenance_coverage}% coverage).")
    if stats.high_greenwashing_claims == 0 and stats.medium_greenwashing_claims == 0 and total > 0:
        strengths.append("No meaningful greenwashing risk signals were detected among assessed claims.")
    elif stats.high_greenwashing_claims == 0 and total > 0:
        strengths.append("No High-risk greenwashing signals were detected among assessed claims.")
    if components.consistency >= 80.0:
        strengths.append("Quantitative claims generally matched the figures, units, and timeframes stated in the available evidence.")
    if components.transparency >= 80.0:
        strengths.append("Most claims included measurable metrics, target years, or named methodologies where relevant.")
    return strengths


def build_weaknesses(stats: TrustScoreStatistics, components: TrustScoreComponents) -> list[str]:
    weaknesses: list[str] = []
    total = stats.total_claims
    if total == 0:
        # Nothing was assessed -- a weakness requires an actual claim to
        # point at, never a component's arithmetic default of 0.
        return weaknesses
    if stats.unsupported_claims / total >= 0.15:
        weaknesses.append(f"{_pct(stats.unsupported_claims, total)}% of claims were unsupported by available evidence.")
    if components.consistency < 70.0:
        weaknesses.append("Several claims had numerical, unit, temporal, or entity inconsistencies against their matched evidence.")
    if components.transparency < 60.0:
        weaknesses.append("Multiple claims lacked measurable metrics, target years, or used vague, unquantified language.")
    if stats.evidence_coverage < 70.0:
        weaknesses.append(f"Evidence coverage was incomplete ({stats.evidence_coverage}% of claims had matched evidence).")
    if stats.high_greenwashing_claims > 0:
        weaknesses.append(f"{stats.high_greenwashing_claims} claim(s) carried a High greenwashing risk signal.")
    if stats.provenance_coverage < 70.0:
        weaknesses.append(f"Provenance coverage was incomplete ({stats.provenance_coverage}% of claims had complete document/page/chunk/evidence-id traceability).")
    return weaknesses


def build_limitations(stats: TrustScoreStatistics, config: TrustScoreConfig) -> list[str]:
    limitations: list[str] = []
    if stats.total_claims == 0:
        limitations.append("No ESG claims were available, so no meaningful trust assessment could be produced.")
    elif stats.total_claims < config.min_claims_for_full_confidence:
        limitations.append(
            f"Only {stats.total_claims} ESG claim(s) were available, so this trust score has limited evidential coverage; see `confidence`."
        )
    if 0.0 < stats.evidence_coverage < 100.0:
        limitations.append("Not every claim had matched evidence available; unmatched claims are treated as unsupported, never as false.")
    if 0.0 < stats.provenance_coverage < 100.0:
        limitations.append("Some evidence lacked complete page-level or chunk-level provenance.")
    limitations.append(
        "This score reflects internal consistency and evidential support within the analyzed pipeline outputs -- it does not "
        "incorporate external authoritative datasets, audits, or regulatory filings unless those were separately ingested as evidence."
    )
    if stats.unsupported_claims > 0 or stats.high_greenwashing_claims > 0 or stats.medium_greenwashing_claims > 0:
        limitations.append("A low score or unsupported claims reflect missing or inconsistent evidence, not a finding of fraud or intentional deception.")
    return limitations
