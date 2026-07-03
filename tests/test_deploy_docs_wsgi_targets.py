"""Deployment-surface contract: every WSGI app target we tell operators to run
must actually resolve to a callable Flask entry point.

Background (SWARM_REVIEW_2026 F01 / F02):
- F01 (a guaranteed startup crash): the docs used ``app_web.server:app``, but
  ``app_web/server.py`` exposes no module-level ``app``/``application`` symbol —
  only the ``create_app()`` factory. The documented gunicorn/waitress commands
  therefore crashed at startup with "Failed to find attribute 'app'". The fix
  switches every deployment surface to the app-factory form
  (``app_web.server:create_app()`` for gunicorn, ``--call
  app_web.server:create_app`` for waitress), which both servers resolve natively.
- F02 (per-process in-memory state): the SSE rate-limiter and the collaboration
  session registry are per-worker. This is NOT fixed by forcing a single worker —
  mpmath's precision lock (``app_web/blueprints/sse.py`` ``_MP_SERIAL_LOCK``)
  serializes ALL compute within one process, so ``gunicorn.conf.py`` deliberately
  floors workers at 2 to keep one user's long fit from blocking everyone. The docs
  therefore KEEP multi-worker and instead document the trade-offs honestly (rate
  limit is per-worker; collab needs sticky sessions + Redis to scale out). There
  is consequently no "workers must be 1" assertion here — that would contradict
  the design. The invariant we DO enforce is F01: no surface may ship the broken
  bare ``app_web.server:app`` target.

These tests parse the deployment surfaces directly, so a future edit that
reintroduces the broken target fails loudly. They do NOT require gunicorn/waitress
to be installed (deployment-only deps absent from the test venv): targets are
resolved with ``werkzeug.utils.import_string``.
"""

from __future__ import annotations

import re
from pathlib import Path

import flask
import pytest
from werkzeug.utils import import_string

ROOT = Path(__file__).resolve().parents[1]

# Every surface that hands an operator a gunicorn/waitress command line.
DEPLOY_SURFACES = (
    ROOT / "docs" / "web" / "deploy.en.md",
    ROOT / "docs" / "web" / "deploy.zh.md",
    ROOT / "docs" / "DATALAB_WEB_GUIDE.md",
    ROOT / "docs" / "DATALAB_WEB_GUIDE.en.md",
    ROOT / "gunicorn.conf.py",
)

# The broken F01 target, as a raw substring for the regression guard.
BROKEN_TARGET = "app_web.server:app"

# A WSGI target token: ``module.path:callable`` optionally followed by ``()``.
_TARGET_TOKEN = r"[\w.]+:[\w.]+(?:\(\))?"
# gunicorn CLI (incl. the ``-c gunicorn.conf.py <target>`` and docstring
# ``Run with: gunicorn ...`` forms) — the target is the last module:callable
# token on the line; single/double quotes around it are optional.
_GUNICORN_LINE = re.compile(r"gunicorn\b.*?['\"]?(" + _TARGET_TOKEN + r")['\"]?\s*$")
_WAITRESS_CALL = re.compile(r"waitress-serve\b.*?--call\s+(" + _TARGET_TOKEN + r")")
_WAITRESS_BARE = re.compile(r"waitress-serve\b.*?\s(" + _TARGET_TOKEN + r")\s*$")

_PATTERNS = (_GUNICORN_LINE, _WAITRESS_CALL, _WAITRESS_BARE)


def _extract_targets(path: Path) -> list[tuple[Path, int, str]]:
    """Return (path, line_no, target) for every WSGI target in a surface.

    Scans command lines AND docstring/comment lines (``gunicorn.conf.py`` puts its
    example target inside a module docstring, and the guides put a manual-override
    example inside a shell comment), so ``#``/``>``-prefixed lines are NOT skipped
    here — the F01 contract applies to any line that hands over a runnable target.
    """
    targets: list[tuple[Path, int, str]] = []
    text = path.read_text(encoding="utf-8")
    for idx, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        for pattern in _PATTERNS:
            match = pattern.search(line)
            if match:
                targets.append((path, idx, match.group(1)))
                break
    return targets


def _all_targets() -> list[tuple[Path, int, str]]:
    found: list[tuple[Path, int, str]] = []
    for path in DEPLOY_SURFACES:
        found.extend(_extract_targets(path))
    return found


def test_deploy_surfaces_exist():
    for path in DEPLOY_SURFACES:
        assert path.is_file(), f"missing deployment surface: {path}"


def test_at_least_one_target_is_documented():
    """Guard against the extraction regex silently matching nothing."""
    targets = _all_targets()
    assert targets, "no gunicorn/waitress WSGI targets found in deployment surfaces"


def test_no_doc_uses_the_broken_bare_app_target():
    """F01 regression guard: no surface may ship the bare ``app_web.server:app``.

    Scans the RAW text (prose, comments, docstrings, and command lines alike) of
    every deployment surface. This is broader than the resolve test below because
    it also catches a broken target mentioned in explanatory text — the exact way
    round 1 missed the two DATALAB_WEB_GUIDE files and the gunicorn.conf.py
    docstring. Uses a negative lookahead so the correct factory forms
    (``app_web.server:create_app`` / ``...:create_app()``) are NOT flagged.
    """
    pattern = re.compile(re.escape(BROKEN_TARGET) + r"(?![\w()])")
    offenders: list[str] = []
    for path in DEPLOY_SURFACES:
        for idx, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(raw):
                offenders.append(f"{path.name}:{idx}: {raw.strip()}")
    assert not offenders, (
        "deployment surfaces still reference the broken bare WSGI target "
        f"{BROKEN_TARGET!r} (F01 — crashes at startup):\n" + "\n".join(offenders)
    )


@pytest.mark.parametrize(
    "path,line_no,target",
    _all_targets(),
    ids=lambda v: f"{v.name}:{v}" if isinstance(v, Path) else str(v),
)
def test_documented_wsgi_target_resolves_to_flask_app(
    path: Path, line_no: int, target: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every documented gunicorn/waitress target must load and yield a Flask app.

    This is the real F01 contract: the docs promise operators a runnable command,
    so the ``module:callable`` token must import and produce a Flask application —
    whether it is a factory that must be called or an already-built app object.
    """
    monkeypatch.setenv("DATALAB_WEB_SECRET", "test-secret")

    dotted = target[:-2] if target.endswith("()") else target
    resolved = import_string(dotted)

    if isinstance(resolved, flask.Flask):
        app = resolved
    else:
        assert callable(resolved), (
            f"{path.name}:{line_no}: target {target!r} is neither a Flask app "
            f"nor a callable factory"
        )
        app = resolved()

    assert isinstance(app, flask.Flask), (
        f"{path.name}:{line_no}: target {target!r} did not resolve to a Flask app "
        f"(got {type(app).__name__})"
    )
