from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

import pytest


pytest.importorskip("flask")


@pytest.fixture
def client() -> Any:
    from app_web import server as srv
    from app_web.blueprints import sse as sse_mod

    app = srv.create_app()
    app.config["TESTING"] = True
    with sse_mod._RATE_LOCK:
        sse_mod._RATE_HISTORY.clear()
    return app.test_client()


def _parse_sse_events(body: bytes) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for frame in body.decode("utf-8").split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        event = "message"
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        data_text = "\n".join(data_lines)
        events.append(
            {
                "event": event,
                "data": json.loads(data_text) if data_text else None,
            }
        )
    return events


def test_fit_stream_error_response_uses_sse_headers(client: Any) -> None:
    response = client.get("/api/fit/stream")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    assert response.headers["Cache-Control"] == "no-cache, no-transform"
    assert response.headers["X-Accel-Buffering"] == "no"
    assert response.headers["X-Content-Type-Options"] == "nosniff"

    events = _parse_sse_events(response.data)
    assert events
    assert events[0]["event"] == "error"
    assert events[0]["data"]["error"] == "BadRequest"


@pytest.mark.parametrize("path", ["/api/fit/stream", "/api/auto-fit/stream"])
def test_fit_stream_routes_are_get_only(client: Any, path: str) -> None:
    response = client.post(path)

    assert response.status_code == 405


def test_removed_auto_fit_stream_keeps_deprecation_error_contract(client: Any) -> None:
    response = client.get("/api/auto-fit/stream?x=1,2,3&y=2,4,6")

    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/event-stream")
    events = _parse_sse_events(response.data)
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


def test_sse_no_compute_error_paths_do_not_import_fitting_or_desktop_stack():
    script = """
import sys

from app_web import server as srv
from app_web.blueprints import sse as sse_mod

app = srv.create_app()
app.config["TESTING"] = True
with sse_mod._RATE_LOCK:
    sse_mod._RATE_HISTORY.clear()
client = app.test_client()

for path in (
    "/api/fit/stream",
    "/api/auto-fit/stream?x=1,2,3&y=2,4,6",
):
    response = client.get(path)
    if response.status_code != 200:
        raise SystemExit(f"{path} returned {response.status_code}")
    if not response.headers["Content-Type"].startswith("text/event-stream"):
        raise SystemExit(f"{path} did not return SSE")
    if b"event: error" not in response.data:
        raise SystemExit(f"{path} did not emit an error event")

forbidden_prefixes = (
    "app_desktop",
    "PySide6",
    "matplotlib.pyplot",
    "app_web.logic.error_propagation",
    "app_web.logic.extrapolation",
    "app_web.logic.fitting",
    "app_web.logic.root_solving",
    "app_web.logic.statistics",
    "fitting",
)
forbidden = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
)
if forbidden:
    raise SystemExit("forbidden imports: " + ", ".join(forbidden))
print("ok")
"""
    env = dict(os.environ)
    env["DATALAB_WEB_SECRET"] = "web-sse-no-compute-import-test-secret"

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"
