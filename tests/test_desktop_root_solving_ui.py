from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QPushButton, QWidget

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


def test_mode_combo_contains_root_solving(window: Any) -> None:
    assert "root_solving" in _combo_data(window.mode_combo)
    index = window.mode_combo.findData("root_solving")
    assert index >= 0

    window._apply_language("zh")
    assert window.mode_combo.itemText(window.mode_combo.findData("root_solving")) == "求根"
    window._apply_language("en")
    assert window.mode_combo.itemText(window.mode_combo.findData("root_solving")) == "Root solving"


def test_root_solving_page_has_required_widgets(window: Any) -> None:
    assert window.root_box.property("datalab_view_module") == "app_desktop.views.root_solving"
    required = [
        "root_equations_edit",
        "root_equations_help_button",
        "root_formula_preview_button",
        "root_mode_combo",
        "root_mode_help_button",
        "root_unknowns_table",
        "root_unknowns_help_button",
        "root_add_unknown_button",
        "root_remove_unknown_button",
        "root_detect_unknowns_button",
        "root_constants_editor",
    ]
    for name in required:
        assert hasattr(window, name), name

    assert _combo_data(window.root_mode_combo) == ["scalar", "scan_multiple", "polynomial", "system"]
    assert window.root_equations_edit.toPlainText() == ""
    assert "x^2 - A" in window.root_equations_edit.placeholderText()
    window._apply_language("zh")
    assert [
        window.root_unknowns_table.table_view.horizontalHeaderItem(index).text()
        for index in range(window.root_unknowns_table.table_view.columnCount())
    ] == ["名称", "初始值", "下界", "上界"]
    assert window.root_constants_editor.table_view.horizontalHeaderItem(0).text() == "名称"
    assert window.root_constants_editor.table_view.horizontalHeaderItem(1).text() == "值"
    window._apply_language("en")
    assert [
        window.root_unknowns_table.table_view.horizontalHeaderItem(index).text()
        for index in range(window.root_unknowns_table.table_view.columnCount())
    ] == ["Name", "Initial", "Lower", "Upper"]
    assert window.root_constants_editor.table_view.horizontalHeaderItem(0).text() == "Name"
    assert window.root_constants_editor.table_view.horizontalHeaderItem(1).text() == "Value"
    assert window.root_constants_editor.numeric_mode() == "uncertainty"
    assert window.root_constants_editor.isChecked() is False
    assert isinstance(window.root_formula_preview_button, QPushButton)
    assert window.root_constants_editor.help_button.text() == "?"
    assert window.root_equations_help_button.toolTip()
    assert window.root_mode_help_button.toolTip()
    assert window.root_unknowns_help_button.toolTip()
    assert window.root_equations_edit.toolTip()
    assert window.root_mode_combo.toolTip()
    assert window.root_unknowns_table.toolTip()
    assert window.root_constants_editor.toolTip()
    assert window.root_constants_editor.help_button.toolTip()
    assert window.root_constants_editor.checkbox.toolTip()
    assert window.root_detect_unknowns_button.toolTip()
    assert window.root_add_unknown_button.toolTip()
    assert window.root_remove_unknown_button.toolTip()


def test_root_panel_uses_workbench_section_card_for_mode_controls(window: Any) -> None:
    assert window.root_box.objectName() == "root_solving_mode_view"
    assert window.root_box.property("datalab_view_module") == "app_desktop.views.root_solving"
    assert window.root_box.property("datalab_workbench_section_host") is True

    card = window.root_box.findChild(QFrame, "root_solving_settings_card")

    assert card is not None
    assert card.property("datalab_workbench_section_role") == "root_solving"
    card_children = card.findChildren(QWidget)
    for widget in (
        window.root_mode_combo,
        window.root_uncertainty_group,
        window.root_uncertainty_method_combo,
    ):
        assert widget.parentWidget() is card or widget.parentWidget() in card_children


def test_root_controls_have_schema_bindings(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    assert window.root_equations_edit.property("datalab_schema_key") == "root.equations"
    assert window.root_equations_edit.property("datalab_schema_required") is True
    assert window.root_equations_help_button.property("datalab_schema_key") == "root.equations"

    assert window.root_mode_combo.property("datalab_schema_key") == "root.mode"
    assert window.root_mode_combo.property("datalab_schema_required") is True
    assert window.root_mode_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.root_mode_combo) == ["scalar", "scan_multiple", "polynomial", "system"]
    assert window.root_mode_help_button.property("datalab_schema_key") == "root.mode"

    assert window.root_unknowns_table.property("datalab_schema_key") == "root.unknowns"
    assert window.root_unknowns_table.property("datalab_schema_required") is True
    assert window.root_unknowns_help_button.property("datalab_schema_key") == "root.unknowns"

    assert window.root_constants_editor.property("datalab_schema_key") == "root.constants"
    assert window.root_constants_editor.property("datalab_schema_required") is False
    assert window.root_constants_editor.table_view.property("datalab_schema_key") is None
    assert window.root_units_enabled_checkbox.property("datalab_schema_key") == "root_solving.units.enabled"
    assert window.root_units_inputs_editor.property("datalab_schema_key") == "root_solving.units.inputs"
    assert window.root_units_constants_editor.property("datalab_schema_key") == "root_solving.units.constants"
    assert window.root_units_output_edit.property("datalab_schema_key") == "root_solving.units.outputs.result"
    assert window.root_units_body.isHidden()
    window.root_units_enabled_checkbox.setChecked(True)
    QApplication.processEvents()
    assert not window.root_units_body.isHidden()
    assert find_unbound_required_widgets(window.root_box) == []


def test_root_mode_empty_manual_table_defaults_to_one_column(window: Any) -> None:
    assert window.manual_table.columnCount() == 3

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    assert window.manual_table.columnCount() == 1
    assert window.manual_table.horizontalHeaderItem(0).text() == "A"

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("extrapolation"))
    QApplication.processEvents()

    assert window.manual_table.columnCount() == 3


def test_main_splitter_clamps_left_panel_to_config_minimum(window: Any) -> None:
    window.resize(1500, 920)
    window.show()
    QApplication.processEvents()

    splitter = window._main_splitter
    splitter.setSizes([1, 1179, 320])
    QApplication.processEvents()

    assert splitter.sizes()[0] >= window._main_splitter_left_min_width


def test_main_splitter_minimum_prevents_left_horizontal_scrollbar(window: Any) -> None:
    window.resize(1300, 790)
    window.show()
    QApplication.processEvents()

    for mode in ("extrapolation", "error", "fitting", "root_solving", "statistics"):
        window.mode_combo.setCurrentIndex(window.mode_combo.findData(mode))
        QApplication.processEvents()
        window._refresh_main_splitter_left_min_width()
        window._main_splitter.setSizes([1, 979, 320])
        QApplication.processEvents()

        horizontal_bar = window._left_scroll.horizontalScrollBar()
        assert window._main_splitter.sizes()[0] >= window._main_splitter_left_min_width
        assert horizontal_bar.maximum() == 0, mode
        assert not horizontal_bar.isVisible(), mode


def test_main_splitter_left_minimum_refreshes_after_mode_visibility(window: Any) -> None:
    window.resize(1500, 920)
    window.show()
    QApplication.processEvents()

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    left_scroll = window._left_scroll
    expected = max(
        320,
        window.left_container.minimumSizeHint().width(),
    ) + left_scroll.frameWidth() * 2 + left_scroll.verticalScrollBar().sizeHint().width()
    assert window._main_splitter_left_min_width == expected
    assert left_scroll.minimumWidth() == expected


def test_root_solving_page_has_uncertainty_controls(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))

    assert _combo_data(window.root_uncertainty_method_combo) == [
        "taylor",
        "monte_carlo",
        "off",
    ]
    assert "auto" not in _combo_data(window.root_uncertainty_method_combo)
    assert window.root_uncertainty_order_spin.minimum() == 1
    assert window.root_uncertainty_order_spin.maximum() == 2
    assert window.root_monte_carlo_samples_spin.minimum() == 100
    assert window.root_monte_carlo_samples_spin.maximum() == 50000
    assert window.root_monte_carlo_samples_spin.value() == 2000
    assert window.root_uncertainty_method_help_label.text()


def test_root_monte_carlo_controls_visible_only_for_monte_carlo(window: Any, qtbot: Any) -> None:
    window.show()
    qtbot.waitExposed(window)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    window.root_uncertainty_method_combo.setCurrentIndex(window.root_uncertainty_method_combo.findData("taylor"))
    QApplication.processEvents()
    assert window.root_uncertainty_taylor_widget.isVisible()
    assert not window.root_monte_carlo_samples_spin.isVisible()
    assert not window.root_monte_carlo_seed_edit.isVisible()

    window.root_uncertainty_method_combo.setCurrentIndex(
        window.root_uncertainty_method_combo.findData("monte_carlo")
    )
    QApplication.processEvents()
    assert not window.root_uncertainty_taylor_widget.isVisible()
    assert window.root_monte_carlo_samples_spin.isVisible()
    assert window.root_monte_carlo_seed_edit.isVisible()


def test_root_uncertainty_help_text_refreshes_on_language_change(window: Any) -> None:
    window.root_uncertainty_method_combo.setCurrentIndex(window.root_uncertainty_method_combo.findData("monte_carlo"))

    window._apply_language("en")
    assert window.root_uncertainty_method_help_label.text() == "Resolves roots from sampled uncertain inputs."

    window._apply_language("zh")
    assert window.root_uncertainty_method_help_label.text() == "对输入不确定度抽样后重新求根。"


def test_root_job_collects_uncertainty_options(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x^2 - C")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "2", "lower": "", "upper": ""}])
    window.root_constants_editor.set_rows([{"name": "C", "value": "4.0(2)"}])
    window.root_uncertainty_method_combo.setCurrentIndex(window.root_uncertainty_method_combo.findData("monte_carlo"))
    window.root_monte_carlo_samples_spin.setValue(123)
    window.root_monte_carlo_seed_edit.setText("5")

    job = window._build_root_solving_job(data_path=None, manual_content="")

    assert job.uncertainty_options == {
        "method": "monte_carlo",
        "taylor_order": 1,
        "monte_carlo_samples": 123,
        "monte_carlo_seed": "5",
    }


def test_root_job_honors_generate_plots_checkbox(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x**2 - 2")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "", "upper": ""}])

    window.generate_plots_checkbox.setChecked(False)
    disabled_job = window._build_root_solving_job(data_path=None, manual_content="")

    window.generate_plots_checkbox.setChecked(True)
    enabled_job = window._build_root_solving_job(data_path=None, manual_content="")

    assert disabled_job.render_plots is False
    assert enabled_job.render_plots is True


def test_root_solving_page_has_no_known_values_table(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))

    assert not hasattr(window, "root_known_values_table")
    assert not hasattr(window, "root_add_known_button")
    assert not hasattr(window, "root_remove_known_button")


def test_root_detect_unknowns_populates_table_from_expression_excluding_data_and_constants(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x**2 - A - C")
    window.root_unknowns_table.set_rows([])
    window.root_constants_editor.set_rows([{"name": "C", "value": "1"}])
    window.root_constants_editor.setChecked(True)
    window.manual_data_edit.setPlainText("A\n4.0(2)")
    window._data_stack.setCurrentIndex(1)

    window.root_detect_unknowns_button.click()

    assert window.root_unknowns_table.rows() == [
        {"name": "x", "initial": "", "lower": "", "upper": "", "source": "detected"}
    ]


def test_root_detect_unknowns_excludes_sectioned_input_constants(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x**2 - A - C")
    window.root_unknowns_table.set_rows([])
    window.root_constants_editor.set_rows([])
    window.manual_data_edit.setPlainText(
        "[data]\n"
        "A\n"
        "4.0(2)\n"
        "\n"
        "[constants]\n"
        "C = 1\n"
    )
    window._data_stack.setCurrentIndex(1)

    window.root_detect_unknowns_button.click()

    assert window.root_unknowns_table.rows() == [
        {"name": "x", "initial": "", "lower": "", "upper": "", "source": "detected"}
    ]


def test_root_detect_unknowns_preserves_header_only_data_columns(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x**2 - A")
    window.root_unknowns_table.set_rows([])
    window.manual_data_edit.setPlainText("A\n")
    window._data_stack.setCurrentIndex(1)

    window.root_detect_unknowns_button.click()

    assert window.root_unknowns_table.rows() == [
        {"name": "x", "initial": "", "lower": "", "upper": "", "source": "detected"}
    ]


def test_root_solving_job_uses_active_data_source_and_preserves_raw_cells(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x**2 - A")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "", "upper": ""}])
    window.root_mode_combo.setCurrentIndex(window.root_mode_combo.findData("scalar"))
    window.manual_data_edit.setPlainText("A\n4.0(2)\n9.00(3)")
    window._data_stack.setCurrentIndex(1)
    window.root_units_enabled_checkbox.setChecked(True)
    window.root_units_inputs_editor.set_rows([{"name": "A", "value": "m^2"}])
    window.root_units_output_edit.setText("m")

    job = window._build_root_solving_job(data_path=None, manual_content=window.manual_data_edit.toPlainText())

    assert job.data_headers == ("A",)
    assert job.data_rows == (("4.0(2)",), ("9.00(3)",))
    assert job.mode == "scalar"
    assert job.core_request is not None
    assert job.core_request.inputs["data_headers"] == ["A"]
    assert job.core_request.inputs["units"]["inputs"] == {"A": {"unit": "m^2"}}
    assert job.core_request.inputs["units"]["outputs"] == {"result": {"unit": "m"}}


def test_root_solving_job_uses_sectioned_input_constants(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x**2 - C")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "", "upper": ""}])
    window.root_mode_combo.setCurrentIndex(window.root_mode_combo.findData("scalar"))
    window.manual_data_edit.setPlainText(
        "[data]\n"
        "A\n"
        "4.0(2)\n"
        "\n"
        "[constants]\n"
        "C = 4.0(2)\n"
    )
    window._data_stack.setCurrentIndex(1)
    window.root_constants_editor.set_rows([])

    job = window._build_root_solving_job(data_path=None, manual_content=window.manual_data_edit.toPlainText())

    assert job.data_headers == ("A",)
    assert job.data_rows == (("4.0(2)",),)
    assert job.constants_enabled is True
    assert job.constants_rows == ({"name": "C", "value": "4.0(2)"},)
    assert job.constants_text == "C = 4.0(2)"
    assert job.core_request.inputs["data_rows"] == [["4.0(2)"]]
    assert job.core_request.inputs["mode"] == "scalar"


def test_root_solving_job_freezes_latex_settings(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x**2 - A")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "", "upper": ""}])
    window.manual_data_edit.setPlainText("A\n4.0(2)")
    window._data_stack.setCurrentIndex(1)
    window.caption_checkbox.setChecked(True)
    window.caption_edit.setText("Launch caption")
    window.latex_input_precision_spin.setValue(12)
    window.latex_group_size_spin.setValue(4)
    window.dcolumn_checkbox.setChecked(True)
    window._apply_language("en")

    job = window._build_root_solving_job(
        data_path=None,
        manual_content=window.manual_data_edit.toPlainText(),
        generate_latex=True,
        output_path="/tmp/root.tex",
    )

    assert job.latex_caption == "Launch caption"
    assert job.latex_digits == 12
    assert job.latex_group_size == 4
    assert job.latex_include_dcolumn is True
    assert job.latex_language == "en"


def test_root_result_clears_stale_plot_state(window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app_desktop.window_extrapolation_mixin.QMessageBox.information", lambda *args: None)
    window.result_plot_bytes = b"old"
    window._result_plot_base_pixmap = object()
    window.current_fit_figures = [object()]
    window.current_stats_figures = [object()]
    window.current_error_figures = [object()]
    window.current_extrap_figures = [object()]
    window._image_mode = "fit"

    window._on_root_solving_finished(
        {
            "markdown": "| root |\n|---|\n| 1 |",
            "csv_headers": ["root"],
            "csv_rows": [{"root": "1"}],
            "warnings": [],
        }
    )

    assert window.result_plot_bytes is None
    assert window._result_plot_base_pixmap is None
    assert window.current_fit_figures == []
    assert window.current_stats_figures == []
    assert window.current_error_figures == []
    assert window.current_extrap_figures == []
    assert window._image_mode is None
    assert window._csv_rows == [{"root": "1"}]


def test_root_result_displays_payload_plot_bytes(window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app_desktop.window_extrapolation_mixin.QMessageBox.information", lambda *args: None)
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\xf8\x0f"
        b"\x00\x01\x01\x01\x00\x18\xdd\x8d\xb0\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    window._on_root_solving_finished(
        {
            "markdown": "| root |\n|---|\n| 1 |",
            "csv_headers": ["root"],
            "csv_rows": [{"root": "1"}],
            "warnings": [],
            "plot_bytes": png,
        }
    )

    assert window.result_plot_bytes == png
    assert window._result_plot_base_pixmap is not None
    assert window._image_mode == "root_solving"


def test_root_solving_controls_mark_workspace_dirty(window: Any) -> None:
    window._workspace_dirty = False
    window.root_equations_edit.setPlainText("x - 1")
    QApplication.processEvents()
    assert window._workspace_dirty is True

    window._workspace_dirty = False
    window.root_mode_combo.setCurrentIndex(window.root_mode_combo.findData("scan_multiple"))
    QApplication.processEvents()
    assert window._workspace_dirty is True

    window._workspace_dirty = False
    window.root_unknowns_table.add_row({"name": "x", "initial": "1"})
    QApplication.processEvents()
    assert window._workspace_dirty is True

    window._workspace_dirty = False
    window.root_constants_editor.set_rows([{"name": "A", "value": "1.0"}])
    QApplication.processEvents()
    assert window._workspace_dirty is True


def test_root_solving_page_has_no_precision_or_backend_toggle(window: Any) -> None:
    forbidden = [
        "root_precision_spin",
        "root_mpmath_precision_spin",
        "root_backend_combo",
        "root_solver_backend_combo",
        "root_backend_toggle",
    ]

    for name in forbidden:
        assert not hasattr(window, name), name


def test_root_page_visible_only_in_root_mode(window: Any, qtbot: Any) -> None:
    window.show()
    qtbot.waitExposed(window)

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    assert window.root_box.isVisible()
    assert not window.fit_box.isVisible()
    assert not window.stats_box.isVisible()
    assert not window.error_box.isVisible()
    assert not window.extrap_box.isVisible()

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()

    assert not window.root_box.isVisible()
    assert window.fit_box.isVisible()


def test_root_formula_preview_uses_f_left_hand_side(window: Any, monkeypatch: pytest.MonkeyPatch, qtbot: Any) -> None:
    captured = []

    def fake_open(parent: Any, expression: str, lhs: str | None = None) -> None:
        captured.append((parent, expression, lhs))

    monkeypatch.setattr("app_desktop.views.root_solving.open_formula_preview_dialog", fake_open)
    window.root_equations_edit.setPlainText("x^2 - C\nx + y - 3")

    qtbot.mouseClick(window.root_formula_preview_button, Qt.MouseButton.LeftButton)

    assert captured == [(window, "x^2 - C\nx + y - 3", "F_i")]


def test_custom_and_root_detected_rows_use_same_helper(window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop.detected_rows_table import DetectedRowsController

    calls = []
    original = DetectedRowsController.set_detected_names

    def spy(self: Any, names: Any, *, keep_orphans: bool = True) -> set[str]:
        calls.append((self, tuple(names), keep_orphans))
        return original(self, names, keep_orphans=keep_orphans)

    monkeypatch.setattr(DetectedRowsController, "set_detected_names", spy)

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.fit_expr_edit.setPlainText("A*x + B")
    window.custom_param_refresh_btn.click()
    window.root_unknowns_table.set_detected_names(["x"], keep_orphans=False)

    assert calls == [
        (window.custom_params_table.detected_rows_controller, ("A", "B"), False),
        (window.root_unknowns_table.detected_rows_controller, ("x",), False),
    ]
    assert window.custom_params_table.rows() == [
        {"name": "A", "initial": "", "fixed": "", "min": "", "max": "", "source": "detected"},
        {"name": "B", "initial": "", "fixed": "", "min": "", "max": "", "source": "detected"},
    ]
    assert window.root_unknowns_table.rows() == [
        {"name": "x", "initial": "", "lower": "", "upper": "", "source": "detected"}
    ]


def test_edited_detected_parameter_row_becomes_manual_before_refresh(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.custom_params_table.set_detected_names(["A"], keep_orphans=False)

    item = window.custom_params_table.item(0, 0)
    assert item is not None
    item.setText("manual")
    window.custom_params_table.set_detected_names(["B"], keep_orphans=False)

    assert window.custom_params_table.rows() == [
        {"name": "B", "initial": "", "fixed": "", "min": "", "max": "", "source": "detected"},
        {"name": "manual", "initial": "", "fixed": "", "min": "", "max": ""},
    ]


def test_edited_detected_root_unknown_row_becomes_manual_before_refresh(window: Any) -> None:
    window.root_unknowns_table.set_detected_names(["x"], keep_orphans=False)

    item = window.root_unknowns_table.table_view.item(0, 0)
    assert item is not None
    item.setText("manual")
    window.root_unknowns_table.set_detected_names(["y"], keep_orphans=False)

    assert window.root_unknowns_table.rows() == [
        {"name": "y", "initial": "", "lower": "", "upper": "", "source": "detected"},
        {"name": "manual", "initial": "", "lower": "", "upper": ""},
    ]


def test_root_solving_run_uses_background_worker(window: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop import window_extrapolation_mixin
    from app_desktop.workers_core import RootSolvingJob

    class _Signal:
        def connect(self, callback: object) -> None:
            captured.setdefault("connections", []).append(callback)

        def disconnect(self, *_args: object) -> None:
            return

    class _DummyRootSolvingWorker:
        finished_ok = _Signal()
        failed = _Signal()
        finished = _Signal()
        cancelled = _Signal()
        log_ready = _Signal()

        def __init__(self, job: RootSolvingJob) -> None:
            captured["job"] = job

        def start(self) -> None:
            captured["started"] = True

        def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
            return False

        def request_stop(self) -> None:
            captured["stopped"] = True

    captured: dict[str, Any] = {}
    monkeypatch.setattr(window_extrapolation_mixin, "RootSolvingWorker", _DummyRootSolvingWorker)

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_equations_edit.setPlainText("x^2 - C")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "2", "lower": "", "upper": ""}])
    window.root_constants_editor.set_rows([{"name": "C", "value": "4.00000000000000000001(2)"}])
    window.root_constants_editor.setChecked(True)
    window.root_mode_combo.setCurrentIndex(window.root_mode_combo.findData("scalar"))
    window.uncertainty_digits_spin.setValue(3)
    window.manual_data_edit.setPlainText("A\n4.0(2)")
    window._data_stack.setCurrentIndex(1)

    window.run_calculation()

    job = captured["job"]
    assert isinstance(job, RootSolvingJob)
    assert captured["started"] is True
    assert job.equations == ("x^2 - C",)
    assert job.unknown_rows == ({"name": "x", "initial": "2", "lower": "", "upper": ""},)
    assert job.constants_enabled is True
    assert job.constants_rows == ({"name": "C", "value": "4.00000000000000000001(2)"},)
    assert job.data_headers == ("A",)
    assert job.data_rows == (("4.0(2)",),)
    assert job.mode == "scalar"
    assert job.uncertainty_digits == 3
