"""#17 Collaboration — wired blueprint integration tests.

Verifies the full stack: create_app_with_socketio wires the collab
blueprint at /collab/*, the SocketIO test client can join sessions,
and broadcast state updates reach other clients.
"""

from __future__ import annotations

import pytest

# These tests require flask-socketio; skip the whole module when absent.
pytest.importorskip("flask_socketio")


@pytest.fixture
def _app_and_sio(monkeypatch):
    """Build a Flask app + SocketIO instance via the production
    factory, without touching the real ``DATALAB_WEB_SECRET``."""
    monkeypatch.setenv("DATALAB_WEB_SECRET", "test-only-secret-do-not-use")
    from app_web.server import create_app_with_socketio

    app, socketio = create_app_with_socketio()
    yield app, socketio


def test_create_app_with_socketio_returns_pair(_app_and_sio):
    app, sio = _app_and_sio
    assert app is not None
    assert sio is not None
    # SocketIO must be retrievable via app.extensions for tests +
    # health checks.
    assert "socketio" in app.extensions
    assert app.extensions["socketio"] is sio


def test_collab_session_endpoint_is_registered(_app_and_sio):
    """POST /collab/session must return 200 + {session_id: "..."}."""
    app, _ = _app_and_sio
    client = app.test_client()
    resp = client.post("/collab/session")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "session_id" in data
    assert isinstance(data["session_id"], str)
    # URL-safe base64 chars only
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    )
    assert all(c in allowed for c in data["session_id"])


def test_collab_session_get_returns_404_for_unknown(_app_and_sio):
    app, _ = _app_and_sio
    client = app.test_client()
    resp = client.get("/collab/session/no-such-session")
    assert resp.status_code == 404


def test_collab_session_get_returns_shape_for_known(_app_and_sio):
    app, _ = _app_and_sio
    client = app.test_client()
    created = client.post("/collab/session").get_json()
    sid = created["session_id"]
    resp = client.get(f"/collab/session/{sid}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["session_id"] == sid
    assert "participants" in data
    assert "shared_state" in data


def test_socketio_client_can_join_session(_app_and_sio):
    """Emulate a client calling socket.emit('join') over the
    /collab namespace. Server must respond with a 'joined' event."""
    app, sio = _app_and_sio
    http = app.test_client()
    session_id = http.post("/collab/session").get_json()["session_id"]

    # flask_socketio's test_client supports namespaces as of 5.x.
    client = sio.test_client(app, namespace="/collab")
    client.emit(
        "join",
        {"session_id": session_id, "participant": "alice"},
        namespace="/collab",
    )
    received = client.get_received(namespace="/collab")
    names = [e["name"] for e in received]
    assert "joined" in names, f"expected 'joined' event, got {received}"


def test_socketio_client_receives_error_on_unknown_session(_app_and_sio):
    app, sio = _app_and_sio
    client = sio.test_client(app, namespace="/collab")
    client.emit(
        "join",
        {"session_id": "bogus-id", "participant": "alice"},
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
    session_id = http.post("/collab/session").get_json()["session_id"]

    client_a = sio.test_client(app, namespace="/collab")
    client_b = sio.test_client(app, namespace="/collab")

    # Both join
    client_a.emit(
        "join",
        {"session_id": session_id, "participant": "alice"},
        namespace="/collab",
    )
    client_b.emit(
        "join",
        {"session_id": session_id, "participant": "bob"},
        namespace="/collab",
    )
    # Drain pending events on both
    client_a.get_received(namespace="/collab")
    client_b.get_received(namespace="/collab")

    # Client A sends a state update
    client_a.emit(
        "state_update",
        {"session_id": session_id, "patch": {"dpi": 300}},
        namespace="/collab",
    )

    # B must receive it
    events_b = client_b.get_received(namespace="/collab")
    update_events_b = [e for e in events_b if e["name"] == "state_update"]
    assert update_events_b, f"Client B missed broadcast: {events_b}"
    assert update_events_b[0]["args"][0]["patch"] == {"dpi": 300}

    # A must NOT echo back (include_self=False in the server)
    events_a = client_a.get_received(namespace="/collab")
    update_events_a = [e for e in events_a if e["name"] == "state_update"]
    assert not update_events_a, (
        f"Client A saw its own broadcast (expected include_self=False): {events_a}"
    )


def test_state_update_rejects_malformed_payload(_app_and_sio):
    app, sio = _app_and_sio
    http = app.test_client()
    session_id = http.post("/collab/session").get_json()["session_id"]

    client = sio.test_client(app, namespace="/collab")
    client.emit(
        "join",
        {"session_id": session_id, "participant": "alice"},
        namespace="/collab",
    )
    client.get_received(namespace="/collab")

    # Missing session_id
    client.emit(
        "state_update",
        {"patch": {"dpi": 300}},
        namespace="/collab",
    )
    received = client.get_received(namespace="/collab")
    names = [e["name"] for e in received]
    assert "error" in names


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
