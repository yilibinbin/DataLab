from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QToolButton


def _button(window: Any, object_name: str) -> QToolButton:
    button = getattr(window, object_name, None)
    assert isinstance(button, QToolButton), object_name
    return button


def test_workbench_examples_and_docs_entrypoints_are_wired(qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    called: list[str] = []
    monkeypatch.setattr(window, "open_example_workspace", lambda *_args, **_kwargs: called.append("examples"))
    monkeypatch.setattr(window, "_show_docs", lambda *_args, **_kwargs: called.append("docs"))

    examples_button = _button(window, "open_examples_button")
    docs_button = _button(window, "docs_button")

    assert examples_button.toolTip()
    assert docs_button.toolTip()

    examples_button.click()
    docs_button.click()

    assert called == ["examples", "docs"]


def test_formula_help_entrypoints_exist_for_formula_workflows(qtbot: Any) -> None:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    for attr in (
        "custom_formula_function_button",
        "func_help_btn",
        "fit_func_help_btn",
    ):
        button = getattr(window, attr, None)
        assert button is not None, attr
        assert button.text().strip()
        assert button.toolTip() or button.accessibleDescription()
