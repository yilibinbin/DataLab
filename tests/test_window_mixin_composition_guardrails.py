"""Batch-10 Stage 0 guardrails: structural invariants that make any future
``ExtrapolationWindow`` mixin split provably behavior-preserving.

These are pure characterization tests (no production change). Two external
adversarial reviews (Codex + Antigravity/Gemini) of the decomposition plan
identified the failure modes below; this file pins them so a split PR that would
trip one fails loudly instead of silently changing behavior.

See docs/BATCH10_WINDOW_DECOMPOSITION_PLAN.md.
"""

from __future__ import annotations

import os
from collections import defaultdict

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QMainWindow

from app_desktop.window import ExtrapolationWindow


def _window_mixins() -> list[type]:
    """The Window*Mixin classes composed into ExtrapolationWindow, in MRO order."""
    return [
        cls
        for cls in ExtrapolationWindow.__mro__
        if cls.__name__.startswith("Window") and cls.__name__.endswith("Mixin")
    ]


# --- Invariant 1: MRO snapshot (provider order is load-bearing) -----------------
# The Qt C++ bases MUST precede every mixin; a split must not re-order this.
_EXPECTED_MRO = [
    "ExtrapolationWindow",
    "QMainWindow",
    "QWidget",
    "QObject",
    "QPaintDevice",
    "Object",
    "WindowLatexPdfMixin",
    "WindowI18nMixin",
    "WindowImagesMixin",
    "WindowStatisticsMixin",
    "WindowDataMixin",
    "WindowFittingMixin",
    "WindowFittingResidualsMixin",
    "WindowFittingModelsMixin",
    "WindowFittingFormattersMixin",
    "WindowExtrapolationMixin",
    "object",
]


def test_extrapolation_window_mro_is_frozen():
    """A split that re-orders bases (or forgets a shim's sub-mixins) changes
    method-resolution precedence — freeze the full MRO. Update this list
    *deliberately* when intentionally adding/splitting a mixin."""
    actual = [c.__name__ for c in ExtrapolationWindow.__mro__]
    assert actual == _EXPECTED_MRO, (
        "ExtrapolationWindow MRO changed. If this is an intentional mixin "
        "split/reorder, update _EXPECTED_MRO; otherwise the change silently "
        "alters method precedence.\n"
        f"expected: {_EXPECTED_MRO}\nactual:   {actual}"
    )


# --- Invariant 2: Qt bases sit before the mixins (severance hazard) --------------
def test_qt_bases_precede_all_mixins_in_mro():
    """QMainWindow (a C++ wrapper that does NOT cooperatively call super())
    precedes every mixin, so a Qt event override placed in a mixin would be
    silently unreachable. This test documents that ordering so the next guard
    (no Qt-event overrides in mixins) is meaningful."""
    names = [c.__name__ for c in ExtrapolationWindow.__mro__]
    qmain = names.index("QMainWindow")
    first_mixin = min(
        (i for i, n in enumerate(names) if n.startswith("Window") and n.endswith("Mixin")),
        default=len(names),
    )
    assert qmain < first_mixin, "QMainWindow must precede the mixins in the MRO"


# --- Invariant 3: no mixin overrides a Qt event handler -------------------------
_QT_EVENT_HANDLERS = frozenset(n for n in dir(QMainWindow) if n.endswith("Event"))


def test_no_mixin_overrides_a_qt_event_handler():
    """A mixin that defines e.g. closeEvent/resizeEvent/showEvent would be
    silently ignored (Qt C++ base severs the cooperative-super chain). Forbid it
    so a split can't accidentally move Qt event handling into a mixin (Gemini)."""
    offenders = []
    for cls in _window_mixins():
        for name in cls.__dict__:
            if name in _QT_EVENT_HANDLERS:
                offenders.append(f"{cls.__name__}.{name}")
    assert offenders == [], (
        "Window mixins must not override Qt event handlers (unreachable through "
        f"the Qt C++ base). Offenders: {offenders}"
    )


# --- Invariant 4: no unexpected duplicate method names across sibling mixins ------
# Splitting a monolith bottom->top and composing Shim(A_top, B, C_bottom) reverses
# shadowing precedence (A shadows C under left-to-right MRO). Any duplicate method
# name across mixins is therefore a precedence hazard — allow only the KNOWN,
# intentional shim override, fail on anything new (Codex + Gemini).
_ALLOWED_DUP_METHODS = {
    # The fitting shim intentionally overrides this: it calls super() then adds
    # fallback-history UI (window_fitting_mixin.py). Both the shim and the
    # residuals sub-mixin define it, by design.
    "_on_fit_finished": {"WindowFittingMixin", "WindowFittingResidualsMixin"},
}


def test_no_unexpected_duplicate_method_names_across_mixins():
    owners: dict[str, set[str]] = defaultdict(set)
    for cls in _window_mixins():
        for name, val in cls.__dict__.items():
            if callable(val) and not name.startswith("__"):
                owners[name].add(cls.__name__)
    dups = {n: cs for n, cs in owners.items() if len(cs) > 1}
    unexpected = {n: cs for n, cs in dups.items() if _ALLOWED_DUP_METHODS.get(n) != cs}
    assert unexpected == {}, (
        "Unexpected method-name collision across sibling window mixins — under "
        "left-to-right MRO the earlier mixin shadows the later one, which a "
        "split can silently reverse. Resolve the collision or, if intentional, "
        f"add it to _ALLOWED_DUP_METHODS. Collisions: {unexpected}"
    )


# --- Invariant 5: split mixins define no __init__ (construction order) ----------
def test_window_mixins_do_not_define_init():
    """Mixins must not define __init__ — ExtrapolationWindow.__init__ drives
    construction, and a mixin __init__ would either be skipped or fight the Qt
    base's construction order. A split must keep pulling all setup from the
    window's own __init__ (Codex/Gemini Stage-0 check)."""
    offenders = [cls.__name__ for cls in _window_mixins() if "__init__" in cls.__dict__]
    assert offenders == [], f"Window mixins must not define __init__: {offenders}"


# --- Invariant 6: internal helpers imported by tests stay importable -------------
# Splits must re-export moved internals from their original module, or these
# direct imports (in the test suite) break. Enumerated so a split is forced to
# preserve them (Codex).
def test_directly_imported_mixin_internals_remain_importable():
    from app_desktop.window_statistics_mixin import (  # noqa: F401
        _statistics_raw_table_preserving_cells,
    )
