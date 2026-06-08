from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


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
