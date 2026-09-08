"""Gold-standard claim/evidence verification test set (Phase 10 section 28).

Every case below is hand-written synthetic data -- never a real company's
disclosure (section 28: "do NOT fabricate real-world company facts").
Covers numeric matches/mismatches, unit mismatches, direction
contradictions, target-year mismatches, vague claims, and wrong-company
evidence, as required.

`evaluate_verification_gold_set` runs each case through Phase 6's actual
deterministic building blocks (`run_consistency_checks` +
`compute_verification_score` + `determine_status`), using
`lexical_similarity` (already used in production for cross-checking, reused
here rather than re-implemented) as a stand-in for the real embedding-based
`semantic_score`, and a neutral 0.5 placeholder for `llm_support` rather
than a live LLM call -- so this harness is fully deterministic and
reproducible without an API key or a model download.

IMPORTANT (section 47): this deliberately evaluates the deterministic
scoring core in isolation, not the full production pipeline. Two real
mechanisms are NOT exercised here and matter for the expected labels below:

1. Only `wrong_company` and an LLM-reported `explicit_contradiction` force
   `Unsupported` outright (`app.verification.scorer.SEVERE_HARD_FAILS`). A
   deterministic numeric/direction/unit/target-year mismatch alone only
   *caps* the result at `Partially Verified`, per Phase 6's documented
   design -- it does not by itself force `Unsupported`. Reaching
   `Unsupported` for those cases in production additionally depends on the
   LLM explicitly reporting a contradiction, which this harness does not
   simulate. The expected labels below reflect what the deterministic core
   alone actually produces, not the full pipeline's likely real-world
   outcome.
2. In production, topically unrelated evidence would usually never be
   retrieved for a claim in the first place (embedding-based retrieval
   ranks it low); this harness instead evaluates the SCORING formula given
   an already-selected evidence pair, so a "vague claim + unrelated
   evidence" pairing here is not fully representative.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.core.config import VerificationThresholds, VerificationWeights
from app.evaluation.metrics import ClassificationReport, compute_classification_report
from app.models.claim import Claim, ClaimCategory, ClaimType
from app.models.evidence import Evidence, SourceType
from app.models.verification import VerificationChecks, VerificationStatus
from app.verification.consistency import lexical_similarity, run_consistency_checks
from app.verification.scorer import compute_verification_score, determine_status

_NEUTRAL_LLM_SUPPORT = 0.5


class GoldVerificationCase(BaseModel):
    case_id: str
    note: str = Field(description="What this case demonstrates")
    claim_text: str
    claim_value: float | None = None
    claim_unit: str | None = None
    claim_target_year: int | None = None
    claim_report_year: int = 2025
    claim_company: str = "Gold Test Co."
    evidence_text: str
    evidence_company: str = "Gold Test Co."
    evidence_report_year: int | None = 2025
    expected_status: VerificationStatus


def _claim(case: GoldVerificationCase) -> Claim:
    return Claim(
        claim_id=case.case_id, document_id="DOC-GOLD", company=case.claim_company, report_year=case.claim_report_year,
        page_number=1, source_chunk_id="CHK-GOLD", claim=case.claim_text, category=ClaimCategory.ENVIRONMENTAL,
        claim_type=ClaimType.PERFORMANCE, value=case.claim_value, unit=case.claim_unit,
        target_year=case.claim_target_year, confidence=0.9,
    )


def _evidence(case: GoldVerificationCase) -> Evidence:
    return Evidence(
        evidence_id=f"EVD-{case.case_id}", source_type=SourceType.UPLOADED_REPORT, company=case.evidence_company,
        document_id="DOC-GOLD", report_year=case.evidence_report_year, page_number=1, source_chunk_id="CHK-GOLD",
        category=ClaimCategory.ENVIRONMENTAL, evidence_text=case.evidence_text,
    )


GOLD_VERIFICATION_CASES: list[GoldVerificationCase] = [
    # --- Numeric matches -> Verified ---------------------------------------
    GoldVerificationCase(case_id="V001", note="exact numeric match", claim_text="Scope 1 emissions decreased by 20% in 2025.", claim_value=20.0, claim_unit="%", evidence_text="Scope 1 emissions decreased by 20% in 2025.", expected_status=VerificationStatus.VERIFIED),
    GoldVerificationCase(case_id="V002", note="numeric match within tolerance", claim_text="Water withdrawal decreased by 10% in 2025.", claim_value=10.0, claim_unit="%", evidence_text="Water withdrawal decreased by 10.5% in 2025.", expected_status=VerificationStatus.PARTIALLY_VERIFIED),
    GoldVerificationCase(case_id="V003", note="exact match, different phrasing", claim_text="Renewable electricity reached 40% of consumption in 2025.", claim_value=40.0, claim_unit="%", evidence_text="Renewable electricity accounted for 40% of total energy consumption in 2025.", expected_status=VerificationStatus.VERIFIED),
    GoldVerificationCase(case_id="V004", note="exact match, tCO2e", claim_text="Scope 2 emissions were 45000 tCO2e in 2025.", claim_value=45000.0, claim_unit="tCO2e", evidence_text="Scope 2 emissions were 45,000 tCO2e in 2025.", expected_status=VerificationStatus.VERIFIED),
    GoldVerificationCase(case_id="V005", note="exact match, waste", claim_text="Landfill waste decreased by 30% in 2025.", claim_value=30.0, claim_unit="%", evidence_text="Textile waste sent to landfill decreased by 30% in 2025.", expected_status=VerificationStatus.VERIFIED),
    GoldVerificationCase(case_id="V019", note="exact match, safety", claim_text="The total recordable injury rate decreased by 25% in 2025.", claim_value=25.0, claim_unit="%", evidence_text="The total recordable injury rate decreased by 25% in 2025.", expected_status=VerificationStatus.VERIFIED),
    GoldVerificationCase(case_id="V020", note="exact match, diversity", claim_text="Women held 38% of management positions in 2025.", claim_value=38.0, claim_unit="%", evidence_text="Women held 38% of management positions in 2025.", expected_status=VerificationStatus.VERIFIED),

    # --- Numeric mismatches -> capped at Partially Verified (see module docstring) ---
    GoldVerificationCase(case_id="V006", note="major numeric mismatch (exaggeration)", claim_text="Scope 1 emissions decreased by 80% in 2025.", claim_value=80.0, claim_unit="%", evidence_text="Scope 1 emissions decreased by 20% in 2025.", expected_status=VerificationStatus.PARTIALLY_VERIFIED),
    GoldVerificationCase(case_id="V007", note="moderate numeric mismatch", claim_text="Water withdrawal decreased by 25% in 2025.", claim_value=25.0, claim_unit="%", evidence_text="Water withdrawal decreased by 8% in 2025.", expected_status=VerificationStatus.PARTIALLY_VERIFIED),
    GoldVerificationCase(case_id="V008", note="numeric mismatch, absolute figure", claim_text="Scope 2 emissions were 20000 tCO2e in 2025.", claim_value=20000.0, claim_unit="tCO2e", evidence_text="Scope 2 emissions were 45,000 tCO2e in 2025.", expected_status=VerificationStatus.PARTIALLY_VERIFIED),
    GoldVerificationCase(case_id="V009", note="numeric mismatch, small over-claim", claim_text="Renewable electricity reached 55% of consumption in 2025.", claim_value=55.0, claim_unit="%", evidence_text="Renewable electricity reached 40% of consumption in 2025.", expected_status=VerificationStatus.PARTIALLY_VERIFIED),

    # --- Direction contradictions -> capped at Partially Verified ----------
    GoldVerificationCase(case_id="V010", note="direction contradiction (claim says decrease, evidence says increase)", claim_text="Scope 1 emissions decreased in 2025.", evidence_text="Scope 1 emissions increased by 12% in 2025.", expected_status=VerificationStatus.PARTIALLY_VERIFIED),
    GoldVerificationCase(case_id="V011", note="direction contradiction, waste", claim_text="Landfill waste decreased in 2025.", evidence_text="Landfill waste increased in 2025.", expected_status=VerificationStatus.PARTIALLY_VERIFIED),

    # --- Unit mismatch: incompatible units drive the score below the
    # Partially Verified floor even with a numerically-styled overlap ------
    GoldVerificationCase(case_id="V012", note="unit mismatch (tCO2e vs MWh)", claim_text="Total energy consumption was 45000 tCO2e in 2025.", claim_value=45000.0, claim_unit="tCO2e", evidence_text="Total energy consumption was 45,000 MWh in 2025.", expected_status=VerificationStatus.UNSUPPORTED),

    # --- Target-year mismatches ----------------------------------------------
    GoldVerificationCase(case_id="V014", note="target year mismatch", claim_text="The company targets net-zero emissions by 2050.", claim_target_year=2050, evidence_text="The company set a net-zero target for 2045.", expected_status=VerificationStatus.PARTIALLY_VERIFIED),
    GoldVerificationCase(case_id="V015", note="target year match", claim_text="The company targets 60% renewable electricity by 2030.", claim_value=60.0, claim_unit="%", claim_target_year=2030, evidence_text="The company targets 60% renewable electricity by 2030.", expected_status=VerificationStatus.VERIFIED),

    # --- Vague claims (no clear number to compare) ---------------------------
    GoldVerificationCase(case_id="V016", note="vague claim, topically relevant evidence", claim_text="We are committed to sustainability and water stewardship.", evidence_text="The company expanded water recycling programs to two additional facilities.", expected_status=VerificationStatus.PARTIALLY_VERIFIED),
    GoldVerificationCase(case_id="V017", note="vague claim, topically unrelated evidence (retrieval, not scoring, would normally exclude this pairing)", claim_text="We are committed to a greener future.", evidence_text="The board's audit committee met six times during the reporting year.", expected_status=VerificationStatus.PARTIALLY_VERIFIED),

    # --- Wrong company -> forced Unsupported (SEVERE_HARD_FAILS) ------------
    GoldVerificationCase(case_id="V021", note="wrong company, otherwise identical claim/evidence text", claim_text="Scope 1 emissions decreased by 20% in 2025.", claim_value=20.0, claim_unit="%", claim_company="Aurora Materials Inc.", evidence_text="Scope 1 emissions decreased by 20% in 2025.", evidence_company="Meridian Foods Co.", expected_status=VerificationStatus.UNSUPPORTED),
    GoldVerificationCase(case_id="V022", note="wrong company, diversity claim", claim_text="Women held 38% of management positions in 2025.", claim_value=38.0, claim_unit="%", claim_company="Northwind Energy Corp.", evidence_text="Women held 38% of management positions in 2025.", evidence_company="Cobalt Textiles Ltd.", expected_status=VerificationStatus.UNSUPPORTED),
    GoldVerificationCase(case_id="V023", note="wrong company, target year claim", claim_text="The company targets net-zero emissions by 2045.", claim_target_year=2045, claim_company="Aurora Materials Inc.", evidence_text="The company set a net-zero target for 2045.", evidence_company="Northwind Energy Corp.", expected_status=VerificationStatus.UNSUPPORTED),
]


def evaluate_verification_gold_set(
    weights: VerificationWeights | None = None,
    thresholds: VerificationThresholds | None = None,
) -> ClassificationReport:
    weights = weights or VerificationWeights(_env_file=None)
    thresholds = thresholds or VerificationThresholds(_env_file=None)

    y_true: list[str] = []
    y_pred: list[str] = []
    for case in GOLD_VERIFICATION_CASES:
        claim = _claim(case)
        evidence = _evidence(case)
        consistency, _claim_components, _evidence_components = run_consistency_checks(claim, evidence, thresholds)
        overlap = lexical_similarity(claim.claim, evidence.evidence_text)

        checks = VerificationChecks(
            semantic=overlap, lexical=overlap, numeric=consistency.numeric, unit=consistency.unit,
            temporal=consistency.temporal, entity=consistency.entity, category=consistency.category,
            llm_support=_NEUTRAL_LLM_SUPPORT, provenance=0.9,
        )
        score = compute_verification_score(checks, weights)
        status = determine_status(score, consistency.hard_fail_reasons, thresholds)

        y_true.append(case.expected_status.value)
        y_pred.append(status.value)

    labels = [s.value for s in VerificationStatus]
    return compute_classification_report(y_true, y_pred, labels=labels)
