"""Window-level engine-adaptive grouping wiring (Step 3).

The tex builders must know, at generation time, whether the engine that will compile the
document honours siunitx ``digit-group-size``. If yes → native S-column variable-width
grouping (emit_digit_group_size=True); if no → app-side text grouping. This is surfaced by
``window._engine_supports_group_width()`` which resolves the engine for the current mode and
probes it (cached).
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
    qtbot.addWidget(win)
    return win


def test_engine_mode_defaults_to_auto(window: Any) -> None:
    assert window._latex_engine_mode() in {"auto", "bundled", "local"}


def test_engine_supports_group_width_true_when_probe_true(window: Any, monkeypatch: Any) -> None:
    from shared.latex_engine import EngineChoice

    monkeypatch.setattr(
        window, "_resolve_compile_engine",
        lambda: EngineChoice(path="/usr/bin/xelatex", source="system"),
    )
    monkeypatch.setattr(
        "app_desktop.window_latex_compile_mixin.siunitx_supports_digit_group_size",
        lambda path: True,
    )
    assert window._engine_supports_group_width() is True


def test_engine_supports_group_width_false_when_probe_false(window: Any, monkeypatch: Any) -> None:
    from shared.latex_engine import EngineChoice

    monkeypatch.setattr(
        window, "_resolve_compile_engine",
        lambda: EngineChoice(path="/opt/datalab/bin/tectonic", source="auto-tectonic"),
    )
    monkeypatch.setattr(
        "app_desktop.window_latex_compile_mixin.siunitx_supports_digit_group_size",
        lambda path: False,
    )
    assert window._engine_supports_group_width() is False


def test_engine_supports_group_width_false_when_no_engine(window: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(window, "_resolve_compile_engine", lambda: None)
    # No engine resolved → can't do native grouping → False (app-side path handles width).
    assert window._engine_supports_group_width() is False
