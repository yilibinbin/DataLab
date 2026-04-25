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
- State patches are size-capped (``MAX_PATCH_BYTES``) and recursively
  schema-validated (every nested key must match
  ``_ALLOWED_PATCH_KEY_RE``) to prevent unbounded broadcast,
  arbitrary-shape payloads reaching participants' DOM, or nested
  prototype-pollution keys (``__proto__`` hidden one level deep).
- Per-session ``shared_state`` is capped at ``MAX_SHARED_STATE_BYTES``
  so accumulating small patches can't grow without bound.
- Snapshots returned by ``get`` / ``authenticate`` are produced via
  ``copy.deepcopy`` so a caller iterating nested dicts/lists can't
  observe a concurrent ``set_state`` mutating shared inner objects.
- Participant names are tracked as ``dict[name → refcount]`` so two
  live sockets with the same display name don't share a single
  participant slot (and one disconnect doesn't evict the other).
- Each SocketIO sid maps to a ``set[(session_id, participant_name)]``
  so a socket that joins multiple sessions has every membership
  cleaned up on ``disconnect``.

Threat model remains "anyone with both the session_id AND the
join_token can participate". Sessions are in-memory and tied to
one worker process — multi-worker collab would need Redis (out of
scope).
"""

from __future__ import annotations

import copy
import json
import logging
import math
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "HAS_SOCKETIO",
    "MAX_LIVE_SESSIONS",
    "MAX_PARTICIPANT_NAME",
    "MAX_PATCH_BYTES",
    "MAX_PATCH_DEPTH",
    "MAX_SHARED_STATE_BYTES",
    "SESSION_IDLE_TTL_SECONDS",
    "CollabSession",
    "ErrorCode",
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

# Patch dicts may not nest deeper than this. A 6-level cap is far
# above any reasonable scientific-UI state shape and bounds the
# recursive validator's stack and broadcast cost.
MAX_PATCH_DEPTH = 6

# Per-session ``shared_state`` size ceiling. Prevents unbounded
# growth from accumulated patches: each individual patch is capped
# at MAX_PATCH_BYTES, but without this, N successive patches of
# size N*MAX_PATCH_BYTES would still grow. 512 KiB caps the total
# in-session UI state at a comfortable ceiling.
MAX_SHARED_STATE_BYTES = 512 * 1024

# Participant display names — truncated at write time to prevent
# memory exhaustion via a very long name.
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

# Allowed JSON primitive types for patch values. We deliberately
# refuse anything else (mp.mpf, numpy arrays, custom objects, sets,
# bytes) — an SSE/SocketIO broadcast must be JSON-clean, and
# silently coercing to ``str`` (the previous default) would let
# server state contain strings that look like floats but lost
# precision, then re-broadcast them as strings to every client.
_ALLOWED_PRIMITIVE_TYPES: tuple[type, ...] = (str, int, float, bool, type(None))


class ErrorCode:
    """SocketIO ``error`` event ``code`` field — single source of truth
    so prod code and tests reference the same identifiers. A typo
    here would silently decouple the two sides; raw string literals
    scattered across the module would not catch that. Public so test
    modules can ``from app_web.blueprints.collaborate import ErrorCode``
    and assert ``code == ErrorCode.PATCH_INVALID_KEY``."""

    # Patch validation
    PATCH_NOT_DICT = "patch_not_dict"
    PATCH_INVALID_KEY = "patch_invalid_key"
    PATCH_TOO_DEEP = "patch_too_deep"
    PATCH_TOO_LARGE = "patch_too_large"
    PATCH_UNSUPPORTED_TYPE = "patch_unsupported_type"
    PATCH_NON_FINITE_NUMBER = "patch_non_finite_number"
    PATCH_NOT_JSON_SERIALISABLE = "patch_not_json_serialisable"

    # Auth / session
    MISSING_SESSION_ID = "missing_session_id"
    MISSING_JOIN_TOKEN = "missing_join_token"
    NOT_JOINED = "not_joined"
    UNAUTHORIZED_OR_UNKNOWN_SESSION = "unauthorized_or_unknown_session"
    UNAUTHORIZED_OR_STATE_TOO_LARGE = "unauthorized_or_state_too_large"


def _monotonic() -> float:
    """Indirected so tests can monkey-patch the clock."""
    return time.monotonic()


@dataclass
class CollabSession:
    """In-memory representation of an active collaboration room.

    ``join_token`` is a per-session bearer secret minted at creation
    time. The SocketIO ``join`` handler requires clients to present
    it; the HTTP ``GET /collab/session/<id>`` also requires it to
    read ``shared_state``. The token is in addition to the session
    id (which is the room reference); the id leaks in URLs / logs
    but the token doesn't.

    ``participants`` is a refcount dict ``name → live_count`` rather
    than ``set[str]`` so two live sockets named "alice" each keep
    one slot; one disconnect decrements the count without evicting
    the other. The exposed-to-callers participant list (via
    ``get`` / ``authenticate``) reads only names where count > 0.
    """

    session_id: str
    join_token: str = field(
        default_factory=lambda: secrets.token_urlsafe(24)
    )
    participants: dict[str, int] = field(default_factory=dict)
    shared_state: dict[str, Any] = field(default_factory=dict)
    # monotonic seconds of last activity (create / join / leave /
    # set_state). The registry's GC sweep evicts sessions whose
    # last_activity is more than SESSION_IDLE_TTL_SECONDS ago.
    last_activity: float = field(default_factory=lambda: _monotonic())


def _sanitize_participant_name(raw: object) -> str:
    """Normalise a client-supplied participant name.

    - Coerces non-strings to str (any client can send a number, list,
      etc. — we never want a TypeError to crash the SocketIO handler).
    - Truncates at ``MAX_PARTICIPANT_NAME`` to bound memory.

    Returns ``"anonymous"`` for empty input rather than the empty
    string — keeps the participant list non-blank in the UI.

    HTML-escaping is intentionally NOT performed here. The
    collaboration broadcast is JSON over SocketIO; the only safe
    rendering on the client side is ``textContent``. If a future
    caller chooses to render via ``innerHTML``, that's a client-side
    XSS bug to fix at the rendering site, not here — escaping at this
    layer would double-escape the name in textContent renderings.
    """
    text = str(raw) if raw is not None else ""
    text = text.strip()
    if not text:
        text = "anonymous"
    return text[:MAX_PARTICIPANT_NAME]


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

    @staticmethod
    def _snapshot_locked(session: CollabSession) -> CollabSession:
        """Return a deep-copied snapshot of ``session``.

        Must be called with the registry lock held — the caller is
        responsible for ensuring no mutation happens between the
        snapshot and ``deepcopy`` returning. ``deepcopy`` (rather
        than the previous ``dict(...)`` shallow copy) is required
        because ``shared_state`` is allowed to contain nested dicts
        / lists; a shallow copy would let a caller's read race with
        a concurrent ``set_state`` that replaces a nested object.
        """
        return CollabSession(
            session_id=session.session_id,
            join_token=session.join_token,
            participants=dict(session.participants),
            shared_state=copy.deepcopy(session.shared_state),
            last_activity=session.last_activity,
        )

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
        """Return a **deep-copied snapshot** of the session.

        The original session remains in the registry — but the caller
        can serialise / inspect the returned object (including nested
        dicts / lists in ``shared_state``) without racing against a
        concurrent ``set_state`` or ``leave`` that would otherwise
        mutate the live structure mid-read.
        """
        with self._lock:
            self._sweep_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            return self._snapshot_locked(session)

    def authenticate(
        self, session_id: str, token: str
    ) -> CollabSession | None:
        """Verify the bearer ``token`` matches the session's
        ``join_token``. Returns a deep-copied snapshot of the session
        if valid, None otherwise.

        Uses ``secrets.compare_digest`` for constant-time comparison
        so an attacker can't infer the token via timing differences.
        """
        if not isinstance(token, str):
            return None
        with self._lock:
            self._sweep_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if not secrets.compare_digest(session.join_token, token):
                return None
            return self._snapshot_locked(session)

    def join(
        self, session_id: str, participant: str, token: str
    ) -> CollabSession | None:
        """Add a participant to a session. Requires a valid token —
        anyone with only the session id is denied access.

        ``participant`` is sanitized via ``_sanitize_participant_name``
        before being recorded — caller may pass any object; we coerce.
        """
        if not isinstance(token, str):
            return None
        name = _sanitize_participant_name(participant)
        with self._lock:
            self._sweep_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if not secrets.compare_digest(session.join_token, token):
                return None
            # Refcount: two live sockets named "alice" each get one
            # slot. One disconnect decrements; only when count hits
            # zero is the name removed.
            session.participants[name] = session.participants.get(name, 0) + 1
            session.last_activity = _monotonic()
            return self._snapshot_locked(session)

    def leave(self, session_id: str, participant: str) -> None:
        """Remove a participant. Idempotent — no-op if the session
        or participant isn't tracked. No token required for leaving
        (a disconnecting client can't always produce a token)."""
        name = _sanitize_participant_name(participant)
        with self._lock:
            self._sweep_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return
            current = session.participants.get(name, 0)
            if current <= 1:
                session.participants.pop(name, None)
            else:
                session.participants[name] = current - 1
            session.last_activity = _monotonic()
            # Auto-delete empty sessions so a long-running process
            # doesn't accumulate dead rooms. The refcount invariant
            # (pop-on-zero above) guarantees no name → 0 entries
            # exist, so emptiness equals "no participants".
            if not session.participants:
                self._sessions.pop(session_id, None)

    def set_state(
        self, session_id: str, state: dict[str, Any], token: str
    ) -> CollabSession | None:
        """Merge ``state`` into the session's ``shared_state`` and
        return a deep-copied snapshot of the updated session on
        success, ``None`` on unknown session, invalid token, or if
        the merged state would exceed ``MAX_SHARED_STATE_BYTES``.

        ``state`` is deep-copied into the session to prevent the
        caller retaining a reference and mutating shared state
        post-hoc. Per the project's immutability convention, the
        merge is expressed as a new dict overlaying the previous
        content — callers that took a reference via ``get()`` see
        the old snapshot unchanged.
        """
        if not isinstance(state, dict):
            return None
        if not isinstance(token, str):
            return None
        with self._lock:
            self._sweep_locked()
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if not secrets.compare_digest(session.join_token, token):
                return None
            # Deep-copy on write so the caller can't mutate stored
            # state via a retained reference, then build the merged
            # dict and check the total size BEFORE committing.
            merged = {**session.shared_state, **copy.deepcopy(state)}
            try:
                serialised = json.dumps(merged, ensure_ascii=False)
            except (TypeError, ValueError):
                # Should already be filtered by _validate_patch, but
                # belt-and-braces — a non-JSON-serialisable value
                # makes the entire session unreadable downstream.
                return None
            if len(serialised.encode("utf-8")) > MAX_SHARED_STATE_BYTES:
                return None
            # Build a fresh dict rather than in-place update so any
            # caller holding a reference to the old shared_state
            # doesn't observe the mutation — matches the
            # "ALWAYS create new objects, NEVER mutate" project rule.
            session.shared_state = merged
            session.last_activity = _monotonic()
            return self._snapshot_locked(session)

    def count(self) -> int:
        with self._lock:
            self._sweep_locked()
            return len(self._sessions)


def _validate_patch_value(
    value: Any, depth: int
) -> tuple[bool, str]:
    """Recursively check that ``value`` is JSON-clean and has only
    safe dict keys, up to ``MAX_PATCH_DEPTH`` levels deep.

    Refuses any value that isn't a JSON primitive (str/int/float/
    bool/None) or a dict / list of valid values. Crucially, this
    means an ``mp.mpf`` or any other custom object is REJECTED at
    validation time — preventing the previous ``default=str``
    behaviour where ``json.dumps`` would silently stringify
    high-precision values, accept the patch, and then store the
    coerced string into ``shared_state``.

    Returns ``(True, "")`` on success, ``(False, "<code>")`` otherwise.
    """
    if depth > MAX_PATCH_DEPTH:
        return False, ErrorCode.PATCH_TOO_DEEP
    if isinstance(value, bool):
        # Order matters: bool is a subclass of int in Python.
        return True, ""
    if isinstance(value, _ALLOWED_PRIMITIVE_TYPES):
        # Reject NaN / Inf: not JSON-spec compliant; some clients
        # parse them as ``null``, others reject the whole frame.
        if isinstance(value, float) and (
            math.isnan(value) or math.isinf(value)
        ):
            return False, ErrorCode.PATCH_NON_FINITE_NUMBER
        return True, ""
    if isinstance(value, list):
        for item in value:
            ok, code = _validate_patch_value(item, depth + 1)
            if not ok:
                return False, code
        return True, ""
    if isinstance(value, dict):
        for key, sub in value.items():
            if (
                not isinstance(key, str)
                or key in _DENIED_PATCH_KEYS
                or not _ALLOWED_PATCH_KEY_RE.match(key)
            ):
                return False, ErrorCode.PATCH_INVALID_KEY
            ok, code = _validate_patch_value(sub, depth + 1)
            if not ok:
                return False, code
        return True, ""
    # Anything else — mp.mpf, numpy arrays, sets, bytes, custom
    # objects — is rejected. The client must serialise to a JSON
    # primitive before sending.
    return False, ErrorCode.PATCH_UNSUPPORTED_TYPE


def _validate_patch(patch: Any) -> tuple[bool, str]:
    """Return ``(ok, error_code)`` for a proposed state-update patch.

    Enforces the hard contract:
    - must be a dict
    - every nested value is JSON-clean (only str/int/float/bool/None
      primitives, lists, or dicts with allowed keys; rejects mp.mpf,
      objects, NaN / Inf)
    - every nested key (top-level AND inside nested dicts) matches
      ``_ALLOWED_PATCH_KEY_RE`` and is not in ``_DENIED_PATCH_KEYS``
      — closes the prototype-pollution surface even when the
      sensitive key is buried one or more levels deep
    - structure does not exceed ``MAX_PATCH_DEPTH``
    - serialised size ≤ ``MAX_PATCH_BYTES``

    Returns ``(True, "")`` on success, ``(False, "<code>")`` on any
    rejection. The caller emits an SSE/SocketIO error event with the
    code.
    """
    if not isinstance(patch, dict):
        return False, ErrorCode.PATCH_NOT_DICT
    ok, code = _validate_patch_value(patch, depth=1)
    if not ok:
        return False, code
    try:
        # No `default=str` — every value is guaranteed to be a
        # native JSON type by the recursive validator above, so a
        # serialisation failure here is a real bug we want to surface.
        serialised = json.dumps(patch, ensure_ascii=False)
    except (TypeError, ValueError):
        return False, ErrorCode.PATCH_NOT_JSON_SERIALISABLE
    if len(serialised.encode("utf-8")) > MAX_PATCH_BYTES:
        return False, ErrorCode.PATCH_TOO_LARGE
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
    - SocketIO ``leave`` event: voluntary departure (independent of
      the transport-level disconnect). Lets a multi-tab user switch
      sessions without waiting for the heartbeat to drop them.
    - SocketIO ``state_update``: requires the caller's current
      SocketIO connection to have already successfully joined (tracked
      in ``flask.session``). Patch payload validated against
      ``_validate_patch`` (recursive — nested ``__proto__`` rejected
      too).
    """
    if not HAS_SOCKETIO:
        raise ModuleNotFoundError(
            "flask-socketio is not installed. Add 'flask-socketio' to "
            "web_requirements.txt to enable collaboration sessions."
        )
    from app_web._security_shim import csrf_protect

    bp = Blueprint("collab", __name__)
    registry = SessionRegistry()
    # Map from SocketIO sid → set[(session_id, participant_name)].
    # A single socket may join multiple sessions; ``disconnect`` must
    # leave EVERY one of them, not just the most recent. The previous
    # design (sid → single tuple) overwrote earlier joins, leaking
    # ghost participants in the abandoned sessions until the TTL sweep.
    _sid_to_joined: dict[str, set[tuple[str, str]]] = {}
    _sid_lock = threading.Lock()

    def _track_join(sid: str | None, session_id: str, name: str) -> None:
        if not sid:
            return
        with _sid_lock:
            _sid_to_joined.setdefault(sid, set()).add((session_id, name))

    def _untrack_join(
        sid: str | None, session_id: str, name: str
    ) -> None:
        if not sid:
            return
        with _sid_lock:
            entries = _sid_to_joined.get(sid)
            if not entries:
                return
            entries.discard((session_id, name))
            if not entries:
                _sid_to_joined.pop(sid, None)

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
        # NOTE: the query-arg path is documented as fallback because
        # tokens in URLs leak through Referer headers and access logs.
        # New clients should always use ``X-Collab-Token``.
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
        raw_participant = (data or {}).get("participant", "anonymous")
        if not isinstance(session_id, str) or not session_id:
            emit("error", {"code": ErrorCode.MISSING_SESSION_ID})
            return
        if not isinstance(join_token, str) or not join_token:
            emit("error", {"code": ErrorCode.MISSING_JOIN_TOKEN})
            return
        # Sanitize ONCE — registry.join would do it internally too,
        # but we need the same string for the `joined` broadcast and
        # the sid→membership tracker, so compute up front.
        participant_name = _sanitize_participant_name(raw_participant)
        session = registry.join(session_id, participant_name, join_token)
        if session is None:
            # Same ambiguous error for missing-session and
            # wrong-token — no side channel for attackers. We don't
            # disconnect() server-side; the client is expected to
            # close after receiving 'error', and the SocketIO session
            # has no privileges until the 'joined' event (tracked in
            # flask.session['collab_joined_sessions']).
            emit("error", {"code": ErrorCode.UNAUTHORIZED_OR_UNKNOWN_SESSION})
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
        # Record SocketIO sid → (session_id, participant_name). Falls
        # through silently if sid is unavailable (some test harnesses
        # don't set request.sid). The set semantics let one socket
        # join multiple sessions and have every membership cleaned up
        # on disconnect.
        try:
            sid = getattr(request, "sid", None)
        except Exception:  # noqa: BLE001
            sid = None
        _track_join(sid, session_id, participant_name)
        emit(
            "joined",
            {"session_id": session_id, "participant": participant_name},
            room=session_id,
        )

    @socketio.on("leave", namespace="/collab")
    def on_leave(data):  # noqa: ANN001
        """Voluntary leave — independent of the transport-level
        disconnect. Lets a multi-tab user switch sessions without
        waiting for the SocketIO heartbeat (which can take 5–30s) to
        drop them from the participant list.

        Required payload: ``{session_id, participant}``. No token —
        a client that wants to leave a room they joined doesn't need
        to re-prove identity; the worst case is a malicious peer
        evicting another participant by guessing the name, but the
        target's connection can simply re-join (it still has the
        token in memory).
        """
        session_id = (data or {}).get("session_id")
        raw_participant = (data or {}).get("participant", "")
        if not isinstance(session_id, str) or not session_id:
            emit("error", {"code": ErrorCode.MISSING_SESSION_ID})
            return
        participant_name = _sanitize_participant_name(raw_participant)
        registry.leave(session_id, participant_name)
        try:
            sid = getattr(request, "sid", None)
        except Exception:  # noqa: BLE001
            sid = None
        _untrack_join(sid, session_id, participant_name)
        # Notify peers (but not the leaver) so the participant list
        # updates immediately for everyone else. include_self=False
        # because the leaver is presumably about to navigate away.
        emit(
            "left",
            {"session_id": session_id, "participant": participant_name},
            room=session_id,
            include_self=False,
        )

    @socketio.on("state_update", namespace="/collab")
    def on_state_update(data):  # noqa: ANN001
        session_id = (data or {}).get("session_id")
        patch = (data or {}).get("patch")
        if not isinstance(session_id, str) or not session_id:
            emit("error", {"code": ErrorCode.MISSING_SESSION_ID})
            return
        ok, err_code = _validate_patch(patch)
        if not ok:
            emit("error", {"code": err_code})
            return
        # Verify the caller previously joined this session on THIS
        # SocketIO connection. Prevents a client that only knows the
        # session_id (but never acquired a token) from broadcasting
        # by guessing; join + the token check below is the gate.
        # NOTE on degraded sessions: if ``flask_session`` is
        # unavailable (e.g., the secret key was rotated mid-connection
        # or an alternate transport changes the session context),
        # this check rejects the caller. The token re-check below
        # would also fail in that case via registry.set_state. The
        # session check is therefore a defence-in-depth gate, not
        # the sole authorisation — never remove it thinking the token
        # check alone is sufficient.
        try:
            joined = flask_session.get("collab_joined_sessions") or []
        except Exception:  # noqa: BLE001
            joined = []
        if session_id not in joined:
            emit("error", {"code": ErrorCode.NOT_JOINED})
            return
        # Re-verify the token on every state_update so a client
        # that lost state (e.g. the Flask session expired) can't
        # keep mutating shared state from a stale SocketIO
        # connection. The token is already known to the client
        # that legitimately joined.
        token = (data or {}).get("join_token") or (data or {}).get("token")
        if not isinstance(token, str):
            emit("error", {"code": ErrorCode.MISSING_JOIN_TOKEN})
            return
        updated = registry.set_state(session_id, patch, token)
        if updated is None:
            # Either the token check failed OR the merged shared
            # state would exceed MAX_SHARED_STATE_BYTES. Distinguish
            # only at the per-error-code level so an attacker can't
            # use the rejection as an oracle. Clients can re-attempt
            # with a smaller patch.
            emit("error", {"code": ErrorCode.UNAUTHORIZED_OR_STATE_TOO_LARGE})
            return
        emit(
            "state_update",
            {"patch": patch},
            room=session_id,
            include_self=False,
        )

    @socketio.on("disconnect", namespace="/collab")
    def on_disconnect():
        """Evict the disconnecting participant from EVERY session
        they were tracked in. Without this, a crashed / tab-closed
        client remains visible in each affected room's participant
        list until the next SESSION_IDLE_TTL sweep — confusing to
        co-participants who think the user is still active.
        """
        try:
            sid = getattr(request, "sid", None)
        except Exception:  # noqa: BLE001
            sid = None
        if not sid:
            return
        with _sid_lock:
            entries = _sid_to_joined.pop(sid, None)
        if not entries:
            return
        for session_id, participant in entries:
            try:
                registry.leave(session_id, participant)
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "on_disconnect: leave(%s, %r) raised: %s",
                    session_id, participant, exc,
                )

    return bp
