from __future__ import annotations

import base64

import mpmath as mp
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
    win.constants_checkbox.setChecked(True)
    win.constants_table.setItem(0, 0, QTableWidgetItem("ALPHA"))
    win.constants_table.setItem(0, 1, QTableWidgetItem("7.29e-3"))
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
    source.fit_param_edit.setPlainText('{"A":{"initial":1.0}}')
    source._reset_variable_rows(default_var="x", default_column="A")
    bundle = capture_workspace(source, title="old")
    fitting = bundle.manifest["workspace"]["config"]["fitting"]
    fitting.pop("implicit", None)

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.fit_param_edit.toPlainText() == '{"A":{"initial":1.0}}'
    assert target.implicit_variable_edit.text() == "u"
    assert target.implicit_equation_edit.text() == "a + b*Cos[u] + c*x"
    assert target.implicit_output_edit.text() == "u"
    assert [(row[0].text(), row[1].text()) for row in target.variable_rows] == [("x", "A")]


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
