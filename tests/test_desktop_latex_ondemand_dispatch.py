"""On-demand LaTeX dispatcher (4·3): generate_latex_for_current_result() routes to the
per-mode builder based on which result is current, and returns None when nothing is stashed.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("en")
    qtbot.addWidget(win)
    return win


def test_dispatch_returns_none_when_nothing_stashed(window: Any) -> None:
    window._last_latex_inputs = {}
    assert window.generate_latex_for_current_result() is None


def test_dispatch_routes_to_statistics_builder(window: Any, monkeypatch: Any) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        window, "generate_statistics_latex_on_demand", lambda: called.append("stats") or "/tmp/s.tex"
    )
    window._last_latex_inputs = {"statistics": {"display_batches": [{}]}}
    result = window.generate_latex_for_current_result()
    assert called == ["stats"]
    assert result == "/tmp/s.tex"


def test_dispatch_routes_to_fitting_builder(window: Any, monkeypatch: Any) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        window, "generate_fitting_latex_on_demand", lambda: called.append("fit") or "/tmp/f.tex"
    )
    window._last_latex_inputs = {"fit_single": {"fit_result": object()}}
    result = window.generate_latex_for_current_result()
    assert called == ["fit"]
    assert result == "/tmp/f.tex"


def test_dispatch_prefers_the_current_result_kind(window: Any, monkeypatch: Any) -> None:
    """If multiple stashes linger, dispatch by the CURRENT result kind."""
    monkeypatch.setattr(window, "generate_root_latex_on_demand", lambda: "/tmp/root.tex")
    monkeypatch.setattr(window, "generate_extrapolation_latex_on_demand", lambda: "/tmp/ex.tex")
    window._last_latex_inputs = {"root_solving": {"raw_rows": []}, "extrapolation": {"headers": []}}
    window._last_result_kind = "extrapolation"
    assert window.generate_latex_for_current_result() == "/tmp/ex.tex"
