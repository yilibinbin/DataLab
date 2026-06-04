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


def test_extrapolation_method_and_help_have_schema_metadata(window: Any) -> None:
    assert window.method_combo.property("datalab_schema_key") == "extrapolation.method"
    assert window.method_combo.property("datalab_schema_required") is True
    assert window.method_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.method_combo) == [
        "power_law",
        "richardson",
        "shanks",
        "levin_u",
        "custom",
    ]

    assert window.method_help_btn.property("datalab_schema_key") == "extrapolation.method"
    assert window.method_help_btn.toolTip()


def test_extrapolation_custom_formula_controls_have_schema_metadata(window: Any) -> None:
    assert window.custom_formula_edit.property("datalab_schema_key") == "extrapolation.custom.formula"
    assert window.custom_formula_edit.property("datalab_schema_required") is True
    assert window.custom_formula_edit.toolTip()
    assert "A/B/C" in window.custom_formula_edit.toolTip()
    assert "(C - B)^2" in window.custom_formula_edit.placeholderText()

    assert window.custom_formula_preview_button.property("datalab_schema_key") == (
        "extrapolation.custom.formula"
    )
    assert window.custom_formula_preview_button.accessibleName() == "预览公式"
    assert "预览" in window.custom_formula_preview_button.toolTip()
    assert window.custom_formula_function_button.property("datalab_schema_key") == (
        "extrapolation.custom.functions"
    )
    assert window.custom_formula_function_button.toolTip()


def test_extrapolation_method_parameter_controls_have_schema_metadata(window: Any) -> None:
    assert [edit.property("datalab_schema_key") for edit in window.power_x_edits] == [
        "extrapolation.power_law.x1",
        "extrapolation.power_law.x2",
        "extrapolation.power_law.x3",
    ]
    for edit in window.power_x_edits:
        assert edit.property("datalab_schema_required") is True
        assert edit.toolTip()

    assert window.power_p_edit.property("datalab_schema_key") == "extrapolation.power_law.p"
    assert window.power_p_edit.property("datalab_schema_required") is False
    assert window.power_p_edit.placeholderText()
    assert window.power_seed_guesses_edit.property("datalab_schema_key") == (
        "extrapolation.power_law.seed_guesses"
    )

    assert window.richardson_p_spin.property("datalab_schema_key") == "extrapolation.richardson.p"

    assert window.levin_variant_combo.property("datalab_schema_key") == "extrapolation.levin.variant"
    assert window.levin_variant_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.levin_variant_combo) == ["u", "t", "v"]
    assert window.levin_order_spin.property("datalab_schema_key") == "extrapolation.levin.order"
    assert window.levin_weight_combo.property("datalab_schema_key") == "extrapolation.levin.weight"
    assert window.levin_weight_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.levin_weight_combo) == ["default", "reciprocal", "reciprocal_beta"]
    assert window.levin_beta_spin.property("datalab_schema_key") == "extrapolation.levin.beta"


def test_extrapolation_uncertainty_selector_has_schema_metadata(window: Any) -> None:
    assert window.uncertainty_combo.property("datalab_schema_key") == (
        "extrapolation.uncertainty.reference_column"
    )
    assert window.uncertainty_combo.property("datalab_schema_required") is False
    assert window.uncertainty_combo.toolTip()
    assert window.uncertainty_refresh_btn.property("datalab_schema_key") == (
        "extrapolation.uncertainty.reference_column"
    )
    assert window.uncertainty_refresh_btn.accessibleName() == "刷新不确定度列"


def test_extrapolation_schema_tooltips_and_choices_refresh_with_language(window: Any) -> None:
    window.method_combo.setCurrentIndex(window.method_combo.findData("levin_u"))
    window.levin_variant_combo.setCurrentIndex(window.levin_variant_combo.findData("t"))
    window.levin_weight_combo.setCurrentIndex(window.levin_weight_combo.findData("reciprocal_beta"))

    window._apply_language("en")

    assert window.method_combo.currentData() == "levin_u"
    assert window.method_combo.itemText(window.method_combo.findData("power_law")) == "Power-law (3-point)"
    assert window.levin_variant_combo.currentData() == "t"
    assert window.levin_variant_combo.itemText(window.levin_variant_combo.findData("u")) == "u (most common)"
    assert window.levin_weight_combo.currentData() == "reciprocal_beta"
    assert "Choose the extrapolation algorithm" in window.method_combo.toolTip()
    assert "Use A/B/C" in window.custom_formula_edit.toolTip()
    assert window.custom_formula_preview_button.accessibleName() == "Preview formula"
    assert "Rescan data" in window.uncertainty_refresh_btn.toolTip()
    assert window.uncertainty_refresh_btn.accessibleName() == "Refresh uncertainty columns"

    window._apply_language("zh")

    assert window.method_combo.currentData() == "levin_u"
    assert window.method_combo.itemText(window.method_combo.findData("power_law")) == "幂律外推(三点外推)"
    assert "选择外推算法" in window.method_combo.toolTip()
    assert "重新扫描数据" in window.uncertainty_refresh_btn.toolTip()


def test_extrapolation_panel_has_no_unbound_required_schema_widgets(window: Any) -> None:
    assert find_unbound_required_widgets(window.extrap_box) == []
