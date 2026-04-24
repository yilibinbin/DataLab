#!/usr/bin/env python3
"""
Lightweight Flask web UI for the existing extrapolation/LaTeX pipeline.

Routes are split into blueprints. Heavy computation lives in `app_web.logic`.
"""

from __future__ import annotations

import os
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


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SECRET_KEY"] = os.environ.get("DATALAB_WEB_SECRET", "datalab-web-dev")

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

    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(docs_bp)

    return app


if __name__ == "__main__":
    app = create_app()

    host = os.environ.get("DATALAB_HOST", "127.0.0.1")
    port = int(os.environ.get("DATALAB_PORT", os.environ.get("PORT", "8000")))
    debug = os.environ.get("DATALAB_DEBUG", "").lower() in ("1", "true", "yes")
    secret_set = bool(os.environ.get("DATALAB_WEB_SECRET"))

    if debug:
        import warnings

        warnings.warn(
            "Running in DEBUG mode. NEVER use debug=True in production! "
            "Set DATALAB_DEBUG=0 for production.",
            RuntimeWarning,
            stacklevel=2,
        )
    elif not secret_set:
        import warnings

        warnings.warn(
            "DATALAB_WEB_SECRET is not set; using a development SECRET_KEY. "
            "Set DATALAB_WEB_SECRET before deploying to production.",
            RuntimeWarning,
            stacklevel=2,
        )

    app.run(host=host, port=port, debug=debug, threaded=False)
