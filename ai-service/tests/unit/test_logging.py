import json
import logging

from app.core.logging import get_logger, setup_logging


def test_get_logger_returns_named_logger():
    logger = get_logger("test.module")
    assert logger.name == "test.module"


def test_log_output_is_valid_json(capsys):
    setup_logging(level="INFO")
    logger = get_logger("test.json")
    logger.info("document_processed", extra={"document_id": "DOC-001", "pages": 42})

    captured = capsys.readouterr()
    line = captured.out.strip().splitlines()[-1]
    payload = json.loads(line)

    assert payload["message"] == "document_processed"
    assert payload["document_id"] == "DOC-001"
    assert payload["pages"] == 42
    assert payload["level"] == "INFO"
    assert "timestamp" in payload


def test_secrets_are_redacted(capsys):
    setup_logging(level="INFO")
    logger = get_logger("test.secrets")
    logger.info(
        "llm_call",
        extra={"gemini_api_key": "sk-should-not-appear", "model": "gemini-2.5-flash"},
    )

    captured = capsys.readouterr()
    assert "sk-should-not-appear" not in captured.out
    line = captured.out.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["gemini_api_key"] == "***REDACTED***"
    assert payload["model"] == "gemini-2.5-flash"


def test_setup_logging_is_idempotent():
    setup_logging(level="INFO")
    handlers_before = len(logging.getLogger().handlers)
    setup_logging(level="DEBUG")
    handlers_after = len(logging.getLogger().handlers)
    assert handlers_before == handlers_after == 1
