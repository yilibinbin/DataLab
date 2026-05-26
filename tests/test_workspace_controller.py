from __future__ import annotations

import base64

from PySide6.QtWidgets import QTableWidgetItem


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _set_combo_data(combo, value: str) -> None:
    idx = combo.findData(value)
    assert idx >= 0
    combo.setCurrentIndex(idx)


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
