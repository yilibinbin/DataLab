"""Input data + constants merged into sheet-like tabs (输入数据 / 常数).

The 常数 tab appears only in constant-using modes (error / custom-fit / implicit); other modes
show just 输入数据. Both underlying widgets stay alive (removeTab, not delete) so their state and
serialization are untouched.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app_desktop.window import ExtrapolationWindow


def _window(qtbot: Any) -> ExtrapolationWindow:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    return window


def _tab_titles(window: ExtrapolationWindow) -> list[str]:
    tabs = window.input_data_tabs
    return [tabs.tabText(i) for i in range(tabs.count())]


def test_input_and_constants_are_sheet_tabs(qtbot: Any) -> None:
    window = _window(qtbot)
    tabs = window.input_data_tabs
    assert tabs is not None
    # The 输入数据 tab hosts a self-contained container (file toggle + picker + manual table).
    assert tabs.indexOf(window._data_tab) != -1
    # The manual table lives inside that data tab.
    assert window.manual_box.parent() is window._data_tab


def test_constants_tab_only_in_constant_using_modes(qtbot: Any) -> None:
    window = _window(qtbot)

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    QApplication.processEvents()
    assert _tab_titles(window) == ["输入数据", "常数"]

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("statistics"))
    QApplication.processEvents()
    assert _tab_titles(window) == ["输入数据"]  # no constants tab

    # Switching back re-adds the constants tab; the editor widget is reused, not rebuilt.
    editor_before = window.input_constants_editor
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    QApplication.processEvents()
    assert _tab_titles(window) == ["输入数据", "常数"]
    assert window.input_constants_editor is editor_before


def test_each_tab_has_independent_data_file_toggle(qtbot: Any) -> None:
    """输入数据 and 常数 each have their own 使用数据文件 checkbox (independent), placed inside
    their tab (below the tab bar) — toggling one must not affect the other, and must not
    corrupt the inactive tab."""
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    QApplication.processEvents()

    # Both checkboxes exist and live inside their respective tabs.
    assert window.use_file_checkbox.parent() is window._data_tab
    assert window.use_constants_file_checkbox.parent() is window._constants_tab

    tabs = window.input_data_tabs
    tabs.setCurrentIndex(tabs.indexOf(window._constants_tab))
    QApplication.processEvents()
    window.use_constants_file_checkbox.setChecked(True)
    QApplication.processEvents()
    # Constants file picker un-hides (isHidden reflects explicit show/hide regardless of whether
    # the top-level window is shown); the data-file checkbox is untouched.
    assert window.constants_file_row.isHidden() is False
    assert window.use_file_checkbox.isChecked() is False


def test_constants_file_source_round_trips_in_workspace(qtbot: Any, tmp_path: Any) -> None:
    """Review S2: a file-backed constants workspace must reopen as file-backed. Restore used to
    unconditionally clear use_constants_file_checkbox → silent revert to manual constants."""
    from app_desktop import workspace_controller as wc

    consts = tmp_path / "consts.txt"
    consts.write_text("ALPHA 7.30(11)\n", encoding="utf-8")

    src = _window(qtbot)
    src.mode_combo.setCurrentIndex(src.mode_combo.findData("error"))
    QApplication.processEvents()
    src.use_constants_file_checkbox.setChecked(True)
    src.constants_file_edit.setText(str(consts))
    QApplication.processEvents()
    bundle = wc.capture_workspace(src, title="t")

    dst = _window(qtbot)
    dst.mode_combo.setCurrentIndex(dst.mode_combo.findData("error"))
    QApplication.processEvents()
    wc.restore_workspace(dst, bundle.manifest, bundle.attachments)
    QApplication.processEvents()
    assert dst.use_constants_file_checkbox.isChecked() is True
    assert dst.constants_file_edit.text() == str(consts)


def test_workspace_save_survives_missing_source_file(qtbot: Any) -> None:
    """Review P-A: saving a workspace whose data/constants file was deleted must not crash."""
    from app_desktop import workspace_controller as wc

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    QApplication.processEvents()
    window.use_file_checkbox.setChecked(True)
    window.data_file_edit.setText("/tmp/definitely_missing_datalab_file.csv")
    QApplication.processEvents()
    bundle = wc.capture_workspace(window, title="t")  # must not raise
    assert bundle is not None


def test_input_tabs_retranslate(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    window._apply_language("zh")
    QApplication.processEvents()
    assert _tab_titles(window) == ["输入数据", "常数"]
    window._apply_language("en")
    QApplication.processEvents()
    assert _tab_titles(window) == ["Data input", "Constants"]
