"""P2-5: guard the datalab_latex -> datalab_core layering boundary.

datalab_latex is the presentation layer; it must not import upward into
datalab_core (the service layer). Stage A of P2-5 removed the redundant
validator re-validation from the grouped/matrix renderers, and this test locks
that in so the inversion can't silently return there.

Mirrors the mechanism of tests/test_core_no_qt_imports.py (static AST scan of
imports). Two modules remain a *known, documented* exception —
``latex_tables_common`` still imports five statistics-display helpers from
datalab_core.statistics (moving them to shared/ is tracked as P2-5 Stage B, a
larger core-schema move) — so they are listed in _KNOWN_EXCEPTIONS with a
pointer rather than silently allowed. Everything else must stay core-free.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_LATEX_DIR = _REPO_ROOT / "datalab_latex"

# Files with a still-open, documented upward import (P2-5 Stage B — move the
# five statistics_display helpers to shared/). Tracked, not silently allowed.
_KNOWN_EXCEPTIONS = {"latex_tables_common.py"}


def _forbidden_module(name: str | None) -> bool:
    return bool(name) and (name == "datalab_core" or name.startswith("datalab_core."))


def _core_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            hits += [f"{node.lineno}:{a.name}" for a in node.names if _forbidden_module(a.name)]
        elif isinstance(node, ast.ImportFrom) and _forbidden_module(node.module):
            hits.append(f"{node.lineno}:{node.module}")
    return hits


def test_datalab_latex_does_not_import_datalab_core_except_known():
    violations: dict[str, list[str]] = {}
    for path in sorted(_LATEX_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.name in _KNOWN_EXCEPTIONS:
            continue
        hits = _core_imports(path)
        if hits:
            violations[str(path.relative_to(_REPO_ROOT))] = hits
    assert not violations, (
        "datalab_latex modules must not import datalab_core (P2-5): " + repr(violations)
    )


def test_grouped_and_matrix_renderers_are_core_free():
    # Stage A specifically freed these two; pin it directly.
    for name in ("latex_tables_statistics_grouped.py", "latex_tables_statistics_matrix.py"):
        assert _core_imports(_LATEX_DIR / name) == [], f"{name} regained a datalab_core import"


def test_known_exception_list_stays_minimal():
    # If Stage B lands, latex_tables_common should drop off this list. Guard that
    # the exception set doesn't quietly grow.
    assert _KNOWN_EXCEPTIONS == {"latex_tables_common.py"}
