from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame, QSizePolicy, QWidget

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
    assert window.stats_box.property("datalab_view_module") == "app_desktop.views.statistics"
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


def test_statistics_panel_uses_compact_workbench_card(window: Any) -> None:
    assert window.stats_box.objectName() == "statistics_mode_view"
    assert window.stats_box.property("datalab_statistics_panel") is True
    assert window.stats_box.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Maximum
    uncapped_widget = QWidget()
    assert window.stats_box.maximumHeight() == uncapped_widget.maximumHeight()

    card = window.stats_box.findChild(QFrame, "statistics_settings_card")

    assert card is not None
    assert card.property("datalab_workbench_section_role") == "statistics"
    card_children = card.findChildren(QWidget)
    assert window.stats_value_column_edit.parentWidget() is card or (
        window.stats_value_column_edit.parentWidget() in card_children
    )
    assert window.stats_mode_combo.parentWidget() is card or (
        window.stats_mode_combo.parentWidget() in card_children
    )


def test_workbench_section_card_helper_builds_localized_host(window: Any, qtbot: Any) -> None:
    from app_desktop.views import helpers as view_helpers

    section = view_helpers.make_workbench_section_card_view(
        window,
        object_name="test_mode_view",
        view_module="test.module",
        card_object_name="test_settings_card",
        role="test",
        title_zh="测试设置",
        title_en="Test settings",
        description_zh="选择测试参数。",
        description_en="Choose test parameters.",
        maximum_height=220,
    )
    qtbot.addWidget(section.host)

    assert section.host.objectName() == "test_mode_view"
    assert section.host.property("datalab_view_module") == "test.module"
    assert section.host.property("datalab_workbench_section_host") is True
    assert section.host.maximumHeight() == 220
    assert section.card.objectName() == "test_settings_card"
    assert section.card.property("datalab_workbench_section_role") == "test"
    assert section.title_label.text() == "测试设置"
    assert section.description_label.text() == "选择测试参数。"

    window._apply_language("en")

    assert section.title_label.text() == "Test settings"
    assert section.description_label.text() == "Choose test parameters."
