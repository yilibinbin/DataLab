from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QStackedWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_mode_editors_reuse_existing_mode_stack_in_center_canvas(qtbot: Any) -> None:
    window = _window(qtbot)

    stack = window.mode_stack
    assert isinstance(stack, QStackedWidget)
    assert stack.parentWidget() is window.workbench_workspace_content
    # manual_box now lives inside the 输入数据 tab (_data_tab) after the sheet-tab restructure.
    assert window.manual_box.parentWidget() is window._data_tab
    assert stack.count() >= 5
    for widget in (window.extrap_box, window.error_box, window.fit_box, window.root_box, window.stats_box):
        assert stack.indexOf(widget) >= 0


def test_mode_stack_neither_clips_nor_gaps_across_modes(qtbot: Any) -> None:
    """Review S3: the mode_stack must be exactly the current page's height — no hollow gap on a
    short mode (error), and no clip on a mode whose config grows after layout (fitting →
    comparison reveals a candidate list). CurrentPageStack pins its height to the active page."""
    from PySide6.QtWidgets import QApplication

    window = _window(qtbot)
    window.resize(1600, 1400)
    window.show()
    stack = window.mode_stack

    def _measure(mode: str, sub: str | None = None) -> tuple[bool, int]:
        window.mode_combo.setCurrentIndex(window.mode_combo.findData(mode))
        QApplication.processEvents()
        if sub is not None and hasattr(window, "fit_model_combo"):
            window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData(sub))
            QApplication.processEvents()
        QApplication.processEvents()
        page = stack.currentWidget()
        clipped = page.height() < page.sizeHint().height()
        gap = stack.height() - page.sizeHint().height()
        return clipped, gap

    for mode in ("error", "statistics", "extrapolation"):
        clipped, gap = _measure(mode)
        assert not clipped and gap == 0, f"{mode}: clipped={clipped} gap={gap}"
    # The previously-clipped dynamic-growth case + re-sync back to a short mode.
    clipped, gap = _measure("fitting", "comparison")
    assert not clipped and gap == 0, f"comparison: clipped={clipped} gap={gap}"
    clipped, gap = _measure("error")
    assert not clipped and gap == 0, f"error after comparison: clipped={clipped} gap={gap}"


def test_mode_switch_updates_center_editor_without_losing_drafts(qtbot: Any) -> None:
    window = _window(qtbot)
    stack = window.mode_stack

    window.fit_expr_edit.setPlainText("A*x+B")
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()
    assert stack.currentWidget() is window.root_box

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()
    assert stack.currentWidget() is window.fit_box
    assert window.fit_expr_edit.toPlainText() == "A*x+B"


def test_no_second_editor_stack_is_created(qtbot: Any) -> None:
    window = _window(qtbot)
    assert window.findChild(QStackedWidget, "workbench_editor_stack") is None


def test_common_workbench_panels_track_mode_changes(qtbot: Any) -> None:
    window = _window(qtbot)

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    assert window.mode_stack.currentWidget() is window.root_box
    assert window.workbench_variable_stack.currentWidget().objectName() == "workbench_variable_page_root_solving"
    assert "root" in window.workbench_variable_stack.currentWidget().objectName()

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()

    assert window.mode_stack.currentWidget() is window.fit_box
    assert window.workbench_variable_stack.currentWidget().objectName() == "workbench_variable_page_fitting"


def test_common_workbench_panel_titles_refresh_on_language_change(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))

    window._apply_language("en")
    assert window.workbench_formula_panel_title.text() == "Formula preview"
    # Constants now live in the shared input-section editor, so the fitting
    # variable panel holds only parameter sections → title reads "Parameters".
    assert window.workbench_variable_title.text() == "Parameters"

    window._apply_language("zh")
    assert window.workbench_formula_panel_title.text() == "公式预览"
    assert window.workbench_variable_title.text() == "参数"
