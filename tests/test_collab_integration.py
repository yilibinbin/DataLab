"""#17 Collaboration — wired blueprint integration tests.

Verifies the full stack: create_app_with_socketio wires the collab
blueprint at /collab/*, the SocketIO test client can join sessions,
and broadcast state updates reach other clients.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

# These tests require flask-socketio; skip the whole module when absent.
pytest.importorskip("flask_socketio")


@pytest.fixture
def _app_and_sio(monkeypatch):
    """Build a Flask app + SocketIO instance via the production
    factory. Enables TESTING so CSRF is relaxed (otherwise every
    POST would need a pre-flight CSRF token); keeps all other
    security on so the token-gated collab path is exercised."""
    monkeypatch.setenv("DATALAB_WEB_SECRET", "test-only-secret-do-not-use")
    from app_web.server import create_app_with_socketio

    app, socketio = create_app_with_socketio()
    app.config["TESTING"] = True
    # Flask-WTF-style CSRF is handled by our custom decorator; TESTING
    # alone doesn't bypass it, so send a valid token with every POST.
    yield app, socketio


def _post_with_csrf(client, path, app):
    """Helper: POST through the client with a server-minted CSRF
    token. Issues a GET first to seed the session cookie, extracts
    the token via the context-processor helper, and replays the
    POST with the ``X-CSRF-Token`` header set."""

    # Seed session cookie
    client.get("/")
    # Request a fresh CSRF token. Must be inside an app context.
    with app.test_request_context():
        with client.session_transaction() as sess:
            # Pre-set the token on the session so the server
            # validation compares the same value.
            from app_web.security import generate_csrf_token
            token = generate_csrf_token()
            sess["csrf_token"] = token
    return client.post(path, headers={"X-CSRF-Token": token})


def test_create_app_with_socketio_returns_pair(_app_and_sio):
    app, sio = _app_and_sio
    assert app is not None
    assert sio is not None
    # SocketIO must be retrievable via app.extensions for tests +
    # health checks.
    assert "socketio" in app.extensions
    assert app.extensions["socketio"] is sio


def test_create_app_with_socketio_does_not_eagerly_import_desktop_or_compute_stack():
    script = """
import sys

from app_web.server import create_app_with_socketio

app, socketio = create_app_with_socketio()
if app is None or socketio is None:
    raise SystemExit("create_app_with_socketio returned an empty pair")
if app.extensions.get("socketio") is not socketio:
    raise SystemExit("socketio extension was not registered")

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
    env["DATALAB_WEB_SECRET"] = "collab-startup-import-test-secret"

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"


def test_collab_session_endpoint_is_registered(_app_and_sio):
    """POST /collab/session (with CSRF) must return
    {session_id, join_token}. The token is new in the
    security-hardened design."""
    app, _ = _app_and_sio
    client = app.test_client()
    resp = _post_with_csrf(client, "/collab/session", app)
    assert resp.status_code == 200, (
        f"expected 200, got {resp.status_code}: {resp.data[:200]!r}"
    )
    data = resp.get_json()
    assert "session_id" in data
    assert isinstance(data["session_id"], str)
    assert "join_token" in data
    assert isinstance(data["join_token"], str)
    # Both should be URL-safe base64 chars only
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    )
    assert all(c in allowed for c in data["session_id"])
    assert all(c in allowed for c in data["join_token"])
    # Token must be at least 128 bits of entropy — url-safe base64
    # of 24 raw bytes = 32 chars.
    assert len(data["join_token"]) >= 32


def test_create_session_requires_csrf_token(_app_and_sio):
    """POST without a CSRF token must fail (400). Previously, the
    endpoint silently accepted any POST — that was a CSRF hole
    flagged in the security review."""
    app, _ = _app_and_sio
    client = app.test_client()
    resp = client.post("/collab/session")  # no CSRF token
    assert resp.status_code == 400


def test_collab_session_get_returns_404_for_unknown(_app_and_sio):
    app, _ = _app_and_sio
    client = app.test_client()
    resp = client.get("/collab/session/no-such-session")
    assert resp.status_code == 404


def test_collab_session_get_requires_token(_app_and_sio):
    """GET without a token returns 404 (deliberately ambiguous —
    doesn't leak whether the session id exists)."""
    app, _ = _app_and_sio
    client = app.test_client()
    created = _post_with_csrf(client, "/collab/session", app).get_json()
    sid = created["session_id"]
    # GET without token
    resp = client.get(f"/collab/session/{sid}")
    assert resp.status_code == 404, (
        "GET without token must return 404 (not leak that the id "
        "exists) — got " f"{resp.status_code}"
    )


def test_collab_session_get_accepts_token_via_header(_app_and_sio):
    app, _ = _app_and_sio
    client = app.test_client()
    created = _post_with_csrf(client, "/collab/session", app).get_json()
    sid = created["session_id"]
    tok = created["join_token"]
    resp = client.get(
        f"/collab/session/{sid}",
        headers={"X-Collab-Token": tok},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["session_id"] == sid
    assert "participants" in data
    assert "shared_state" in data
    # Critical: the session-snapshot view must NEVER echo the
    # join_token back to the client. The token is a bearer secret
    # shared OOB; if it leaked into a JSON response, any page that
    # could read the response (e.g. via a misconfigured CORS) would
    # gain full session access. Pinning this so a future refactor
    # that does ``**session.__dict__`` accidentally doesn't
    # regress security.
    assert "join_token" not in data


def test_collab_session_get_accepts_token_via_query(_app_and_sio):
    app, _ = _app_and_sio
    client = app.test_client()
    created = _post_with_csrf(client, "/collab/session", app).get_json()
    sid = created["session_id"]
    tok = created["join_token"]
    resp = client.get(f"/collab/session/{sid}?token={tok}")
    assert resp.status_code == 200
    # Same security pin as above — query-arg flavour also must not
    # echo the token in the response body.
    assert "join_token" not in resp.get_json()


def test_collab_session_get_rejects_wrong_token(_app_and_sio):
    app, _ = _app_and_sio
    client = app.test_client()
    created = _post_with_csrf(client, "/collab/session", app).get_json()
    sid = created["session_id"]
    resp = client.get(f"/collab/session/{sid}?token=bogus")
    assert resp.status_code == 404


def test_socketio_client_can_join_session(_app_and_sio):
    """Emulate a client calling socket.emit('join') with the
    join_token. Server must respond with a 'joined' event."""
    app, sio = _app_and_sio
    http = app.test_client()
    created = _post_with_csrf(http, "/collab/session", app).get_json()
    sid = created["session_id"]
    tok = created["join_token"]

    client = sio.test_client(app, namespace="/collab")
    client.emit(
        "join",
        {"session_id": sid, "join_token": tok, "participant": "alice"},
        namespace="/collab",
    )
    received = client.get_received(namespace="/collab")
    names = [e["name"] for e in received]
    assert "joined" in names, f"expected 'joined' event, got {received}"


def test_socketio_client_join_without_token_rejected(_app_and_sio):
    """Token-less join must fail with error event (CRITICAL fix for
    the SocketIO CSRF-bypass flagged in the security review)."""
    app, sio = _app_and_sio
    http = app.test_client()
    created = _post_with_csrf(http, "/collab/session", app).get_json()
    sid = created["session_id"]
    client = sio.test_client(app, namespace="/collab")
    client.emit(
        "join",
        {"session_id": sid, "participant": "alice"},  # no token
        namespace="/collab",
    )
    received = client.get_received(namespace="/collab")
    names = [e["name"] for e in received]
    assert "error" in names
    # Extract error code
    err_events = [e for e in received if e["name"] == "error"]
    assert any(
        (e["args"] and e["args"][0].get("code") == "missing_join_token")
        for e in err_events
    )


def test_socketio_client_join_wrong_token_rejected(_app_and_sio):
    app, sio = _app_and_sio
    http = app.test_client()
    created = _post_with_csrf(http, "/collab/session", app).get_json()
    sid = created["session_id"]
    client = sio.test_client(app, namespace="/collab")
    client.emit(
        "join",
        {
            "session_id": sid,
            "join_token": "bogus",
            "participant": "alice",
        },
        namespace="/collab",
    )
    received = client.get_received(namespace="/collab")
    err_events = [e for e in received if e["name"] == "error"]
    assert err_events


def test_socketio_client_receives_error_on_unknown_session(_app_and_sio):
    app, sio = _app_and_sio
    client = sio.test_client(app, namespace="/collab")
    client.emit(
        "join",
        {
            "session_id": "bogus-id",
            "join_token": "bogus-token",
            "participant": "alice",
        },
        namespace="/collab",
    )
    received = client.get_received(namespace="/collab")
    names = [e["name"] for e in received]
    assert "error" in names


def test_state_update_broadcasts_to_other_participants(_app_and_sio):
    """Two clients in the same session; a state update from client A
    must reach client B but not echo back to A."""
    app, sio = _app_and_sio
    http = app.test_client()
    created = _post_with_csrf(http, "/collab/session", app).get_json()
    sid = created["session_id"]
    tok = created["join_token"]

    client_a = sio.test_client(app, namespace="/collab")
    client_b = sio.test_client(app, namespace="/collab")

    for c, name in ((client_a, "alice"), (client_b, "bob")):
        c.emit(
            "join",
            {"session_id": sid, "join_token": tok, "participant": name},
            namespace="/collab",
        )
        c.get_received(namespace="/collab")

    # Client A sends a state update
    client_a.emit(
        "state_update",
        {
            "session_id": sid,
            "join_token": tok,
            "patch": {"dpi": 300},
        },
        namespace="/collab",
    )

    events_b = client_b.get_received(namespace="/collab")
    update_events_b = [e for e in events_b if e["name"] == "state_update"]
    assert update_events_b, f"Client B missed broadcast: {events_b}"
    assert update_events_b[0]["args"][0]["patch"] == {"dpi": 300}

    events_a = client_a.get_received(namespace="/collab")
    update_events_a = [e for e in events_a if e["name"] == "state_update"]
    assert not update_events_a, (
        f"Client A saw its own broadcast (expected include_self=False): {events_a}"
    )


def test_state_update_rejects_malformed_payload(_app_and_sio):
    app, sio = _app_and_sio
    http = app.test_client()
    created = _post_with_csrf(http, "/collab/session", app).get_json()
    sid = created["session_id"]
    tok = created["join_token"]

    client = sio.test_client(app, namespace="/collab")
    client.emit(
        "join",
        {"session_id": sid, "join_token": tok, "participant": "alice"},
        namespace="/collab",
    )
    client.get_received(namespace="/collab")

    # Missing session_id
    client.emit(
        "state_update",
        {"patch": {"dpi": 300}, "join_token": tok},
        namespace="/collab",
    )
    received = client.get_received(namespace="/collab")
    names = [e["name"] for e in received]
    assert "error" in names


def test_state_update_oversized_patch_rejected(_app_and_sio):
    """MAX_PATCH_BYTES=64KiB cap prevents broadcast flooding."""
    app, sio = _app_and_sio
    from app_web.blueprints.collaborate import MAX_PATCH_BYTES

    http = app.test_client()
    created = _post_with_csrf(http, "/collab/session", app).get_json()
    sid = created["session_id"]
    tok = created["join_token"]

    client = sio.test_client(app, namespace="/collab")
    client.emit(
        "join",
        {"session_id": sid, "join_token": tok, "participant": "alice"},
        namespace="/collab",
    )
    client.get_received(namespace="/collab")

    oversized = {"payload": "x" * (MAX_PATCH_BYTES + 1000)}
    client.emit(
        "state_update",
        {"session_id": sid, "join_token": tok, "patch": oversized},
        namespace="/collab",
    )
    received = client.get_received(namespace="/collab")
    err = [e for e in received if e["name"] == "error"]
    assert err
    assert any(
        e["args"][0].get("code") == "patch_too_large" for e in err
    )


def test_state_update_rejects_dangerous_key(_app_and_sio):
    """Keys must match _ALLOWED_PATCH_KEY_RE — defends against
    framework-sensitive names reaching participants' clients."""
    app, sio = _app_and_sio
    http = app.test_client()
    created = _post_with_csrf(http, "/collab/session", app).get_json()
    sid = created["session_id"]
    tok = created["join_token"]

    client = sio.test_client(app, namespace="/collab")
    client.emit(
        "join",
        {"session_id": sid, "join_token": tok, "participant": "alice"},
        namespace="/collab",
    )
    client.get_received(namespace="/collab")

    client.emit(
        "state_update",
        {
            "session_id": sid,
            "join_token": tok,
            "patch": {"__proto__": "evil"},
        },
        namespace="/collab",
    )
    received = client.get_received(namespace="/collab")
    err = [e for e in received if e["name"] == "error"]
    assert err
    assert any(
        e["args"][0].get("code") == "patch_invalid_key" for e in err
    )


def test_collab_js_module_is_served(_app_and_sio):
    """Verify the client JS is served under static/."""
    app, _ = _app_and_sio
    client = app.test_client()
    resp = client.get("/static/js/collab.js")
    assert resp.status_code == 200
    body = resp.data.decode("utf-8")
    for needle in ("DATALAB_COLLAB", "createSession", "joinSession", "sendStateUpdate"):
        assert needle in body, f"collab.js missing {needle}"


def test_create_app_still_works_without_socketio(monkeypatch):
    """``create_app()`` must remain callable without the SocketIO
    path — single-frontend deploys that don't install flask-socketio
    should keep working."""
    monkeypatch.setenv("DATALAB_WEB_SECRET", "test-only-secret")
    from app_web.server import create_app

    app = create_app()
    assert app is not None
    # /collab blueprint must NOT be registered on the plain app
    client = app.test_client()
    resp = client.post("/collab/session")
    assert resp.status_code == 404, (
        "plain create_app() must not register /collab — that's the "
        "create_app_with_socketio() path's job"
    )
