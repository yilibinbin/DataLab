/**
 * DataLab Web — real-time collaboration client (Phase 3 #17).
 *
 * Lightweight wrapper over socket.io-client that:
 * - creates a session via POST /collab/session (returns session_id)
 * - joins a room via socketio 'join' event on /collab namespace
 * - emits 'state_update' events for local UI changes
 * - applies incoming 'state_update' patches to a caller-supplied
 *   apply callback
 *
 * No persistent storage, no auth — sessions are ephemeral per-process.
 * Callers wanting stronger guarantees should layer an auth cookie
 * and Redis-backed session registry.
 *
 * Exposes ``window.DATALAB_COLLAB = { createSession, joinSession,
 * leaveSession, sendStateUpdate, currentSessionId }`` so tests +
 * page scripts can drive it without parsing the internal closure.
 */
(function () {
  "use strict";

  /** @type {null | {socket: any, sessionId: string, onUpdate: Function | null}} */
  var _session = null;

  /**
   * @returns {Promise<string>} session_id
   */
  function createSession() {
    return fetch("/collab/session", { method: "POST" })
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error("createSession: server returned " + resp.status);
        }
        return resp.json();
      })
      .then(function (data) {
        if (!data || typeof data.session_id !== "string") {
          throw new Error("createSession: malformed response");
        }
        return data.session_id;
      });
  }

  /**
   * @param {string} sessionId
   * @param {string} participant — user-chosen display name
   * @param {Function} onUpdate — called with (patch) on each remote update
   * @returns {Promise<void>}
   */
  function joinSession(sessionId, participant, onUpdate) {
    if (typeof window.io !== "function") {
      return Promise.reject(new Error(
        "socket.io-client not loaded; include it before collab.js"
      ));
    }
    if (!sessionId || typeof sessionId !== "string") {
      return Promise.reject(new Error("joinSession: session_id required"));
    }
    if (_session && _session.socket) {
      _session.socket.disconnect();
    }
    var socket = window.io("/collab", { transports: ["websocket", "polling"] });
    _session = {
      socket: socket,
      sessionId: sessionId,
      onUpdate: typeof onUpdate === "function" ? onUpdate : null,
    };
    return new Promise(function (resolve, reject) {
      var joined = false;
      socket.on("connect", function () {
        socket.emit("join", {
          session_id: sessionId,
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
   * @param {Object} patch — JSON-serialisable patch to merge into shared state
   */
  function sendStateUpdate(patch) {
    if (!_session || !_session.socket) {
      throw new Error("sendStateUpdate: not in a session");
    }
    _session.socket.emit("state_update", {
      session_id: _session.sessionId,
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
