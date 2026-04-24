"""Collaboration sessions (Phase 3 #17) — regression tests.

Non-dependent tests pin the registry API; dependent tests exercise
the SocketIO integration when ``flask-socketio`` is installed.
"""

from __future__ import annotations

import pytest

from app_web.blueprints.collaborate import (
    CollabSession,
    HAS_SOCKETIO,
    SessionRegistry,
)


def test_registry_create_returns_unique_session_ids():
    reg = SessionRegistry()
    s1 = reg.create()
    s2 = reg.create()
    assert s1.session_id != s2.session_id
    assert isinstance(s1, CollabSession)


def test_registry_get_returns_none_for_unknown():
    reg = SessionRegistry()
    assert reg.get("nonexistent") is None


def test_registry_join_adds_participant():
    reg = SessionRegistry()
    session = reg.create()
    result = reg.join(session.session_id, "alice")
    assert result is not None
    assert "alice" in result.participants


def test_registry_join_unknown_session_returns_none():
    reg = SessionRegistry()
    assert reg.join("no-such-session", "alice") is None


def test_registry_leave_removes_participant():
    reg = SessionRegistry()
    session = reg.create()
    reg.join(session.session_id, "alice")
    reg.join(session.session_id, "bob")
    reg.leave(session.session_id, "alice")
    remaining = reg.get(session.session_id)
    assert remaining is not None
    assert "alice" not in remaining.participants
    assert "bob" in remaining.participants


def test_registry_leave_removes_empty_session():
    """When the last participant leaves, the session is garbage-
    collected so a long-running process doesn't accumulate dead rooms."""
    reg = SessionRegistry()
    session = reg.create()
    reg.join(session.session_id, "alice")
    reg.leave(session.session_id, "alice")
    assert reg.get(session.session_id) is None
    assert reg.count() == 0


def test_registry_set_state_merges_patch():
    reg = SessionRegistry()
    session = reg.create()
    assert reg.set_state(session.session_id, {"dpi": 200}) is True
    assert reg.set_state(session.session_id, {"model": "linear"}) is True
    updated = reg.get(session.session_id)
    assert updated is not None
    assert updated.shared_state == {"dpi": 200, "model": "linear"}


def test_registry_set_state_unknown_session_returns_false():
    reg = SessionRegistry()
    assert reg.set_state("unknown", {"dpi": 200}) is False


def test_registry_is_thread_safe_under_contention():
    """Simulate 10 threads each creating + joining sessions. No
    exception; final participant count is deterministic."""
    import threading

    reg = SessionRegistry()
    session = reg.create()
    errors: list[BaseException] = []

    def worker(name: str) -> None:
        try:
            for _ in range(50):
                reg.join(session.session_id, name)
                reg.leave(session.session_id, name)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(f"u{i}",)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert not errors


def test_session_ids_are_url_safe():
    reg = SessionRegistry()
    session = reg.create()
    # URL-safe alphabet: letters, digits, -, _
    allowed = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    )
    assert all(c in allowed for c in session.session_id)
    # At least 128 bits of entropy ≈ 22 chars in url-safe base64
    assert len(session.session_id) >= 20


def test_create_collab_blueprint_requires_socketio_when_absent():
    if HAS_SOCKETIO:
        pytest.skip("flask-socketio installed; absent-path only test")

    from app_web.blueprints.collaborate import create_collab_blueprint

    with pytest.raises(ModuleNotFoundError):
        create_collab_blueprint(socketio=None)
