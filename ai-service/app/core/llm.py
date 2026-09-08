"""LLM abstraction.

No module outside this file may import `google.generativeai` (or any other
provider SDK) directly -- everything else depends on `LLMManager`, which
wraps a swappable `LLMProvider`. This keeps the model provider replaceable
and keeps API keys out of every other module.
"""
from __future__ import annotations

import json
import re
from typing import Protocol

from app.core.config import LLMConfig, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class LLMGenerationError(Exception):
    """Raised when the provider fails to produce a response after retries."""


class LLMJsonError(Exception):
    """Raised when a response cannot be parsed as JSON even after a
    controlled repair attempt and retries."""


class LLMProvider(Protocol):
    def generate_text(self, prompt: str, *, json_mode: bool, temperature: float) -> str: ...

    def health_check(self) -> bool: ...


class GeminiProvider:
    """The only file in the codebase that touches google.generativeai."""

    def __init__(self, api_key: str, model_name: str) -> None:
        import google.generativeai as genai

        self._genai = genai
        self._model_name = model_name
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model_name)

    def generate_text(self, prompt: str, *, json_mode: bool = False, temperature: float = 0.0) -> str:
        generation_config = self._genai.GenerationConfig(
            temperature=temperature,
            response_mime_type="application/json" if json_mode else "text/plain",
        )
        try:
            response = self._model.generate_content(prompt, generation_config=generation_config)
        except Exception as exc:  # provider SDK exceptions vary; normalize them
            raise LLMGenerationError(f"Gemini request failed: {type(exc).__name__}") from exc

        text = getattr(response, "text", None)
        if not text:
            raise LLMGenerationError("Gemini returned an empty response")
        return text

    def health_check(self) -> bool:
        try:
            self._model.generate_content("ping", generation_config=self._genai.GenerationConfig(max_output_tokens=1))
            return True
        except Exception as exc:  # noqa: BLE001 -- health check must never raise
            logger.warning("llm_health_check_failed", extra={"error_type": type(exc).__name__})
            return False


_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)
_TRAILING_COMMA_RE = re.compile(r",(\s*[\]}])")


def _repair_json(raw: str) -> str:
    """Conservative, safe repairs only: strips markdown code fences and
    surrounding prose, and removes trailing commas before a closing
    bracket. Never rewrites or guesses at content."""
    text = _CODE_FENCE_RE.sub("", raw).strip()

    first = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
    last = max(text.rfind("}"), text.rfind("]"))
    if first != -1 and last != -1 and last > first:
        text = text[first : last + 1]

    text = _TRAILING_COMMA_RE.sub(r"\1", text)
    return text


class LLMManager:
    """Wraps an `LLMProvider` with retry, JSON parsing + controlled repair,
    and logging. This is what every other module depends on -- never a
    provider directly."""

    def __init__(self, provider: LLMProvider, config: LLMConfig | None = None) -> None:
        self._provider = provider
        self._config = config or get_settings().llm

    def generate_text(self, prompt: str, *, temperature: float | None = None) -> str:
        temp = self._config.temperature if temperature is None else temperature
        last_error: Exception | None = None
        for attempt in range(self._config.max_retries + 1):
            try:
                return self._provider.generate_text(prompt, json_mode=False, temperature=temp)
            except LLMGenerationError as exc:
                last_error = exc
                logger.warning("llm_generate_text_retry", extra={"attempt": attempt, "error": str(exc)})
        raise LLMGenerationError(f"generate_text failed after {self._config.max_retries + 1} attempts") from last_error

    def generate_json(self, prompt: str, *, temperature: float | None = None) -> tuple[dict, dict]:
        """Returns (parsed_json, metadata). metadata includes `attempts`
        and `repair_count` so callers can factor retry/repair activity into
        a documented confidence score."""
        temp = self._config.temperature if temperature is None else temperature
        repair_count = 0
        last_error: Exception | None = None

        for attempt in range(self._config.max_retries + 1):
            try:
                raw = self._provider.generate_text(prompt, json_mode=True, temperature=temp)
            except LLMGenerationError as exc:
                last_error = exc
                logger.warning("llm_generate_json_retry", extra={"attempt": attempt, "error": str(exc)})
                continue

            try:
                parsed = json.loads(raw)
                return parsed, {"attempts": attempt + 1, "repair_count": repair_count}
            except json.JSONDecodeError:
                pass

            repair_count += 1
            try:
                parsed = json.loads(_repair_json(raw))
                logger.warning("llm_json_repaired", extra={"attempt": attempt})
                return parsed, {"attempts": attempt + 1, "repair_count": repair_count}
            except json.JSONDecodeError as exc:
                last_error = exc
                logger.warning("llm_json_repair_failed", extra={"attempt": attempt, "error": str(exc)})

        reason = f": {last_error}" if last_error is not None else ""
        raise LLMJsonError(
            f"generate_json failed to produce valid JSON after {self._config.max_retries + 1} attempts{reason}"
        ) from last_error

    def health_check(self) -> bool:
        return self._provider.health_check()


_llm_manager: LLMManager | None = None


def get_llm_manager() -> LLMManager:
    global _llm_manager
    if _llm_manager is None:
        settings = get_settings()
        if settings.gemini_api_key is None:
            raise LLMGenerationError(
                "GEMINI_API_KEY is not configured; set it in the environment before using the LLM manager"
            )
        provider = GeminiProvider(
            api_key=settings.gemini_api_key.get_secret_value(),
            model_name=settings.gemini_model_name,
        )
        _llm_manager = LLMManager(provider)
    return _llm_manager
