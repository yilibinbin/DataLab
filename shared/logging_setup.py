"""Structured logging setup for DataLab (Phase 5 #25).

Provides ``configure_logging()`` — a single entry point that every
process-level ``main`` calls exactly once to install a structured
formatter on the root logger.

Design goals:
- Default to a human-readable plain-text format so ``DATALAB_DEBUG=1``
  runs stay readable on a terminal.
- Opt in to JSON-line format via ``DATALAB_LOG_JSON=1`` for production
  deploys that feed into a log aggregator (ELK, Datadog, etc.).
- No extra dependency required — uses stdlib ``logging`` + a custom
  ``logging.Formatter`` subclass for JSON. If ``structlog`` is
  installed, wire it in as the richer option but don't require it.
- Never raise at import time. A bad environment value falls back to
  the plain-text default rather than crashing the app startup.
- Idempotent: calling ``configure_logging()`` twice doesn't add
  duplicate handlers.
- Sensitive-value scrubbing: messages are not scanned (too invasive)
  but the wrapper guarantees that `extra={...}` dicts with obvious
  secret keys (``password``, ``token``, ``api_key``, ``secret``)
  get their values replaced with ``"***"`` before emission.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import IO, Any, Iterable, Optional

__all__ = [
    "DATALAB_LOG_JSON_ENV",
    "DATALAB_LOG_LEVEL_ENV",
    "configure_logging",
    "scrub_sensitive",
]

# Public env-var names — centralise so tests + docs can reference them.
DATALAB_LOG_JSON_ENV = "DATALAB_LOG_JSON"
DATALAB_LOG_LEVEL_ENV = "DATALAB_LOG_LEVEL"

# Log record keys whose values should never be emitted in clear.
# Case-insensitive match on the ``extra`` dict keys.
_SENSITIVE_KEYS: frozenset[str] = frozenset({
    "password", "passwd",
    "token", "api_token", "auth_token", "access_token", "refresh_token",
    "api_key", "apikey",
    "secret", "client_secret",
    "authorization",
    "cookie", "session",
})

_SCRUBBED_PLACEHOLDER = "***"


def scrub_sensitive(
    data: Any,
    sensitive_keys: Optional[Iterable[str]] = None,
) -> Any:
    """Recursively redact values whose keys look sensitive.

    Dicts are walked; nested dicts and lists get the same treatment.
    Primitive values pass through unchanged. This is intentionally a
    best-effort filter — it catches the common ``extra={"token": "x"}``
    mistake without trying to parse arbitrary log message text (which
    would risk false-positive redactions of scientific data).
    """
    if sensitive_keys is None:
        sensitive = _SENSITIVE_KEYS
    else:
        sensitive = frozenset(k.lower() for k in sensitive_keys)

    if isinstance(data, dict):
        return {
            key: (
                _SCRUBBED_PLACEHOLDER
                if str(key).lower() in sensitive
                else scrub_sensitive(value, sensitive_keys=sensitive)
            )
            for key, value in data.items()
        }
    if isinstance(data, list):
        return [scrub_sensitive(item, sensitive_keys=sensitive) for item in data]
    return data


class _JSONLineFormatter(logging.Formatter):
    """Emit one JSON object per log record, suitable for ingestion by
    log aggregators. Standard fields:

    - ``ts``: ISO 8601 timestamp
    - ``level``: uppercase level name
    - ``logger``: logger name (usually the module's ``__name__``)
    - ``msg``: formatted message
    - ``extra``: any ``extra={...}`` args, with sensitive values scrubbed
    - ``exc``: traceback string if present
    """

    # Record attributes that logging adds itself — we exclude them
    # from the ``extra`` blob so the output isn't polluted with Python
    # internals like ``processName`` or ``thread``.
    _STD_ATTRS: frozenset[str] = frozenset({
        "name", "msg", "args", "levelname", "levelno", "pathname",
        "filename", "module", "exc_info", "exc_text", "stack_info",
        "lineno", "funcName", "created", "msecs", "relativeCreated",
        "thread", "threadName", "processName", "process", "message",
        "asctime", "taskName",
    })

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        extras = {
            k: v for k, v in record.__dict__.items()
            if k not in self._STD_ATTRS
        }
        if extras:
            payload["extra"] = scrub_sensitive(extras)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        try:
            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001 - last-ditch fallback
            # JSON encoding failed; fall back to plain-text so the log
            # line still makes it to the aggregator. Better noisy than
            # silent.
            return (
                f"{payload.get('ts')} {payload.get('level')} "
                f"{payload.get('logger')}: {payload.get('msg')}"
            )


def _resolve_level(raw: Optional[str]) -> int:
    """Translate an env-var string to a logging level. Bad values
    fall back to INFO (defensive — don't crash on a typo)."""
    if not raw:
        return logging.INFO
    upper = raw.strip().upper()
    level = logging.getLevelNamesMapping().get(upper)
    if isinstance(level, int):
        return level
    try:
        return int(upper)
    except ValueError:
        return logging.INFO


def configure_logging(
    *,
    level: Optional[int] = None,
    json_format: Optional[bool] = None,
    stream: Optional[IO[str]] = None,
) -> None:
    """Install a single structured handler on the root logger.

    Idempotent. Reads defaults from ``DATALAB_LOG_LEVEL`` /
    ``DATALAB_LOG_JSON`` env vars when explicit args aren't passed.
    """
    root = logging.getLogger()

    # Remove handlers we've installed previously so a second call is
    # idempotent. Handlers we didn't install (pytest's caplog, etc.)
    # are left in place.
    for h in list(root.handlers):
        if getattr(h, "_datalab_handler", False):
            root.removeHandler(h)

    effective_level = (
        level if level is not None
        else _resolve_level(os.environ.get(DATALAB_LOG_LEVEL_ENV))
    )

    if json_format is None:
        raw_json = os.environ.get(DATALAB_LOG_JSON_ENV, "")
        use_json = raw_json.strip() in ("1", "true", "TRUE", "yes", "on")
    else:
        use_json = bool(json_format)

    handler = logging.StreamHandler(stream or sys.stderr)
    if use_json:
        handler.setFormatter(_JSONLineFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
    # Mark the handler so a subsequent call can identify and replace
    # it without stepping on caller-installed handlers.
    handler._datalab_handler = True  # type: ignore[attr-defined]

    root.addHandler(handler)
    root.setLevel(effective_level)
