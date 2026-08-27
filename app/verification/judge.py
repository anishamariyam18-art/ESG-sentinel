"""LLM evidence judgment (section 15/16).

The LLM's output is one input signal among several (see scorer.py) --
never the final verification score, and its own reported "confidence" (if
any) is not even read; only the structured support_level/contradictions
are used. If the LLM is unavailable or its response never becomes valid
JSON matching the expected schema, `judge()` returns an empty dict rather
than inventing a judgment -- callers must treat a missing judgment as
"this signal is unavailable", not as support or non-support.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.core.config import VerificationConfig
from app.core.llm import LLMGenerationError, LLMJsonError, LLMManager
from app.core.logging import get_logger
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.verification.prompt import build_judgment_prompt

logger = get_logger(__name__)


class JudgmentResult(BaseModel):
    evidence_id: str = Field(min_length=1)
    supports_claim: bool
    support_level: str  # "full" | "partial" | "none"
    supported_components: list[str] = Field(default_factory=list)
    unsupported_components: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    reason: str = ""


class _JudgmentBatch(BaseModel):
    judgments: list[JudgmentResult] = Field(default_factory=list)


_SUPPORT_LEVEL_SCORES = {"full": 1.0, "partial": 0.5, "none": 0.0}


def judgment_to_score(judgment: JudgmentResult | None) -> float:
    """Maps a judgment to the llm_support check score (section 17). A
    missing judgment (LLM unavailable/failed) returns 0.5 -- a documented
    neutral default, not a fabricated answer; the score is still driven by
    the other 8 signals."""
    if judgment is None:
        return 0.5
    score = _SUPPORT_LEVEL_SCORES.get(judgment.support_level, 0.0)
    if judgment.contradictions:
        score = 0.0
    return score


class EvidenceJudge:
    def __init__(self, llm_manager: LLMManager, config: VerificationConfig) -> None:
        self._llm = llm_manager
        self._config = config

    def judge(self, claim: Claim, evidence_candidates: list[Evidence]) -> dict[str, JudgmentResult]:
        """Returns evidence_id -> JudgmentResult for every candidate the
        LLM successfully judged. An empty dict means the LLM signal is
        unavailable for this claim (never fabricated)."""
        if not evidence_candidates:
            return {}

        prompt = build_judgment_prompt(claim, evidence_candidates)
        attempts = self._config.max_schema_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                raw_json, _meta = self._llm.generate_json(prompt)
            except (LLMJsonError, LLMGenerationError) as exc:
                last_error = exc
                logger.warning(
                    "verification_judgment_call_failed",
                    extra={"claim_id": claim.claim_id, "attempt": attempt},
                )
                continue

            try:
                batch = _JudgmentBatch.model_validate(raw_json)
            except ValidationError as exc:
                last_error = exc
                logger.warning(
                    "verification_judgment_schema_invalid",
                    extra={"claim_id": claim.claim_id, "attempt": attempt},
                )
                continue

            valid_ids = {e.evidence_id for e in evidence_candidates}
            return {j.evidence_id: j for j in batch.judgments if j.evidence_id in valid_ids}

        logger.warning(
            "verification_judgment_unavailable",
            extra={"claim_id": claim.claim_id, "error": str(last_error)},
        )
        return {}
