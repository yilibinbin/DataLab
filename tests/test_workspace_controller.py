from __future__ import annotations

import base64
from pathlib import Path

import mpmath as mp
import pytest
from PySide6.QtWidgets import QTableWidgetItem
from types import SimpleNamespace

from fitting.hp_fitter import FitResult


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def _set_combo_data(combo, value: str) -> None:
    idx = combo.findData(value)
    assert idx >= 0
    combo.setCurrentIndex(idx)


class _FakeCombo:
    def __init__(self, value: str = "taylor") -> None:
        self.value = value
        self._pending_value = value

    def currentData(self) -> str:
        return self.value

    def currentText(self) -> str:
        return self.value

    def findData(self, value: str) -> int:
        if value not in {"taylor", "off", "monte_carlo"}:
            return -1
        self._pending_value = value
        return 0

    def findText(self, value: str) -> int:
        return self.findData(value)

    def setCurrentIndex(self, _index: int) -> None:
        self.value = self._pending_value


class _FakeSpin:
    def __init__(self, value: int = 2000, *, minimum: int = 2, maximum: int = 50000) -> None:
        self._value = value
        self._minimum = minimum
        self._maximum = maximum

    def value(self) -> int:
        return self._value

    def setValue(self, value: int) -> None:
        self._value = int(value)

    def minimum(self) -> int:
        return self._minimum

    def maximum(self) -> int:
        return self._maximum


class _FakeLineEdit:
    def __init__(self, value: str = "") -> None:
        self._value = value

    def text(self) -> str:
        return self._value

    def setText(self, value: str) -> None:
        self._value = str(value)


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
    assert constants["numeric_mode"] == "uncertainty"
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


def test_workspace_round_trip_preserves_redesigned_shell_ui_state(qtbot, tmp_path) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from shared.workspace_io import read_workspace, write_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    source.fit_expr_edit.setPlainText("A*x + B")
    source.fit_target_edit.setText("y")
    source.custom_constants_editor.setChecked(True)
    source.custom_constants_editor.set_rows([{"name": "K", "value": "1.0(2)"}])
    source.custom_params_table.set_rows(
        [
            {"name": "A", "initial": "1", "fixed": "", "min": "0", "max": "2"},
            {"name": "B", "initial": "0", "fixed": "", "min": "", "max": ""},
        ]
    )
    source.root_equations_edit.setPlainText("x^2 - A")
    source.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "0", "upper": "2"}])
    source.result_edit.setPlainText("Fit complete")
    source.log_edit.setPlainText("done")
    source.latex_edit.setPlainText("\\begin{tabular}{cc}A & B\\end{tabular}")
    source._set_csv_data([{"name": "A", "value": "1.0(2)"}], ["name", "value"], "fit.csv")
    source.result_plot_bytes = PNG_1X1
    source.result_tabs.setCurrentIndex(source.result_tabs_indices["image"])
    source.result_plot_zoom = 1.5

    bundle = capture_workspace(source, title="redesigned shell")
    workspace = bundle.manifest["workspace"]
    assert workspace["ui"]["result_subtab"] == source.result_tabs_indices["image"]
    assert workspace["ui"]["selected_plot_index"] == 0
    assert workspace["ui"]["plot_zoom"] == 1.5

    path = tmp_path / "redesigned-shell.datalab"
    write_workspace(path, bundle.manifest, bundle.attachments)
    loaded = read_workspace(path)

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, loaded.manifest, loaded.attachments)

    assert target.mode_combo.currentData() == "fitting"
    assert target.fit_expr_edit.toPlainText() == "A*x + B"
    assert target.fit_target_edit.text() == "y"
    assert target.custom_constants_editor.isChecked() is True
    assert target.custom_constants_editor.rows() == [{"name": "K", "value": "1.0(2)"}]
    assert target.custom_params_table.rows() == [
        {"name": "A", "initial": "1", "fixed": "", "min": "0", "max": "2"},
        {"name": "B", "initial": "0", "fixed": "", "min": "", "max": ""},
    ]
    assert target.root_equations_edit.toPlainText() == "x^2 - A"
    assert target.root_unknowns_table.rows() == [{"name": "x", "initial": "1", "lower": "0", "upper": "2"}]
    assert target.result_edit.toPlainText() == "Fit complete"
    assert target.log_edit.toPlainText() == "done"
    assert target.latex_edit.toPlainText() == "\\begin{tabular}{cc}A & B\\end{tabular}"
    assert target._csv_headers == ["name", "value"]
    assert target._csv_rows == [{"name": "A", "value": "1.0(2)"}]
    assert target.result_plot_bytes == PNG_1X1
    assert target.result_tabs.currentIndex() == target.result_tabs_indices["image"]
    assert target.image_page_spin.value() == 1
    assert target.zoom_percent_spin.value() == 150
    assert getattr(target, "_workspace_snapshot_only", False) is True
    assert getattr(target, "_workspace_dirty", True) is False


def test_workspace_restore_clamps_invalid_ui_indices(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.result_tabs.setCurrentIndex(source.result_tabs_indices["latex"])
    source.result_edit.setPlainText("Result")
    bundle = capture_workspace(source, title="invalid ui")
    bundle.manifest["workspace"]["ui"].update(
        {
            "main_tab": 999,
            "result_subtab": 999,
            "selected_plot_index": 999,
            "plot_zoom": "bad",
        }
    )

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    target.result_tabs.setCurrentIndex(target.result_tabs_indices["numeric"])
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.result_tabs.currentIndex() == target.result_tabs_indices["numeric"]
    assert target.image_page_spin.value() == 1
    assert target.zoom_percent_spin.value() == 100


def test_workspace_preserves_root_result_plot_attachment(qtbot, monkeypatch) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    monkeypatch.setattr("app_desktop.window_extrapolation_mixin.QMessageBox.information", lambda *args: None)
    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "root_solving")
    source._on_root_solving_finished(
        {
            "markdown": "| root |\n|---|\n| 1 |",
            "csv_headers": ["root"],
            "csv_rows": [{"root": "1"}],
            "warnings": [],
            "plot_bytes": PNG_1X1,
        }
    )

    bundle = capture_workspace(source, title="root result")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    assert snapshot["kind"] == "root_solving"
    assert snapshot["plots"][0]["path"] == "attachments/plots/plot-001.png"
    assert bundle.attachments["attachments/plots/plot-001.png"] == PNG_1X1

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.result_plot_bytes == PNG_1X1
    assert target._csv_rows == [{"root": "1"}]


def test_workspace_restore_refreshes_plot_only_result_overview(qtbot, tmp_path) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from shared.workspace_io import read_workspace, write_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._reset_csv_data()
    source._last_result_rendered_text = ""
    source._update_result_plot(PNG_1X1)
    path = tmp_path / "plot-only.datalab"
    bundle = capture_workspace(source, title="plot only")
    write_workspace(path, bundle.manifest, bundle.attachments)

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    loaded = read_workspace(path)
    restore_workspace(target, loaded.manifest, loaded.attachments)
    target._apply_language("en")

    assert target.workbench_result_overview.text() == "Result ready; no tabular data"


def test_workspace_restore_clears_stale_failed_state_before_result_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._set_result_text("restored text", final_result=True)
    bundle = capture_workspace(source, title="text result")

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    target._mark_workbench_result_failed()
    restore_workspace(target, bundle.manifest, bundle.attachments)
    target._apply_language("en")

    assert target.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_workspace_preserves_empty_success_result_overview(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._mark_workbench_result_complete()

    bundle = capture_workspace(source, title="empty result")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    assert snapshot["present"] is True
    assert snapshot["overview_state"] == "complete"

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)
    target._apply_language("en")

    assert target.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_workspace_preserves_empty_tabular_result_schema(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._set_csv_data([], ["x", "y"])

    bundle = capture_workspace(source, title="empty table")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    assert snapshot["present"] is True

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)
    target._apply_language("en")

    assert target.workbench_result_overview.text() == "Result data: 0 rows, 2 columns"


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


def test_legacy_result_snapshot_fixture_round_trips_display_and_attachment(qtbot, tmp_path) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import restore_workspace
    from shared.workspace_io import read_workspace

    fixture_path = (
        Path(__file__).parent / "fixtures" / "workspaces" / "pre_schema_result_snapshot.datalab"
    )
    loaded = read_workspace(fixture_path)

    restored = ExtrapolationWindow()
    qtbot.addWidget(restored)
    restore_workspace(restored, loaded.manifest, loaded.attachments)

    assert "<table" in restored.result_edit.toHtml()
    assert "Legacy parameter" in restored.result_edit.toPlainText()
    assert "| Legacy parameter |" not in restored.result_edit.toPlainText()
    assert restored.log_edit.toPlainText() == "legacy log line"
    assert "\\begin{tabular}" in restored.latex_edit.toPlainText()
    assert restored._csv_headers == ["name", "value"]
    assert restored._csv_rows == [{"name": "legacy", "value": "1.23(4)"}]
    assert restored.result_plot_bytes == PNG_1X1

    round_trip_path = tmp_path / "round-trip.datalab"
    assert restored._save_workspace_to_path(round_trip_path)

    reopened = ExtrapolationWindow()
    qtbot.addWidget(reopened)
    assert reopened._open_workspace_from_path(round_trip_path)

    assert "<table" in reopened.result_edit.toHtml()
    assert "Legacy parameter" in reopened.result_edit.toPlainText()
    assert "| Legacy parameter |" not in reopened.result_edit.toPlainText()
    assert reopened.log_edit.toPlainText() == "legacy log line"
    assert "\\begin{tabular}" in reopened.latex_edit.toPlainText()
    assert reopened._csv_headers == ["name", "value"]
    assert reopened._csv_rows == [{"name": "legacy", "value": "1.23(4)"}]
    assert reopened.result_plot_bytes == PNG_1X1
    assert reopened._workspace_snapshot_only is True


def test_workspace_preserves_root_solving_config(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "root_solving")
    source.root_equations_edit.setPlainText("x**2 - A - C")
    _set_combo_data(source.root_mode_combo, "scan_multiple")
    source.root_unknowns_table.set_rows(
        [
            {"name": "x", "initial": "1", "lower": "-3", "upper": "3", "source": "detected"},
            {"name": "manual", "initial": "0", "lower": "", "upper": ""},
        ]
    )
    source.root_constants_editor.setChecked(True)
    source.root_constants_editor.set_rows([{"name": "C", "value": "1.0(2)"}])
    source.root_constants_editor.set_text("# root draft\nC = 1.0(2)\n")
    source.root_constants_editor.use_text_view(False)

    bundle = capture_workspace(source, title="root")
    root_config = bundle.manifest["workspace"]["config"]["root_solving"]

    assert root_config == {
        "schema": 1,
        "equations": "x**2 - A - C",
        "mode": "scan_multiple",
        "unknowns": [
            {"name": "x", "initial": "1", "lower": "-3", "upper": "3", "source": "detected"},
            {"name": "manual", "initial": "0", "lower": "", "upper": ""},
        ],
        "constants": {
            "enabled": True,
            "view": "table",
            "rows": [{"name": "C", "value": "1.0(2)"}],
            "text": "# root draft\nC = 1.0(2)\n",
            "numeric_mode": "uncertainty",
        },
        "uncertainty_options": {
            "method": "taylor",
            "taylor_order": 1,
            "monte_carlo_samples": 2000,
            "monte_carlo_seed": "",
        },
    }

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.mode_combo.currentData() == "root_solving"
    assert target.root_equations_edit.toPlainText() == "x**2 - A - C"
    assert target.root_mode_combo.currentData() == "scan_multiple"
    assert target.root_unknowns_table.rows() == [
        {"name": "x", "initial": "1", "lower": "-3", "upper": "3", "source": "detected"},
        {"name": "manual", "initial": "0", "lower": "", "upper": ""},
    ]
    assert target.root_constants_editor.isChecked() is True
    assert target.root_constants_editor.using_text_view() is False
    assert target.root_constants_editor.numeric_mode() == "uncertainty"
    assert target.root_constants_editor.rows() == [{"name": "C", "value": "1.0(2)"}]
    assert target.root_constants_editor.raw_text() == "# root draft\nC = 1.0(2)\n"


def test_workspace_helpers_preserve_root_uncertainty_options_when_controls_exist() -> None:
    from app_desktop.workspace_controller import _capture_root_config, _restore_root_config

    source = SimpleNamespace(
        root_equations_edit=None,
        root_mode_combo=None,
        root_unknowns_table=None,
        root_constants_editor=None,
        root_uncertainty_method_combo=_FakeCombo("monte_carlo"),
        root_uncertainty_order_spin=_FakeSpin(1, minimum=1, maximum=2),
        root_monte_carlo_samples_spin=_FakeSpin(321),
        root_monte_carlo_seed_edit=_FakeLineEdit("11"),
    )

    config = _capture_root_config(source)

    assert config["uncertainty_options"] == {
        "method": "monte_carlo",
        "taylor_order": 1,
        "monte_carlo_samples": 321,
        "monte_carlo_seed": "11",
    }

    target = SimpleNamespace(
        root_equations_edit=None,
        root_mode_combo=None,
        root_unknowns_table=None,
        root_constants_editor=None,
        root_uncertainty_method_combo=_FakeCombo("taylor"),
        root_uncertainty_order_spin=_FakeSpin(1, minimum=1, maximum=2),
        root_monte_carlo_samples_spin=_FakeSpin(2000),
        root_monte_carlo_seed_edit=_FakeLineEdit(""),
    )

    _restore_root_config(target, config)

    assert target.root_uncertainty_method_combo.currentData() == "monte_carlo"
    assert target.root_monte_carlo_samples_spin.value() == 321
    assert target.root_monte_carlo_seed_edit.text() == "11"


def test_workspace_preserves_root_uncertainty_options(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "root_solving")
    _set_combo_data(source.root_uncertainty_method_combo, "monte_carlo")
    source.root_monte_carlo_samples_spin.setValue(321)
    source.root_monte_carlo_seed_edit.setText("11")

    bundle = capture_workspace(source, title="root uncertainty")
    root_options = bundle.manifest["workspace"]["config"]["root_solving"]["uncertainty_options"]

    assert root_options == {
        "method": "monte_carlo",
        "taylor_order": 1,
        "monte_carlo_samples": 321,
        "monte_carlo_seed": "11",
    }

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.root_uncertainty_method_combo.currentData() == "monte_carlo"
    assert target.root_monte_carlo_samples_spin.value() == 321
    assert target.root_monte_carlo_seed_edit.text() == "11"


def test_workspace_preserves_root_taylor_order(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "root_solving")
    _set_combo_data(source.root_uncertainty_method_combo, "taylor")
    source.root_uncertainty_order_spin.setValue(2)

    bundle = capture_workspace(source, title="root taylor order")
    root_options = bundle.manifest["workspace"]["config"]["root_solving"]["uncertainty_options"]

    assert root_options["method"] == "taylor"
    assert root_options["taylor_order"] == 2

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.root_uncertainty_method_combo.currentData() == "taylor"
    assert target.root_uncertainty_order_spin.value() == 2


def test_workspace_restore_root_uncertainty_options_falls_back_for_bad_sample_count() -> None:
    from app_desktop.workspace_controller import _restore_root_config

    target = SimpleNamespace(
        root_equations_edit=None,
        root_mode_combo=None,
        root_unknowns_table=None,
        root_constants_editor=None,
        root_uncertainty_method_combo=_FakeCombo("taylor"),
        root_uncertainty_order_spin=_FakeSpin(1, minimum=1, maximum=2),
        root_monte_carlo_samples_spin=_FakeSpin(123),
        root_monte_carlo_seed_edit=_FakeLineEdit(""),
    )

    _restore_root_config(
        target,
        {
            "uncertainty_options": {
                "method": "monte_carlo",
                "monte_carlo_samples": "bad",
                "monte_carlo_seed": "11",
            }
        },
    )

    assert target.root_uncertainty_method_combo.currentData() == "monte_carlo"
    assert target.root_monte_carlo_samples_spin.value() == 2000
    assert target.root_monte_carlo_seed_edit.text() == "11"


def test_workspace_restore_root_uncertainty_options_clamps_sample_count_to_widget_range() -> None:
    from app_desktop.workspace_controller import _restore_root_config

    target = SimpleNamespace(
        root_equations_edit=None,
        root_mode_combo=None,
        root_unknowns_table=None,
        root_constants_editor=None,
        root_uncertainty_method_combo=_FakeCombo("taylor"),
        root_uncertainty_order_spin=_FakeSpin(1, minimum=1, maximum=2),
        root_monte_carlo_samples_spin=_FakeSpin(123),
        root_monte_carlo_seed_edit=_FakeLineEdit(""),
    )

    _restore_root_config(
        target,
        {
            "uncertainty_options": {
                "method": "monte_carlo",
                "monte_carlo_samples": "999999",
                "monte_carlo_seed": "11",
            }
        },
    )

    assert target.root_monte_carlo_samples_spin.value() == 50000


def test_workspace_restore_root_uncertainty_options_clamps_taylor_order_to_widget_range() -> None:
    from app_desktop.workspace_controller import _restore_root_config

    target = SimpleNamespace(
        root_equations_edit=None,
        root_mode_combo=None,
        root_unknowns_table=None,
        root_constants_editor=None,
        root_uncertainty_method_combo=_FakeCombo("taylor"),
        root_uncertainty_order_spin=_FakeSpin(1, minimum=1, maximum=2),
        root_monte_carlo_samples_spin=_FakeSpin(123),
        root_monte_carlo_seed_edit=_FakeLineEdit(""),
    )

    _restore_root_config(
        target,
        {
            "uncertainty_options": {
                "method": "taylor",
                "taylor_order": "99",
            }
        },
    )

    assert target.root_uncertainty_order_spin.value() == 2


def test_workspace_restore_root_uncertainty_options_resets_unknown_method_to_taylor() -> None:
    from app_desktop.workspace_controller import _restore_root_config

    target = SimpleNamespace(
        root_equations_edit=None,
        root_mode_combo=None,
        root_unknowns_table=None,
        root_constants_editor=None,
        root_uncertainty_method_combo=_FakeCombo("monte_carlo"),
        root_uncertainty_order_spin=_FakeSpin(1, minimum=1, maximum=2),
        root_monte_carlo_samples_spin=_FakeSpin(123),
        root_monte_carlo_seed_edit=_FakeLineEdit(""),
    )

    _restore_root_config(
        target,
        {
            "uncertainty_options": {
                "method": "future_method",
                "monte_carlo_samples": "200",
                "monte_carlo_seed": "11",
            }
        },
    )

    assert target.root_uncertainty_method_combo.currentData() == "taylor"


def test_workspace_restore_without_root_config_clears_stale_root_ui(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    bundle = capture_workspace(source, title="old")
    bundle.manifest["workspace"]["config"].pop("root_solving", None)

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    target.root_equations_edit.setPlainText("stale")
    _set_combo_data(target.root_mode_combo, "scan_multiple")
    target.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "", "upper": ""}])
    target.root_constants_editor.setChecked(True)
    target.root_constants_editor.set_rows([{"name": "C", "value": "1"}])
    target.root_constants_editor.set_raw_text("C = 1")

    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.root_equations_edit.toPlainText() == ""
    assert target.root_mode_combo.currentData() == "scalar"
    assert target.root_unknowns_table.rows() == []
    assert target.root_constants_editor.isChecked() is False
    assert target.root_constants_editor.rows() == []
    assert target.root_constants_editor.raw_text() == ""


def test_workspace_restore_migrates_legacy_root_auto_mode(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import _restore_root_config

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    _set_combo_data(target.root_mode_combo, "scan_multiple")

    _restore_root_config(
        target,
        {
            "equations": "x - 1",
            "mode": "auto",
            "unknowns": [{"name": "x", "initial": "1", "lower": "", "upper": ""}],
        },
    )

    assert target.root_mode_combo.currentData() == "scalar"


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

    assert target.custom_params_table.rows() == [
        {"name": "A", "initial": "1.0", "fixed": "", "min": "", "max": ""}
    ]
    assert target.implicit_variable_edit.text() == "u"
    assert target.implicit_equation_edit.toPlainText() == ""
    assert "a + b*Cos[u] + c*x" in target.implicit_equation_edit.placeholderText()
    assert target.implicit_output_edit.toPlainText() == ""
    assert "u" in target.implicit_output_edit.placeholderText()
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
        "numeric_mode": "mpmath",
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
    assert target.custom_constants_editor.numeric_mode() == "mpmath"
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
    assert fitting["custom_constants"]["numeric_mode"] == "mpmath"
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
        "numeric_mode": "mpmath",
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
    assert implicit["constants_numeric_mode"] == "mpmath"
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
    source._reset_implicit_constants_rows({"CR": "3.2898419602500(36)[+9]"})

    bundle = capture_workspace(source, title="implicit")
    implicit = bundle.manifest["workspace"]["config"]["fitting"]["implicit"]
    assert implicit["schema"] == 2
    assert implicit["constants_numeric_mode"] == "mpmath"
    assert implicit["parameters"] == [
        {"name": "d0", "initial": "0.32", "fixed": "", "min": "", "max": ""},
        {"name": "En", "initial": "-0.0121425", "fixed": "", "min": "", "max": ""},
        {"name": "K", "initial": "-0.007", "fixed": "", "min": "", "max": ""},
    ]
    assert implicit["constants"] == [{"name": "CR", "value": "3.2898419602500(36)[+9]"}]

    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.fit_model_combo.currentData() == "self_consistent"
    assert target.variable_rows[0][0].text() == "n"
    assert target.variable_rows[0][1].text() == "A"
    assert target.implicit_variable_edit.text() == "delta"
    assert target.implicit_equation_edit.toPlainText() == "d0"
    assert target.implicit_output_edit.toPlainText() == "En - K/(n-delta)^2"
    assert target.implicit_timeout_spin.value() == 420
    assert target.implicit_constants_editor.numeric_mode() == "mpmath"
    assert target._collect_implicit_constants() == {"CR": "3.2898419602500(36)[+9]"}
    assert target._collect_implicit_parameter_config(["d0", "En", "K"]) == {
        "d0": {"initial": "0.32"},
        "En": {"initial": "-0.0121425"},
        "K": {"initial": "-0.007"},
    }


def test_workspace_preserves_detected_parameter_source_for_later_refresh(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    target = ExtrapolationWindow()
    qtbot.addWidget(target)

    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "self_consistent")
    source._reset_variable_rows(default_var="n", default_column="A")
    source.implicit_variable_edit.setText("u")
    source.implicit_equation_edit.setPlainText("d0 + d2/(n-u)^2")
    source.implicit_output_edit.setPlainText("En")
    source._refresh_implicit_parameter_rows()
    source.implicit_params_table.add_parameter_row({"name": "manual", "initial": "3"})

    bundle = capture_workspace(source, title="detected source")
    restore_workspace(target, bundle.manifest, bundle.attachments)

    target.implicit_equation_edit.setPlainText("d0")
    target._refresh_implicit_parameter_rows()

    assert target.implicit_params_table.rows() == [
        {"name": "d0", "initial": "", "fixed": "", "min": "", "max": "", "source": "detected"},
        {"name": "En", "initial": "", "fixed": "", "min": "", "max": "", "source": "detected"},
        {"name": "manual", "initial": "3", "fixed": "", "min": "", "max": ""},
    ]


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
    assert (
        r"Implicit equation: \texttt{a\_b + c\% \& \# \textbackslash{}\textbackslash{} x}\\" in text
    )
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


def test_workspace_round_trip_preserves_workbench_variable_panel_state(qtbot, tmp_path) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from shared.workspace_io import read_workspace, write_workspace

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.custom_params_table.set_rows([{"name": "A", "initial": "1.25"}])
    window.custom_constants_editor.setChecked(True)
    window.custom_constants_editor.set_rows([{"name": "CR", "value": "3.2898419602500(36)[+9]"}])
    path = tmp_path / "variables.datalab"

    bundle = capture_workspace(window, title="variables")
    write_workspace(path, bundle.manifest, bundle.attachments)
    loaded = read_workspace(path)
    restored = ExtrapolationWindow()
    qtbot.addWidget(restored)
    restore_workspace(restored, loaded.manifest, loaded.attachments)

    assert restored.custom_params_table.rows()[0]["name"] == "A"
    assert restored.custom_constants_editor.rows()[0]["name"] == "CR"
