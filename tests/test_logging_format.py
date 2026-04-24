"""Phase 5 #25 — structured logging regression tests.

Pins the ``shared.logging_setup`` contract: idempotent installation,
env-var-driven format, sensitive-value scrubbing, JSON output shape.
"""

from __future__ import annotations

import io
import json
import logging

import pytest

from shared.logging_setup import (
    DATALAB_LOG_JSON_ENV,
    DATALAB_LOG_LEVEL_ENV,
    configure_logging,
    scrub_sensitive,
)


@pytest.fixture(autouse=True)
def _reset_root_handlers():
    """Between tests, tear down any handlers we installed so we don't
    accumulate across the test session."""
    root = logging.getLogger()
    before = list(root.handlers)
    yield
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)


def test_configure_logging_installs_handler_idempotently():
    configure_logging(json_format=False, stream=io.StringIO())
    configure_logging(json_format=False, stream=io.StringIO())
    # Exactly one handler with our marker
    marked = [
        h for h in logging.getLogger().handlers
        if getattr(h, "_datalab_handler", False)
    ]
    assert len(marked) == 1


def test_json_format_emits_valid_json_per_line():
    buf = io.StringIO()
    configure_logging(json_format=True, stream=buf)
    logger = logging.getLogger("test.json.line")
    logger.warning("hello %s", "world")
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    assert lines, "no log output captured"
    payload = json.loads(lines[-1])
    assert payload["level"] == "WARNING"
    assert payload["logger"] == "test.json.line"
    assert payload["msg"] == "hello world"
    assert "ts" in payload


def test_json_format_includes_extra_fields():
    buf = io.StringIO()
    configure_logging(json_format=True, stream=buf)
    logger = logging.getLogger("test.json.extra")
    logger.info("with extras", extra={"model": "linear", "dpi": 200})
    payload = json.loads(buf.getvalue().splitlines()[-1])
    assert payload["extra"]["model"] == "linear"
    assert payload["extra"]["dpi"] == 200


def test_json_format_scrubs_sensitive_extras():
    buf = io.StringIO()
    configure_logging(json_format=True, stream=buf)
    logger = logging.getLogger("test.json.scrub")
    logger.info(
        "login attempt",
        extra={"user": "alice", "password": "hunter2", "token": "xyz"},
    )
    payload = json.loads(buf.getvalue().splitlines()[-1])
    assert payload["extra"]["user"] == "alice"
    assert payload["extra"]["password"] == "***"
    assert payload["extra"]["token"] == "***"


def test_json_format_includes_exception_traceback():
    buf = io.StringIO()
    configure_logging(json_format=True, stream=buf)
    logger = logging.getLogger("test.json.exc")
    try:
        raise RuntimeError("kaboom")
    except RuntimeError:
        logger.exception("failure")
    payload = json.loads(buf.getvalue().splitlines()[-1])
    assert "exc" in payload
    assert "RuntimeError" in payload["exc"]


def test_plain_text_format_is_human_readable():
    buf = io.StringIO()
    configure_logging(json_format=False, stream=buf)
    logger = logging.getLogger("test.plain")
    logger.warning("plain message")
    output = buf.getvalue()
    assert "plain message" in output
    assert "[WARNING]" in output
    assert "test.plain" in output


def test_env_var_selects_json_format(monkeypatch):
    monkeypatch.setenv(DATALAB_LOG_JSON_ENV, "1")
    buf = io.StringIO()
    configure_logging(stream=buf)
    logger = logging.getLogger("test.env.json")
    logger.info("check")
    line = buf.getvalue().splitlines()[-1]
    # Must parse as JSON
    assert json.loads(line)["msg"] == "check"


def test_env_var_selects_plain_when_unset(monkeypatch):
    monkeypatch.delenv(DATALAB_LOG_JSON_ENV, raising=False)
    buf = io.StringIO()
    configure_logging(stream=buf)
    logger = logging.getLogger("test.env.plain")
    logger.info("check")
    # Plain-text output — not JSON
    line = buf.getvalue().splitlines()[-1]
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)


def test_env_var_level_debug(monkeypatch):
    monkeypatch.setenv(DATALAB_LOG_LEVEL_ENV, "DEBUG")
    buf = io.StringIO()
    configure_logging(stream=buf)
    logger = logging.getLogger("test.env.debug")
    logger.debug("debug line")
    assert "debug line" in buf.getvalue()


def test_env_var_level_invalid_falls_back_to_info(monkeypatch):
    """Defensive: a bad env value shouldn't crash startup."""
    monkeypatch.setenv(DATALAB_LOG_LEVEL_ENV, "NOT-A-LEVEL")
    buf = io.StringIO()
    configure_logging(stream=buf)
    # Root level now INFO — debug suppressed
    logger = logging.getLogger("test.env.invalid")
    logger.debug("should be hidden")
    logger.info("should appear")
    out = buf.getvalue()
    assert "should be hidden" not in out
    assert "should appear" in out


def test_scrub_sensitive_nested_dicts():
    data = {
        "user": "alice",
        "credentials": {"password": "x", "token": "y"},
        "items": [{"secret": "z", "name": "item1"}],
    }
    result = scrub_sensitive(data)
    assert result["user"] == "alice"
    assert result["credentials"]["password"] == "***"
    assert result["credentials"]["token"] == "***"
    assert result["items"][0]["secret"] == "***"
    assert result["items"][0]["name"] == "item1"


def test_scrub_sensitive_case_insensitive():
    data = {"Token": "x", "API_KEY": "y"}
    result = scrub_sensitive(data)
    assert result["Token"] == "***"
    assert result["API_KEY"] == "***"


def test_scrub_sensitive_passes_through_primitives():
    for value in (1, 1.5, "hello", None, True, [1, 2, 3]):
        assert scrub_sensitive(value) == value


def test_scrub_sensitive_custom_key_list():
    data = {"foo": "bar", "user_id": 42}
    result = scrub_sensitive(data, sensitive_keys=["user_id"])
    assert result["user_id"] == "***"
    assert result["foo"] == "bar"


def test_json_format_non_json_serialisable_extra_falls_back():
    """A non-JSON-serialisable value in ``extra`` must not crash the
    logger — it should fall back to plain-text."""
    buf = io.StringIO()
    configure_logging(json_format=True, stream=buf)
    logger = logging.getLogger("test.json.unserialisable")

    class _Weird:
        def __repr__(self):
            return "Weird()"

    logger.info("got weird", extra={"thing": _Weird()})
    # Must not raise; output line must be non-empty
    assert buf.getvalue().strip()
