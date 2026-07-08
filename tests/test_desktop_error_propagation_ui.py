from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QFrame, QLineEdit, QMessageBox, QWidget

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
    assert window.error_box.property("datalab_view_module") == "app_desktop.views.error"
    assert window.formula_edit.property("datalab_schema_key") == "error.formula"
    assert window.formula_edit.property("datalab_schema_required") is True
    assert window.error_formula_preview_button.property("datalab_schema_key") == "error.formula"
    assert "x1" in window.formula_edit.placeholderText()
    assert window.formula_edit.toolTip()

    assert window.func_help_btn.property("datalab_schema_key") == "error.functions"
    assert window.func_help_btn.toolTip()


def test_error_panel_uses_workbench_section_card(window: Any) -> None:
    assert window.error_box.objectName() == "error_mode_view"
    assert window.error_box.property("datalab_view_module") == "app_desktop.views.error"
    assert window.error_box.property("datalab_workbench_section_host") is True

    card = window.error_box.findChild(QFrame, "error_settings_card")

    assert card is not None
    assert card.property("datalab_workbench_section_role") == "error"
    card_children = card.findChildren(QWidget)
    for widget in (
        window.error_method_combo,
        window.error_taylor_widget,
        window.error_mc_widget,
    ):
        assert widget.parentWidget() is card or widget.parentWidget() in card_children
    assert window.error_constants_editor is window.input_constants_editor
    assert window.error_constants_editor.parentWidget() is not card


def test_error_constants_controls_have_schema_metadata_and_help(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    QApplication.processEvents()

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


def test_unbound_required_schema_scan_discovers_qobject_children() -> None:
    QApplication.instance() or QApplication([])
    root = QWidget()
    child = QLineEdit(root)
    child.setProperty("datalab_schema_required", True)

    assert find_unbound_required_widgets(root) == [child]


def test_error_schema_tooltips_and_choices_refresh_with_language(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    window.error_method_combo.setCurrentIndex(window.error_method_combo.findData("monte_carlo"))
    QApplication.processEvents()

    window._apply_language("en")

    assert window.error_method_combo.currentData() == "monte_carlo"
    assert _combo_data(window.error_method_combo) == ["taylor", "monte_carlo"]
    assert "Enter the formula" in window.formula_edit.toolTip()
    assert "left input area" in window.error_constants_editor.help_button.toolTip()
    assert "left input area" in window.error_constants_editor.checkbox.toolTip()
    assert "Taylor propagates" in window.error_method_combo.toolTip()
    assert window.error_method_combo.itemText(window.error_method_combo.findData("taylor")) == "Taylor (derivative)"

    window._apply_language("zh")

    assert window.error_method_combo.currentData() == "monte_carlo"
    assert "输入要传播不确定度的公式" in window.formula_edit.toolTip()
    assert "左侧输入区" in window.error_constants_editor.help_button.toolTip()
    assert "左侧输入区" in window.error_constants_editor.checkbox.toolTip()
    assert window.error_method_combo.itemText(window.error_method_combo.findData("taylor")) == "Taylor（偏导）"


def test_error_schema_bound_controls_keep_mode_and_constants_toggle_behavior(window: Any) -> None:
    window.show()
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    QApplication.processEvents()

    window.error_method_combo.setCurrentIndex(window.error_method_combo.findData("taylor"))
    QApplication.processEvents()
    assert window.error_taylor_widget.isVisible() is True
    assert window.error_mc_widget.isVisible() is False
    assert window.error_mc_samples_spin.isEnabled() is False
    assert window.error_mc_seed_edit.isEnabled() is False

    window.error_method_combo.setCurrentIndex(window.error_method_combo.findData("monte_carlo"))
    QApplication.processEvents()
    assert window.error_mc_samples_spin.isEnabled() is True
    assert window.error_mc_seed_edit.isEnabled() is True

    window.error_constants_editor.set_rows([{"name": "K", "value": "2.0(1)"}])
    QApplication.processEvents()
    assert window.error_constants_editor.isChecked() is True
    # Constants now live on the 常数 sheet tab; activate it so its controls are visible.
    tabs = window.input_data_tabs
    tabs.setCurrentIndex(tabs.indexOf(window._constants_tab))
    QApplication.processEvents()
    assert window.error_constants_editor.controls_widget.isVisible()


def test_error_run_uses_sectioned_input_constants(window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop import window_extrapolation_mixin
    from app_desktop.workers_core import CalcJob

    class _Signal:
        def connect(self, callback: object) -> None:
            captured.setdefault("connections", []).append(callback)

        def disconnect(self, *_args: object) -> None:
            return

    class _DummyCalcWorker:
        finished_ok = _Signal()
        failed = _Signal()
        finished = _Signal()
        cancelled = _Signal()
        log_ready = _Signal()

        def __init__(self, job: CalcJob) -> None:
            captured["job"] = job

        def start(self) -> None:
            captured["started"] = True

        def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
            return False

        def request_stop(self) -> None:
            captured["stopped"] = True

    captured: dict[str, Any] = {}
    monkeypatch.setattr(window_extrapolation_mixin, "CalcWorker", _DummyCalcWorker)

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    window.formula_edit.setPlainText("A + K")
    window.manual_data_edit.setPlainText("[data]\nA\n1.0(1)\n\n[constants]\nK = 2.0(1)\n")
    window._data_stack.setCurrentIndex(1)
    window.error_constants_editor.set_rows([])

    window.run_calculation()

    job = captured["job"]
    assert captured["started"] is True
    assert job.mode == "error"
    assert job.manual_content == "A\n1.0(1)"
    assert job.constants_enabled is True
    assert job.manual_constants == "K = 2.0(1)"
    assert job.use_constants_file is False


def test_error_run_accepts_sectioned_file_input_constants(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    from app_desktop import window_extrapolation_mixin
    from app_desktop.workers_core import CalcJob

    class _Signal:
        def connect(self, callback: object) -> None:
            captured.setdefault("connections", []).append(callback)

        def disconnect(self, *_args: object) -> None:
            return

    class _DummyCalcWorker:
        finished_ok = _Signal()
        failed = _Signal()
        finished = _Signal()
        cancelled = _Signal()
        log_ready = _Signal()

        def __init__(self, job: CalcJob) -> None:
            captured["job"] = job

        def start(self) -> None:
            captured["started"] = True

        def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
            return False

        def request_stop(self) -> None:
            captured["stopped"] = True

    captured: dict[str, Any] = {}
    monkeypatch.setattr(window_extrapolation_mixin, "CalcWorker", _DummyCalcWorker)
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *_args, **_kwargs: captured.setdefault("critical", True),
    )
    sectioned_file = tmp_path / "sectioned.datalab.txt"
    sectioned_file.write_text(
        "[data]\n"
        "A\n"
        "1.0(1)\n"
        "\n"
        "[constants]\n"
        "K = 2.0(1)\n",
        encoding="utf-8",
    )

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    window.formula_edit.setPlainText("A + K")
    window.use_file_checkbox.setChecked(True)
    window.data_file_edit.setText(str(sectioned_file))
    window.error_constants_editor.set_rows([])

    window.run_calculation()

    assert "critical" not in captured
    job = captured["job"]
    assert captured["started"] is True
    assert job.mode == "error"
    assert job.data_path is None
    assert job.manual_content == "A\n1.0(1)"
    assert job.constants_enabled is True
    assert job.manual_constants == "K = 2.0(1)"
    assert job.use_constants_file is False
