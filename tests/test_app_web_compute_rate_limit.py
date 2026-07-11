"""The heavy compute POST routes must be per-IP rate limited (audit A2).

Each compute route runs an mpmath computation while holding a process-global serial lock, so an
attacker hammering them can starve legitimate users. A blueprint before_request throttles POST
(reusing the SSE sliding-window limiter); GET (cheap form render) is never throttled.
"""

from __future__ import annotations

import pytest

pytest.importorskip("flask")


def _app_with_active_limiter(monkeypatch):
    # The limiter is a no-op under TESTING / the disable env var — turn both off so the throttle is
    # actually exercised, and reset the shared window so the test is order-independent.
    monkeypatch.delenv("DATALAB_SSE_DISABLE_RATE_LIMIT", raising=False)
    monkeypatch.setenv("DATALAB_DEBUG", "1")
    from app_web.server import create_app
    import app_web.blueprints.sse as sse

    sse._RATE_HISTORY.clear()
    app = create_app()
    app.config["TESTING"] = False
    return app, sse


def test_compute_post_is_rate_limited(monkeypatch):
    app, sse = _app_with_active_limiter(monkeypatch)
    client = app.test_client()
    codes = [client.post("/", data={}).status_code for _ in range(sse.RATE_MAX_REQUESTS + 5)]
    assert 429 in codes, "compute POST route was never rate-limited"
    # The first RATE_MAX_REQUESTS are admitted (whatever their handler status), then 429 kicks in.
    assert codes[sse.RATE_MAX_REQUESTS] == 429


def test_get_form_render_is_not_rate_limited(monkeypatch):
    app, sse = _app_with_active_limiter(monkeypatch)
    client = app.test_client()
    codes = [client.get("/").status_code for _ in range(sse.RATE_MAX_REQUESTS + 5)]
    assert 429 not in codes, "GET form render must not be throttled"


def test_limiter_is_bypassed_under_testing(monkeypatch):
    # Regression guard: the normal test suite (TESTING=True) must not be throttled.
    monkeypatch.delenv("DATALAB_SSE_DISABLE_RATE_LIMIT", raising=False)
    monkeypatch.setenv("DATALAB_DEBUG", "1")
    from app_web.server import create_app
    import app_web.blueprints.sse as sse

    sse._RATE_HISTORY.clear()
    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    codes = [client.post("/", data={}).status_code for _ in range(sse.RATE_MAX_REQUESTS + 5)]
    assert 429 not in codes
