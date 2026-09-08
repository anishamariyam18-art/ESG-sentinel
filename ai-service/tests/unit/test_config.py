import pytest
from pydantic import ValidationError

from app.core.config import (
    AnalyzerConfidenceWeights,
    AnalyzerConfig,
    ChunkingConfig,
    LLMConfig,
    Settings,
    TrustScoreWeights,
    VerificationConfidenceWeights,
    VerificationConfig,
    VerificationThresholds,
    VerificationWeights,
    get_settings,
)


def test_settings_load_with_defaults(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = Settings(_env_file=None)
    assert settings.environment == "development"
    assert settings.log_level == "INFO"
    assert settings.gemini_api_key is None
    assert settings.retrieval.top_k == 5
    assert settings.verification_thresholds.verified_score_min == 80.0


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    settings = Settings(_env_file=None)
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"


def test_gemini_api_key_never_printed_in_repr(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-value")
    settings = Settings(_env_file=None)
    assert "super-secret-value" not in repr(settings.gemini_api_key)
    assert settings.gemini_api_key.get_secret_value() == "super-secret-value"


def test_get_settings_is_cached():
    assert get_settings() is get_settings()


def test_trust_score_weights_must_sum_to_one():
    TrustScoreWeights(_env_file=None)  # default weights are valid


def test_trust_score_weights_reject_bad_sum(monkeypatch):
    monkeypatch.setenv("TRUST_WEIGHTS__CLAIM_SUPPORT", "0.9")
    with pytest.raises(ValidationError):
        TrustScoreWeights(_env_file=None)


def test_invalid_environment_literal_rejected():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, environment="staging")


def test_chunking_config_defaults():
    config = ChunkingConfig(_env_file=None)
    assert config.target_chunk_chars == 1000
    assert config.max_chunk_chars >= config.target_chunk_chars


def test_chunking_config_rejects_max_below_target():
    with pytest.raises(ValidationError):
        ChunkingConfig(_env_file=None, target_chunk_chars=1000, max_chunk_chars=500)


def test_llm_config_defaults():
    config = LLMConfig(_env_file=None)
    assert config.max_retries == 2
    assert config.temperature == 0.0


def test_analyzer_config_defaults():
    config = AnalyzerConfig(_env_file=None)
    assert config.max_batch_chars > 0
    assert config.max_chunks_per_batch > 0
    assert config.max_schema_retries >= 0


def test_analyzer_confidence_weights_default_sums_to_one():
    AnalyzerConfidenceWeights(_env_file=None)  # must not raise


def test_analyzer_confidence_weights_reject_bad_sum():
    with pytest.raises(ValidationError):
        AnalyzerConfidenceWeights(_env_file=None, source_coverage=0.9)


def test_settings_include_llm_and_analyzer_subconfigs():
    settings = Settings(_env_file=None)
    assert isinstance(settings.llm, LLMConfig)
    assert isinstance(settings.analyzer, AnalyzerConfig)
    assert isinstance(settings.analyzer_confidence_weights, AnalyzerConfidenceWeights)


def test_verification_thresholds_defaults():
    thresholds = VerificationThresholds(_env_file=None)
    assert thresholds.verified_score_min == 80.0
    assert thresholds.partially_verified_score_min == 60.0


def test_verification_thresholds_reject_out_of_order():
    with pytest.raises(ValidationError):
        VerificationThresholds(_env_file=None, verified_score_min=50.0, partially_verified_score_min=70.0)


def test_verification_weights_default_sums_to_one():
    VerificationWeights(_env_file=None)  # must not raise


def test_verification_weights_reject_bad_sum():
    with pytest.raises(ValidationError):
        VerificationWeights(_env_file=None, semantic=0.9)


def test_verification_confidence_weights_default_sums_to_one():
    VerificationConfidenceWeights(_env_file=None)


def test_verification_confidence_weights_reject_bad_sum():
    with pytest.raises(ValidationError):
        VerificationConfidenceWeights(_env_file=None, provenance_quality=0.9)


def test_verification_config_defaults():
    config = VerificationConfig(_env_file=None)
    assert config.candidates_per_claim > 0
    assert config.max_llm_judgment_candidates > 0


def test_settings_include_verification_subconfigs():
    settings = Settings(_env_file=None)
    assert isinstance(settings.verification, VerificationConfig)
    assert isinstance(settings.verification_weights, VerificationWeights)
    assert isinstance(settings.verification_confidence_weights, VerificationConfidenceWeights)
