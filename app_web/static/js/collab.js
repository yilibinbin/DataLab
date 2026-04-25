/**
 * DataLab Web — real-time collaboration client (Phase 3 #17).
 *
 * Lightweight wrapper over socket.io-client that:
 * - creates a session via POST /collab/session, which returns BOTH
 *   ``session_id`` AND ``join_token`` — both required to participate
 * - joins a room via the SocketIO 'join' event on /collab namespace
 *   (server rejects the join if either is missing or the token is
 *   wrong)
 * - emits 'state_update' events for local UI changes (server
 *   re-verifies the token + room membership on every emit)
 * - applies incoming 'state_update' patches to a caller-supplied
 *   apply callback
 *
 * Auth model: the ``join_token`` is a per-session bearer secret
 * minted at creation. Anyone with both the ``session_id`` AND the
 * ``join_token`` can participate; the id alone is insufficient.
 * The token is delivered out-of-band (typically alongside a share
 * link). Sessions are in-memory and tied to one server worker
 * process — multi-worker collaboration would need a shared registry
 * (Redis), which is out of scope for the current implementation.
 *
 * Exposes ``window.DATALAB_COLLAB = { createSession, joinSession,
 * leaveSession, sendStateUpdate, currentSessionId }`` so tests +
 * page scripts can drive it without parsing the internal closure.
 */
(function () {
  "use strict";

  /** @type {null | {socket: any, sessionId: string, joinToken: string, onUpdate: Function | null}} */
  var _session = null;

  /**
   * Find the CSRF token rendered by Flask. The server uses
   * ``X-CSRF-Token`` header OR ``csrf_token`` form field. Pages that
   * embed collab.js are expected to render the token in a
   * <meta name="csrf-token" content="..."> tag or a
   * <input name="csrf_token" ...> element.
   *
   * @returns {string}
   */
  function _findCsrfToken() {
    try {
      var meta = document.querySelector('meta[name="csrf-token"]');
      if (meta && meta.content) return meta.content;
      var input = document.querySelector('input[name="csrf_token"]');
      if (input && input.value) return input.value;
    } catch (e) { /* ignore */ }
    return "";
  }

  /**
   * Creates a new collaboration session server-side.
   *
   * @returns {Promise<{session_id: string, join_token: string}>}
   */
  function createSession() {
    var csrf = _findCsrfToken();
    var headers = { "Content-Type": "application/json" };
    if (csrf) headers["X-CSRF-Token"] = csrf;
    return fetch("/collab/session", {
      method: "POST",
      headers: headers,
      credentials: "same-origin",
    })
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("createSession: server returned " + resp.status);
        }
        return resp.json();
      })
      .then(function (data) {
        if (!data
            || typeof data.session_id !== "string"
            || typeof data.join_token !== "string") {
          throw new Error(
            "createSession: malformed response — need session_id + join_token"
          );
        }
        return {
          session_id: data.session_id,
          join_token: data.join_token,
        };
      });
  }

  /**
   * Join an existing session. Requires BOTH the session_id and the
   * join_token minted at creation — the token must be transmitted
   * out-of-band (e.g., alongside the session URL in a share link).
   *
   * @param {string} sessionId
   * @param {string} joinToken — bearer secret from createSession()
   * @param {string} participant — user-chosen display name
   * @param {Function} onUpdate — called with (patch) on each remote update
   * @returns {Promise<void>}
   */
  function joinSession(sessionId, joinToken, participant, onUpdate) {
    if (typeof window.io !== "function") {
      return Promise.reject(new Error(
        "socket.io-client not loaded; include it before collab.js"
      ));
    }
    if (!sessionId || typeof sessionId !== "string") {
      return Promise.reject(new Error("joinSession: session_id required"));
    }
    if (!joinToken || typeof joinToken !== "string") {
      return Promise.reject(new Error("joinSession: join_token required"));
    }
    if (_session && _session.socket) {
      _session.socket.disconnect();
    }
    var socket = window.io("/collab", { transports: ["websocket", "polling"] });
    _session = {
      socket: socket,
      sessionId: sessionId,
      joinToken: joinToken,
      onUpdate: typeof onUpdate === "function" ? onUpdate : null,
    };
    return new Promise(function (resolve, reject) {
      var joined = false;
      socket.on("connect", function () {
        socket.emit("join", {
          session_id: sessionId,
          join_token: joinToken,
          participant: participant || "anonymous",
        });
      });
      socket.on("joined", function () {
        joined = true;
        resolve();
      });
      socket.on("error", function (err) {
        if (!joined) {
          reject(err);
        } else {
          // Post-join errors are surfaced via console; callers can
          // attach additional listeners on the socket object via
          // window.DATALAB_COLLAB.socket
          console.error("collab error:", err);
        }
      });
      socket.on("state_update", function (msg) {
        if (_session && _session.onUpdate && msg && msg.patch) {
          try {
            _session.onUpdate(msg.patch);
          } catch (e) {
            console.error("collab onUpdate handler threw:", e);
          }
        }
      });
      socket.on("disconnect", function () {
        joined = false;
      });
    });
  }

  function leaveSession() {
    if (_session && _session.socket) {
      try { _session.socket.disconnect(); } catch (e) { /* ignore */ }
    }
    _session = null;
  }

  /**
   * Broadcast a patch to all other participants in the current
   * session. The server re-verifies the ``join_token`` on every
   * send so a stale connection can't keep writing after the
   * session expired.
   *
   * @param {Object} patch — JSON-serialisable patch to merge into shared state
   */
  function sendStateUpdate(patch) {
    if (!_session || !_session.socket) {
      throw new Error("sendStateUpdate: not in a session");
    }
    _session.socket.emit("state_update", {
      session_id: _session.sessionId,
      join_token: _session.joinToken,
      patch: patch || {},
    });
  }

  function currentSessionId() {
    return _session ? _session.sessionId : null;
  }

  window.DATALAB_COLLAB = {
    createSession: createSession,
    joinSession: joinSession,
    leaveSession: leaveSession,
    sendStateUpdate: sendStateUpdate,
    currentSessionId: currentSessionId,
  };
})();
