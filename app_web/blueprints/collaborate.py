"""Optional real-time collaboration sessions via flask-socketio.

Scaffolded for Phase 3 Task 3.7. Full wiring into ``app_web/server.py``
is deferred until flask-socketio lands in ``web_requirements.txt``
(the plan notes this). In the interim:

- ``HAS_SOCKETIO`` exports install state.
- ``create_collab_blueprint()`` constructs the Flask Blueprint when
  socketio is present; raises ``ModuleNotFoundError`` otherwise.
- Session state (participant list + last known UI state per session)
  is held in a per-process dict guarded by a lock.

Threat model: anyone with the session URL joins. Sessions are
ephemeral (in-memory) and tied to one Gunicorn/Waitress worker,
so a client reload could land on a different worker with no
session. Real multi-worker collaboration would need Redis, which
is explicitly out of scope.
"""

from __future__ import annotations

import logging
import secrets
import threading
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "HAS_SOCKETIO",
    "CollabSession",
    "SessionRegistry",
    "create_collab_blueprint",
]

_logger = logging.getLogger(__name__)

try:
    from flask import Blueprint, jsonify, request
    from flask_socketio import SocketIO, emit, join_room

    HAS_SOCKETIO = True
except ImportError:
    Blueprint = None  # type: ignore[assignment]
    jsonify = None  # type: ignore[assignment]
    request = None  # type: ignore[assignment]
    SocketIO = None  # type: ignore[assignment]
    emit = None  # type: ignore[assignment]
    join_room = None  # type: ignore[assignment]
    HAS_SOCKETIO = False


@dataclass
class CollabSession:
    """In-memory representation of an active collaboration room."""

    session_id: str
    participants: set[str] = field(default_factory=set)
    shared_state: dict[str, Any] = field(default_factory=dict)


class SessionRegistry:
    """Thread-safe in-memory registry of active sessions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, CollabSession] = {}

    def create(self) -> CollabSession:
        # 128 bits of entropy — enough to resist online guessing while
        # staying short enough for a URL.
        sid = secrets.token_urlsafe(16)
        session = CollabSession(session_id=sid)
        with self._lock:
            self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> CollabSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def join(self, session_id: str, participant: str) -> CollabSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            session.participants.add(participant)
            return session

    def leave(self, session_id: str, participant: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.participants.discard(participant)
            # Auto-delete empty sessions so a long-running process
            # doesn't accumulate dead rooms.
            if not session.participants:
                self._sessions.pop(session_id, None)

    def set_state(self, session_id: str, state: dict[str, Any]) -> bool:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return False
            session.shared_state.update(state)
            return True

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)


def create_collab_blueprint(socketio: Any) -> Any:
    """Construct the collaboration blueprint. Wire with::

        from flask_socketio import SocketIO
        sio = SocketIO(app, cors_allowed_origins='*')
        app.register_blueprint(
            create_collab_blueprint(sio), url_prefix='/collab',
        )
    """
    if not HAS_SOCKETIO:
        raise ModuleNotFoundError(
            "flask-socketio is not installed. Add 'flask-socketio' to "
            "web_requirements.txt to enable collaboration sessions."
        )
    bp = Blueprint("collab", __name__)
    registry = SessionRegistry()

    @bp.route("/session", methods=["POST"])
    def create_session():
        session = registry.create()
        return jsonify({"session_id": session.session_id})

    @bp.route("/session/<session_id>", methods=["GET"])
    def get_session(session_id: str):
        session = registry.get(session_id)
        if session is None:
            return jsonify({"error": "not_found"}), 404
        return jsonify({
            "session_id": session.session_id,
            "participants": sorted(session.participants),
            "shared_state": session.shared_state,
        })

    @socketio.on("join", namespace="/collab")
    def on_join(data):  # noqa: ANN001
        session_id = (data or {}).get("session_id")
        participant = (data or {}).get("participant", "anonymous")
        if not isinstance(session_id, str) or not session_id:
            emit("error", {"code": "missing_session_id"})
            return
        if registry.join(session_id, str(participant)) is None:
            emit("error", {"code": "unknown_session"})
            return
        join_room(session_id)
        emit("joined", {"session_id": session_id, "participant": participant},
             room=session_id)

    @socketio.on("state_update", namespace="/collab")
    def on_state_update(data):  # noqa: ANN001
        session_id = (data or {}).get("session_id")
        patch = (data or {}).get("patch") or {}
        if not isinstance(session_id, str) or not isinstance(patch, dict):
            emit("error", {"code": "malformed_update"})
            return
        if not registry.set_state(session_id, patch):
            emit("error", {"code": "unknown_session"})
            return
        emit("state_update", {"patch": patch}, room=session_id, include_self=False)

    return bp
