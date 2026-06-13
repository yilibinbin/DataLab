from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame, QLabel, QWidget

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
    assert window.extrap_box.property("datalab_view_module") == "app_desktop.views.extrapolation"
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


def test_extrapolation_panel_uses_workbench_section_card(window: Any) -> None:
    assert window.extrap_box.objectName() == "extrapolation_mode_view"
    assert window.extrap_box.property("datalab_view_module") == "app_desktop.views.extrapolation"
    assert window.extrap_box.property("datalab_workbench_section_host") is True

    card = window.extrap_box.findChild(QFrame, "extrapolation_settings_card")

    assert card is not None
    assert card.property("datalab_workbench_section_role") == "extrapolation"
    card_children = card.findChildren(QWidget)
    for widget in (
        window.method_combo,
        window.extrap_method_stack,
        window.uncertainty_combo,
        window.uncertainty_refresh_btn,
    ):
        assert widget.parentWidget() is card or widget.parentWidget() in card_children


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


def test_extrapolation_custom_function_hint_refreshes_with_language(window: Any) -> None:
    def function_hint_texts() -> list[str]:
        return [
            label.text()
            for label in window.custom_formula_widget.findChildren(QLabel)
            if "Sin[x]" in label.text() or "Cos[x]" in label.text()
        ]

    assert any(text.startswith("支持") for text in function_hint_texts())

    window._apply_language("en")

    english_hints = function_hint_texts()
    assert any(text.startswith("Supports") for text in english_hints)
    assert all("支持" not in text for text in english_hints)

    window._apply_language("zh")

    chinese_hints = function_hint_texts()
    assert any(text.startswith("支持") for text in chinese_hints)


def test_desktop_extrapolation_method_options_are_read_from_controls() -> None:
    from types import SimpleNamespace

    from app_desktop.window_extrapolation_mixin import (
        _read_extrapolation_method_options_from_controls,
    )

    class Spin:
        def __init__(self, value: object) -> None:
            self._value = value

        def value(self) -> object:
            return self._value

    class Combo:
        def __init__(self, data: object) -> None:
            self._data = data

        def currentData(self) -> object:
            return self._data

    owner = SimpleNamespace(
        richardson_p_spin=Spin(3.5),
        levin_order_spin=Spin(4),
        levin_weight_combo=Combo("reciprocal_beta"),
        levin_beta_spin=Spin(2.75),
    )

    assert _read_extrapolation_method_options_from_controls(owner) == {
        "richardson_p": 3.5,
        "levin_order": 4,
        "levin_weight": "reciprocal_beta",
        "levin_beta": 2.75,
    }


def test_run_calculation_preserves_extrapolation_method_options_in_job(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_desktop import window_extrapolation_mixin
    from app_desktop.workers_core import CalcJob

    captured: dict[str, object] = {}

    class _Signal:
        def connect(self, _callback: object) -> None:
            return

    class _DummyCalcWorker:
        def __init__(self, job: CalcJob) -> None:
            captured["job"] = job
            self.finished_ok = _Signal()
            self.failed = _Signal()
            self.finished = _Signal()
            self.cancelled = _Signal()
            self.log_ready = _Signal()

        def start(self) -> None:
            captured["started"] = True

        def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
            return False

        def wait(self, _timeout: int | None = None) -> bool:
            return True

        def terminate(self) -> None:
            return None

        def deleteLater(self) -> None:  # noqa: N802 - Qt-style test double
            return None

    monkeypatch.setattr(window_extrapolation_mixin, "CalcWorker", _DummyCalcWorker)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("extrapolation"))
    window.method_combo.setCurrentIndex(window.method_combo.findData("levin_u"))
    window._data_stack.setCurrentIndex(1)
    window.manual_data_edit.setPlainText("A B C\n1 2 3\n2 3 4\n")
    window.richardson_p_spin.setValue(3.5)
    window.levin_order_spin.setValue(4)
    window.levin_weight_combo.setCurrentIndex(window.levin_weight_combo.findData("reciprocal_beta"))
    window.levin_beta_spin.setValue(2.75)

    window.run_calculation()

    job = captured["job"]
    assert captured["started"] is True
    assert isinstance(job, CalcJob)
    assert job.mode == "extrapolation"
    assert job.options.richardson_p == pytest.approx(3.5)
    assert job.options.levin_order == 4
    assert job.options.levin_weight == "reciprocal_beta"
    assert job.options.levin_beta == pytest.approx(2.75)


def test_extrapolation_panel_has_no_unbound_required_schema_widgets(window: Any) -> None:
    assert find_unbound_required_widgets(window.extrap_box) == []
