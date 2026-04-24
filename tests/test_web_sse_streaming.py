"""Phase 4 #3 — SSE streaming helper regression tests.

Pins the frame format, error-path contract, and size cap.
"""

from __future__ import annotations

import json

import pytest

from app_web.streaming import (
    MAX_SSE_FRAME_BYTES,
    SSE_CONTENT_TYPE,
    format_sse_event,
    sse_stream,
)


def test_content_type_is_text_event_stream():
    assert SSE_CONTENT_TYPE == "text/event-stream"


def test_format_event_minimal_dict():
    frame = format_sse_event({"foo": 1})
    assert frame.startswith("data: ")
    assert frame.endswith("\n\n"), "frame must end with blank line (SSE spec)"
    # The data field must be a single JSON-encoded line
    assert json.loads(frame.split("data: ", 1)[1].strip()) == {"foo": 1}


def test_format_event_with_name():
    frame = format_sse_event({"pct": 50}, event_name="progress")
    assert "event: progress\n" in frame


def test_format_event_with_id():
    frame = format_sse_event({"n": 1}, event_name="tick", event_id="42")
    assert "id: 42\n" in frame


def test_format_event_multiline_data_split_into_data_fields():
    """SSE spec: multi-line data must be emitted as multiple data:
    lines, with the client concatenating them with '\\n'."""
    frame = format_sse_event("line one\nline two\nline three")
    # Count data: prefix occurrences
    assert frame.count("data: ") == 3


def test_format_event_rejects_newline_in_event_name():
    with pytest.raises(ValueError, match="newline"):
        format_sse_event({}, event_name="bad\nname")


def test_format_event_rejects_newline_in_event_id():
    with pytest.raises(ValueError, match="newline"):
        format_sse_event({}, event_id="bad\nid")


def test_format_event_rejects_oversized_frame():
    giant = {"blob": "x" * (MAX_SSE_FRAME_BYTES + 100)}
    with pytest.raises(ValueError, match="frame size"):
        format_sse_event(giant)


def test_sse_stream_materialises_tuple_events():
    gen = iter([
        ("progress", {"pct": 10}),
        ("progress", {"pct": 50}),
        ("result", {"model": "linear"}),
    ])
    frames = list(sse_stream(gen))
    assert len(frames) == 3
    assert "event: progress" in frames[0]
    assert "event: progress" in frames[1]
    assert "event: result" in frames[2]


def test_sse_stream_materialises_bare_dict_as_message_event():
    gen = iter([{"foo": "bar"}])
    frames = list(sse_stream(gen))
    assert len(frames) == 1
    assert "event: message" in frames[0]
    assert '"foo": "bar"' in frames[0]


def test_sse_stream_emits_error_frame_on_exception():
    def _failing():
        yield ("progress", {"pct": 10})
        raise RuntimeError("something broke")

    frames = list(sse_stream(_failing()))
    assert len(frames) == 2  # progress + error
    assert "event: progress" in frames[0]
    assert "event: error" in frames[1]
    # Error payload must be JSON-decodable with the documented shape
    err_line = next(
        ln for ln in frames[1].splitlines() if ln.startswith("data: ")
    )
    err_body = json.loads(err_line[len("data: "):])
    assert err_body["error"] == "RuntimeError"
    assert err_body["message"] == "something broke"


def test_sse_stream_emit_callback_receives_every_frame():
    captured: list[str] = []
    gen = iter([("a", 1), ("b", 2)])
    frames = list(sse_stream(gen, emit=captured.append))
    assert captured == frames


def test_sse_stream_error_path_invokes_emit_callback():
    captured: list[str] = []

    def _failing():
        yield ("start", 1)
        raise ValueError("bang")

    list(sse_stream(_failing(), emit=captured.append))
    assert any("event: error" in frame for frame in captured)


def test_format_event_json_encodes_unicode():
    """Non-ASCII payloads must round-trip through the stream."""
    frame = format_sse_event({"label": "拟合"})
    # ensure_ascii=False — chinese chars survive the JSON encode
    assert "拟合" in frame


def test_format_event_empty_data_produces_empty_data_field():
    """data=None → no data: line; event-name-only frames are
    valid SSE (useful for triggering a client-side event without
    payload)."""
    frame = format_sse_event(None, event_name="tick")
    assert "event: tick" in frame
    assert "data:" not in frame


def test_sse_integrates_with_flask_response():
    """End-to-end: mount an SSE endpoint on a throwaway Flask app
    and confirm the response streams the expected frames."""
    pytest.importorskip("flask")
    from flask import Flask, Response

    app = Flask(__name__)

    @app.route("/stream")
    def _stream():
        def events():
            yield ("a", {"v": 1})
            yield ("b", {"v": 2})

        return Response(
            sse_stream(events()),
            mimetype=SSE_CONTENT_TYPE,
        )

    client = app.test_client()
    response = client.get("/stream")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    body = response.get_data(as_text=True)
    assert "event: a" in body
    assert "event: b" in body
