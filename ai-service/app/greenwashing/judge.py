"""LLM greenwashing judgment (section 13).

Called selectively -- only when at least one deterministic signal fired
(service.py decides this, per section 30: "use the LLM only when semantic
interpretation is required, ambiguity exists, multiple signals interact").
The LLM's output never controls `greenwashing_type` or `greenwashing_score`
directly (section 13: "do not allow the LLM to independently invent
greenwashing findings") -- it only contributes explanatory `reasoning`
lines and a qualitative `risk_assessment` used solely as one input to the
confidence score. If the LLM is unavailable or never returns valid JSON,
`judge()` returns None -- callers must treat that as "this signal is
unavailable", never fabricate a judgment.
"""
from __future__ import annotations

from pydantic import BaseModel, Field, ValidationError

from app.core.config import GreenwashingAggregationConfig
from app.core.llm import LLMGenerationError, LLMJsonError, LLMManager
from app.core.logging import get_logger
from app.greenwashing.detector import DetectorReport
from app.greenwashing.prompt import build_judgment_prompt
from app.models.claim import Claim
from app.models.evidence import Evidence
from app.models.verification import VerificationResult

logger = get_logger(__name__)


class GreenwashingJudgment(BaseModel):
    risk_assessment: str  # "low" | "medium" | "high"
    reasoning: list[str] = Field(default_factory=list)
    intent_assumed: bool = False


_INTENT_KEYWORDS = ("intentionally", "deliberately", "knowingly", "willfully", "purposely", "on purpose")


def _asserts_intent(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in _INTENT_KEYWORDS)


class GreenwashingJudge:
    def __init__(self, llm_manager: LLMManager, config: GreenwashingAggregationConfig) -> None:
        self._llm = llm_manager
        self._config = config

    def judge(
        self, claim: Claim, verification_result: VerificationResult, evidence: Evidence | None, report: DetectorReport
    ) -> GreenwashingJudgment | None:
        prompt = build_judgment_prompt(claim, verification_result, evidence, report)
        attempts = self._config.max_schema_retries + 1
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                raw_json, _meta = self._llm.generate_json(prompt)
            except (LLMJsonError, LLMGenerationError) as exc:
                last_error = exc
                logger.warning("greenwashing_judgment_call_failed", extra={"claim_id": claim.claim_id, "attempt": attempt})
                continue

            try:
                judgment = GreenwashingJudgment.model_validate(raw_json)
            except ValidationError as exc:
                last_error = exc
                logger.warning("greenwashing_judgment_schema_invalid", extra={"claim_id": claim.claim_id, "attempt": attempt})
                continue

            # Safety net: never trust the LLM's own `intent_assumed` self-report
            # alone -- it could report False while `reasoning` itself still
            # asserts intent. Scan the actual text and strip any line that does,
            # regardless of what the model claimed about itself.
            filtered_reasoning = [line for line in judgment.reasoning if not _asserts_intent(line)]
            intent_detected = judgment.intent_assumed or len(filtered_reasoning) != len(judgment.reasoning)
            if intent_detected:
                logger.warning("greenwashing_judgment_assumed_intent_discarded", extra={"claim_id": claim.claim_id})
            return judgment.model_copy(update={"reasoning": filtered_reasoning, "intent_assumed": intent_detected})

        logger.warning(
            "greenwashing_judgment_unavailable", extra={"claim_id": claim.claim_id, "error": str(last_error)}
        )
        return None
