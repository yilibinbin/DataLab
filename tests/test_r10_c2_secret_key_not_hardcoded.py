"""R10 C2 regression: SECRET_KEY fallback must not be the hardcoded
'datalab-web-dev' string.

Two invariants are asserted:
1. In production (DATALAB_DEBUG unset and DATALAB_WEB_SECRET unset), create_app()
   must raise RuntimeError — refusing to start is safer than silently running with
   a git-history-visible fallback.
2. In development (DATALAB_DEBUG set, DATALAB_WEB_SECRET unset), SECRET_KEY must
   be a random per-process value, never the literal 'datalab-web-dev'.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


def _reload_server():
    """Fresh import of app_web.server to pick up environment changes."""
    import importlib
    import app_web.server
    return importlib.reload(app_web.server)


def test_production_without_secret_env_refuses_to_start():
    """DATALAB_DEBUG unset and DATALAB_WEB_SECRET unset ⇒ RuntimeError."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("DATALAB_WEB_SECRET", "DATALAB_DEBUG")}
    with patch.dict(os.environ, env, clear=True):
        server = _reload_server()
        with pytest.raises(RuntimeError) as excinfo:
            server.create_app()
        msg = str(excinfo.value)
        assert " / " in msg, f"Startup error must be bilingual, got: {msg!r}"
        assert "DATALAB_WEB_SECRET" in msg


def test_development_fallback_is_random_not_hardcoded():
    """DATALAB_DEBUG=1 and DATALAB_WEB_SECRET unset ⇒ random key, not literal."""
    env = {k: v for k, v in os.environ.items()
           if k not in ("DATALAB_WEB_SECRET",)}
    env["DATALAB_DEBUG"] = "1"
    with patch.dict(os.environ, env, clear=True):
        server = _reload_server()
        app = server.create_app()
        key = app.config["SECRET_KEY"]
        assert isinstance(key, str)
        assert key != "datalab-web-dev", (
            "Development fallback must be a random value, not the hardcoded "
            "'datalab-web-dev' string that is visible in git history."
        )
        # A random hex secret of reasonable length
        assert len(key) >= 32, f"Random key should be ≥32 chars, got {len(key)}"


def test_explicit_env_secret_is_honored():
    """Regression guard: explicit DATALAB_WEB_SECRET is still used."""
    env = dict(os.environ)
    env["DATALAB_WEB_SECRET"] = "test-explicit-secret-value-32chars"
    with patch.dict(os.environ, env, clear=True):
        server = _reload_server()
        app = server.create_app()
        assert app.config["SECRET_KEY"] == "test-explicit-secret-value-32chars"
