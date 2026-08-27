"""Gold-standard greenwashing classification test set (Phase 10 section 29).

Every case is hand-written synthetic data. Unlike verification (see
`gold_verification.py`), greenwashing type classification is ALREADY 100%
deterministic in production (Phase 7: the LLM only ever contributes
explanatory text, never the type list or score) -- so this harness calls
the real `app.greenwashing.detector.run_detectors` +
`app.greenwashing.scorer.determine_greenwashing_types` directly, with no
simplification and no LLM involved at all.

`GreenwashingType` is multi-label (a claim can be several types at once);
for a single-label confusion matrix/precision/recall/F1 report, each case's
`expected_primary_type` is compared against the FIRST type in the actual
(deterministically-ordered) result list. This is a simplification, not a
full multi-label evaluation -- documented here rather than silently
assumed (section 47)."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.evaluation.metrics import ClassificationReport, compute_classification_report
from app.greenwashing.detector import run_detectors
from app.greenwashing.scorer import determine_greenwashing_types
from app.models.claim import Claim, ClaimCategory, ClaimType
from app.models.evidence import Evidence, SourceType
from app.models.greenwashing import GreenwashingType
from app.models.verification import VerificationStatus

_NUMERICAL_TOLERANCE_PCT = 2.0


class GoldGreenwashingCase(BaseModel):
    case_id: str
    note: str
    claim_text: str
    claim_value: float | None = None
    claim_unit: str | None = None
    verification_status: VerificationStatus
    evidence_text: str | None = None
    evidence_value: float | None = None
    evidence_unit: str | None = None
    expected_primary_type: GreenwashingType


def _claim(case: GoldGreenwashingCase) -> Claim:
    return Claim(
        claim_id=case.case_id, document_id="DOC-GOLD", company="Gold Test Co.", report_year=2025, page_number=1,
        source_chunk_id="CHK-GOLD", claim=case.claim_text, category=ClaimCategory.ENVIRONMENTAL,
        claim_type=ClaimType.PERFORMANCE, value=case.claim_value, unit=case.claim_unit, confidence=0.9,
    )


def _evidence(case: GoldGreenwashingCase) -> Evidence | None:
    if case.evidence_text is None:
        return None
    return Evidence(
        evidence_id=f"EVD-{case.case_id}", source_type=SourceType.UPLOADED_REPORT, company="Gold Test Co.",
        document_id="DOC-GOLD", report_year=2025, page_number=1, source_chunk_id="CHK-GOLD",
        category=ClaimCategory.ENVIRONMENTAL, evidence_text=case.evidence_text,
        value=case.evidence_value, unit=case.evidence_unit,
    )


GOLD_GREENWASHING_CASES: list[GoldGreenwashingCase] = [
    # --- No significant signal: fully supported, specific claims ------------
    GoldGreenwashingCase(case_id="G001", note="fully supported, specific, no signal", claim_text="Scope 1 emissions decreased by 20% in 2025.", claim_value=20.0, claim_unit="%", verification_status=VerificationStatus.VERIFIED, evidence_text="Scope 1 emissions decreased by 20% in 2025.", evidence_value=20.0, evidence_unit="%", expected_primary_type=GreenwashingType.NO_SIGNIFICANT_SIGNAL),
    GoldGreenwashingCase(case_id="G002", note="fully supported, specific, no signal (safety)", claim_text="The total recordable injury rate decreased by 25% in 2025.", claim_value=25.0, claim_unit="%", verification_status=VerificationStatus.VERIFIED, evidence_text="The total recordable injury rate decreased by 25% in 2025.", evidence_value=25.0, evidence_unit="%", expected_primary_type=GreenwashingType.NO_SIGNIFICANT_SIGNAL),
    GoldGreenwashingCase(case_id="G003", note="unsupported but no promotional/vague language -- not automatically greenwashing", claim_text="The facility completed its annual third-party audit in March.", verification_status=VerificationStatus.UNSUPPORTED, expected_primary_type=GreenwashingType.UNSUPPORTED_ENVIRONMENTAL_CLAIM),

    # --- Vague claims -------------------------------------------------------
    GoldGreenwashingCase(case_id="G004", note="vague, no metric, no evidence", claim_text="We are committed to a greener future.", verification_status=VerificationStatus.UNSUPPORTED, expected_primary_type=GreenwashingType.VAGUE_CLAIM),
    GoldGreenwashingCase(case_id="G005", note="vague sustainability language", claim_text="Our operations reflect a strong commitment to a sustainable future.", verification_status=VerificationStatus.UNSUPPORTED, expected_primary_type=GreenwashingType.VAGUE_CLAIM),

    # --- Absolute claims ------------------------------------------------
    GoldGreenwashingCase(case_id="G006", note="absolute claim, no evidence", claim_text="We have achieved carbon neutral status across all operations.", verification_status=VerificationStatus.UNSUPPORTED, expected_primary_type=GreenwashingType.ABSOLUTE_CLAIM),
    GoldGreenwashingCase(case_id="G007", note="absolute claim, zero emissions", claim_text="We have achieved zero emissions across all operations.", verification_status=VerificationStatus.UNSUPPORTED, expected_primary_type=GreenwashingType.ABSOLUTE_CLAIM),
    GoldGreenwashingCase(case_id="G008", note="absolute claim contradicted by a partial figure in the evidence", claim_text="Our packaging is completely sustainable.", verification_status=VerificationStatus.PARTIALLY_VERIFIED, evidence_text="60% of packaging materials were diverted from landfill in 2025.", expected_primary_type=GreenwashingType.CONTRADICTORY_CLAIM),

    # --- Exaggerated claims ---------------------------------------------
    GoldGreenwashingCase(case_id="G009", note="exaggerated numeric claim (80% vs 20%)", claim_text="We reduced Scope 1 emissions by 80%.", claim_value=80.0, claim_unit="%", verification_status=VerificationStatus.PARTIALLY_VERIFIED, evidence_text="Scope 1 emissions decreased by 20% in 2025.", evidence_value=20.0, evidence_unit="%", expected_primary_type=GreenwashingType.EXAGGERATED_CLAIM),
    GoldGreenwashingCase(case_id="G010", note="exaggerated numeric claim (55% vs 40%)", claim_text="Renewable electricity reached 55% of consumption.", claim_value=55.0, claim_unit="%", verification_status=VerificationStatus.PARTIALLY_VERIFIED, evidence_text="Renewable electricity accounted for 40% of total energy consumption in 2025.", evidence_value=40.0, evidence_unit="%", expected_primary_type=GreenwashingType.EXAGGERATED_CLAIM),

    # --- Contradictory claims ---------------------------------------------
    GoldGreenwashingCase(case_id="G011", note="direction contradiction", claim_text="Scope 1 emissions decreased in 2025.", verification_status=VerificationStatus.UNSUPPORTED, evidence_text="Scope 1 emissions increased by 12% in 2025.", expected_primary_type=GreenwashingType.CONTRADICTORY_CLAIM),
    GoldGreenwashingCase(case_id="G012", note="unit-incompatible contradiction", claim_text="Total energy consumption was 45000 tCO2e in 2025.", claim_value=45000.0, claim_unit="tCO2e", verification_status=VerificationStatus.UNSUPPORTED, evidence_text="Total energy consumption was 45,000 MWh in 2025.", evidence_value=45000.0, evidence_unit="MWh", expected_primary_type=GreenwashingType.CONTRADICTORY_CLAIM),

    # --- Unsubstantiated benefit ---------------------------------------
    GoldGreenwashingCase(case_id="G013", note="stated benefit, no evidence at all", claim_text="Our new packaging reduces environmental impact.", verification_status=VerificationStatus.UNSUPPORTED, expected_primary_type=GreenwashingType.UNSUBSTANTIATED_BENEFIT),
    GoldGreenwashingCase(case_id="G014", note="stated benefit, no evidence (helps the planet)", claim_text="This initiative helps the planet and benefits the environment.", verification_status=VerificationStatus.UNSUPPORTED, expected_primary_type=GreenwashingType.UNSUBSTANTIATED_BENEFIT),
]


def evaluate_greenwashing_gold_set() -> ClassificationReport:
    y_true: list[str] = []
    y_pred: list[str] = []
    for case in GOLD_GREENWASHING_CASES:
        claim = _claim(case)
        evidence = _evidence(case)
        report = run_detectors(claim, evidence, _NUMERICAL_TOLERANCE_PCT)
        types = determine_greenwashing_types(report, case.verification_status)

        y_true.append(case.expected_primary_type.value)
        y_pred.append(types[0].value)

    # Labels are inferred from the cases actually present, not the full
    # GreenwashingType enum -- macro-averaging over types this gold set
    # never exercises would be a meaningless "0 precision/recall" drag on
    # the reported metrics, not an honest reflection of what was tested.
    return compute_classification_report(y_true, y_pred)
