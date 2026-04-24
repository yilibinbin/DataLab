"""Server-Sent Events (SSE) helpers for long-running DataLab jobs.

Phase 4 #3 — the web app's auto-fit / MCMC / error-propagation runs
can take minutes. Without streaming, the user sees a blank page for
the duration; with SSE they see incremental events ("model 1 of 10
complete", "best AIC so far: 42.1").

SSE is chosen over WebSocket because:
- unidirectional server→client is sufficient (client never sends
  events to the server within a single job)
- plain HTTP works through every reverse proxy / firewall
- no extra dependency beyond Flask
- automatic reconnect is built into browsers' EventSource

Contract:
- ``format_sse_event(data, event_name=None, event_id=None)`` formats
  a single SSE frame. Escapes newlines inside ``data`` so a
  multi-line JSON payload still frames correctly.
- ``sse_stream(event_generator)`` wraps a Python generator yielding
  ``(event_name, payload)`` tuples or ``payload`` dicts into a
  Flask response with ``text/event-stream`` Content-Type and the
  standard anti-buffering headers.
- Generator is wrapped in try/except so a failure on the server
  side emits an ``error`` event to the client before closing.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Iterable, Optional, Union

__all__ = [
    "SSE_CONTENT_TYPE",
    "format_sse_event",
    "sse_stream",
]

_logger = logging.getLogger(__name__)

SSE_CONTENT_TYPE = "text/event-stream"

# Cap on frame size. An individual event beyond ~64 KB is almost
# certainly a bug (a caller dumping an entire plot's PNG bytes into
# an SSE frame, for instance) and would also choke the default
# nginx proxy_buffer_size.
MAX_SSE_FRAME_BYTES = 65_536

# Separator for SSE frames. Two LF per spec.
_FRAME_SEP = "\n\n"


def _encode_data_field(data: Any) -> str:
    """Serialise a payload into the SSE ``data:`` field format.

    Multi-line data must be emitted as multiple ``data:`` lines; the
    client concatenates them with newlines. We JSON-encode dicts for
    the caller so the client side gets a single ``JSON.parse(ev.data)``
    code path.
    """
    if data is None:
        return ""
    if isinstance(data, (dict, list)):
        encoded = json.dumps(data, ensure_ascii=False)
    else:
        encoded = str(data)
    # Each line becomes its own data: field. SSE clients concatenate
    # multi-line data values with a single '\n'.
    lines = encoded.split("\n")
    return "\n".join(f"data: {line}" for line in lines)


def format_sse_event(
    data: Any,
    event_name: Optional[str] = None,
    event_id: Optional[str] = None,
) -> str:
    """Format a single SSE frame from a payload.

    Frame layout per spec:
        event: <name>\\n       (optional)
        id: <id>\\n             (optional)
        data: <line1>\\n        (one or more — multi-line data)
        data: <line2>\\n
        \\n                    (blank line = end of frame)

    Returns the full frame as a string, terminated by the mandatory
    blank-line separator.
    """
    parts: list[str] = []
    if event_name is not None:
        # Newlines in event_name would inject a separator and split
        # the frame — reject at the boundary.
        if "\n" in event_name or "\r" in event_name:
            raise ValueError("event_name must not contain newlines")
        parts.append(f"event: {event_name}")
    if event_id is not None:
        if "\n" in str(event_id) or "\r" in str(event_id):
            raise ValueError("event_id must not contain newlines")
        parts.append(f"id: {event_id}")
    data_line = _encode_data_field(data)
    if data_line:
        parts.append(data_line)
    frame = "\n".join(parts) + _FRAME_SEP
    if len(frame.encode("utf-8")) > MAX_SSE_FRAME_BYTES:
        raise ValueError(
            f"SSE frame size {len(frame)} exceeds MAX_SSE_FRAME_BYTES "
            f"{MAX_SSE_FRAME_BYTES}; emit progress in smaller chunks"
        )
    return frame


def sse_stream(
    event_generator: Iterable[Union[tuple[str, Any], dict, Any]],
    *,
    heartbeat_interval: Optional[float] = None,
    emit: Optional[Callable[[str], None]] = None,
) -> Iterable[str]:
    """Convert a Python generator of events into an SSE frame iterator.

    Each item yielded by ``event_generator`` can be:
    - A ``(event_name, payload)`` tuple — event name controls the
      event type dispatched to the client's JS ``addEventListener``.
    - A dict or any JSON-serialisable value — emitted as an unnamed
      default-``message`` event.
    - A string — emitted as a raw data line.

    Exceptions raised by the generator are converted into a final
    ``error`` SSE event (with a JSON payload describing the class and
    message) before the stream closes — the client UI can surface
    the failure without having to parse a Flask HTML error page.

    ``heartbeat_interval`` is a future hook for keep-alive frames;
    not yet implemented (the proxies we deploy to have idle-connection
    timeouts well above typical job durations).

    ``emit`` is an optional logging callback; used by the integration
    tests to capture every frame server-side without having to consume
    the HTTP iterator. Never call from production.
    """
    def _materialise(item: Any) -> tuple[str, Any]:
        if isinstance(item, tuple) and len(item) == 2:
            return str(item[0]), item[1]
        return "message", item

    try:
        for raw in event_generator:
            event_name, payload = _materialise(raw)
            frame = format_sse_event(payload, event_name=event_name)
            if emit is not None:
                emit(frame)
            yield frame
    except Exception as exc:  # noqa: BLE001
        _logger.warning("sse_stream: generator raised %s", exc)
        err_frame = format_sse_event(
            {"error": type(exc).__name__, "message": str(exc)},
            event_name="error",
        )
        if emit is not None:
            emit(err_frame)
        yield err_frame
