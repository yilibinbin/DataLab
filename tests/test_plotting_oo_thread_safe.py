"""P2-7: internal plot rendering uses the object-oriented matplotlib API, not the
pyplot state machine.

The pyplot state machine (plt.subplots / plt.figure / plt.close) keeps a global
figure registry that is not thread-safe — a hazard since the desktop renders
plots on worker threads. The render helpers now build figures via
matplotlib.figure.Figure + FigureCanvasAgg. This test pins that no render helper
reaches back into pyplot, and that failures log instead of vanishing.
"""

from __future__ import annotations

import ast
from pathlib import Path

_PLOTTING = Path(__file__).resolve().parents[1] / "shared" / "plotting.py"


def _pyplot_calls_in_functions() -> list[str]:
    """Return `func:lineno` for every plt.<attr>() call inside a def body.

    plt stays importable/re-exported for external callers (e.g. the MCMC corner
    plot), so a bare `plt` reference is fine; what must not happen is an internal
    render helper *calling* the pyplot state machine.
    """
    tree = ast.parse(_PLOTTING.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and isinstance(inner.func.value, ast.Name)
                and inner.func.value.id == "plt"
            ):
                hits.append(f"{node.name}:{inner.lineno}")
    return hits


def test_no_render_helper_calls_the_pyplot_state_machine():
    hits = _pyplot_calls_in_functions()
    assert hits == [], f"pyplot state-machine calls inside functions (use the OO API): {hits}"


def test_new_figure_factory_uses_oo_api():
    text = _PLOTTING.read_text(encoding="utf-8")
    assert "_FigureCanvasAgg" in text and "_Figure(" in text
    assert "def _new_figure_ax(" in text


def test_plot_failures_are_logged_not_swallowed():
    # Every `except Exception: return None` in a render path should log first.
    text = _PLOTTING.read_text(encoding="utf-8")
    assert "_logger = logging.getLogger(__name__)" in text
    # No `except Exception:` immediately followed by a bare `return None` with no
    # logging line in between.
    lines = text.splitlines()
    for i, line in enumerate(lines[:-2]):
        if line.strip() == "except Exception:" and lines[i + 1].strip() == "return None":
            raise AssertionError(f"silent swallow at line {i + 1}: add a _logger call before return None")
