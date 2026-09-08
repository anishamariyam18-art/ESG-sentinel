import pytest

from app.core.config import LLMConfig
from app.core.llm import LLMGenerationError, LLMJsonError, LLMManager


class FakeLLMProvider:
    """Test double implementing the LLMProvider protocol -- no network."""

    def __init__(self, responses=None, health=True):
        self.responses = list(responses or [])
        self.calls = []
        self.health = health

    def generate_text(self, prompt, *, json_mode, temperature):
        self.calls.append({"prompt": prompt, "json_mode": json_mode, "temperature": temperature})
        if not self.responses:
            raise LLMGenerationError("FakeLLMProvider: no more scripted responses")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def health_check(self):
        return self.health


def _manager(responses, max_retries=1):
    provider = FakeLLMProvider(responses=responses)
    return LLMManager(provider, config=LLMConfig(_env_file=None, max_retries=max_retries)), provider


def test_generate_text_returns_provider_output():
    manager, provider = _manager(["hello"])
    assert manager.generate_text("prompt") == "hello"
    assert provider.calls[0]["json_mode"] is False


def test_generate_text_retries_then_succeeds():
    manager, provider = _manager([LLMGenerationError("boom"), "recovered"])
    assert manager.generate_text("prompt") == "recovered"
    assert len(provider.calls) == 2


def test_generate_text_raises_after_exhausting_retries():
    manager, provider = _manager([LLMGenerationError("a"), LLMGenerationError("b")], max_retries=1)
    with pytest.raises(LLMGenerationError):
        manager.generate_text("prompt")
    assert len(provider.calls) == 2  # 1 initial + 1 retry


def test_generate_json_parses_clean_json():
    manager, _ = _manager(['{"company_name": "Acme"}'])
    parsed, meta = manager.generate_json("prompt")
    assert parsed == {"company_name": "Acme"}
    assert meta["repair_count"] == 0


def test_generate_json_repairs_markdown_code_fence():
    manager, _ = _manager(['```json\n{"company_name": "Acme"}\n```'])
    parsed, meta = manager.generate_json("prompt")
    assert parsed == {"company_name": "Acme"}
    assert meta["repair_count"] == 1


def test_generate_json_repairs_trailing_comma():
    manager, _ = _manager(['{"a": 1, "b": [1, 2,],}'])
    parsed, meta = manager.generate_json("prompt")
    assert parsed == {"a": 1, "b": [1, 2]}
    assert meta["repair_count"] == 1


def test_generate_json_retries_full_generation_when_unrepairable():
    manager, provider = _manager(["not json at all {{{", '{"company_name": "Acme"}'], max_retries=1)
    parsed, meta = manager.generate_json("prompt")
    assert parsed == {"company_name": "Acme"}
    assert len(provider.calls) == 2


def test_generate_json_raises_after_exhausting_retries():
    manager, _ = _manager(["not json", "still not json {{{"], max_retries=1)
    with pytest.raises(LLMJsonError):
        manager.generate_json("prompt")


def test_health_check_delegates_to_provider():
    manager, _ = _manager([], max_retries=0)
    manager_healthy, _ = _manager([])
    unhealthy_provider = FakeLLMProvider(responses=[], health=False)
    unhealthy_manager = LLMManager(unhealthy_provider, config=LLMConfig(_env_file=None))
    assert unhealthy_manager.health_check() is False


def test_get_llm_manager_raises_clear_error_without_api_key(monkeypatch):
    import app.core.llm as llm_module
    from app.core.config import Settings

    monkeypatch.setattr(llm_module, "_llm_manager", None)
    fake_settings = Settings(_env_file=None, gemini_api_key=None)
    monkeypatch.setattr(llm_module, "get_settings", lambda: fake_settings)

    with pytest.raises(LLMGenerationError):
        llm_module.get_llm_manager()

    monkeypatch.setattr(llm_module, "_llm_manager", None)
