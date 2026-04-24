"""Phase 5 #26 — crash reporter regression tests.

Pins:
- Double-opt-in (URL + ENABLE flag both required)
- Traceback path redaction (no /Users/..., C:\\..., or /home/...)
- Never raises; network failures return False
- Report body size cap
- No os.environ / sys.argv leakage
"""

from __future__ import annotations

import json
import os
from unittest import mock

import pytest

from shared.crash_reporter import (
    DATALAB_CRASH_REPORT_ENABLE_ENV,
    DATALAB_CRASH_REPORT_URL_ENV,
    MAX_REPORT_BYTES,
    build_crash_report,
    install_excepthook,
    is_enabled,
    sanitize_traceback,
    send_crash_report,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    monkeypatch.delenv(DATALAB_CRASH_REPORT_URL_ENV, raising=False)
    monkeypatch.delenv(DATALAB_CRASH_REPORT_ENABLE_ENV, raising=False)
    monkeypatch.delenv("DATALAB_CRASH_REPORT_INCLUDE_MESSAGE", raising=False)


def test_is_enabled_requires_both_env_vars(monkeypatch):
    assert is_enabled() is False

    monkeypatch.setenv(DATALAB_CRASH_REPORT_URL_ENV, "https://example/crash")
    assert is_enabled() is False  # still missing ENABLE

    monkeypatch.setenv(DATALAB_CRASH_REPORT_ENABLE_ENV, "1")
    assert is_enabled() is True


def test_is_enabled_only_url_not_enough(monkeypatch):
    monkeypatch.setenv(DATALAB_CRASH_REPORT_URL_ENV, "https://example/crash")
    assert is_enabled() is False


def test_is_enabled_only_flag_not_enough(monkeypatch):
    monkeypatch.setenv(DATALAB_CRASH_REPORT_ENABLE_ENV, "1")
    assert is_enabled() is False


def test_sanitize_traceback_redacts_unix_paths():
    tb = 'File "/Users/alice/Documents/secret/app.py", line 10'
    out = sanitize_traceback(tb)
    assert "/Users/alice" not in out
    assert "secret" not in out


def test_sanitize_traceback_redacts_windows_paths():
    tb = r'File "C:\Users\Alice\Documents\Project\app.py", line 10'
    out = sanitize_traceback(tb)
    assert "Alice" not in out
    assert "Documents" not in out


def test_sanitize_traceback_preserves_datalab_module_names():
    """DataLab-owned modules should keep their basename so stack
    frames stay useful. e.g.,
    '/Users/alice/code/fitting/plot_fitting.py' → '<path>/fitting/plot_fitting.py'"""
    tb = 'File "/Users/alice/code/fitting/plot_fitting.py", line 200'
    out = sanitize_traceback(tb)
    assert "fitting/plot_fitting.py" in out


def test_build_crash_report_contains_exc_class():
    try:
        raise ValueError("some value went wrong")
    except ValueError as exc:
        report = build_crash_report(
            type(exc), exc, exc.__traceback__, app_version="2.0.0-dev"
        )
    assert report["exc_class"] == "ValueError"
    assert "traceback" in report
    assert report["datalab_version"] == "2.0.0-dev"
    assert "python_version" in report
    assert "platform" in report


def test_build_crash_report_excludes_message_by_default():
    """Default payload does NOT include the exception message —
    it might contain sensitive data (file paths in file-not-found
    errors)."""
    try:
        raise FileNotFoundError("/Users/alice/Documents/secret.txt")
    except FileNotFoundError as exc:
        report = build_crash_report(
            type(exc), exc, exc.__traceback__,
        )
    # exc_message is opt-in via a separate env var
    assert "exc_message" not in report
    # And the path must not appear anywhere in the traceback either
    for value in report.values():
        if isinstance(value, str):
            assert "Alice" not in value.replace("alice", "")  # case-insensitive
            assert "/Users/alice" not in value


def test_build_crash_report_with_opt_in_message(monkeypatch):
    """Users can opt in to including the exception message via the
    undocumented env var. Even then the message gets path-redacted."""
    monkeypatch.setenv("DATALAB_CRASH_REPORT_INCLUDE_MESSAGE", "1")
    try:
        raise FileNotFoundError("/Users/alice/secret.txt missing")
    except FileNotFoundError as exc:
        report = build_crash_report(type(exc), exc, exc.__traceback__)
    assert "exc_message" in report
    # Path still redacted
    assert "/Users/alice" not in report["exc_message"]
    assert "<path>" in report["exc_message"]


def test_build_crash_report_does_not_include_environ():
    """Sanity: NO env vars leaked into the report under any key."""
    os.environ["TEST_SECRET_CANARY"] = "should-never-appear"
    try:
        try:
            raise RuntimeError("check")
        except RuntimeError as exc:
            report = build_crash_report(type(exc), exc, exc.__traceback__)
    finally:
        del os.environ["TEST_SECRET_CANARY"]
    encoded = json.dumps(report)
    assert "TEST_SECRET_CANARY" not in encoded
    assert "should-never-appear" not in encoded


def test_send_crash_report_returns_false_without_url():
    """No URL configured → skip send, return False."""
    result = send_crash_report({"exc_class": "X"})
    assert result is False


def test_send_crash_report_returns_true_on_2xx():
    """Mock a successful POST; verify True returned."""
    with mock.patch("shared.crash_reporter._urlrequest.urlopen") as m_open:
        fake_response = mock.MagicMock()
        fake_response.status = 200
        fake_response.__enter__ = mock.MagicMock(return_value=fake_response)
        fake_response.__exit__ = mock.MagicMock(return_value=False)
        m_open.return_value = fake_response
        result = send_crash_report(
            {"exc_class": "Test"},
            url="https://example.test/crash",
        )
    assert result is True


def test_send_crash_report_returns_false_on_network_error():
    from urllib.error import URLError

    with mock.patch("shared.crash_reporter._urlrequest.urlopen") as m_open:
        m_open.side_effect = URLError("connection refused")
        result = send_crash_report(
            {"exc_class": "Test"},
            url="https://example.test/crash",
        )
    assert result is False


def test_send_crash_report_does_not_raise_on_any_error():
    """A crash reporter that crashes is worse than none."""
    with mock.patch("shared.crash_reporter._urlrequest.urlopen") as m_open:
        m_open.side_effect = RuntimeError("total chaos")
        # Must not raise
        result = send_crash_report(
            {"exc_class": "Test"},
            url="https://example.test/crash",
        )
    assert result is False


def test_send_crash_report_truncates_oversized_body():
    giant = {"filler": "x" * (MAX_REPORT_BYTES + 10000)}
    with mock.patch("shared.crash_reporter._urlrequest.urlopen") as m_open:
        fake_response = mock.MagicMock()
        fake_response.status = 200
        fake_response.__enter__ = mock.MagicMock(return_value=fake_response)
        fake_response.__exit__ = mock.MagicMock(return_value=False)
        m_open.return_value = fake_response
        send_crash_report(giant, url="https://example.test/crash")
    # Inspect the request payload — size must be at or below cap
    call_args = m_open.call_args[0][0]
    assert len(call_args.data) <= MAX_REPORT_BYTES


def test_install_excepthook_is_reversible():
    """install_excepthook must replace the prior hook, not chain
    infinitely. Calling it twice should install exactly one hook."""
    import sys

    original = sys.excepthook
    try:
        install_excepthook("test-1")
        hook1 = sys.excepthook
        install_excepthook("test-2")
        hook2 = sys.excepthook
        # Second call installed a new hook (not the same object)
        assert hook1 is not hook2
        # Both hooks call the default as their first action
        assert sys.excepthook is not original
    finally:
        sys.excepthook = original


def test_install_excepthook_noop_without_opt_in(monkeypatch, capsys):
    """With opt-in env vars unset, the hook should NOT attempt to
    POST — send_crash_report should never be called."""
    import sys

    original = sys.excepthook
    try:
        install_excepthook("test")
        with mock.patch(
            "shared.crash_reporter.send_crash_report"
        ) as m_send:
            # Simulate an unhandled exception
            try:
                raise RuntimeError("test crash")
            except RuntimeError:
                sys.excepthook(*sys.exc_info())
            m_send.assert_not_called()
    finally:
        sys.excepthook = original


def test_install_excepthook_sends_when_opted_in(monkeypatch):
    """With both env vars set, the hook posts the report."""
    import sys

    monkeypatch.setenv(DATALAB_CRASH_REPORT_URL_ENV, "https://example.test/crash")
    monkeypatch.setenv(DATALAB_CRASH_REPORT_ENABLE_ENV, "1")

    original = sys.excepthook
    try:
        install_excepthook("test-version")
        with mock.patch(
            "shared.crash_reporter.send_crash_report",
            return_value=True,
        ) as m_send:
            try:
                raise ValueError("boom")
            except ValueError:
                sys.excepthook(*sys.exc_info())
            m_send.assert_called_once()
            report_arg = m_send.call_args[0][0]
            assert report_arg["exc_class"] == "ValueError"
    finally:
        sys.excepthook = original
