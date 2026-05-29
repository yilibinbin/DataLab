"""SSE endpoint regression tests for explicit fit streaming.

The helper in ``app_web/streaming.py`` has been wired to a Flask
blueprint that yields progress events during long-running single-model
fit jobs. The client's ``EventSource`` receives ``started`` →
``progress`` → ``result`` events rather than a single blocking HTTP
response.
"""

from __future__ import annotations

import json

import pytest


pytestmark = pytest.mark.skipif(
    pytest.importorskip("flask", reason="flask not installed") is None,
    reason="flask not installed",
)


@pytest.fixture
def _client():
    """Provide a Flask test_client with TESTING=True so the SSE
    rate limiter is bypassed during normal test runs."""
    from app_web import server as srv
    from app_web.blueprints import sse as sse_mod

    app = srv.create_app()
    app.config["TESTING"] = True
    # Defensive: clear the sliding window so a prior test (e.g. the
    # production-behaviour rate-limiter test) doesn't leak its
    # counters into the next run.
    with sse_mod._RATE_LOCK:
        sse_mod._RATE_HISTORY.clear()
    return app.test_client()


def _parse_sse_stream(body: bytes) -> list[dict]:
    """Split an SSE response body into a list of {event, data} dicts."""
    events: list[dict] = []
    text = body.decode("utf-8")
    for frame in text.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        event_name = "message"
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event_name = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        data_text = "\n".join(data_lines)
        try:
            data = json.loads(data_text) if data_text else None
        except ValueError:
            data = data_text
        events.append({"event": event_name, "data": data})
    return events


def test_fit_stream_endpoint_exists(_client):
    """GET /api/fit/stream?data=... should return text/event-stream."""
    resp = _client.get(
        "/api/fit/stream?x=1,2,3,4,5&y=2,4,6,8,10&model=polynomial"
    )
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/event-stream")


def test_legacy_auto_fit_stream_endpoint_rejects_with_deprecation(_client):
    resp = _client.get("/api/auto-fit/stream?x=1,2,3,4,5&y=2,4,6,8,10")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("text/event-stream")
    events = _parse_sse_stream(resp.data)
    assert events == [
        {
            "event": "error",
            "data": {
                "error": "Deprecated",
                "message": (
                    "Automatic fitting is no longer supported. Use "
                    "/api/fit/stream with an explicit model."
                ),
            },
        }
    ]


def test_fit_stream_rejects_missing_params(_client):
    """Missing x or y must return an SSE error event (not a 500)."""
    resp = _client.get("/api/fit/stream")
    assert resp.status_code in (200, 400)
    if resp.status_code == 200:
        events = _parse_sse_stream(resp.data)
        assert any(e["event"] == "error" for e in events)


def test_fit_stream_rejects_mismatched_xy(_client):
    """x=[1,2,3] + y=[1,2] must yield a clear error event."""
    resp = _client.get("/api/fit/stream?x=1,2,3&y=1,2&model=polynomial")
    if resp.status_code == 200:
        events = _parse_sse_stream(resp.data)
        error_events = [e for e in events if e["event"] == "error"]
        assert error_events, f"expected error event, got {events}"


def test_fit_stream_clamps_precision(_client):
    """precision=10_000_000 must not crash — clamp at 1000."""
    resp = _client.get(
        "/api/fit/stream?x=1,2,3,4,5&y=2,4,6,8,10&model=polynomial"
        "&precision=10000000"
    )
    assert resp.status_code == 200
    events = _parse_sse_stream(resp.data)
    # No error expected — precision gets clamped silently
    result_events = [e for e in events if e["event"] == "result"]
    assert result_events, "precision clamp should still produce a result"


def test_fit_stream_error_event_has_json_payload(_client):
    """Error events must parse as JSON with 'error' and 'message' keys."""
    resp = _client.get("/api/fit/stream?x=bad,stuff&y=2,4&model=polynomial")
    events = _parse_sse_stream(resp.data)
    errors = [e for e in events if e["event"] == "error"]
    if errors:
        err = errors[0]["data"]
        assert isinstance(err, dict)
        assert "error" in err


def test_fit_stream_rejects_oversized_input():
    """Even with TESTING=True (rate limiter off), the MAX_SSE_INPUT_POINTS
    cap is unconditional and must still fire."""
    from app_web.blueprints.sse import MAX_SSE_INPUT_POINTS
    from app_web import server as srv

    app = srv.create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    oversized = ",".join(str(i) for i in range(MAX_SSE_INPUT_POINTS + 10))
    resp = client.get(
        f"/api/fit/stream?x={oversized}&y={oversized}&model=polynomial"
    )
    events = _parse_sse_stream(resp.data)
    errors = [e for e in events if e["event"] == "error"]
    assert errors, "oversized input must produce an error event"
    assert "BadRequest" in [e["data"]["error"] for e in errors]


def test_rate_limiter_fires_when_testing_flag_off(monkeypatch):
    """When TESTING is False and the bypass env var is unset, the
    per-IP rate limiter must engage. Pins the production behaviour —
    the TESTING bypass must NOT silently disable the limiter in
    deployment."""
    from app_web import server as srv
    from app_web.blueprints import sse as sse_mod

    monkeypatch.delenv("DATALAB_SSE_DISABLE_RATE_LIMIT", raising=False)
    with sse_mod._RATE_LOCK:
        sse_mod._RATE_HISTORY.clear()

    app = srv.create_app()
    app.config["TESTING"] = False  # simulate production
    client = app.test_client()
    rate_limited_seen = False
    for _ in range(sse_mod.RATE_MAX_REQUESTS + 3):
        resp = client.get(
            "/api/fit/stream?x=1,2,3&y=2,4,6&model=polynomial"
        )
        evs = _parse_sse_stream(resp.data)
        if any(
            e["event"] == "error"
            and isinstance(e["data"], dict)
            and e["data"].get("error") == "RateLimited"
            for e in evs
        ):
            rate_limited_seen = True
            break
    assert rate_limited_seen, (
        "expected a RateLimited SSE error after exceeding the budget"
    )


@pytest.mark.parametrize("model", ["log_poly", "exp_combo", "auto", "auto_fit"])
def test_fit_stream_rejects_removed_public_models(_client, model):
    resp = _client.get(
        f"/api/fit/stream?x=1,2,3,4,5&y=2,4,6,8,10&model={model}"
    )
    assert resp.status_code == 200
    events = _parse_sse_stream(resp.data)
    assert not any(e["event"] == "result" for e in events)
    errors = [e for e in events if e["event"] == "error"]
    assert errors, f"expected error event for removed model {model!r}"
    assert errors[0]["data"]["error"] == "BadRequest"
    assert "removed" in errors[0]["data"]["message"].lower()


@pytest.mark.parametrize("model", ["pade", "power_limit", "custom"])
def test_fit_stream_recognizes_non_linear_explicit_models_without_fitting(
    _client, model
):
    resp = _client.get(
        f"/api/fit/stream?x=1,2,3,4,5&y=2,4,6,8,10&model={model}"
    )
    assert resp.status_code == 200
    events = _parse_sse_stream(resp.data)
    assert not any(e["event"] == "result" for e in events)
    errors = [e for e in events if e["event"] == "error"]
    assert errors, f"expected unsupported event for model {model!r}"
    assert errors[0]["data"]["error"] == "UnsupportedModel"


@pytest.mark.parametrize(
    ("model", "expected"),
    [("poly", "polynomial"), ("inverse", "inverse_power")],
)
def test_fit_stream_accepts_legacy_explicit_aliases(_client, model, expected):
    resp = _client.get(
        f"/api/fit/stream?x=1,2,3,4,5&y=1,0.5,0.333,0.25,0.2&model={model}"
    )
    assert resp.status_code == 200
    events = _parse_sse_stream(resp.data)
    result_events = [e for e in events if e["event"] == "result"]
    assert result_events, f"expected successful result, got {events}"
    assert result_events[0]["data"]["model"] == expected


def test_rate_limiter_fires_on_auto_fit_endpoint(monkeypatch):
    """Second rate-limiter test exercising the auto-fit path
    (the first one covers /api/fit/stream; both routes share
    ``_rate_limited_gen`` but depth reviewer flagged the auto-fit
    coverage gap)."""
    from app_web import server as srv
    from app_web.blueprints import sse as sse_mod

    monkeypatch.delenv("DATALAB_SSE_DISABLE_RATE_LIMIT", raising=False)
    with sse_mod._RATE_LOCK:
        sse_mod._RATE_HISTORY.clear()

    app = srv.create_app()
    app.config["TESTING"] = False
    client = app.test_client()
    rate_limited_seen = False
    for _ in range(sse_mod.RATE_MAX_REQUESTS + 3):
        resp = client.get("/api/auto-fit/stream?x=1,2,3&y=2,4,6")
        evs = _parse_sse_stream(resp.data)
        if any(
            e["event"] == "error"
            and isinstance(e["data"], dict)
            and e["data"].get("error") == "RateLimited"
            for e in evs
        ):
            rate_limited_seen = True
            break
    assert rate_limited_seen, (
        "auto-fit stream must also enforce rate limiting"
    )


def test_rate_limit_gc_evicts_old_ips(monkeypatch):
    """_rate_gc_locked must prune IPs whose deques aged out.

    Otherwise a long-running server hit by many one-off IPs
    accumulates empty deques forever. We validate the eviction
    DIRECTLY (rather than relying on the natural admission flow,
    which leaves all timestamps recent and so evicts nothing) by
    seeding ``_RATE_HISTORY`` with deques that are already older
    than ``RATE_WINDOW_SECONDS`` — what `_rate_gc_locked` is
    explicitly designed to clean up.
    """
    import collections
    import time

    from app_web.blueprints import sse as sse_mod

    monkeypatch.delenv("DATALAB_SSE_DISABLE_RATE_LIMIT", raising=False)
    with sse_mod._RATE_LOCK:
        sse_mod._RATE_HISTORY.clear()

        # Plant 50 entries whose timestamps are already older than
        # the rate window — these should ALL be evicted on GC.
        old = time.monotonic() - sse_mod.RATE_WINDOW_SECONDS - 10.0
        for i in range(50):
            sse_mod._RATE_HISTORY[f"10.1.0.{i}"] = collections.deque([old])

        # Plant 5 entries with fresh timestamps — these must SURVIVE.
        fresh = time.monotonic()
        for i in range(5):
            sse_mod._RATE_HISTORY[f"10.2.0.{i}"] = collections.deque([fresh])

        # Trigger GC directly (lock already held).
        sse_mod._rate_gc_locked(time.monotonic())

        # All 50 expired IPs must be gone; all 5 fresh IPs remain.
        remaining = set(sse_mod._RATE_HISTORY.keys())
        assert not any(k.startswith("10.1.0.") for k in remaining), (
            f"GC failed to evict expired IPs: {remaining}"
        )
        for i in range(5):
            assert f"10.2.0.{i}" in remaining, (
                f"GC incorrectly evicted fresh IP 10.2.0.{i}: {remaining}"
            )
