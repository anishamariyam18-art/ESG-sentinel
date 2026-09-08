"""Claim verification contract.

`Unsupported` means adequate supporting evidence was not found -- it is
explicitly NOT a claim of falsity. `False`/`Misleading`/`Exaggerated` are
Phase 7 (Greenwashing) territory, not this phase's.

`VerificationChecks` holds one float (0.0-1.0) score per consistency signal
(section 17) rather than a bare pass/fail bool, so the weighted
`verification_score` calculation and the explanation can both point at
exactly which signal was weak. `verification_score` ("how strongly does the
evidence support the claim?") and `confidence_score` ("how reliable is this
verification decision?") are deliberately separate numbers -- see
app.verification.scorer for the documented formulas behind each.
"""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from app.models.evidence import EvidenceMatch


class VerificationStatus(str, Enum):
    VERIFIED = "Verified"
    PARTIALLY_VERIFIED = "Partially Verified"
    UNSUPPORTED = "Unsupported"


class VerificationChecks(BaseModel):
    semantic: float = Field(ge=0.0, le=1.0, default=0.0)
    lexical: float = Field(ge=0.0, le=1.0, default=0.0)
    numeric: float = Field(ge=0.0, le=1.0, default=1.0)
    unit: float = Field(ge=0.0, le=1.0, default=1.0)
    temporal: float = Field(ge=0.0, le=1.0, default=1.0)
    entity: float = Field(ge=0.0, le=1.0, default=0.0)
    category: float = Field(ge=0.0, le=1.0, default=1.0)
    llm_support: float = Field(ge=0.0, le=1.0, default=0.0)
    provenance: float = Field(ge=0.0, le=1.0, default=0.0)


class VerificationResult(BaseModel):
    claim_id: str = Field(min_length=1)
    status: VerificationStatus
    verification_score: float = Field(ge=0.0, le=100.0)
    confidence_score: float = Field(ge=0.0, le=100.0)
    matched_evidence: list[EvidenceMatch] = Field(default_factory=list)
    checks: VerificationChecks
    reason: str = ""
    explanation: list[str] = Field(default_factory=list)
