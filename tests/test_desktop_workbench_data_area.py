from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QTableWidgetItem


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_actual_data_editor_lives_in_center_workspace(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.input_section.parentWidget() is window.workbench_config_content
    assert window.manual_box.parentWidget() is window.workbench_workspace_content
    assert window.manual_table.parentWidget() is window._data_stack
    assert window.manual_data_edit.parentWidget() is window._data_stack
    assert window.file_box.parentWidget() is window.input_section


def test_manual_data_card_has_title_and_live_summary(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.manual_box.property("datalab_data_card") is True
    title = window.findChild(QLabel, "manual_data_title")
    summary = window.findChild(QLabel, "manual_data_summary")
    assert title is not None
    assert summary is not None
    assert title.text() in {"输入数据", "Data input"}
    assert "0" in summary.text()

    window.manual_table.setItem(0, 0, QTableWidgetItem("1.0"))
    QApplication.processEvents()

    assert "1" in summary.text()
    assert str(window.manual_table.columnCount()) in summary.text()


def test_manual_data_summary_refreshes_on_language_change(qtbot: Any) -> None:
    window = _window(qtbot)

    summary = window.findChild(QLabel, "manual_data_summary")
    assert summary is not None

    window._apply_language("zh")
    QApplication.processEvents()
    assert "行" in summary.text()
    assert "列" in summary.text()

    window._apply_language("en")
    QApplication.processEvents()
    assert "rows" in summary.text()
    assert "columns" in summary.text()


def test_manual_data_card_uses_shared_theme_and_compact_toolbar(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.manual_box.property("datalab_data_card") is True
    assert "QGroupBox#manual_box" in window.manual_box.styleSheet()
    assert "datalab_data_toolbar_button" in window.manual_box.styleSheet()

    buttons = [
        button
        for button in window.manual_box.findChildren(QPushButton)
        if button.property("datalab_data_toolbar_button") is True
    ]
    assert len(buttons) >= 6


def test_data_card_theme_refresh_does_not_recompute_summary(qtbot: Any, monkeypatch: Any) -> None:
    import app_desktop.panels as panels

    window = _window(qtbot)
    calls = 0

    def count_summary_refresh(owner: Any) -> None:
        nonlocal calls
        assert owner is window
        calls += 1

    monkeypatch.setattr(panels, "_update_data_summary", count_summary_refresh)

    window.refresh_workbench_data_card()
    assert calls == 0

    window.refresh_workbench_data_summary()
    assert calls == 1


def test_data_input_state_is_not_duplicated_or_mirrored(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.findChild(type(window.manual_table), "workbench_data_preview_table") is None
    window._data_view_toggle.click()
    QApplication.processEvents()
    assert window._data_stack.currentWidget() is window.manual_data_edit
    window._data_view_toggle.click()
    QApplication.processEvents()
    assert window._data_stack.currentWidget() is window.manual_table


def test_configuration_sections_stay_in_left_rail(qtbot: Any) -> None:
    window = _window(qtbot)
    assert window.mode_section.parentWidget() is window.workbench_config_content
    assert window.input_section.parentWidget() is window.workbench_config_content
    assert window.output_setup_section.parentWidget() is window.workbench_config_content
    assert window.run_section.parentWidget() is window.workbench_config_content
