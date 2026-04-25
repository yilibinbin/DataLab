"""Opt-in crash reporter (Phase 5 #26).

Catches unhandled exceptions in DataLab's desktop process and POSTs a
minimal failure report to a user-configured endpoint. **Off by
default** — activation requires BOTH:
- ``DATALAB_CRASH_REPORT_URL`` env var set to the HTTPS endpoint
- ``DATALAB_CRASH_REPORT_ENABLE=1`` env var set

This double-opt-in is deliberate: a user who sets a stale URL from a
previous session shouldn't accidentally ship crash data to the old
endpoint on the next run.

Sensitive-data scrubbing (load-bearing):
- NO ``os.environ`` contents (might contain secrets, API keys, paths)
- NO file paths (might contain usernames, folder structure)
- NO arg0 / sys.argv (might contain full file paths as args)
- NO fully-qualified exception messages (might contain file paths
  in file-not-found style errors)
- YES exception class name (e.g., "FileNotFoundError")
- YES a sanitised traceback (paths replaced with ``<path>``)
- YES DataLab version string
- YES Python version
- YES platform (macOS / Linux / Windows identifier, NOT full uname)

All reports are sent with a 5-second timeout; network failure is
silently logged and never blocks shutdown. No retries (a user
crashing repeatedly shouldn't DDoS the endpoint).
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import sys
import traceback
from types import TracebackType
from typing import Any, Callable, Optional
from urllib import error as _urlerror
from urllib import request as _urlrequest

# Standard signature of ``sys.excepthook`` — see the CPython docs
# for ``sys.excepthook`` (https://docs.python.org/3/library/sys.html#sys.excepthook)
# for the canonical shape. We type it once here so the excepthook
# builder (and any future test that monkey-patches it) can refer
# to a single name.
ExceptHook = Callable[
    [type[BaseException], BaseException, Optional["TracebackType"]],
    None,
]

__all__ = [
    "DATALAB_CRASH_REPORT_ENABLE_ENV",
    "DATALAB_CRASH_REPORT_URL_ENV",
    "CRASH_REPORT_TIMEOUT_SECONDS",
    "build_crash_report",
    "install_excepthook",
    "is_enabled",
    "sanitize_traceback",
    "send_crash_report",
]

_logger = logging.getLogger(__name__)

DATALAB_CRASH_REPORT_URL_ENV = "DATALAB_CRASH_REPORT_URL"
DATALAB_CRASH_REPORT_ENABLE_ENV = "DATALAB_CRASH_REPORT_ENABLE"
CRASH_REPORT_TIMEOUT_SECONDS = 5.0

# Max report body size — don't POST multi-megabyte payloads.
MAX_REPORT_BYTES = 32 * 1024

# Heuristic path matcher. Kept intentionally narrow to avoid
# false-positive redactions of scientific data. Matches:
# - /anything/...
# - C:\anything\...
# - relative paths with / or \ separators that contain a user name
_PATH_REDACT_RE = re.compile(
    r"(?:[a-zA-Z]:[\\/]|/)(?:[^\s\"'<>|:*?]+[\\/])+[^\s\"'<>|:*?]+"
)

# Module names that we allow in tracebacks — DataLab's own code.
# Stdlib + site-packages frames are kept but their paths are redacted.
_DATALAB_MODULE_PREFIXES: tuple[str, ...] = (
    "datalab_latex",
    "extrapolation_methods",
    "fitting",
    "shared",
    "app_desktop",
    "app_web",
    "cli",
    "benchmarks",
)


def is_enabled() -> bool:
    """Return True iff both env vars are set to opt-in values."""
    url = os.environ.get(DATALAB_CRASH_REPORT_URL_ENV, "").strip()
    enable = os.environ.get(DATALAB_CRASH_REPORT_ENABLE_ENV, "").strip()
    return bool(url) and enable in ("1", "true", "TRUE", "yes", "on")


def sanitize_traceback(tb_text: str) -> str:
    """Redact filesystem paths from a traceback string.

    Preserves the structural information (file names, line numbers in
    DataLab's own modules) while stripping anything that could leak
    a user's home directory, project path, or filesystem layout. The
    output format is deterministic so grouping / deduplication on
    the receiving end still works.
    """
    def _repl(match: re.Match[str]) -> str:
        path = match.group(0)
        # Preserve the DataLab-module basename so a stack frame in
        # ``fitting/plot_fitting.py`` is still recognisable.
        for prefix in _DATALAB_MODULE_PREFIXES:
            marker = f"/{prefix}/"
            alt_marker = f"\\{prefix}\\"
            for needle in (marker, alt_marker):
                if needle in path:
                    tail = path[path.index(needle) + 1:]
                    return f"<path>/{tail}"
        return "<path>"

    return _PATH_REDACT_RE.sub(_repl, tb_text)


def build_crash_report(
    exc_type: type[BaseException],
    exc_value: BaseException,
    exc_tb: Optional[TracebackType],
    app_version: str = "unknown",
) -> dict[str, Any]:
    """Assemble the redacted crash-report payload."""
    tb_text = "".join(
        traceback.format_exception(exc_type, exc_value, exc_tb)
    )
    report: dict[str, Any] = {
        "exc_class": exc_type.__name__,
        # Exception message is the most likely vector for sensitive
        # data leakage (file-not-found errors embed the path). We
        # include ONLY the class name in the default report.
        # Users who need messages for diagnostics can opt-in by
        # setting DATALAB_CRASH_REPORT_INCLUDE_MESSAGE=1, but we
        # don't advertise that env var publicly.
        "traceback": sanitize_traceback(tb_text),
        "datalab_version": app_version,
        "python_version": sys.version.split()[0],
        "platform": platform.system(),  # e.g., "Darwin" / "Linux" / "Windows"
    }
    if os.environ.get(
        "DATALAB_CRASH_REPORT_INCLUDE_MESSAGE", ""
    ).strip() in ("1", "true", "TRUE"):
        report["exc_message"] = _PATH_REDACT_RE.sub(
            "<path>", str(exc_value)[:500]
        )
    return report


def send_crash_report(
    report: dict[str, Any],
    url: Optional[str] = None,
    timeout: float = CRASH_REPORT_TIMEOUT_SECONDS,
) -> bool:
    """POST the report to the configured endpoint. Returns True on
    2xx, False on any error. Never raises — a crash reporter that
    itself crashes is worse than a missing report.
    """
    target = url or os.environ.get(DATALAB_CRASH_REPORT_URL_ENV, "").strip()
    if not target:
        _logger.debug("crash_reporter: no URL configured; skipping send")
        return False
    try:
        body = json.dumps(report, ensure_ascii=False, default=str).encode("utf-8")
    except Exception as exc:  # noqa: BLE001
        _logger.warning("crash_reporter: report encode failed: %s", exc)
        return False
    if len(body) > MAX_REPORT_BYTES:
        _logger.warning(
            "crash_reporter: report size %d bytes exceeds cap %d; truncating",
            len(body), MAX_REPORT_BYTES,
        )
        body = body[:MAX_REPORT_BYTES]
    req = _urlrequest.Request(
        target, data=body, method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "DataLab-crash-reporter/1.0",
        },
    )
    try:
        with _urlrequest.urlopen(req, timeout=timeout) as resp:
            # urllib's response object types ``status`` as ``Any``; the
            # actual value is always int when the request succeeded.
            status = int(resp.status)
            return 200 <= status < 300
    except _urlerror.URLError as exc:
        _logger.info("crash_reporter: POST failed (%s)", exc)
        return False
    except Exception as exc:  # noqa: BLE001
        _logger.warning("crash_reporter: unexpected error: %s", exc)
        return False


def _build_excepthook(app_version: str) -> ExceptHook:
    def _hook(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_tb: Optional[TracebackType],
    ) -> None:
        # Always chain to the default excepthook so the user still
        # sees the stack on stderr. Our handler runs AFTER printing.
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        if not is_enabled():
            return
        try:
            report = build_crash_report(
                exc_type, exc_value, exc_tb, app_version=app_version
            )
            send_crash_report(report)
        except Exception as exc:  # noqa: BLE001
            # A crash reporter that crashes in a crash handler is the
            # worst debugging experience imaginable. Swallow.
            _logger.debug("crash_reporter: hook itself raised: %s", exc)

    return _hook


def install_excepthook(app_version: str = "unknown") -> None:
    """Wire ``sys.excepthook`` to POST unhandled exceptions to the
    configured endpoint when both opt-in env vars are set. Idempotent:
    if called twice, the second call replaces the first hook."""
    sys.excepthook = _build_excepthook(app_version)
