from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app_desktop.ui_schema_binder import find_unbound_required_widgets


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def _combo_data(combo: Any) -> list[object]:
    return [combo.itemData(index) for index in range(combo.count())]


def test_error_formula_and_help_controls_have_schema_metadata(window: Any) -> None:
    assert window.formula_edit.property("datalab_schema_key") == "error.formula"
    assert window.formula_edit.property("datalab_schema_required") is True
    assert window.error_formula_preview_button.property("datalab_schema_key") == "error.formula"
    assert "x1" in window.formula_edit.placeholderText()
    assert window.formula_edit.toolTip()

    assert window.func_help_btn.property("datalab_schema_key") == "error.functions"
    assert window.func_help_btn.toolTip()


def test_error_constants_controls_have_schema_metadata_and_help(window: Any) -> None:
    assert window.use_constants_file_checkbox.property("datalab_schema_key") == "error.constants.use_file"
    assert window.use_constants_file_checkbox.toolTip()

    assert window.constants_file_edit.property("datalab_schema_key") == "error.constants.file_path"
    assert window.constants_hint_btn.property("datalab_schema_key") == "error.constants.file_path"
    assert window.constants_hint_btn.toolTip()

    assert window.error_constants_editor.property("datalab_schema_key") == "error.constants"
    assert window.error_constants_editor.property("datalab_schema_required") is False
    assert window.error_constants_editor.help_button.property("datalab_schema_key") == "error.constants"
    assert window.error_constants_editor.table_view.property("datalab_schema_key") is None
    assert window.error_constants_editor.text_view.property("datalab_schema_key") is None
    assert window.error_constants_editor.help_button.toolTip()
    assert window.error_constants_editor.checkbox.toolTip()


def test_error_method_and_parameter_controls_have_schema_metadata(window: Any) -> None:
    assert window.error_method_combo.property("datalab_schema_key") == "error.method"
    assert window.error_method_combo.property("datalab_schema_required") is True
    assert window.error_method_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.error_method_combo) == ["taylor", "monte_carlo"]

    assert window.error_order_spin.property("datalab_schema_key") == "error.taylor.order"
    assert window.error_order_spin.toolTip()
    assert window.error_mc_samples_spin.property("datalab_schema_key") == "error.monte_carlo.samples"
    assert window.error_mc_samples_spin.toolTip()
    assert window.error_mc_seed_edit.property("datalab_schema_key") == "error.monte_carlo.seed"
    assert window.error_mc_seed_edit.toolTip()
    assert window.error_mc_seed_edit.placeholderText()


def test_error_panel_has_no_unbound_required_schema_widgets(window: Any) -> None:
    assert find_unbound_required_widgets(window.error_box) == []


def test_error_schema_tooltips_and_choices_refresh_with_language(window: Any) -> None:
    window.error_method_combo.setCurrentIndex(window.error_method_combo.findData("monte_carlo"))

    window._apply_language("en")

    assert window.error_method_combo.currentData() == "monte_carlo"
    assert _combo_data(window.error_method_combo) == ["taylor", "monte_carlo"]
    assert "Enter the formula" in window.formula_edit.toolTip()
    assert "external constants file" in window.use_constants_file_checkbox.toolTip()
    assert "Optional constants" in window.error_constants_editor.help_button.toolTip()
    assert "Optional constants" in window.error_constants_editor.checkbox.toolTip()
    assert "Taylor propagates" in window.error_method_combo.toolTip()
    assert window.error_method_combo.itemText(window.error_method_combo.findData("taylor")) == "Taylor (derivative)"

    window._apply_language("zh")

    assert window.error_method_combo.currentData() == "monte_carlo"
    assert "输入要传播不确定度的公式" in window.formula_edit.toolTip()
    assert "外部常数文件" in window.use_constants_file_checkbox.toolTip()
    assert window.error_method_combo.itemText(window.error_method_combo.findData("taylor")) == "Taylor（偏导）"


def test_error_schema_bound_controls_keep_mode_and_constants_toggle_behavior(window: Any) -> None:
    window.show()
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    QApplication.processEvents()

    window.error_method_combo.setCurrentIndex(window.error_method_combo.findData("taylor"))
    QApplication.processEvents()
    assert window.error_taylor_widget.isVisible() or not window.error_mc_widget.isVisible()
    assert window.error_mc_samples_spin.isEnabled() is False
    assert window.error_mc_seed_edit.isEnabled() is False

    window.error_method_combo.setCurrentIndex(window.error_method_combo.findData("monte_carlo"))
    QApplication.processEvents()
    assert window.error_mc_samples_spin.isEnabled() is True
    assert window.error_mc_seed_edit.isEnabled() is True

    window.use_constants_file_checkbox.setChecked(True)
    QApplication.processEvents()
    assert window.constants_file_row.isVisible()
    assert not window.error_constants_editor.controls_widget.isVisible()

    window.use_constants_file_checkbox.setChecked(False)
    QApplication.processEvents()
    assert not window.constants_file_row.isVisible()
