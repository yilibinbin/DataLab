from __future__ import annotations

import base64

import mpmath as mp
import pytest
from PySide6.QtWidgets import QTableWidgetItem

from fitting.hp_fitter import FitResult


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _set_combo_data(combo, value: str) -> None:
    idx = combo.findData(value)
    assert idx >= 0
    combo.setCurrentIndex(idx)


def _sample_fit_result() -> FitResult:
    return FitResult(
        params={"a_b": mp.mpf("1.5")},
        param_errors={"a_b": mp.mpf("0.1")},
        chi2=mp.mpf("1.0"),
        reduced_chi2=mp.mpf("1.0"),
        aic=mp.mpf("1.0"),
        bic=mp.mpf("1.0"),
        r2=mp.mpf("0.9"),
        rmse=mp.mpf("0.01"),
        residuals=[mp.mpf("0.0")],
        fitted_curve=[mp.mpf("0.0")],
        covariance=[[mp.mpf("0.01")]],
        param_errors_total={"a_b": mp.mpf("0.1")},
        details={
            "equation": r"a_b + c% & # \\ x",
            "output_expression": r"u_out & y",
        },
    )


def test_workspace_controller_captures_manual_state(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace
    from shared.workspace_schema import compute_workspace_hash, sha256_bytes

    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    _set_combo_data(win.mode_combo, "fitting")
    win.manual_table.setRowCount(1)
    win.manual_table.setColumnCount(2)
    win.manual_table.setHorizontalHeaderLabels(["x", "y"])
    win.manual_table.setItem(0, 0, QTableWidgetItem("1"))
    win.manual_table.setItem(0, 1, QTableWidgetItem("2"))
    win.error_constants_editor.setChecked(True)
    win.error_constants_editor.set_rows([{"name": "ALPHA", "value": "7.29e-3"}])
    win.fit_expr_edit.setPlainText("A*x + B")
    win.fit_target_edit.setText("y")
    win.result_edit.setPlainText("Fit complete")
    win.log_edit.setPlainText("done")
    win.latex_edit.setPlainText("\\begin{table}\\end{table}")
    win._set_csv_data([{"name": "A", "value": "1.0"}], ["name", "value"], "fit.csv")
    win.result_plot_bytes = PNG_1X1

    bundle = capture_workspace(win, title="case")
    workspace = bundle.manifest["workspace"]

    assert workspace["title"] == "case"
    assert workspace["current_mode"] == "fitting"
    assert workspace["data"]["canonical_table"]["headers"] == ["x", "y"]
    assert workspace["data"]["canonical_table"]["rows"] == [["1", "2"]]
    assert workspace["constants"]["enabled"] is True
    assert workspace["config"]["fitting"]["expression"] == "A*x + B"
    assert workspace["config"]["fitting"]["target_column"] == "y"
    assert workspace["result_snapshot"]["present"] is True
    assert workspace["result_snapshot"]["result_of_hash"] == compute_workspace_hash(workspace)
    assert workspace["result_snapshot"]["plots"][0]["sha256"] == sha256_bytes(PNG_1X1)
    assert bundle.attachments["attachments/plots/plot-001.png"] == PNG_1X1


def test_workspace_preserves_raw_constants_text_view_draft(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    raw_text = "# note\nALPHA 1\n\nBETA 2\n"
    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.error_constants_editor.setChecked(True)
    source.error_constants_editor.set_text(raw_text)
    source.error_constants_editor.use_text_view(True)

    bundle = capture_workspace(source, title="raw constants")
    assert bundle.manifest["workspace"]["constants"]["decoded_text"] == raw_text

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.error_constants_editor.using_text_view()
    assert target.error_constants_editor.raw_text() == raw_text
    assert target.error_constants_editor.rows() == [
        {"name": "ALPHA", "value": "1"},
        {"name": "BETA", "value": "2"},
    ]


def test_workspace_preserves_disabled_error_constants_draft(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    raw_text = "# inactive draft\nBETA = 2\n"
    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.error_constants_editor.setChecked(True)
    source.error_constants_editor.set_text(raw_text)
    source.error_constants_editor.set_rows([{"name": "ALPHA", "value": "1"}])
    source.error_constants_editor.use_text_view(False)
    source.error_constants_editor.setChecked(False)

    bundle = capture_workspace(source, title="disabled constants")
    constants = bundle.manifest["workspace"]["constants"]

    assert constants["enabled"] is False
    assert constants["active_view"] == "table"
    assert constants["decoded_text"] == raw_text
    assert constants["canonical_table"]["rows"] == [["ALPHA", "1"]]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.error_constants_editor.isChecked() is False
    assert target.error_constants_editor.using_text_view() is False
    assert target.error_constants_editor.raw_text() == raw_text
    assert target.error_constants_editor.rows() == [{"name": "ALPHA", "value": "1"}]


def test_workspace_controller_restores_snapshot_without_live_payloads(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    source.manual_table.setRowCount(1)
    source.manual_table.setColumnCount(2)
    source.manual_table.setHorizontalHeaderLabels(["x", "y"])
    source.manual_table.setItem(0, 0, QTableWidgetItem("1"))
    source.manual_table.setItem(0, 1, QTableWidgetItem("2"))
    source.fit_expr_edit.setPlainText("A*x + B")
    source.fit_target_edit.setText("y")
    source.result_edit.setPlainText("Fit complete")
    source.log_edit.setPlainText("done")
    source.latex_edit.setPlainText("\\begin{table}\\end{table}")
    source._remember_last_result("fit_single", {"not": "serializable"})
    source._set_csv_data([{"name": "A", "value": "1.0"}], ["name", "value"], "fit.csv")
    source.result_plot_bytes = PNG_1X1
    bundle = capture_workspace(source, title="case")

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.windowTitle().startswith("DataLab")
    assert target.result_edit.toPlainText() == "Fit complete"
    assert target.log_edit.toPlainText() == "done"
    assert target.latex_edit.toPlainText() == "\\begin{table}\\end{table}"
    assert target._csv_rows == [{"name": "A", "value": "1.0"}]
    assert target._csv_headers == ["name", "value"]
    assert target.result_plot_bytes == PNG_1X1
    assert getattr(target, "_last_result_payloads", {}) == {}
    assert getattr(target, "_workspace_snapshot_only", False) is True
    assert target.export_csv_btn.isEnabled()
    assert not target.scientific_checkbox.isEnabled()
    assert not target.display_digits_spin.isEnabled()


def test_workspace_preserves_rendered_result_markdown_table(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    markdown = "\n".join(
        [
            "## Fit Results",
            "",
            "| Parameter | Value ± Error |",
            "| --- | --- |",
            "| a | 1.23 ± 0.04 |",
        ]
    )
    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._set_result_text(markdown)

    bundle = capture_workspace(source, title="rendered result")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]

    assert snapshot["markdown"] == markdown
    assert snapshot["markdown_format"] == "markdown"

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert "<table" in target.result_edit.toHtml()
    assert "Parameter" in target.result_edit.toPlainText()
    assert "| Parameter |" not in target.result_edit.toPlainText()


def test_workspace_capture_ignores_stale_result_markdown_cache(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._set_result_text("| A | B |\n| --- | --- |\n| x | y |")
    source.result_edit.setPlainText("plain replacement")

    bundle = capture_workspace(source, title="plain result")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]

    assert snapshot["markdown"] == "plain replacement"
    assert snapshot["markdown_format"] == "plain"


def test_workspace_save_and_open_round_trip_file(qtbot, tmp_path) -> None:
    from app_desktop.window import ExtrapolationWindow

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    source.manual_table.setRowCount(1)
    source.manual_table.setColumnCount(2)
    source.manual_table.setHorizontalHeaderLabels(["x", "y"])
    source.manual_table.setItem(0, 0, QTableWidgetItem("1"))
    source.manual_table.setItem(0, 1, QTableWidgetItem("2"))
    source.fit_expr_edit.setPlainText("A*x + B")
    source.fit_target_edit.setText("y")
    source.result_edit.setPlainText("Fit complete")
    source._set_csv_data([{"name": "A", "value": "1.0"}], ["name", "value"], "fit.csv")

    path = tmp_path / "case.datalab"
    assert source._save_workspace_to_path(path)
    assert source.windowTitle() == "DataLab - case.datalab"

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    assert target._open_workspace_from_path(path)

    assert target.windowTitle() == "DataLab - case.datalab"
    assert target.result_edit.toPlainText() == "Fit complete"
    assert target._csv_rows == [{"name": "A", "value": "1.0"}]
    assert target._workspace_snapshot_only is True
    assert not target.display_digits_spin.isEnabled()


def test_workspace_restore_old_fitting_config_without_implicit(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    source.custom_params_table.set_rows([{"name": "A", "initial": "1.0"}])
    source._reset_variable_rows(default_var="x", default_column="A")
    bundle = capture_workspace(source, title="old")
    fitting = bundle.manifest["workspace"]["config"]["fitting"]
    fitting.pop("implicit", None)

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.custom_params_table.rows() == [{"name": "A", "initial": "1.0", "fixed": "", "min": "", "max": ""}]
    assert target.implicit_variable_edit.text() == "u"
    assert target.implicit_equation_edit.toPlainText() == "a + b*Cos[u] + c*x"
    assert target.implicit_output_edit.toPlainText() == "u"
    assert [(row[0].text(), row[1].text()) for row in target.variable_rows] == [("x", "A")]


def test_workspace_restore_rejects_malformed_custom_parameter_rows(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    source.custom_params_table.set_rows([{"name": "A", "initial": "1.0"}])
    bundle = capture_workspace(source, title="malformed custom params")
    bundle.manifest["workspace"]["config"]["fitting"]["parameter_rows"] = [
        {"name": "A", "initial": "1.0"},
        "bad-row",
    ]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    with pytest.raises(ValueError, match="Parameter rows.*row 2|第 2 行"):
        restore_workspace(target, bundle.manifest, bundle.attachments)


def test_workspace_restore_rejects_malformed_custom_parameter_rows_top_level(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    source.custom_params_table.set_rows([{"name": "A", "initial": "1.0"}])
    bundle = capture_workspace(source, title="malformed custom params")
    bundle.manifest["workspace"]["config"]["fitting"]["parameter_rows"] = "bad-rows"

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    with pytest.raises(ValueError, match="Parameter rows.*list|必须是行对象列表"):
        restore_workspace(target, bundle.manifest, bundle.attachments)


def test_workspace_restore_rejects_malformed_implicit_constants(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    source.implicit_constants_editor.setChecked(True)
    source.implicit_constants_editor.set_rows([{"name": "K", "value": "1"}])
    bundle = capture_workspace(source, title="malformed implicit constants")
    bundle.manifest["workspace"]["config"]["fitting"]["implicit"]["constants"] = [
        {"name": "K", "value": "1"},
        3,
    ]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    with pytest.raises(ValueError, match="Constant rows.*row 2|第 2 行"):
        restore_workspace(target, bundle.manifest, bundle.attachments)


def test_custom_fit_config_uses_parameter_table_and_constants_editor(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow

    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    _set_combo_data(win.mode_combo, "fitting")
    _set_combo_data(win.fit_model_combo, "custom")
    win.fit_expr_edit.setPlainText("A*x + B + K")
    win.custom_constants_editor.setChecked(True)
    win.custom_constants_editor.set_rows([{"name": "K", "value": "1"}])
    win.custom_params_table.set_rows(
        [
            {"name": "A", "initial": "2"},
            {"name": "B", "fixed": "3"},
        ]
    )
    win.custom_constraints_checkbox.setChecked(True)

    config = win._collect_custom_fit_config(validate_parameters=True)

    assert config["parameter_names"] == ["A", "B"]
    assert config["parameter_config"] == {
        "A": {"initial": "2"},
        "B": {"fixed": "3"},
    }
    assert config["constants"] == {"K": "1"}


def test_workspace_preserves_custom_fit_parameters_and_constants(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "custom")
    source.fit_expr_edit.setPlainText("A*x + K")
    source.custom_constraints_checkbox.setChecked(True)
    source.custom_params_table.set_rows([{"name": "A", "initial": "2", "min": "0"}])
    source.custom_constants_editor.setChecked(True)
    source.custom_constants_editor.set_text("# draft\nK = 1\n")
    source.custom_constants_editor.use_text_view(True)

    bundle = capture_workspace(source, title="custom constants")
    fitting = bundle.manifest["workspace"]["config"]["fitting"]

    assert fitting["custom_constants"] == {
        "enabled": True,
        "view": "text",
        "rows": [{"name": "K", "value": "1"}],
        "text": "# draft\nK = 1\n",
    }

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.fit_expr_edit.toPlainText() == "A*x + K"
    assert target.custom_constraints_checkbox.isChecked() is True
    assert target.custom_params_table.rows() == [
        {"name": "A", "initial": "2", "fixed": "", "min": "0", "max": ""}
    ]
    assert target.custom_constants_editor.isChecked() is True
    assert target.custom_constants_editor.using_text_view() is True
    assert target.custom_constants_editor.raw_text() == "# draft\nK = 1\n"
    assert target.custom_constants_editor.rows() == [{"name": "K", "value": "1"}]


def test_workspace_restore_enables_custom_constraints_before_parameter_rows(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "custom")
    source.fit_expr_edit.setPlainText("A*x")
    source.custom_constraints_checkbox.setChecked(True)
    source.custom_params_table.set_rows([{"name": "A", "initial": "2", "min": "0", "max": "5"}])

    bundle = capture_workspace(source, title="legacy custom constraints")
    fitting = bundle.manifest["workspace"]["config"]["fitting"]
    fitting.pop("constraints_enabled", None)

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.custom_constraints_checkbox.isChecked() is True
    assert target.custom_params_table.rows() == [
        {"name": "A", "initial": "2", "fixed": "", "min": "0", "max": "5"}
    ]


def test_workspace_restore_enables_custom_constraints_for_legacy_parameter_list(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "custom")
    source.fit_expr_edit.setPlainText("A*x")

    bundle = capture_workspace(source, title="legacy list constraints")
    fitting = bundle.manifest["workspace"]["config"]["fitting"]
    fitting.pop("constraints_enabled", None)
    fitting.pop("parameter_rows", None)
    fitting["parameters"] = [{"name": "A", "initial": "2", "min": "0", "max": "5"}]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.custom_constraints_checkbox.isChecked() is True
    assert target.custom_params_table.rows() == [
        {"name": "A", "initial": "2", "fixed": "", "min": "0", "max": "5"}
    ]


def test_workspace_preserves_custom_constants_table_rows(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "custom")
    source.custom_constants_editor.setChecked(True)
    source.custom_constants_editor.set_rows([{"name": "K", "value": "1"}])

    bundle = capture_workspace(source, title="custom constants table")
    fitting = bundle.manifest["workspace"]["config"]["fitting"]

    assert fitting["custom_constants"]["view"] == "table"
    assert fitting["custom_constants"]["rows"] == [{"name": "K", "value": "1"}]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.custom_constants_editor.isChecked() is True
    assert target.custom_constants_editor.using_text_view() is False
    assert target.custom_constants_editor.rows() == [{"name": "K", "value": "1"}]


def test_workspace_preserves_custom_constants_table_view_raw_text_draft(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    raw_text = "# inactive custom draft\nK = 2\n"
    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "custom")
    source.custom_constants_editor.setChecked(True)
    source.custom_constants_editor.set_text(raw_text)
    source.custom_constants_editor.set_rows([{"name": "K", "value": "1"}])
    source.custom_constants_editor.use_text_view(False)

    bundle = capture_workspace(source, title="custom constants table raw text")
    fitting = bundle.manifest["workspace"]["config"]["fitting"]

    assert fitting["custom_constants"] == {
        "enabled": True,
        "view": "table",
        "rows": [{"name": "K", "value": "1"}],
        "text": raw_text,
    }

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.custom_constants_editor.isChecked() is True
    assert target.custom_constants_editor.using_text_view() is False
    assert target.custom_constants_editor.rows() == [{"name": "K", "value": "1"}]
    assert target.custom_constants_editor.raw_text() == raw_text


def test_workspace_capture_preserves_incomplete_implicit_config(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    source.implicit_variable_edit.setText("bad-name")
    source.implicit_equation_edit.setPlainText("")
    source.implicit_output_edit.setPlainText("u")

    bundle = capture_workspace(source, title="draft")
    implicit = bundle.manifest["workspace"]["config"]["fitting"]["implicit"]

    assert implicit["implicit_variable"] == "bad-name"
    assert implicit["equation"] == ""
    assert implicit["output_expression"] == "u"


def test_workspace_capture_preserves_incomplete_implicit_constants(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    source.implicit_constants_editor.set_rows([{"name": "K", "value": ""}])

    bundle = capture_workspace(source, title="draft")
    implicit = bundle.manifest["workspace"]["config"]["fitting"]["implicit"]

    assert implicit["constants"] == [{"name": "K", "value": ""}]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.implicit_constants_editor.rows()[0] == {"name": "K", "value": ""}


def test_workspace_capture_preserves_draft_implicit_constant_rows(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    source.implicit_constants_editor.set_rows(
        [
            {"name": "K", "value": "1"},
            {"name": "K", "value": "2"},
            {"name": "", "value": "3"},
        ]
    )

    bundle = capture_workspace(source, title="draft")
    implicit = bundle.manifest["workspace"]["config"]["fitting"]["implicit"]

    assert implicit["constants"] == [
        {"name": "K", "value": "1"},
        {"name": "K", "value": "2"},
        {"name": "", "value": "3"},
    ]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.implicit_constants_editor.rows() == [
        {"name": "K", "value": "1"},
        {"name": "K", "value": "2"},
        {"name": "", "value": "3"},
    ]


def test_workspace_preserves_implicit_constants_enabled_view_and_text_draft(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    source.implicit_constants_editor.setChecked(True)
    source.implicit_constants_editor.set_text("# keep formatting\nK = 1\n")
    source.implicit_constants_editor.use_text_view(True)

    bundle = capture_workspace(source, title="implicit constants draft")
    implicit = bundle.manifest["workspace"]["config"]["fitting"]["implicit"]

    assert implicit["constants_enabled"] is True
    assert implicit["constants_view"] == "text"
    assert implicit["constants"] == [{"name": "K", "value": "1"}]
    assert implicit["constants_text"] == "# keep formatting\nK = 1\n"

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.implicit_constants_editor.isChecked() is True
    assert target.implicit_constants_editor.using_text_view() is True
    assert target.implicit_constants_editor.raw_text() == "# keep formatting\nK = 1\n"
    assert target.implicit_constants_editor.rows() == [{"name": "K", "value": "1"}]


def test_workspace_preserves_implicit_constants_table_view_raw_text_draft(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    raw_text = "# inactive implicit draft\nK = 2\n"
    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    source.implicit_constants_editor.setChecked(True)
    source.implicit_constants_editor.set_text(raw_text)
    source.implicit_constants_editor.set_rows([{"name": "K", "value": "1"}])
    source.implicit_constants_editor.use_text_view(False)

    bundle = capture_workspace(source, title="implicit constants table raw text")
    implicit = bundle.manifest["workspace"]["config"]["fitting"]["implicit"]

    assert implicit["constants_enabled"] is True
    assert implicit["constants_view"] == "table"
    assert implicit["constants"] == [{"name": "K", "value": "1"}]
    assert implicit["constants_text"] == raw_text

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.implicit_constants_editor.isChecked() is True
    assert target.implicit_constants_editor.using_text_view() is False
    assert target.implicit_constants_editor.rows() == [{"name": "K", "value": "1"}]
    assert target.implicit_constants_editor.raw_text() == raw_text


def test_workspace_preserves_implicit_draft_after_switching_back_to_custom(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    source.implicit_variable_edit.setText("delta")
    source.implicit_equation_edit.setPlainText("d0 + d2/(n-delta)^2")
    source.implicit_output_edit.setPlainText("En - K/(n-delta)^2")
    source.implicit_constraints_checkbox.setChecked(True)
    source.implicit_params_table.set_rows(
        [
            {"name": "d0", "initial": "0.3"},
            {"name": "d2", "fixed": "0.01"},
        ]
    )
    source.implicit_constants_editor.setChecked(True)
    source.implicit_constants_editor.set_text("# draft constant\nK = 0.007\n")
    source.implicit_constants_editor.use_text_view(True)
    _set_combo_data(source.fit_model_combo, "custom")

    bundle = capture_workspace(source, title="implicit draft while custom active")
    fitting = bundle.manifest["workspace"]["config"]["fitting"]
    implicit = fitting["implicit"]

    assert fitting["model"] == "custom"
    assert implicit["active"] is False
    assert implicit["implicit_variable"] == "delta"
    assert implicit["equation"] == "d0 + d2/(n-delta)^2"
    assert implicit["output_expression"] == "En - K/(n-delta)^2"
    assert implicit["constraints_enabled"] is True
    assert implicit["parameters"] == [
        {"name": "d0", "initial": "0.3", "fixed": "", "min": "", "max": ""},
        {"name": "d2", "initial": "", "fixed": "0.01", "min": "", "max": ""},
    ]
    assert implicit["constants_enabled"] is True
    assert implicit["constants_view"] == "text"
    assert implicit["constants"] == [{"name": "K", "value": "0.007"}]
    assert implicit["constants_text"] == "# draft constant\nK = 0.007\n"

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.fit_model_combo.currentData() == "custom"
    _set_combo_data(target.fit_model_combo, "self_consistent")
    assert target.implicit_variable_edit.text() == "delta"
    assert target.implicit_equation_edit.toPlainText() == "d0 + d2/(n-delta)^2"
    assert target.implicit_output_edit.toPlainText() == "En - K/(n-delta)^2"
    assert target.implicit_constraints_checkbox.isChecked() is True
    assert target.implicit_params_table.rows() == [
        {"name": "d0", "initial": "0.3", "fixed": "", "min": "", "max": ""},
        {"name": "d2", "initial": "", "fixed": "0.01", "min": "", "max": ""},
    ]
    assert target.implicit_constants_editor.isChecked() is True
    assert target.implicit_constants_editor.using_text_view() is True
    assert target.implicit_constants_editor.raw_text() == "# draft constant\nK = 0.007\n"


def test_workspace_preserves_implicit_parameters_and_constants(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    target = ExtrapolationWindow()
    qtbot.addWidget(target)

    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    source._reset_variable_rows(default_var="n", default_column="A")
    source.fit_target_edit.setText("B")
    source.implicit_variable_edit.setText("delta")
    source.implicit_equation_edit.setPlainText("d0")
    source.implicit_output_edit.setPlainText("En - K/(n-delta)^2")
    source.implicit_timeout_spin.setValue(420)
    source._reset_implicit_param_rows(
        {
            "d0": {"initial": "0.32"},
            "En": {"initial": "-0.0121425"},
            "K": {"initial": "-0.007"},
        }
    )
    source._reset_implicit_constants_rows({"unit": "1"})

    bundle = capture_workspace(source, title="implicit")
    implicit = bundle.manifest["workspace"]["config"]["fitting"]["implicit"]
    assert implicit["schema"] == 2
    assert implicit["parameters"] == [
        {"name": "d0", "initial": "0.32", "fixed": "", "min": "", "max": ""},
        {"name": "En", "initial": "-0.0121425", "fixed": "", "min": "", "max": ""},
        {"name": "K", "initial": "-0.007", "fixed": "", "min": "", "max": ""},
    ]
    assert implicit["constants"] == [{"name": "unit", "value": "1"}]

    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.fit_model_combo.currentData() == "self_consistent"
    assert target.variable_rows[0][0].text() == "n"
    assert target.variable_rows[0][1].text() == "A"
    assert target.implicit_variable_edit.text() == "delta"
    assert target.implicit_equation_edit.toPlainText() == "d0"
    assert target.implicit_output_edit.toPlainText() == "En - K/(n-delta)^2"
    assert target.implicit_timeout_spin.value() == 420
    assert target._collect_implicit_constants() == {"unit": "1"}
    assert target._collect_implicit_parameter_config(["d0", "En", "K"]) == {
        "d0": {"initial": "0.32"},
        "En": {"initial": "-0.0121425"},
        "K": {"initial": "-0.007"},
    }


def test_workspace_restore_schema2_respects_explicit_disabled_implicit_constraints(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    bundle = capture_workspace(source, title="implicit disabled constraints")
    implicit = bundle.manifest["workspace"]["config"]["fitting"]["implicit"]
    implicit["constraints_enabled"] = False
    implicit["parameters"] = [
        {"name": "A", "initial": "1", "fixed": "2", "min": "0", "max": "3"},
        {"name": "", "initial": "", "fixed": "", "min": "draft", "max": ""},
    ]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.implicit_constraints_checkbox.isChecked() is False
    assert target.implicit_params_table.rows() == [
        {"name": "A", "initial": "1", "fixed": "2", "min": "0", "max": "3"},
        {"name": "", "initial": "", "fixed": "", "min": "draft", "max": ""},
    ]


def test_workspace_restore_schema2_preserves_implicit_parameter_draft_rows(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    bundle = capture_workspace(source, title="implicit parameter drafts")
    implicit = bundle.manifest["workspace"]["config"]["fitting"]["implicit"]
    implicit["constraints_enabled"] = True
    implicit["parameters"] = [
        {"name": "A", "initial": "1", "fixed": "", "min": "", "max": ""},
        {"name": "A", "initial": "2", "fixed": "", "min": "", "max": ""},
        {"name": "", "initial": "3", "fixed": "", "min": "", "max": ""},
    ]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.implicit_constraints_checkbox.isChecked() is True
    assert target.implicit_params_table.rows() == [
        {"name": "A", "initial": "1", "fixed": "", "min": "", "max": ""},
        {"name": "A", "initial": "2", "fixed": "", "min": "", "max": ""},
        {"name": "", "initial": "3", "fixed": "", "min": "", "max": ""},
    ]


def test_workspace_restore_old_implicit_builtin_constants(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    bundle = capture_workspace(source, title="legacy")
    fitting = bundle.manifest["workspace"]["config"]["fitting"]
    fitting["implicit"] = {
        "x_variables": ("n",),
        "implicit_variable": "delta",
        "equation": "d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
        "output_expression": "En - R*c/(n-delta)^2",
        "method": "fixed_point",
        "initial": "0",
        "tolerance": "1e-30",
        "max_iterations": 80,
    }

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.implicit_equation_edit.toPlainText() == "d0 + d2/(n-delta)^2 + d4/(n-delta)^4"
    assert target.implicit_output_edit.toPlainText() == "En - R*c/(n-delta)^2"
    assert target.implicit_timeout_spin.value() == 300
    assert target._collect_implicit_constants() == {"R": "10973731.568160", "c": "299792458"}


def test_workspace_restore_old_implicit_parameter_zero_values(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    for legacy_parameters in (
        {"d0": {"initial": 0.0}, "K": {"fixed": 0}},
        [{"name": "d0", "initial": 0.0}, {"name": "K", "fixed": 0}],
    ):
        source = ExtrapolationWindow()
        qtbot.addWidget(source)
        _set_combo_data(source.mode_combo, "fitting")
        _set_combo_data(source.fit_model_combo, "self_consistent")
        bundle = capture_workspace(source, title="legacy")
        fitting = bundle.manifest["workspace"]["config"]["fitting"]
        fitting["implicit"] = {
            "x_variables": ("n",),
            "implicit_variable": "delta",
            "equation": "d0",
            "output_expression": "En - K/(n-delta)^2",
            "method": "fixed_point",
            "initial": "0",
            "tolerance": "1e-30",
            "max_iterations": 80,
            "parameters": legacy_parameters,
        }

        target = ExtrapolationWindow()
        qtbot.addWidget(target)
        restore_workspace(target, bundle.manifest, bundle.attachments)

        assert target._collect_implicit_parameter_config(["d0", "K"]) == {
            "d0": {"initial": "0.0"},
            "K": {"fixed": "0"},
        }


def test_fit_latex_report_escapes_implicit_equation_and_output_text() -> None:
    from app_desktop import fitting_latex_writer as writer

    lines = writer.build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf("1.0"), mp.mpf("2.0"))],
        sigma_rows=[(None, None)],
        fit_result=_sample_fit_result(),
        expression="u_out",
        substituted="u_out",
        image_path=None,
        use_dcolumn=False,
        digits=6,
        latex_group_size=3,
        target_column="y",
        variable_pairs=[("x", "x")],
        caption_text="Fit results",
        default_uncertainty_digits=1,
        cleaned_substituted="u_out",
    )

    text = "\n".join(lines)
    assert r"Implicit equation: \texttt{a\_b + c\% \& \# \textbackslash{}\textbackslash{} x}\\" in text
    assert r"Implicit output: \texttt{u\_out \& y}\\" in text


def test_fit_latex_report_escapes_quantum_defect_special_chars() -> None:
    from app_desktop import fitting_latex_writer as writer

    fit_result = _sample_fit_result()
    fit_result.details["equation"] = r"d0 + d2/(n-delta)^2 + {d4} ~ $bad"
    fit_result.details["output_expression"] = r"En - K/(n-delta)^2"

    lines = writer.build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf("1.0"), mp.mpf("2.0"))],
        sigma_rows=[(None, None)],
        fit_result=fit_result,
        expression="u",
        substituted="u",
        image_path=None,
        use_dcolumn=False,
        digits=6,
        target_column="y",
        variable_pairs=[("x", "x")],
        cleaned_substituted="u",
    )

    text = "\n".join(lines)
    assert r"(n-delta)\textasciicircum{}2" in text
    assert r"\{d4\}" in text
    assert r"\textasciitilde{}" in text
    assert r"\$bad" in text
