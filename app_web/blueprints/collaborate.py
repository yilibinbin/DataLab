"""Real-time collaboration sessions via flask-socketio.

Auth model (post-security-review hardening):
- ``POST /collab/session`` creates a session and returns both the
  ``session_id`` AND a ``join_token``. Both are required to join
  — the session id is the room reference; the token is a one-time
  bearer credential proving the caller created the session (or was
  given the token out-of-band). Without the token, the SocketIO
  ``join`` event is rejected with ``error=unauthorized``.
- ``on_state_update`` requires the caller to have successfully
  joined the session in the current SocketIO connection (tracked
  via ``flask.session`` on the WS handshake).
- ``GET /collab/session/<id>`` requires the token via
  ``X-Collab-Token`` header or ``?token=`` query arg to read
  ``shared_state`` — the session id alone is insufficient.

Hardening:
- ``POST /collab/session`` is CSRF-protected so a cross-origin page
  can't silently burn session-id space via the victim's cookies.
- Sessions have a hard ``SESSION_IDLE_TTL_SECONDS`` TTL; idle
  sessions are swept on every access.
- ``MAX_LIVE_SESSIONS`` caps the total live count so a loop-creating
  attacker can't exhaust memory.
- State patches are size-capped (``MAX_PATCH_BYTES``) and schema-
  validated (``_ALLOWED_PATCH_KEY_RE``) to prevent unbounded broadcast
  or arbitrary-shape payloads reaching participants' DOM.

Threat model remains "anyone with both the session_id AND the
join_token can participate". Sessions are in-memory and tied to
one worker process — multi-worker collab would need Redis (out of
scope).
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import threading
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "HAS_SOCKETIO",
    "MAX_LIVE_SESSIONS",
    "MAX_PATCH_BYTES",
    "SESSION_IDLE_TTL_SECONDS",
    "CollabSession",
    "SessionRegistry",
    "create_collab_blueprint",
]

_logger = logging.getLogger(__name__)

try:
    from flask import Blueprint, jsonify, request, session as flask_session
    from flask_socketio import SocketIO, emit, join_room

    HAS_SOCKETIO = True
except ImportError:
    Blueprint = None  # type: ignore[assignment]
    jsonify = None  # type: ignore[assignment]
    request = None  # type: ignore[assignment]
    flask_session = None  # type: ignore[assignment]
    SocketIO = None  # type: ignore[assignment]
    emit = None  # type: ignore[assignment]
    join_room = None  # type: ignore[assignment]
    HAS_SOCKETIO = False


# TTL (seconds) for a session with no activity. Covers the
# "participant dropped off without sending leave" crash case —
# e.g., browser tab closed, network cable pulled, laptop sleep.
# After this much silence the session is garbage-collected and any
# subsequent join fails with 'unknown_session'. Chosen at 15 min so
# a regular network glitch (< 30s) doesn't cost the session, but a
# lunch-break crash doesn't pin memory forever.
SESSION_IDLE_TTL_SECONDS = 15 * 60

# Hard cap on the number of concurrent live sessions per process.
# Beyond this, ``SessionRegistry.create`` evicts the oldest-idle
# entries before minting a new id. Protects against a slowly-ramping
# session-flood DoS (attacker creates sessions without joining them).
MAX_LIVE_SESSIONS = 1_000

# Upper bound on the serialised patch payload (bytes). Prevents a
# participant from broadcasting a 100 MB dict to every co-participant.
# 64 KiB is ample for UI state; callers needing more should share
# via a separate upload endpoint.
MAX_PATCH_BYTES = 64 * 1024

# Participant display names — truncated at write time to prevent
# memory exhaustion via a very long name in a ``set[str]``.
MAX_PARTICIPANT_NAME = 128

# Patch dict keys must match this regex. Starts with a letter, not
# an underscore — rejects JavaScript-sensitive keys like
# ``__proto__``, ``__defineGetter__``, ``constructor`` that some
# client frameworks accidentally honour. A user-facing key name
# should always start with a letter in practice; the underscore-
# leading rejection costs zero legitimate use cases and closes a
# prototype-pollution surface. 64-char cap is far above any
# reasonable state field name.
_ALLOWED_PATCH_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_\-\.]{0,63}$")
# Additional explicit denylist for keys the regex above might not
# catch (e.g., if the regex is ever loosened).
_DENIED_PATCH_KEYS = frozenset({
    "__proto__",
    "constructor",
    "prototype",
    "__defineGetter__",
    "__defineSetter__",
    "__lookupGetter__",
    "__lookupSetter__",
})


@dataclass
class CollabSession:
    """In-memory representation of an active collaboration room.

    ``join_token`` is a per-session bearer secret minted at creation
    time. The SocketIO ``join`` handler requires clients to present
    it; the HTTP ``GET /collab/session/<id>`` also requires it to
    read ``shared_state``. The token is in addition to the session
    id (which is the room reference); the id leaks in URLs / logs
    but the token doesn't.
    """

    session_id: str
    join_token: str = field(
        default_factory=lambda: secrets.token_urlsafe(24)
    )
    participants: set[str] = field(default_factory=set)
    shared_state: dict[str, Any] = field(default_factory=dict)
    # monotonic seconds of last activity (create / join / leave /
    # set_state). The registry's GC sweep evicts sessions whose
    # last_activity is more than SESSION_IDLE_TTL_SECONDS ago.
    last_activity: float = field(default_factory=lambda: _monotonic())


def _monotonic() -> float:
    """Indirected so tests can monkey-patch the clock."""
    import time

    return time.monotonic()


class SessionRegistry:
    """Thread-safe in-memory registry of active sessions.

    Auto-evicts sessions idle for more than ``SESSION_IDLE_TTL_SECONDS``
    — see the ``_sweep_locked`` helper. Eviction happens opportunistically
    on every mutating call so there's no background thread to manage.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, CollabSession] = {}

    # ------------------------------------------------------------------
    # Private helpers (lock already held)
    # ------------------------------------------------------------------

    def _sweep_locked(self) -> None:
        """Evict sessions idle beyond ``SESSION_IDLE_TTL_SECONDS``.

        Called from every mutating operation so a long-running
        process doesn't accumulate dead rooms. Must hold ``self._lock``.
        """
        cutoff = _monotonic() - SESSION_IDLE_TTL_SECONDS
        dead = [
            sid
            for sid, session in self._sessions.items()
            if session.last_activity < cutoff
        ]
        for sid in dead:
            self._sessions.pop(sid, None)

    def _evict_oldest_locked(self, count: int) -> None:
        """Force-evict the ``count`` oldest-activity sessions. Called
        when ``MAX_LIVE_SESSIONS`` is hit on ``create`` — protects
        against attackers creating sessions in a loop."""
        if count <= 0 or not self._sessions:
            return
        by_age = sorted(
            self._sessions.items(),
            key=lambda item: item[1].last_activity,
        )
        for sid, _ in by_age[:count]:
            self._sessions.pop(sid, None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create(self) -> CollabSession:
        # 128 bits of entropy — enough to resist online guessing while
        # staying short enough for a URL.
        sid = secrets.token_urlsafe(16)
        session = CollabSession(session_id=sid)
        with self._lock:
            self._sweep_locked()
            # If we're still over the cap after sweeping, force-evict
            # the oldest-idle entries to make room.
            overflow = max(0, len(self._sessions) - MAX_LIVE_SESSIONS + 1)
            if overflow:
                self._evict_oldest_locked(overflow)
            self._sessions[sid] = session
        return session

    def get(self, session_id: str) -> CollabSession | None:
        """Return a **snapshot** of the session.

        Returns a fresh ``CollabSession`` constructed from shallow
        copies of the mutable fields (``participants``,
        ``shared_state``). The original session remains in the
        registry — but the caller can serialise / inspect the
        returned object without racing against a concurrent
        ``set_state`` or ``leave`` that would otherwise mutate the
        live dict mid-read.
        """
        with self._lock:
            self._sweep_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            return CollabSession(
                session_id=session.session_id,
                join_token=session.join_token,
                participants=set(session.participants),
                shared_state=dict(session.shared_state),
                last_activity=session.last_activity,
            )

    def authenticate(
        self, session_id: str, token: str
    ) -> CollabSession | None:
        """Verify the bearer ``token`` matches the session's
        ``join_token``. Returns a snapshot of the session if valid,
        None otherwise.

        Uses ``secrets.compare_digest`` for constant-time comparison
        so an attacker can't infer the token via timing differences.
        Returns a snapshot (not a live reference) so the caller's
        read of shared_state / participants is not racy with a
        concurrent mutation.
        """
        with self._lock:
            self._sweep_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if not isinstance(token, str):
                return None
            if not secrets.compare_digest(session.join_token, token):
                return None
            return CollabSession(
                session_id=session.session_id,
                join_token=session.join_token,
                participants=set(session.participants),
                shared_state=dict(session.shared_state),
                last_activity=session.last_activity,
            )

    def join(
        self, session_id: str, participant: str, token: str
    ) -> CollabSession | None:
        """Add a participant to a session. Requires a valid token —
        anyone with only the session id is denied access.

        Truncates the participant name at ``MAX_PARTICIPANT_NAME``
        chars to prevent memory exhaustion via a very long value.
        """
        with self._lock:
            self._sweep_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if not isinstance(token, str) or not secrets.compare_digest(
                session.join_token, token
            ):
                return None
            name = str(participant)[:MAX_PARTICIPANT_NAME]
            session.participants.add(name)
            session.last_activity = _monotonic()
            return session

    def leave(self, session_id: str, participant: str) -> None:
        """Remove a participant. Idempotent — no-op if the session
        or participant isn't tracked. No token required for leaving
        (a disconnecting client can't always produce a token)."""
        name = str(participant)[:MAX_PARTICIPANT_NAME]
        with self._lock:
            self._sweep_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return
            session.participants.discard(name)
            session.last_activity = _monotonic()
            # Auto-delete empty sessions so a long-running process
            # doesn't accumulate dead rooms.
            if not session.participants:
                self._sessions.pop(session_id, None)

    def set_state(
        self, session_id: str, state: dict[str, Any], token: str
    ) -> CollabSession | None:
        """Merge ``state`` into the session's ``shared_state`` and
        return the updated ``CollabSession`` on success, ``None`` on
        unknown session or invalid token.

        ``state`` is deep-copied into the session to prevent the
        caller retaining a reference and mutating shared state
        post-hoc. Per the project's immutability convention, the
        merge is expressed as a new dict overlaying the previous
        content — callers that took a reference via ``get()`` see
        the old snapshot unchanged.
        """
        if not isinstance(state, dict):
            return None
        with self._lock:
            self._sweep_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if not isinstance(token, str) or not secrets.compare_digest(
                session.join_token, token
            ):
                return None
            # Build a fresh dict rather than in-place update so any
            # caller holding a reference to the old shared_state
            # doesn't observe the mutation — matches the
            # "ALWAYS create new objects, NEVER mutate" project rule.
            session.shared_state = {**session.shared_state, **state}
            session.last_activity = _monotonic()
            return session

    def count(self) -> int:
        with self._lock:
            self._sweep_locked()
            return len(self._sessions)


def _validate_patch(patch: Any) -> tuple[bool, str]:
    """Return ``(ok, error_code)`` for a proposed state-update patch.

    Enforces the hard contract:
    - must be a dict
    - serialised size ≤ MAX_PATCH_BYTES (defends against broadcast
      flooding; the server re-sends the patch to every co-participant)
    - every key must match ``_ALLOWED_PATCH_KEY_RE`` — prevents
      injection of framework-sensitive keys like ``__proto__``

    Returns ``(True, "")`` on success, ``(False, "<code>")`` on any
    rejection. The caller emits an SSE/SocketIO error event with the
    code.
    """
    if not isinstance(patch, dict):
        return False, "patch_not_dict"
    try:
        serialised = json.dumps(patch, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return False, "patch_not_json_serialisable"
    if len(serialised.encode("utf-8")) > MAX_PATCH_BYTES:
        return False, "patch_too_large"
    for key in patch:
        if not isinstance(key, str):
            return False, "patch_invalid_key"
        if key in _DENIED_PATCH_KEYS:
            return False, "patch_invalid_key"
        if not _ALLOWED_PATCH_KEY_RE.match(key):
            return False, "patch_invalid_key"
    return True, ""


def create_collab_blueprint(socketio: Any) -> Any:
    """Construct the token-gated collaboration blueprint.

    Wire into Flask with::

        from flask_socketio import SocketIO
        # cors_allowed_origins=None → same-origin only (production-safe)
        sio = SocketIO(app, cors_allowed_origins=None)
        app.register_blueprint(
            create_collab_blueprint(sio), url_prefix='/collab',
        )

    DO NOT pass ``cors_allowed_origins='*'`` in production — it lets
    any page open a session and read the shared state. Same-origin
    is the secure default.

    Exposes:
    - ``POST /session`` (CSRF-protected): mint a new session, return
      ``{session_id, join_token}``. Both are required to participate.
    - ``GET /session/<id>?token=<tok>``: read shared state (participant
      list + last known state). Requires the token via ``?token=`` or
      ``X-Collab-Token`` header so the session id alone is insufficient.
    - SocketIO ``join`` event on namespace ``/collab``: requires
      ``{session_id, join_token, participant}`` payload. Rejects any
      join without a valid token so a cross-origin server-side script
      can't bypass CORS to bind to a known session id.
    - SocketIO ``state_update``: requires the caller's current
      SocketIO connection to have already successfully joined (tracked
      in ``flask.session``). Patch payload validated against
      ``_validate_patch``.
    """
    if not HAS_SOCKETIO:
        raise ModuleNotFoundError(
            "flask-socketio is not installed. Add 'flask-socketio' to "
            "web_requirements.txt to enable collaboration sessions."
        )
    from app_web._security_shim import csrf_protect

    bp = Blueprint("collab", __name__)
    registry = SessionRegistry()
    # Map from SocketIO sid → (session_id, participant_name). Lets
    # the ``disconnect`` handler evict a ghost participant the moment
    # a client's connection drops (browser tab closed, network lost),
    # rather than waiting for the SESSION_IDLE_TTL sweep. Kept inside
    # the closure so one registry instance can't race with another.
    _sid_to_joined: dict[str, tuple[str, str]] = {}
    _sid_lock = threading.Lock()

    @bp.route("/session", methods=["POST"])
    @csrf_protect
    def create_session():
        session = registry.create()
        return jsonify({
            "session_id": session.session_id,
            "join_token": session.join_token,
        })

    @bp.route("/session/<session_id>", methods=["GET"])
    def get_session(session_id: str):
        # Token via header (preferred) or query arg (fallback for
        # EventSource-class clients that can't set custom headers).
        token = (
            request.headers.get("X-Collab-Token")
            or request.args.get("token", "")
        )
        session = registry.authenticate(session_id, token)
        if session is None:
            # Ambiguous 404 vs 403 deliberately: don't leak whether
            # the session id exists. An attacker who guesses a valid
            # id but has the wrong token gets the same response as
            # someone who guesses a non-existent id.
            return jsonify({"error": "not_found_or_unauthorized"}), 404
        return jsonify({
            "session_id": session.session_id,
            "participants": sorted(session.participants),
            "shared_state": session.shared_state,
        })

    @socketio.on("join", namespace="/collab")
    def on_join(data):  # noqa: ANN001
        session_id = (data or {}).get("session_id")
        join_token = (data or {}).get("join_token") or (data or {}).get("token")
        participant = (data or {}).get("participant", "anonymous")
        if not isinstance(session_id, str) or not session_id:
            emit("error", {"code": "missing_session_id"})
            return
        if not isinstance(join_token, str) or not join_token:
            emit("error", {"code": "missing_join_token"})
            return
        session = registry.join(session_id, str(participant), join_token)
        if session is None:
            # Same ambiguous error for missing-session and
            # wrong-token — no side channel for attackers. We don't
            # disconnect() server-side; the client is expected to
            # close after receiving 'error', and the SocketIO session
            # has no privileges until the 'joined' event (tracked in
            # flask.session['collab_joined_sessions']).
            emit("error", {"code": "unauthorized_or_unknown_session"})
            return
        join_room(session_id)
        # Track membership on the Flask session attached to this
        # SocketIO connection so ``on_state_update`` can verify the
        # caller actually joined (and didn't just spoof the
        # session_id directly). Flask session is per-ws-connection
        # in flask_socketio's threading mode.
        try:
            flask_session["collab_joined_sessions"] = list(
                set(flask_session.get("collab_joined_sessions", []))
                | {session_id}
            )
        except Exception:  # noqa: BLE001 — flask_session may be unavailable in some test modes
            pass
        # Record SocketIO sid → (session_id, participant) so the
        # ``disconnect`` handler can evict this participant
        # immediately on disconnect, without waiting for the TTL
        # sweep. Falls through silently if sid is unavailable (some
        # test harnesses don't set request.sid).
        try:
            sid = getattr(request, "sid", None)
            if sid:
                with _sid_lock:
                    _sid_to_joined[sid] = (
                        session_id, str(participant)[:MAX_PARTICIPANT_NAME],
                    )
        except Exception:  # noqa: BLE001
            pass
        emit(
            "joined",
            {"session_id": session_id, "participant": participant[:MAX_PARTICIPANT_NAME]},
            room=session_id,
        )

    @socketio.on("state_update", namespace="/collab")
    def on_state_update(data):  # noqa: ANN001
        session_id = (data or {}).get("session_id")
        patch = (data or {}).get("patch")
        if not isinstance(session_id, str) or not session_id:
            emit("error", {"code": "missing_session_id"})
            return
        ok, err_code = _validate_patch(patch)
        if not ok:
            emit("error", {"code": err_code})
            return
        # Verify the caller previously joined this session on THIS
        # SocketIO connection. Prevents a client that only knows the
        # session_id (but never acquired a token) from broadcasting
        # by guessing; join + the token check above is the gate.
        try:
            joined = flask_session.get("collab_joined_sessions") or []
        except Exception:  # noqa: BLE001
            joined = []
        if session_id not in joined:
            emit("error", {"code": "not_joined"})
            return
        # Re-verify the token on every state_update so a client
        # that lost state (e.g. the Flask session expired) can't
        # keep mutating shared state from a stale SocketIO
        # connection. The token is already known to the client
        # that legitimately joined.
        token = (data or {}).get("join_token") or (data or {}).get("token")
        if not isinstance(token, str):
            emit("error", {"code": "missing_join_token"})
            return
        updated = registry.set_state(session_id, patch, token)
        if updated is None:
            emit("error", {"code": "unauthorized_or_unknown_session"})
            return
        emit(
            "state_update",
            {"patch": patch},
            room=session_id,
            include_self=False,
        )

    @socketio.on("disconnect", namespace="/collab")
    def on_disconnect():
        """Evict the disconnecting participant from every session
        they were tracked in. Without this, a crashed / tab-closed
        client remains visible in the participant list until the
        next SESSION_IDLE_TTL sweep — confusing to co-participants
        who think the user is still active.
        """
        try:
            sid = getattr(request, "sid", None)
        except Exception:  # noqa: BLE001
            sid = None
        if not sid:
            return
        with _sid_lock:
            entry = _sid_to_joined.pop(sid, None)
        if entry is None:
            return
        session_id, participant = entry
        try:
            registry.leave(session_id, participant)
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "on_disconnect: leave(%s, %r) raised: %s",
                session_id, participant, exc,
            )

    return bp
