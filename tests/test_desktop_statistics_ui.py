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


def test_statistics_inputs_have_schema_metadata(window: Any) -> None:
    assert window.stats_value_column_edit.property("datalab_schema_key") == "statistics.value_column"
    assert window.stats_value_column_edit.property("datalab_schema_required") is True
    assert window.stats_value_column_edit.toolTip()

    assert window.stats_sigma_column_edit.property("datalab_schema_key") == "statistics.sigma_column"
    assert window.stats_sigma_column_edit.property("datalab_schema_required") is False
    assert window.stats_sigma_column_edit.placeholderText()
    assert window.stats_sigma_column_edit.toolTip()


def test_statistics_mode_and_options_have_schema_metadata(window: Any) -> None:
    assert window.stats_mode_combo.property("datalab_schema_key") == "statistics.mode"
    assert window.stats_mode_combo.property("datalab_schema_required") is True
    assert window.stats_mode_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.stats_mode_combo) == ["mean", "weighted_sigma"]
    assert window.stats_mode_combo.toolTip()

    assert window.stats_weight_variance_checkbox.property("datalab_schema_key") == (
        "statistics.weight_variance"
    )
    assert window.stats_weight_variance_checkbox.property("datalab_schema_required") is False
    assert window.stats_weight_variance_checkbox.toolTip()

    assert window.stats_sample_checkbox.property("datalab_schema_key") == "statistics.sample_mode"
    assert window.stats_sample_checkbox.toolTip()


def test_statistics_schema_tooltips_and_choices_refresh_with_language(window: Any) -> None:
    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("weighted_sigma"))

    window._apply_language("en")

    assert window.stats_mode_combo.currentData() == "weighted_sigma"
    assert window.stats_mode_combo.itemText(window.stats_mode_combo.findData("mean")) == "Arithmetic mean"
    assert "Column containing measured values" in window.stats_value_column_edit.toolTip()
    assert "Optional uncertainty column" in window.stats_sigma_column_edit.toolTip()
    assert "Use sigma values" in window.stats_mode_combo.toolTip()

    window._apply_language("zh")

    assert window.stats_mode_combo.currentData() == "weighted_sigma"
    assert window.stats_mode_combo.itemText(window.stats_mode_combo.findData("mean")) == "算术平均"
    assert "数值数据所在列" in window.stats_value_column_edit.toolTip()
    assert "可选的不确定度列" in window.stats_sigma_column_edit.toolTip()


def test_statistics_panel_has_no_unbound_required_schema_widgets(window: Any) -> None:
    assert find_unbound_required_widgets(window.stats_box) == []
