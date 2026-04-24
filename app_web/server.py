#!/usr/bin/env python3
"""
Lightweight Flask web UI for the existing extrapolation/LaTeX pipeline.

Routes are split into blueprints. Heavy computation lives in `app_web.logic`.
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

# Ensure project root is importable when the module is executed directly
# (e.g. `python app_web/server.py`).
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flask import Flask, request

from app_web._security_shim import configure_app_security, get_csrf_token
from app_web.logic import _generate_fitting_latex  # re-exported for tests/backward-compat


def _resolve_secret_key() -> str:
    """Resolve the Flask SECRET_KEY with no hardcoded fallback.

    - If ``DATALAB_WEB_SECRET`` is set (production and dev alike), use it.
    - Else, if ``DATALAB_DEBUG`` is truthy, generate a random per-process
      secret so the dev workflow keeps working without a committed key.
    - Otherwise, refuse to start: a missing SECRET_KEY in production is a
      hard failure — a git-history-visible literal would be worse than a
      crash.
    """
    explicit = os.environ.get("DATALAB_WEB_SECRET")
    if explicit:
        return explicit

    debug_flag = os.environ.get("DATALAB_DEBUG", "").lower() in ("1", "true", "yes")
    if debug_flag:
        # Random per-process secret — sessions will not survive a restart,
        # which is exactly what we want in development.
        return secrets.token_hex(32)

    raise RuntimeError(
        "必须设置环境变量 DATALAB_WEB_SECRET 才能启动 DataLab Web。 / "
        "DATALAB_WEB_SECRET must be set before starting DataLab Web."
    )


def create_app() -> Flask:
    """Build the Flask app with every blueprint registered.

    For deployments that also want real-time collaboration sessions,
    call :func:`create_app_with_socketio` instead — it constructs a
    ``SocketIO`` instance, attaches it at ``app.extensions["socketio"]``,
    and wires the ``/collab`` blueprint against it.
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = _resolve_secret_key()

    configure_app_security(app)

    @app.context_processor
    def inject_csrf_token():
        safe_form_values: dict[str, str] = {}
        try:
            safe_form_values = request.form.to_dict(flat=True)
        except Exception:
            safe_form_values = {}
        return dict(csrf_token=get_csrf_token, form_values=safe_form_values)

    from app_web.blueprints.pages import bp as pages_bp
    from app_web.blueprints.api import bp as api_bp
    from app_web.blueprints.docs import bp as docs_bp
    from app_web.blueprints.sse import bp as sse_bp

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(docs_bp)
    # SSE streaming endpoints (/api/fit/stream, /api/auto-fit/stream) —
    # registered after the regular API blueprint so the POST-form
    # alternatives continue to work; SSE callers use GET.
    app.register_blueprint(sse_bp)

    return app


def create_app_with_socketio(
    cors_allowed_origins: str | list[str] | None = None,
):
    """Build the Flask app plus a SocketIO instance for collaboration.

    Returns ``(app, socketio)``. Raises ``ModuleNotFoundError`` if
    ``flask_socketio`` isn't installed — the caller should fall back
    to plain ``create_app()`` in that case.

    Parameters
    ----------
    cors_allowed_origins:
        CORS policy passed through to ``SocketIO``. Defaults to
        ``None`` (same-origin only, the secure default). Callers
        running behind a CDN or cross-origin proxy can pass the
        allowlist explicitly. DO NOT pass ``"*"`` in production —
        it lets any page open a session and read collaboration
        state.
    """
    try:
        from flask_socketio import SocketIO
    except ImportError as exc:
        raise ModuleNotFoundError(
            "flask-socketio is not installed. Add 'flask-socketio' to "
            "web_requirements.txt or pip install it manually."
        ) from exc
    from app_web.blueprints.collaborate import create_collab_blueprint

    app = create_app()
    # async_mode="threading" keeps everything in-process (no eventlet/
    # gevent monkey-patching) — matches the WSGI server choice for
    # Windows deploys (Waitress is thread-per-request). For higher
    # concurrency move to eventlet or gunicorn with gevent workers.
    socketio = SocketIO(
        app,
        async_mode="threading",
        cors_allowed_origins=cors_allowed_origins,
        logger=False,
        engineio_logger=False,
    )
    collab_bp = create_collab_blueprint(socketio)
    app.register_blueprint(collab_bp, url_prefix="/collab")

    # Store on app.extensions for retrieval by tests and health checks.
    app.extensions["socketio"] = socketio
    return app, socketio


if __name__ == "__main__":
    host = os.environ.get("DATALAB_HOST", "127.0.0.1")
    port = int(os.environ.get("DATALAB_PORT", os.environ.get("PORT", "8000")))
    debug = os.environ.get("DATALAB_DEBUG", "").lower() in ("1", "true", "yes")

    if debug:
        import warnings

        warnings.warn(
            "Running in DEBUG mode. NEVER use debug=True in production! "
            "Set DATALAB_DEBUG=0 for production.",
            RuntimeWarning,
            stacklevel=2,
        )

    # Try SocketIO first (real-time collab enabled); fall back to
    # plain Flask when flask-socketio isn't installed. The fallback
    # keeps the existing single-frontend deploy path working even
    # when optional deps aren't present.
    try:
        app, socketio = create_app_with_socketio()
        socketio.run(
            app,
            host=host,
            port=port,
            debug=debug,
            allow_unsafe_werkzeug=debug,
        )
    except ModuleNotFoundError:
        app = create_app()
        app.run(host=host, port=port, debug=debug, threaded=False)
