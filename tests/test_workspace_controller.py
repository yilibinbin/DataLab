from __future__ import annotations

import base64
import json
from pathlib import Path

import mpmath as mp
import pytest
from PySide6.QtWidgets import QApplication, QTableWidgetItem
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


class _FakeTextEdit:
    def __init__(self, value: str = "") -> None:
        self._value = value

    def toPlainText(self) -> str:
        return self._value

    def setPlainText(self, value: str) -> None:
        self._value = str(value)

    def clear(self) -> None:
        self._value = ""

    def textCursor(self):
        return SimpleNamespace(blockNumber=lambda: 0, positionInBlock=lambda: 0)


class _HistoryFakeWindow(SimpleNamespace):
    def __init__(self, *, semantic: dict[str, object] | None = None, text: str = "Rendered") -> None:
        super().__init__(
            result_edit=_FakeTextEdit(text),
            log_edit=_FakeTextEdit(""),
            latex_edit=_FakeTextEdit(""),
            _csv_rows=[],
            _csv_headers=[],
            _workbench_result_state="complete",
            _last_result_kind="statistics_single",
            _last_result_payloads={},
            _last_result_semantic_snapshot=semantic,
            _last_result_semantic_snapshot_kind="statistics_single" if semantic is not None else "",
            result_plot_bytes=None,
        )

    def _set_csv_data(self, rows, headers, *_args) -> None:
        self._csv_rows = list(rows)
        self._csv_headers = list(headers)

    def _reset_csv_data(self, **_kwargs) -> None:
        self._csv_rows = []
        self._csv_headers = []

    def _set_result_text(self, value: str) -> None:
        self.result_edit.setPlainText(value)


def _history_statistics_semantic() -> dict[str, object]:
    from datalab_core.statistics import build_statistics_result_snapshot

    snapshot = build_statistics_result_snapshot(
        "statistics_single",
        {
            "result": {
                "mode": "mean",
                "mean": "1.25",
                "std": "0",
                "v_min": "1.25",
                "v_max": "2.5",
                "source_row_ids": ["line-1", "line-2"],
            },
            "n": 2,
            "value_col": "A",
        },
        overview_state="complete",
        precision={"compute_digits": 50, "display_digits": 10},
    )
    assert snapshot is not None
    return snapshot


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


def test_workspace_round_trips_common_and_latex_precision_settings(qtbot) -> None:
    """The common (mpmath_precision, uncertainty/display digits, scientific) and
    latex (input digits, group size) settings are saved but were never restored,
    silently resetting compute-affecting precision to defaults on reload
    (audit finding F11)."""
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.mpmath_precision_spin.setValue(50)
    source.uncertainty_digits_spin.setValue(3)
    source.display_digits_spin.setValue(25)
    source.scientific_checkbox.setChecked(True)
    source.latex_input_precision_spin.setValue(40)
    source.latex_group_size_spin.setValue(5)
    # caption text + TeX engine are also captured at save; they must round-trip
    # too, or the F11 "captured but never restored" fix is incomplete.
    source.caption_edit.setText("Table 1: extrapolated limits")
    source.latex_engine_combo.setCurrentText("pdflatex")

    bundle = capture_workspace(source, title="precision settings")

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.mpmath_precision_spin.value() == 50
    assert target.uncertainty_digits_spin.value() == 3
    assert target.display_digits_spin.value() == 25
    assert target.scientific_checkbox.isChecked() is True
    assert target.latex_input_precision_spin.value() == 40
    assert target.latex_group_size_spin.value() == 5
    assert target.caption_edit.text() == "Table 1: extrapolated limits"
    assert target.latex_engine_combo.currentText() == "pdflatex"


def test_workspace_round_trips_fitting_log_axes(qtbot) -> None:
    """log-x / log-y plot axis selection is captured on save but was never
    restored, so a reloaded workspace re-ran fits with linear axes (audit F12)."""
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.log_x_checkbox.setChecked(True)
    source.log_y_checkbox.setChecked(True)

    bundle = capture_workspace(source, title="log axes")

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.log_x_checkbox.isChecked() is True
    assert target.log_y_checkbox.isChecked() is True


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


def test_workspace_restores_file_backed_constants_as_embedded_text(qtbot, tmp_path: Path) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    constants_path = tmp_path / "constants.txt"
    constants_path.write_text("ALPHA 7.29e-3\n", encoding="utf-8")

    source = ExtrapolationWindow()
    qtbot.addWidget(source)

    bundle = capture_workspace(source, title="file backed constants")
    constants = bundle.manifest["workspace"]["constants"]
    constants.update(
        {
            "enabled": True,
            "source_kind": "file",
            "source_path_label": str(constants_path),
            "decoded_text": constants_path.read_text(encoding="utf-8"),
            "canonical_table": {"headers": ["Name", "Value"], "rows": []},
            "numeric_mode": "uncertainty",
        }
    )
    constants_path.unlink()

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.error_constants_editor.isChecked() is True
    assert target.error_constants_editor.using_text_view() is True
    assert "ALPHA 7.29e-3" in target.error_constants_editor.raw_text()
    assert target.error_constants_editor.constants_dict() == {"ALPHA": "7.29e-3"}


def test_workspace_preserves_legacy_disabled_error_constants_as_content_driven_draft(qtbot) -> None:
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

    assert constants["enabled"] is True
    assert constants["active_view"] == "table"
    assert constants["numeric_mode"] == "uncertainty"
    assert constants["decoded_text"] == raw_text
    assert constants["canonical_table"]["rows"] == [["ALPHA", "1"]]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.error_constants_editor.isChecked() is True
    assert target.error_constants_editor.using_text_view() is False
    assert target.error_constants_editor.raw_text() == raw_text
    assert target.error_constants_editor.rows() == [{"name": "ALPHA", "value": "1"}]


def test_set_table_from_canonical_shrinks_and_clears_stale_cells(qtbot) -> None:
    from PySide6.QtWidgets import QTableWidget

    from app_desktop.workspace_controller import _set_table_from_canonical

    table = QTableWidget(4, 3)
    qtbot.addWidget(table)
    table.setHorizontalHeaderLabels(["old_x", "old_y", "old_z"])
    table.setItem(0, 0, QTableWidgetItem("stale 00"))
    table.setItem(0, 1, QTableWidgetItem("stale 01"))
    table.setItem(3, 2, QTableWidgetItem("stale 32"))

    _set_table_from_canonical(table, {"headers": ["A"], "rows": [["1"], ["2"]]})

    assert table.rowCount() == 2
    assert table.columnCount() == 1
    assert table.horizontalHeaderItem(0).text() == "A"
    assert table.item(0, 0).text() == "1"
    assert table.item(1, 0).text() == "2"


def test_set_table_from_empty_canonical_resets_to_single_blank_column(qtbot) -> None:
    from PySide6.QtWidgets import QTableWidget

    from app_desktop.workspace_controller import _set_table_from_canonical

    table = QTableWidget(4, 3)
    qtbot.addWidget(table)
    table.setHorizontalHeaderLabels(["old_x", "old_y", "old_z"])
    table.setItem(0, 0, QTableWidgetItem("stale"))

    _set_table_from_canonical(table, {"headers": [], "rows": []})

    assert table.rowCount() == 1
    assert table.columnCount() == 1
    assert table.horizontalHeaderItem(0).text() == "A"
    assert table.item(0, 0) is None


def test_active_data_source_ignores_header_only_manual_table(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.use_file_checkbox.setChecked(False)
    window._data_stack.setCurrentIndex(0)
    window.manual_table.setRowCount(3)
    window.manual_table.setColumnCount(2)
    window.manual_table.setHorizontalHeaderLabels(["x", "y"])

    assert window._active_data_source() == (None, "")

    window.manual_table.setItem(0, 0, QTableWidgetItem("1"))

    assert window._active_data_source() == (None, "x\ty\n1")


def test_workspace_restore_refreshes_manual_summary_and_adaptive_height(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.manual_table.setRowCount(2)
    source.manual_table.setColumnCount(2)
    source.manual_table.setHorizontalHeaderLabels(["x", "y"])
    source.manual_table.setItem(0, 0, QTableWidgetItem("1"))
    source.manual_table.setItem(0, 1, QTableWidgetItem("2"))
    source.manual_table.setItem(1, 0, QTableWidgetItem("3"))
    source.manual_table.setItem(1, 1, QTableWidgetItem("4"))
    bundle = capture_workspace(source, title="manual table")

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    target._apply_language("en")
    QApplication.processEvents()
    empty_height = target.manual_table.maximumHeight()

    restore_workspace(target, bundle.manifest, bundle.attachments)
    QApplication.processEvents()

    assert "2 rows" in target.manual_data_summary.text()
    assert "2 columns" in target.manual_data_summary.text()
    assert target.manual_table.maximumHeight() > empty_height


def test_uncertainty_display_ignores_nonfinite_error_estimates(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    finite_value = window._format_precision_value(mp.mpf("1.2345"))

    assert window._format_uncertainty_value(mp.mpf("1.2345"), mp.inf) == finite_value
    assert window._format_uncertainty_value(mp.mpf("1.2345"), mp.nan) == finite_value


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


def test_workspace_round_trip_ignores_legacy_formula_preview_syntax_without_hash_change(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from shared.workspace_schema import compute_workspace_hash

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    source.fit_model_combo.setCurrentIndex(source.fit_model_combo.findData("custom"))
    source.fit_expr_edit.setPlainText("Sin[x] + A")

    baseline = capture_workspace(source, title="formula syntax baseline").manifest["workspace"]
    source._workbench_formula_preview_languages = {"fitting.custom.expression": "mathematica"}
    changed = capture_workspace(source, title="formula syntax changed").manifest["workspace"]

    assert "formula_preview" not in changed["ui"]
    assert compute_workspace_hash(baseline) == compute_workspace_hash(changed)
    source.fit_expr_edit.setPlainText("Sin[x] + A + B")
    formula_changed = capture_workspace(source, title="formula text changed").manifest["workspace"]
    assert compute_workspace_hash(baseline) != compute_workspace_hash(formula_changed)

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, {"workspace": changed}, {})

    assert target.mode_combo.currentData() == "fitting"
    assert not hasattr(target, "workbench_formula_language_combo")
    assert target._workspace_dirty is False


def test_workspace_round_trip_omits_default_formula_preview_syntax(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    source.fit_model_combo.setCurrentIndex(source.fit_model_combo.findData("custom"))
    source.fit_expr_edit.setPlainText("A*x + B")

    workspace = capture_workspace(source, title="default formula preview").manifest["workspace"]

    assert "formula_preview" not in workspace["ui"]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    target._workbench_formula_preview_languages = {"fitting.custom.expression": "mathematica"}

    restore_workspace(target, {"workspace": workspace}, {})

    assert not hasattr(target, "workbench_formula_language_combo")
    assert not hasattr(target, "_workbench_formula_preview_languages")


def test_workspace_capture_omits_unknown_formula_preview_schema_keys(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._workbench_formula_preview_languages = {
        "fitting.custom.expression": "mathematica",
        "unknown.formula": "python",
    }

    workspace = capture_workspace(source, title="unknown formula preview key").manifest["workspace"]

    assert "formula_preview" not in workspace["ui"]


@pytest.mark.parametrize("corrupt_state", ["python", ["python"], {"fitting.custom.expression": 42}])
def test_workspace_capture_ignores_corrupt_formula_preview_state(qtbot, corrupt_state) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._workbench_formula_preview_languages = corrupt_state

    workspace = capture_workspace(source, title="corrupt formula preview").manifest["workspace"]

    assert "formula_preview" not in workspace["ui"]


def test_workspace_capture_treats_missing_formula_preview_state_as_default(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)

    missing_workspace = capture_workspace(source, title="missing formula preview").manifest["workspace"]
    assert "formula_preview" not in missing_workspace["ui"]

    source._workbench_formula_preview_languages = None
    none_workspace = capture_workspace(source, title="none formula preview").manifest["workspace"]
    assert "formula_preview" not in none_workspace["ui"]


def test_workspace_capture_routes_compute_state_through_workbench_model(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app_desktop.workspace_controller as workspace_controller
    from app_desktop.window import ExtrapolationWindow

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    original_capture_config = workspace_controller._capture_config

    def capture_config_with_float(window) -> dict[str, object]:
        config = original_capture_config(window)
        config["fitting"]["parameter_rows"] = [{"name": "A", "initial": 1.0}]
        return config

    monkeypatch.setattr(workspace_controller, "_capture_config", capture_config_with_float)

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        workspace_controller.capture_workspace(source, title="float compute config")


def test_workspace_restore_ignores_malformed_formula_preview_state(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    bundle = capture_workspace(source, title="malformed preview restore")
    workspace = bundle.manifest["workspace"]
    workspace["ui"]["formula_preview"] = ["python"]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, {"workspace": workspace}, {})

    assert not hasattr(target, "_workbench_formula_preview_languages")


def test_workspace_restore_ignores_unknown_formula_preview_schema_keys(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    bundle = capture_workspace(source, title="unknown preview restore")
    workspace = bundle.manifest["workspace"]
    workspace["ui"]["formula_preview"] = {
        "fitting.custom.expression": "mathematica",
        "unknown.formula": "python",
    }

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, {"workspace": workspace}, {})

    assert not hasattr(target, "_workbench_formula_preview_languages")


def test_workspace_restore_routes_legacy_compute_float_through_workbench_model(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    bundle = capture_workspace(source, title="float restore")
    workspace = bundle.manifest["workspace"]
    workspace["config"]["fitting"]["parameter_rows"] = [{"name": "A", "initial": 1.0}]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.custom_params_table.rows()[0]["initial"] == "1.0"


def test_workspace_restore_allows_ui_float_state_through_workbench_model(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    bundle = capture_workspace(source, title="ui float restore")
    bundle.manifest["workspace"]["ui"]["plot_zoom"] = 1.25

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.zoom_percent_spin.value() == 125


def test_restore_workspace_restoring_flag_is_exception_safe(qtbot, monkeypatch) -> None:
    from app_desktop.window import ExtrapolationWindow
    import app_desktop.workspace_controller as workspace_controller

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    target._workspace_restoring = False

    def fail_restore_data_section(*_args, **_kwargs) -> None:
        raise RuntimeError("forced restore failure")

    monkeypatch.setattr(workspace_controller, "_restore_data_section", fail_restore_data_section)

    with pytest.raises(RuntimeError, match="forced restore failure"):
        workspace_controller.restore_workspace(target, {"workspace": {"config": {}}}, {})

    assert target._workspace_restoring is False


def test_restore_workspace_refresh_failure_marks_dirty_and_degraded(qtbot, monkeypatch) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    bundle = capture_workspace(source, title="refresh failure")

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    target._workspace_dirty = False
    target._workspace_degraded = False

    def fail_refresh() -> None:
        raise RuntimeError("forced formula refresh failure")

    monkeypatch.setattr(target, "refresh_workbench_formula_panel", fail_refresh)

    with pytest.raises(RuntimeError, match="forced formula refresh failure"):
        restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target._workspace_restoring is False
    assert target._workspace_dirty is True
    assert target._workspace_degraded is True


def test_workspace_restore_clamps_invalid_ui_indices(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.result_tabs.setCurrentIndex(source.result_tabs_indices["log"])
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


def test_workspace_restore_preserves_failed_result_subtab(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.log_edit.setPlainText("traceback")
    source._mark_workbench_result_failed()
    source.result_tabs.setCurrentIndex(source.result_tabs_indices["numeric"])
    bundle = capture_workspace(source, title="failed result")

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    target._workbench_result_details_kind = "running"
    restore_workspace(target, bundle.manifest, bundle.attachments)
    target._apply_language("en")

    assert target.workbench_result_overview.text() == "Calculation failed"
    assert target.result_tabs.currentIndex() == target.result_tabs_indices["numeric"]


def test_workspace_restore_failed_result_next_run_autoselects_log(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    class Worker:
        def start(self) -> None:
            pass

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.log_edit.setPlainText("traceback")
    source._mark_workbench_result_failed()
    source.result_tabs.setCurrentIndex(source.result_tabs_indices["numeric"])
    bundle = capture_workspace(source, title="failed result")

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)
    target._apply_language("en")
    assert target.result_tabs.currentIndex() == target.result_tabs_indices["numeric"]

    target._start_worker_with_workbench_result_state(Worker())
    assert target.result_tabs.currentIndex() == target.result_tabs_indices["log"]

    target.result_tabs.setCurrentIndex(target.result_tabs_indices["numeric"])
    target._mark_workbench_result_failed()
    assert target.result_tabs.currentIndex() == target.result_tabs_indices["log"]


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
    target._workbench_result_details_kind = "running"
    restore_workspace(target, bundle.manifest, bundle.attachments)
    target._apply_language("en")

    assert target.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_workspace_restore_preserves_empty_success_result_subtab(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.log_edit.setPlainText("completed without displayable output")
    source._mark_workbench_result_complete()
    source.result_tabs.setCurrentIndex(source.result_tabs_indices["numeric"])
    bundle = capture_workspace(source, title="empty result subtab")

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)
    target._apply_language("en")

    assert target.workbench_result_overview.text() == "Calculation complete; no displayable result"
    assert target.result_tabs.currentIndex() == target.result_tabs_indices["numeric"]


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


def test_workspace_captures_semantic_statistics_snapshot_round_trip(qtbot, tmp_path) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from shared.workspace_io import read_workspace, write_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    result = {
        "mode": "weighted_sigma",
        "mean": mp.mpf("1.25"),
        "std_mean": mp.mpf("0"),
        "std": mp.mpf("0"),
        "v_min": mp.mpf("1.25"),
        "v_max": mp.mpf("2.5"),
        "method_label": "Weighted mean (sigma=0 anchor)",
        "dropped": 1,
        "effective_n": mp.mpf("1"),
        "zero_sigma_anchor": True,
        "warnings": ["Detected zero sigma."],
        "source_row_ids": ("line-10", "line-11"),
    }
    source._display_statistics_result(
        result,
        "A",
        2,
        values=[mp.mpf("1.25"), mp.mpf("2.5")],
        sigmas=[mp.mpf("0"), mp.mpf("0.1")],
        render_plots=False,
    )

    bundle = capture_workspace(source, title="semantic statistics")
    semantic = bundle.manifest["workspace"]["result_snapshot"]["semantic"]

    json.dumps(semantic)
    assert semantic["schema_version"] == 1
    assert semantic["family"] == "statistics"
    assert semantic["mode"] == "weighted_sigma"
    assert {row["key"] for row in semantic["metric_rows"]} >= {"mean", "row_count", "min", "max"}
    assert {row["key"] for row in semantic["row_flags"]} == {"dropped", "zero_sigma_anchor"}
    assert semantic["source"]["value_column"] == "A"
    assert semantic["source"]["source_row_ids"] == ["line-10", "line-11"]
    assert semantic["precision"]["display_digits"] == source.display_digits_spin.value()
    assert semantic["compatibility"]["rendered_caches_authoritative"] is False

    path = tmp_path / "semantic-statistics.datalab"
    write_workspace(path, bundle.manifest, bundle.attachments)
    loaded = read_workspace(path)
    assert loaded.manifest["workspace"]["result_snapshot"]["semantic"] == semantic

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, loaded.manifest, loaded.attachments)

    assert target._last_result_semantic_snapshot == semantic
    assert "Mean" in target.result_edit.toPlainText()
    assert target._csv_headers == ["batch", "metric", "value", "uncertainty"]
    assert target._csv_rows

    recaptured = capture_workspace(target, title="semantic statistics restored")
    assert recaptured.manifest["workspace"]["result_snapshot"]["semantic"] == semantic


def test_workspace_round_trips_statistics_matrix_config(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.stats_workflow_combo.setCurrentIndex(source.stats_workflow_combo.findData("covariance_correlation"))
    source.stats_value_column_edit.setText("A, B")
    source.stats_matrix_missing_policy_combo.setCurrentIndex(
        source.stats_matrix_missing_policy_combo.findData("pairwise")
    )

    bundle = capture_workspace(source, title="statistics matrix config")
    config = bundle.manifest["workspace"]["config"]["statistics"]

    assert config["workflow_mode"] == "covariance_correlation"
    assert config["value_columns"] == ["A", "B"]
    assert config["matrix"]["missing_policy"] == "pairwise"

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.stats_workflow_combo.currentData() == "covariance_correlation"
    assert target.stats_value_column_edit.text() == "A, B"
    assert target.stats_matrix_missing_policy_combo.currentData() == "pairwise"


def test_workspace_round_trips_statistics_grouped_config(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.stats_workflow_combo.setCurrentIndex(source.stats_workflow_combo.findData("grouped_statistics"))
    source.stats_group_column_edit.setText("Group")
    source.stats_value_column_edit.setText("A, B")
    source.stats_sigma_column_edit.setText("sigma")
    source.stats_mode_combo.setCurrentIndex(source.stats_mode_combo.findData("weighted_sigma"))
    source.stats_weight_variance_checkbox.setChecked(True)

    bundle = capture_workspace(source, title="statistics grouped config")
    config = bundle.manifest["workspace"]["config"]["statistics"]

    assert config["workflow_mode"] == "grouped_statistics"
    assert config["group_column"] == "Group"
    assert config["value_columns"] == ["A", "B"]
    assert config["sigma_column"] == "sigma"
    assert config["mode"] == "weighted_sigma"
    assert config["weighted_variance"] is True

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.stats_workflow_combo.currentData() == "grouped_statistics"
    assert target.stats_group_column_edit.text() == "Group"
    assert target.stats_value_column_edit.text() == "A, B"
    assert target.stats_sigma_column_edit.text() == "sigma"
    assert target.stats_mode_combo.currentData() == "weighted_sigma"
    assert target.stats_weight_variance_checkbox.isChecked() is True
    assert not target.stats_group_column_edit.isHidden()


def test_workspace_history_is_omitted_by_default_for_legacy_saves() -> None:
    from app_desktop.workspace_controller import capture_workspace

    source = _HistoryFakeWindow(text="Rendered only")

    bundle = capture_workspace(source, title="legacy")

    assert "history" not in bundle.manifest["workspace"]


def test_workspace_persists_and_restores_semantic_history(tmp_path) -> None:
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from datalab_core.history import history_store_from_json
    from shared.workspace_io import read_workspace, write_workspace

    source = _HistoryFakeWindow(semantic=_history_statistics_semantic(), text="tampered rendered cache")

    bundle = capture_workspace(source, title="history", include_history=True)
    workspace = bundle.manifest["workspace"]
    semantic = workspace["result_snapshot"]["semantic"]
    history_payload = workspace["history"]
    current = history_payload["current"]

    assert history_payload["schema"] == "datalab.history.store.v1"
    assert current["semantic_snapshot"]["result"]["family"] == semantic["family"]
    assert current["semantic_snapshot"]["result"]["mode"] == semantic["mode"]
    assert current["semantic_snapshot"]["result"]["metric_rows"] == semantic["metric_rows"]
    assert "markdown" not in current["semantic_snapshot"]["result"]
    assert "rendered_caches_authoritative" not in current["semantic_snapshot"]["result"]["compatibility"]
    history_store_from_json(history_payload)

    path = tmp_path / "history.datalab"
    write_workspace(path, bundle.manifest, bundle.attachments)
    loaded = read_workspace(path)

    target = _HistoryFakeWindow(text="")
    restore_workspace(target, loaded.manifest, loaded.attachments)

    assert target._last_result_semantic_snapshot == semantic
    assert target._workspace_history_enabled is True
    assert target._workspace_history_store.to_json() == history_payload


def test_workspace_history_save_prunes_optional_entries_and_preserves_current() -> None:
    from app_desktop.workspace_controller import capture_workspace
    from datalab_core.history import HistoryEntry, HistoryStore

    source = _HistoryFakeWindow(semantic=_history_statistics_semantic())
    old_workspace = {
        "title": "old",
        "current_mode": "statistics",
        "language": "auto",
        "ui": {},
        "data": {},
        "constants": {},
        "config": {},
        "result_snapshot": {"present": False},
    }
    old_entry = HistoryEntry.from_workspace_snapshot(
        entry_id="old-too-large",
        label="old",
        created_at="2026-06-19T00:00:00Z",
        workspace=old_workspace,
        family="statistics",
        kind="statistics_single",
        result_snapshot={"status": "success", "value": "x" * (2 * 1024 * 1024 + 1)},
    )
    source._workspace_history_store = HistoryStore(entries=(old_entry,))
    source._workspace_history_enabled = True

    bundle = capture_workspace(source, title="history", include_history=True)

    history_payload = bundle.manifest["workspace"]["history"]
    assert history_payload["current"] is not None
    assert history_payload["current"]["entry_id"] != "old-too-large"
    assert history_payload["entries"] == []
    assert source._workspace_history_prune_report.dropped_entry_ids == ("old-too-large",)


def test_workspace_history_save_demotes_stale_current_when_current_result_has_no_semantic() -> None:
    from app_desktop.workspace_controller import capture_workspace
    from datalab_core.history import history_store_from_json

    source = _HistoryFakeWindow(semantic=_history_statistics_semantic())
    first = capture_workspace(source, title="history", include_history=True)
    first_history = history_store_from_json(first.manifest["workspace"]["history"])
    assert first_history.current is not None

    source._workspace_history_store = first_history
    source._workspace_history_enabled = True
    source._last_result_semantic_snapshot = None
    source._last_result_semantic_snapshot_kind = ""
    source.result_edit.setPlainText("Rendered-only replacement")

    second = capture_workspace(source, title="rendered-only", include_history=True)
    second_history = second.manifest["workspace"]["history"]

    assert "semantic" not in second.manifest["workspace"]["result_snapshot"]
    assert second_history["current"] is None
    assert [entry["entry_id"] for entry in second_history["entries"]] == [first_history.current.entry_id]


def test_workspace_history_save_prunes_to_manifest_budget_and_remains_writable(tmp_path) -> None:
    from app_desktop.workspace_controller import capture_workspace
    from datalab_core.history import HistoryEntry, HistoryStore
    from shared.workspace_io import write_workspace
    from shared.workspace_schema import MAX_MANIFEST_BYTES

    source = _HistoryFakeWindow(semantic=_history_statistics_semantic())
    old_workspace = {
        "title": "old",
        "current_mode": "statistics",
        "language": "auto",
        "ui": {},
        "data": {},
        "constants": {},
        "config": {},
        "result_snapshot": {"present": False},
    }
    entries = tuple(
        HistoryEntry.from_workspace_snapshot(
            entry_id=f"old-{index}",
            label=f"old {index}",
            created_at=f"2026-06-19T00:00:0{index}Z",
            workspace=old_workspace,
            family="statistics",
            kind="statistics_single",
            result_snapshot={"status": "success", "value": f"{index}-" + ("x" * 500_000)},
        )
        for index in range(5)
    )
    source._workspace_history_store = HistoryStore(entries=entries)
    source._workspace_history_enabled = True

    bundle = capture_workspace(source, title="history", include_history=True)

    manifest_bytes = json.dumps(
        bundle.manifest,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    assert len(manifest_bytes) <= MAX_MANIFEST_BYTES
    assert bundle.manifest["workspace"]["history"]["current"] is not None
    assert len(bundle.manifest["workspace"]["history"]["entries"]) < len(entries)
    assert source._workspace_history_prune_report.dropped_entry_ids
    write_workspace(tmp_path / "history-budget.datalab", bundle.manifest, bundle.attachments)


def test_workspace_malformed_history_fails_before_mutating_current_data() -> None:
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = _HistoryFakeWindow(text="current")
    bundle = capture_workspace(source, title="bad history", include_history=True)
    bundle.manifest["workspace"]["history"] = {
        "schema": "datalab.history.store.v1",
        "schema_version": 1,
        "current": None,
        "entries": "bad",
    }

    target = _HistoryFakeWindow(text="keep me")

    with pytest.raises(ValueError, match="entries must be a JSON array"):
        restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.result_edit.toPlainText() == "keep me"


def test_workspace_history_float_fails_before_mutating_current_data() -> None:
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = _HistoryFakeWindow(semantic=_history_statistics_semantic(), text="current")
    bundle = capture_workspace(source, title="bad history", include_history=True)
    bundle.manifest["workspace"]["history"]["current"]["semantic_snapshot"]["result"]["value"] = 1.0

    target = _HistoryFakeWindow(text="keep me")

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.result_edit.toPlainText() == "keep me"


def test_workspace_history_save_fails_when_current_semantic_snapshot_cannot_fit() -> None:
    from app_desktop.workspace_controller import capture_workspace
    from datalab_core.history import HistoryPruneError

    source = _HistoryFakeWindow(semantic=_history_statistics_semantic())
    semantic = dict(source._last_result_semantic_snapshot)
    semantic["metric_rows"] = [
        {"key": "huge", "label": "Huge", "value": "x" * (2 * 1024 * 1024 + 1)}
    ]
    source._last_result_payloads = {}
    source._last_result_semantic_snapshot = semantic
    source._last_result_semantic_snapshot_kind = "statistics_single"
    source._last_result_kind = "statistics_single"

    with pytest.raises(HistoryPruneError, match="current history entry exceeds"):
        capture_workspace(source, title="too large", include_history=True)


def test_workspace_restores_statistics_text_and_csv_from_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    result = {
        "mode": "weighted_sigma",
        "mean": mp.mpf("1.25"),
        "std_mean": mp.mpf("0"),
        "std": mp.mpf("0"),
        "v_min": mp.mpf("1.25"),
        "v_max": mp.mpf("2.5"),
        "method_label": "Weighted mean (sigma=0 anchor)",
        "dropped": 1,
        "effective_n": mp.mpf("1"),
        "zero_sigma_anchor": True,
        "warnings": ["Detected zero sigma."],
        "source_row_ids": ("line-10", "line-11"),
    }
    source._display_statistics_result(result, "A", 2, render_plots=False)
    bundle = capture_workspace(source, title="semantic statistics stale caches")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}
    snapshot["latex_source"] = "% stale latex cache remains cache-only"

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    # result_edit renders markdown (matching the live run); assert the markdown
    # source via the cached _last_result_text, not the rendered toPlainText().
    restored_text = target._last_result_text
    metrics = {str(row["metric"]): row for row in target._csv_rows}
    assert "=== Statistics ===" in restored_text
    assert "Mode: weighted_sigma" in restored_text
    assert "Mean | 1.25 | 0.0" in restored_text
    assert target._csv_headers == ["batch", "metric", "value", "uncertainty"]
    assert metrics["mean"]["value"] == "1.25"
    assert metrics["mean"]["uncertainty"] == "0.0"
    assert metrics["zero_sigma_anchor"]["value"] == "True"
    assert target.latex_edit.toPlainText() == "% stale latex cache remains cache-only"
    assert semantic["compatibility"]["rendered_caches_authoritative"] is False
    assert semantic["compatibility"]["latex_regeneration"] == "cache_only_until_p0_5_shared_latex"


def test_workspace_restores_fitting_comparison_rows_from_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from datalab_core.fitting_comparison import (
        build_fitting_comparison_request,
        run_fitting_comparison,
    )
    from fitting.comparison_formatting import COMPARISON_TABLE_HEADERS

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "3"), ("2", "5"), ("3", "7")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
            {"candidate_id": "quadratic", "label": "Quadratic", "model_type": "polynomial", "poly_degree": 2},
        ),
        precision_digits=60,
    )
    envelope = run_fitting_comparison(request)

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    source.result_edit.setPlainText("rendered comparison cache")
    source._last_result_kind = "fitting_comparison"
    source._last_result_payloads = {"fitting_comparison": envelope.payload}
    source._workbench_result_state = "complete"
    source.latex_edit.setPlainText("% comparison latex cache remains cache-only")

    bundle = capture_workspace(source, title="fitting comparison")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    assert semantic["family"] == "fitting_comparison"
    assert [row["candidate_id"] for row in semantic["comparison_rows"]] == ["linear", "quadratic"]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    # result_edit renders markdown (matching the live run); assert the markdown
    # source via the cached _last_result_text, not the rendered toPlainText().
    restored_text = target._last_result_text
    assert "Selected Fit Comparison" in restored_text
    assert "Linear | success" in restored_text
    assert target._csv_headers == COMPARISON_TABLE_HEADERS
    assert [row["candidate_id"] for row in target._csv_rows] == ["linear", "quadratic"]
    assert target.latex_edit.toPlainText() == "% comparison latex cache remains cache-only"
    assert target._last_result_semantic_snapshot == semantic


def test_workspace_restores_root_rows_from_semantic_snapshot(qtbot, monkeypatch) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from datalab_core.root_solving import build_root_solving_request, run_root_solving

    monkeypatch.setattr("app_desktop.window_extrapolation_mixin.QMessageBox.information", lambda *args: None)
    request = build_root_solving_request(
        equations=("x^2 - A",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "0", "upper": "10"},),
        data_headers=("A",),
        data_rows=(("4",),),
        mode="scalar",
        precision_digits=50,
        display_digits=12,
        uncertainty_digits=2,
    )
    envelope = run_root_solving(request)

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    _set_combo_data(source.mode_combo, "root_solving")
    source._on_root_solving_finished(
        {
            "kind": "root_solving",
            "markdown": "stale rendered root cache",
            "csv_headers": ["stale"],
            "csv_rows": [{"name": "stale"}],
            "batch": envelope.payload["batch"],
            "display_digits": 12,
            "uncertainty_digits": 2,
            "language": "en",
            "warnings": [],
            "log": "root solving completed",
        }
    )
    source.latex_edit.setPlainText("% root latex cache remains cache-only")

    bundle = capture_workspace(source, title="semantic root")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    assert semantic["family"] == "root_solving"
    assert semantic["compatibility"]["result_cache_kind"] == "root_solving"
    assert semantic["compatibility"]["rendered_caches_authoritative"] is False

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    # result_edit renders markdown (matching the live run); assert the markdown
    # source via the cached _last_result_text, not the rendered toPlainText().
    restored_text = target._last_result_text
    assert "stale rendered root cache" not in restored_text
    assert "| input_row_index | root_index | A | name | value | classification_tags | backend |" in restored_text
    assert target._csv_headers[:3] == ["input_row_index", "root_index", "A"]
    assert "name" in target._csv_headers
    assert "value" in target._csv_headers
    assert "failure" in target._csv_headers
    assert target._csv_rows[0]["name"] == "x"
    assert target._csv_rows[0]["A"] == "4"
    assert target._csv_rows[0]["value"].startswith("2")
    assert target.latex_edit.toPlainText() == "% root latex cache remains cache-only"
    assert target._last_result_semantic_snapshot == semantic

    recaptured = capture_workspace(target, title="semantic root restored")
    assert recaptured.manifest["workspace"]["result_snapshot"]["semantic"] == semantic


def test_workspace_restores_error_rows_from_uncertainty_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from shared.uncertainty import UncertainValue

    units_config = {
        "schema": "datalab.units.annotations.v1",
        "schema_version": 1,
        "enabled": True,
        "mode": "display_only",
        "inputs": {"A": {"unit": "m"}, "B": {"unit": "m"}},
        "constants": {},
        "parameters": {},
        "outputs": {"result": {"unit": "m"}},
    }
    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    _set_combo_data(source.mode_combo, "extrapolation")
    source._show_error_results(
        ["A", "B"],
        [[mp.mpf("1.25"), mp.mpf("2.5")], [mp.mpf("2"), mp.mpf("2.5")]],
        [
            UncertainValue(
                mp.mpf("3.75"),
                mp.mpf("0.125"),
                contributions={"A": mp.mpf("0.01"), "B": mp.mpf("0.005")},
            ),
            UncertainValue(mp.mpf("4.5"), mp.mpf("0.2"), contributions={"A": mp.mpf("0.04")}),
        ],
        "A + B",
        precision_used=70,
        warnings="single warning",
        propagation={
            "method": "monte_carlo",
            "order": 2,
            "mc_samples": 2048,
            "mc_seed": 2468,
        },
        units=units_config,
    )
    source.latex_edit.setPlainText("% uncertainty latex cache remains cache-only")

    bundle = capture_workspace(source, title="semantic uncertainty")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    assert semantic["family"] == "uncertainty"
    assert semantic["compatibility"]["result_cache_kind"] == "error"
    assert semantic["metric_rows"][0]["key"] == "result_value.1"
    assert semantic["source"] == {"row_count": 2, "source_columns": ["A", "B"]}
    assert semantic["results"][0]["contributions"] == {"A": "0.01", "B": "0.005"}
    assert semantic["units"] == units_config
    assert semantic["precision"]["compute_digits"] == 70
    assert semantic["warnings"] == ["single warning"]
    assert semantic["configuration"] == {
        "propagation": {
            "method": "monte_carlo",
            "order": 2,
            "mc_samples": 2048,
            "mc_seed": 2468,
        }
    }
    diagnostic_rows = {row["key"]: row for row in semantic["diagnostic_rows"]}
    assert diagnostic_rows["configuration.propagation.method"]["value"] == "monte_carlo"
    assert diagnostic_rows["configuration.propagation.order"]["value"] == 2
    assert diagnostic_rows["configuration.propagation.mc_samples"]["value"] == 2048
    assert diagnostic_rows["configuration.propagation.mc_seed"]["value"] == 2468

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    # result_edit renders markdown (matching the live run); assert the markdown
    # source via the cached _last_result_text, not the rendered toPlainText().
    restored_text = target._last_result_text
    assert "## Error Propagation Results" in restored_text
    assert "**Formula**: `A + B`" in restored_text
    assert "**Rows**: 2" in restored_text
    assert "| # | Value [m] | Uncertainty [m] | LaTeX |" in restored_text
    assert "| 1 | 3.75 | 0.125 | 3.75 +/- 0.125 |" in restored_text
    assert target._csv_headers == ["index", "value", "uncertainty", "latex", "output_unit"]
    assert target._csv_rows == [
        {"index": 1, "value": "3.75", "uncertainty": "0.125", "latex": "3.75 +/- 0.125", "output_unit": "m"},
        {"index": 2, "value": "4.5", "uncertainty": "0.2", "latex": "4.5 +/- 0.2", "output_unit": "m"},
    ]
    assert target.latex_edit.toPlainText() == "% uncertainty latex cache remains cache-only"
    assert target._last_result_semantic_snapshot == semantic

    recaptured = capture_workspace(target, title="semantic uncertainty restored")
    assert recaptured.manifest["workspace"]["result_snapshot"]["semantic"] == semantic


def test_workspace_round_trips_error_units_config(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.formula_edit.setPlainText("distance")
    source.error_units_enabled_checkbox.setChecked(True)
    source.error_units_inputs_editor.set_rows([{"name": "distance", "value": "m"}])
    source.error_units_output_edit.setText("m")

    bundle = capture_workspace(source, title="error units")
    normalized_units = bundle.manifest["workspace"]["config"]["error"]["units"]

    assert normalized_units["inputs"] == {"distance": {"unit": "m"}}
    assert normalized_units["outputs"] == {"result": {"unit": "m"}}

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.error_units_config == normalized_units
    assert target.error_units_enabled_checkbox.isChecked()
    assert target.error_units_inputs_editor.rows() == [{"name": "distance", "value": "m"}]
    assert target.error_units_output_edit.text() == "m"


def test_workspace_round_trips_display_units_for_root_statistics_and_fitting(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.root_units_enabled_checkbox.setChecked(True)
    source.root_units_inputs_editor.set_rows([{"name": "A", "value": "m^2"}])
    source.root_units_constants_editor.set_rows([{"name": "K", "value": "J"}])
    source.root_units_output_edit.setText("m")
    source.stats_units_enabled_checkbox.setChecked(True)
    source.stats_units_inputs_editor.set_rows([{"name": "B", "value": "K"}])
    source.stats_units_output_edit.setText("K")
    source.fit_units_enabled_checkbox.setChecked(True)
    source.fit_units_inputs_editor.set_rows([{"name": "x", "value": "s"}])
    source.fit_units_constants_editor.set_rows([{"name": "C", "value": "m"}])
    source.fit_units_parameters_editor.set_rows([{"name": "a", "value": "m/s"}])
    source.fit_units_output_edit.setText("m")

    bundle = capture_workspace(source, title="display units")
    config = bundle.manifest["workspace"]["config"]

    assert config["root_solving"]["units"]["inputs"] == {"A": {"unit": "m^2"}}
    assert config["root_solving"]["units"]["constants"] == {"K": {"unit": "J"}}
    assert config["statistics"]["units"]["outputs"] == {"result": {"unit": "K"}}
    assert config["fitting"]["units"]["parameters"] == {"a": {"unit": "m/s"}}

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.root_units_enabled_checkbox.isChecked()
    assert target.root_units_inputs_editor.rows() == [{"name": "A", "value": "m^2"}]
    assert target.root_units_constants_editor.rows() == [{"name": "K", "value": "J"}]
    assert target.root_units_output_edit.text() == "m"
    assert target.stats_units_enabled_checkbox.isChecked()
    assert target.stats_units_inputs_editor.rows() == [{"name": "B", "value": "K"}]
    assert target.stats_units_output_edit.text() == "K"
    assert target.fit_units_enabled_checkbox.isChecked()
    assert target.fit_units_inputs_editor.rows() == [{"name": "x", "value": "s"}]
    assert target.fit_units_constants_editor.rows() == [{"name": "C", "value": "m"}]
    assert target.fit_units_parameters_editor.rows() == [{"name": "a", "value": "m/s"}]
    assert target.fit_units_output_edit.text() == "m"


def test_workspace_restore_without_error_config_clears_visible_error_units(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    bundle = capture_workspace(source, title="legacy without error config")
    workspace = bundle.manifest["workspace"]
    workspace["config"].pop("error", None)

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    target.error_units_enabled_checkbox.setChecked(True)
    target.error_units_inputs_editor.set_rows([{"name": "stale", "value": "m"}])
    target.error_units_constants_editor.set_rows([{"name": "K", "value": "s"}])
    target.error_units_output_edit.setText("m")
    target.error_units_config = {"enabled": True, "mode": "display_only", "inputs": {"stale": "m"}}

    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.error_units_config is None
    assert not target.error_units_enabled_checkbox.isChecked()
    assert target.error_units_inputs_editor.rows() == []
    assert target.error_units_constants_editor.rows() == []
    assert target.error_units_output_edit.text() == ""


def test_workspace_restore_without_display_units_clears_root_statistics_and_fitting_units(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    bundle = capture_workspace(source, title="legacy without display units")
    config = bundle.manifest["workspace"]["config"]
    config["root_solving"].pop("units", None)
    config["statistics"].pop("units", None)
    config["fitting"].pop("units", None)

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    target.root_units_enabled_checkbox.setChecked(True)
    target.root_units_inputs_editor.set_rows([{"name": "stale", "value": "m"}])
    target.stats_units_enabled_checkbox.setChecked(True)
    target.stats_units_inputs_editor.set_rows([{"name": "stale", "value": "s"}])
    target.fit_units_enabled_checkbox.setChecked(True)
    target.fit_units_parameters_editor.set_rows([{"name": "stale", "value": "J"}])

    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.root_units_config is None
    assert target.stats_units_config is None
    assert target.fit_units_config is None
    assert not target.root_units_enabled_checkbox.isChecked()
    assert not target.stats_units_enabled_checkbox.isChecked()
    assert not target.fit_units_enabled_checkbox.isChecked()
    assert target.root_units_inputs_editor.rows() == []
    assert target.stats_units_inputs_editor.rows() == []
    assert target.fit_units_parameters_editor.rows() == []


def test_workspace_uncertainty_snapshot_nulls_inactive_taylor_monte_carlo_options(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace
    from shared.uncertainty import UncertainValue

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    source._show_error_results(
        ["A"],
        [[mp.mpf("1")]],
        [UncertainValue(mp.mpf("1"), mp.mpf("0.1"))],
        "A",
        precision_used=50,
        propagation={
            "method": "unknown-method",
            "order": 0,
            "mc_samples": 5000,
            "mc_seed": 123,
        },
    )

    bundle = capture_workspace(source, title="semantic uncertainty taylor")
    semantic = bundle.manifest["workspace"]["result_snapshot"]["semantic"]

    assert semantic["configuration"] == {
        "propagation": {
            "method": "taylor",
            "order": 1,
            "mc_samples": None,
            "mc_seed": None,
        }
    }
    diagnostic_rows = {row["key"]: row for row in semantic["diagnostic_rows"]}
    assert diagnostic_rows["configuration.propagation.method"]["value"] == "taylor"
    assert diagnostic_rows["configuration.propagation.order"]["value"] == 1
    assert "value" not in diagnostic_rows["configuration.propagation.mc_samples"]
    assert "value" not in diagnostic_rows["configuration.propagation.mc_seed"]


def test_workspace_root_semantic_snapshot_uses_payload_compute_precision_after_ui_precision_change(
    qtbot,
    monkeypatch,
) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from root_solving.models import RootBatchResult, RootBatchRowResult, RootResult, RootValue
    from shared.root_solving_engine import serialize_root_batch_result

    monkeypatch.setattr("app_desktop.window_extrapolation_mixin.QMessageBox.information", lambda *args: None)
    value_text = "1.234567890123456789012345678901234567890123456789"
    with mp.mp.workdps(90):
        batch = RootBatchResult(
            rows=(
                RootBatchRowResult(
                    row_index=None,
                    source_values={},
                    result=RootResult(
                        roots=(RootValue(name="x", value=mp.mpf(value_text)),),
                        backend="mpmath",
                        mode="scalar",
                        residual_norm=mp.mpf("0"),
                    ),
                ),
            ),
        )
        batch_payload = serialize_root_batch_result(batch, digits=80)

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    _set_combo_data(source.mode_combo, "root_solving")
    source._on_root_solving_finished(
        {
            "kind": "root_solving",
            "markdown": "stale rendered root cache",
            "csv_headers": ["stale"],
            "csv_rows": [{"name": "stale"}],
            "batch": batch_payload,
            "compute_digits": 90,
            "display_digits": 45,
            "uncertainty_digits": 1,
            "language": "en",
            "warnings": [],
            "log": "root solving completed",
        }
    )
    source.mpmath_precision_spin.setValue(16)

    bundle = capture_workspace(source, title="semantic high precision root")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    assert semantic["precision"]["compute_digits"] == 90

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    previous_dps = mp.mp.dps
    try:
        mp.mp.dps = 15
        restore_workspace(target, bundle.manifest, bundle.attachments)
    finally:
        mp.mp.dps = previous_dps

    assert target._csv_rows[0]["value"].startswith("1.23456789012345678901234567890123456789012")


def test_desktop_refresh_display_formats_fitting_comparison_payload(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from datalab_core.fitting_comparison import (
        build_fitting_comparison_request,
        run_fitting_comparison,
    )
    from fitting.comparison_formatting import COMPARISON_TABLE_HEADERS

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "3"), ("2", "5"), ("3", "7")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
            {"candidate_id": "quadratic", "label": "Quadratic", "model_type": "polynomial", "poly_degree": 2},
        ),
        precision_digits=60,
    )
    envelope = run_fitting_comparison(request)

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window._apply_language("en")
    window._remember_last_result("fitting_comparison", dict(envelope.payload))

    window._refresh_display_format()

    rendered_text = window.result_edit.toPlainText()
    assert "Selected Fit Comparison" in rendered_text
    assert "Linear" in rendered_text
    assert "success" in rendered_text
    assert "['" not in rendered_text
    assert window._csv_headers == COMPARISON_TABLE_HEADERS
    assert [row["candidate_id"] for row in window._csv_rows] == ["linear", "quadratic"]
    assert window._csv_suggest_name == "fitting_comparison_results.csv"


def test_desktop_refresh_display_formats_error_payload_with_semantic_metadata(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from shared.uncertainty import UncertainValue

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window._apply_language("en")
    window._show_error_results(
        ["A"],
        [[mp.mpf("1")]],
        [UncertainValue(mp.mpf("1"), mp.mpf("0.1"))],
        "A",
        precision_used=50,
        warnings=["warning"],
        propagation={
            "method": "monte_carlo",
            "order": 1,
            "mc_samples": 5000,
            "mc_seed": None,
        },
        units={
            "schema": "datalab.units.annotations.v1",
            "schema_version": 1,
            "enabled": True,
            "mode": "display_only",
            "inputs": {"A": {"unit": "m"}},
            "constants": {},
            "parameters": {},
            "outputs": {"result": {"unit": "m"}},
        },
    )

    window._refresh_display_format()

    rendered_text = window.result_edit.toPlainText()
    assert "Error Propagation Results" in rendered_text
    assert "Formula: A" in rendered_text
    assert "Value [m]" in rendered_text
    assert "Uncertainty [m]" in rendered_text
    assert window._csv_headers == ["index", "value", "uncertainty", "latex", "output_unit"]
    assert window._csv_rows[0]["output_unit"] == "m"
    assert window._last_result_payloads["error"]["propagation"] == {
        "method": "monte_carlo",
        "order": 1,
        "mc_samples": 5000,
        "mc_seed": None,
    }


def test_workspace_ignores_wrong_kind_fitting_comparison_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from datalab_core.fitting_comparison import (
        build_fitting_comparison_request,
        run_fitting_comparison,
    )

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "3"), ("2", "5"), ("3", "7")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
        ),
        precision_digits=60,
    )
    envelope = run_fitting_comparison(request)
    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.result_edit.setPlainText("cached root snapshot text")
    source._last_result_kind = "fitting_comparison"
    source._last_result_payloads = {"fitting_comparison": envelope.payload}
    source._workbench_result_state = "complete"

    bundle = capture_workspace(source, title="wrong kind fitting comparison")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    snapshot["kind"] = "root_solving"
    snapshot["markdown"] = "cached root fallback"
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": ["root"], "rows": [{"root": "2"}]}

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.result_edit.toPlainText() == "cached root fallback"
    assert target._csv_headers == ["root"]
    assert target._csv_rows == [{"root": "2"}]
    assert target._last_result_semantic_snapshot is None

    recaptured = capture_workspace(target, title="wrong kind fitting comparison recaptured")
    recaptured_snapshot = recaptured.manifest["workspace"]["result_snapshot"]
    assert "semantic" not in recaptured_snapshot
    assert recaptured_snapshot["kind"] == "snapshot"
    assert semantic["family"] == "fitting_comparison"


def test_workspace_restores_weighted_consistency_rows_from_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    result = {
        "mode": "weighted_sigma",
        "mean": mp.mpf(16) / 9,
        "std_mean": mp.mpf("0.6666666666666666667"),
        "std": mp.mpf("1.3333333333333333333"),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("4"),
        "method_label": "Weighted mean (sample)",
        "dropped": 0,
        "effective_n": mp.mpf(81) / 33,
        "weighted_chi_square": mp.mpf(17) / 9,
        "weighted_consistency_dof": 2,
        "weighted_reduced_chi_square": mp.mpf(17) / 18,
        "birge_ratio": mp.sqrt(mp.mpf(17) / 18),
        "source_row_ids": ("1", "2", "3"),
    }
    source._display_statistics_result(result, "A", 3, render_plots=False)
    bundle = capture_workspace(source, title="weighted consistency statistics")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    assert {row["key"] for row in semantic["metric_rows"]} >= {
        "weighted_chi_square",
        "weighted_consistency_dof",
        "weighted_reduced_chi_square",
        "birge_ratio",
    }

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    # result_edit renders markdown (matching the live run); assert the markdown
    # source via the cached _last_result_text, not the rendered toPlainText().
    restored_text = target._last_result_text
    metrics = {str(row["metric"]): row for row in target._csv_rows}
    assert "Weighted chi-square |" in restored_text
    assert "Weighted consistency dof | 2" in restored_text
    assert "weighted_chi_square" in metrics
    assert metrics["weighted_consistency_dof"]["value"] == 2


def test_workspace_restores_confidence_interval_rows_from_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    result = {
        "mode": "mean_population",
        "mean": mp.mpf("2.5"),
        "std_mean": mp.sqrt(mp.mpf("1.25")) / 2,
        "std": mp.sqrt(mp.mpf("1.25")),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("4"),
        "method_label": "Arithmetic mean (population)",
        "dropped": 0,
        "mean_ci_confidence_level": mp.mpf("0.95"),
        "mean_ci_lower": mp.mpf("0.445739743239121"),
        "mean_ci_upper": mp.mpf("4.554260256760879"),
        "mean_ci_margin": mp.mpf("2.054260256760879"),
        "mean_ci_method_label": "Student-t mean CI (sample standard deviation)",
        "mean_ci_critical_value": mp.mpf("3.182446305284263"),
        "mean_sample_se_for_ci": mp.mpf("0.6454972243679028"),
        "mean_ci_dof": 3,
        "source_row_ids": ("1", "2", "3", "4"),
    }
    source._display_statistics_result(result, "A", 4, render_plots=False)
    bundle = capture_workspace(source, title="confidence interval statistics")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    assert {row["key"] for row in semantic["metric_rows"]} >= {
        "mean_ci_lower",
        "mean_ci_upper",
        "mean_sample_se_for_ci",
        "mean_ci_method",
    }

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    # result_edit renders markdown (matching the live run); assert the markdown
    # source via the cached _last_result_text, not the rendered toPlainText().
    restored_text = target._last_result_text
    metrics = {str(row["metric"]): row for row in target._csv_rows}
    assert "Mean CI lower | 0.445739743239121" in restored_text
    assert metrics["mean_ci_lower"]["value"] == "0.445739743239121"
    assert metrics["mean_ci_method"]["value"] == "Student-t mean CI (sample standard deviation)"


def test_workspace_restores_descriptive_statistics_rows_from_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    result = {
        "mode": "descriptive",
        "mean": mp.mpf("2.5"),
        "std_mean": mp.mpf("0.6454972243679028142"),
        "std": mp.mpf("1.2909944487358056284"),
        "variance": mp.mpf("1.6666666666666666667"),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("4"),
        "count": 4,
        "trimmed_mean": mp.mpf("2.5"),
        "median": mp.mpf("2.5"),
        "q1": mp.mpf("1.75"),
        "q3": mp.mpf("3.25"),
        "iqr": mp.mpf("1.5"),
        "mad": mp.mpf("1"),
        "skewness": mp.mpf("0"),
        "excess_kurtosis": mp.mpf("-1.2"),
        "method_label": "Descriptive statistics (sample)",
        "dropped": 0,
        "effective_n": None,
        "zero_sigma_anchor": False,
        "warnings": [],
        "source_row_ids": ("1", "2", "3", "4"),
    }
    source.stats_trim_fraction_edit.setText("0.25")
    source._display_statistics_result(result, "A", 4, render_plots=False)
    bundle = capture_workspace(source, title="descriptive statistics")
    assert bundle.manifest["workspace"]["config"]["statistics"]["trim_fraction"] == "0.25"
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    assert {row["key"] for row in semantic["metric_rows"]} >= {"trimmed_mean", "median", "q1", "q3", "iqr", "mad"}

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    # result_edit renders markdown (matching the live run); assert the markdown
    # source via the cached _last_result_text, not the rendered toPlainText().
    restored_text = target._last_result_text
    assert target.stats_trim_fraction_edit.text() == "0.25"
    assert "Trimmed mean | 2.5" in restored_text
    assert "Median | 2.5" in restored_text
    assert "Excess kurtosis | -1.2" in restored_text
    assert {str(row["metric"]) for row in target._csv_rows} >= {"trimmed_mean", "median", "q1", "q3", "iqr", "mad"}


def test_workspace_restores_outlier_row_flags_from_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    result = {
        "mode": "mean_sample",
        "mean": mp.mpf("3.3333333333333333333"),
        "std_mean": mp.mpf("3.3333333333333333333"),
        "std": mp.mpf("5.7735026918962576451"),
        "v_min": mp.mpf("0"),
        "v_max": mp.mpf("10"),
        "method_label": "Arithmetic mean (sample)",
        "dropped": 0,
        "source_row_ids": ("r1", "r2", "r3"),
        "outlier_flags": [
            {
                "source_row_id": "r3",
                "value": "10.0",
                "metric": "sigma",
                "reason": "statistics.flag.outlier_sigma.residual_gt_3sigma",
            }
        ],
    }
    source._display_statistics_result(result, "A", 3, render_plots=False)
    bundle = capture_workspace(source, title="outlier statistics")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    assert semantic["row_flags"][0]["key"] == "outlier.sigma.1"
    assert semantic["row_flags"][0]["row_index"] == "r3"

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    # result_edit renders markdown (matching the live run); assert the markdown
    # source via the cached _last_result_text, not the rendered toPlainText().
    restored_text = target._last_result_text
    metrics = {str(row["metric"]): row for row in target._csv_rows}
    assert "Sigma outlier | 10.0 | source row r3; metric sigma; absolute residual exceeds 3 sigma" in restored_text
    assert metrics["outlier.sigma.1"]["value"] == "10.0"
    assert metrics["outlier.sigma.1"]["uncertainty"] == (
        "source row r3; metric sigma; absolute residual exceeds 3 sigma"
    )


def test_workspace_restores_descriptive_warning_text_not_message_key(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics, statistics_payload_to_compute_result

    core_result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={"values": ["7"], "stats_mode": "descriptive", "use_sample": True},
            options=JobOptions(precision_digits=60),
            request_id="workspace-descriptive-warning-text",
        )
    )
    result = statistics_payload_to_compute_result(core_result.payload, core_result.warnings)

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    source._display_statistics_result(result, "A", 1, render_plots=False)
    bundle = capture_workspace(source, title="descriptive warning statistics")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    warning_rows = semantic["diagnostic_rows"]
    assert any(row.get("message_key") == "statistics.warning.descriptive_zero_variance" for row in warning_rows)
    assert any("Zero variance" in str(row.get("value")) for row in warning_rows)

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    restored_text = target.result_edit.toPlainText()
    assert "Zero variance" in restored_text
    assert "Sample descriptive statistics require n>=2" in restored_text
    assert "statistics.warning.descriptive" not in restored_text


def test_workspace_restores_statistics_batch_snapshot_from_semantic_source(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    batches = [
        {
            "index": 1,
            "row_count": 2,
            "value_col": "A",
            "result": {
                "mode": "mean",
                "mean": mp.mpf("1.5"),
                "std_mean": mp.mpf("0.5"),
                "std": mp.mpf("0.7071067811865475"),
                "v_min": mp.mpf("1"),
                "v_max": mp.mpf("2"),
                "method_label": "Arithmetic mean (sample)",
                "dropped": 0,
                "source_row_ids": ("batch-1-row-1", "batch-1-row-2"),
            },
        },
        {
            "index": 2,
            "row_count": 3,
            "value_col": "A",
            "result": {
                "mode": "mean",
                "mean": mp.mpf("4"),
                "std_mean": mp.mpf("1"),
                "std": mp.mpf("1.7320508075688772"),
                "v_min": mp.mpf("2"),
                "v_max": mp.mpf("6"),
                "method_label": "Arithmetic mean (sample)",
                "dropped": 0,
                "source_row_ids": ("batch-2-row-1", "batch-2-row-2", "batch-2-row-3"),
            },
        },
    ]
    source._display_statistics_batches(batches, "A", render_plots=False)

    bundle = capture_workspace(source, title="semantic statistics batches")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]
    assert semantic["compatibility"]["result_cache_kind"] == "statistics_batches"
    assert semantic["source"]["batches"] == [
        {
            "index": 1,
            "row_count": 2,
            "value_column": "A",
            "source_row_ids": ["batch-1-row-1", "batch-1-row-2"],
        },
        {
            "index": 2,
            "row_count": 3,
            "value_column": "A",
            "source_row_ids": ["batch-2-row-1", "batch-2-row-2", "batch-2-row-3"],
        },
    ]
    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    restored_text = target.result_edit.toPlainText()
    metrics = {(row["batch"], row["metric"]): row for row in target._csv_rows}
    assert "=== Statistics: Batch 1 ===" in restored_text
    assert "=== Statistics: Batch 2 ===" in restored_text
    assert target._csv_headers == ["batch", "metric", "value", "uncertainty"]
    assert metrics[(1, "mean")]["value"] == "1.5"
    assert metrics[(2, "mean")]["value"] == "4.0"

    recaptured = capture_workspace(target, title="semantic statistics batches restored")
    assert recaptured.manifest["workspace"]["result_snapshot"]["semantic"] == semantic


def test_workspace_preserves_statistics_value_columns_config(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.stats_value_column_edit.setText("B, A")

    bundle = capture_workspace(source, title="statistics columns")
    statistics_config = bundle.manifest["workspace"]["config"]["statistics"]
    assert statistics_config["value_column"] == "B"
    assert statistics_config["value_columns"] == ["B", "A"]

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.stats_value_column_edit.text() == "B, A"


def test_workspace_preserves_statistics_bootstrap_config(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.stats_workflow_combo, "bootstrap_confidence_intervals")
    _set_combo_data(source.stats_bootstrap_target_combo, "trimmed_mean")
    source.stats_bootstrap_resamples_spin.setValue(125)
    source.stats_bootstrap_seed_edit.setText("42")
    source.stats_trim_fraction_edit.setText("0.2")
    source.stats_sample_checkbox.setChecked(True)
    source.stats_value_column_edit.setText("B, A")

    bundle = capture_workspace(source, title="statistics bootstrap")
    statistics_config = bundle.manifest["workspace"]["config"]["statistics"]

    assert statistics_config["workflow_mode"] == "bootstrap_confidence_intervals"
    assert statistics_config["value_columns"] == ["B", "A"]
    assert statistics_config["bootstrap"] == {
        "target_statistic": "trimmed_mean",
        "confidence_level": "0.95",
        "resample_count": 125,
        "seed": "42",
    }
    assert statistics_config["trim_fraction"] == "0.2"

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.stats_workflow_combo.currentData() == "bootstrap_confidence_intervals"
    assert target.stats_bootstrap_target_combo.currentData() == "trimmed_mean"
    assert target.stats_bootstrap_resamples_spin.value() == 125
    assert target.stats_bootstrap_seed_edit.text() == "42"
    assert target.stats_trim_fraction_edit.text() == "0.2"
    assert target.stats_value_column_edit.text() == "B, A"
    assert target.stats_mode_combo.isHidden()
    assert not target.stats_bootstrap_target_combo.isHidden()
    assert not target.stats_trim_fraction_edit.isHidden()


def test_workspace_preserves_statistics_hypothesis_config(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.stats_workflow_combo, "hypothesis_tests")
    _set_combo_data(source.stats_hypothesis_test_combo, "welch_t")
    _set_combo_data(source.stats_hypothesis_alternative_combo, "greater")
    source.stats_value_column_edit.setText("A")
    source.stats_hypothesis_b_column_edit.setText("B")
    source.stats_hypothesis_null_edit.setText("0.25")
    source.stats_hypothesis_alpha_edit.setText("0.01")

    bundle = capture_workspace(source, title="statistics hypothesis")
    statistics_config = bundle.manifest["workspace"]["config"]["statistics"]

    assert statistics_config["workflow_mode"] == "hypothesis_tests"
    assert statistics_config["hypothesis"] == {
        "test_kind": "welch_t",
        "second_column": "B",
        "null_parameter": "0.25",
        "alternative": "greater",
        "alpha": "0.01",
        "expected_source": "counts",
        "fitted_parameter_count": 0,
    }

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.stats_workflow_combo.currentData() == "hypothesis_tests"
    assert target.stats_hypothesis_test_combo.currentData() == "welch_t"
    assert target.stats_hypothesis_alternative_combo.currentData() == "greater"
    assert target.stats_hypothesis_b_column_edit.text() == "B"
    assert target.stats_hypothesis_null_edit.text() == "0.25"
    assert target.stats_hypothesis_alpha_edit.text() == "0.01"
    assert target.stats_mode_combo.isHidden()
    assert not target.stats_hypothesis_b_column_edit.isHidden()


def test_workspace_restore_resets_missing_statistics_bootstrap_config(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.stats_value_column_edit.setText("A")
    bundle = capture_workspace(source, title="legacy statistics")
    statistics_config = bundle.manifest["workspace"]["config"]["statistics"]
    statistics_config.pop("bootstrap", None)
    statistics_config["workflow_mode"] = "standard"

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    _set_combo_data(target.stats_workflow_combo, "bootstrap_confidence_intervals")
    _set_combo_data(target.stats_bootstrap_target_combo, "trimmed_mean")
    target.stats_bootstrap_resamples_spin.setValue(125)
    target.stats_bootstrap_seed_edit.setText("42")

    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.stats_workflow_combo.currentData() == "standard"
    assert target.stats_bootstrap_target_combo.currentData() == "mean"
    assert target.stats_bootstrap_confidence_edit.text() == "0.95"
    assert target.stats_bootstrap_resamples_spin.value() == 2000
    assert target.stats_bootstrap_seed_edit.text() == ""
    restored = capture_workspace(target, title="restored legacy statistics")
    assert restored.manifest["workspace"]["config"]["statistics"]["bootstrap"] == {
        "target_statistic": "mean",
        "confidence_level": "0.95",
        "resample_count": 2000,
        "seed": "",
    }


def test_desktop_statistics_bootstrap_controls_mark_workspace_dirty(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    def reset_snapshot_state() -> None:
        window._workspace_dirty = False
        window._workspace_snapshot_only = True
        window._workspace_snapshot_stale = False

    reset_snapshot_state()
    _set_combo_data(window.stats_workflow_combo, "bootstrap_confidence_intervals")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    _set_combo_data(window.stats_bootstrap_target_combo, "median")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    window.stats_bootstrap_resamples_spin.setValue(125)
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    window.stats_bootstrap_seed_edit.setText("42")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True


def test_workspace_round_trips_statistics_time_series_config(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.stats_workflow_combo, "time_series_rolling")
    source.stats_value_column_edit.setText("A, B")
    source.stats_sigma_column_edit.setText("sA, sB")
    _set_combo_data(source.stats_time_series_method_combo, "ewma")
    source.stats_time_series_time_column_edit.setText("t")
    source.stats_time_series_window_size_spin.setValue(7)
    source.stats_time_series_min_periods_spin.setValue(3)
    _set_combo_data(source.stats_time_series_alignment_combo, "center")
    _set_combo_data(source.stats_time_series_denominator_combo, "population")
    _set_combo_data(source.stats_time_series_ewma_parameter_combo, "span")
    source.stats_time_series_ewma_value_edit.setText("5")
    source.stats_time_series_ewma_adjust_checkbox.setChecked(True)

    bundle = capture_workspace(source, title="time series config")
    statistics_config = bundle.manifest["workspace"]["config"]["statistics"]

    assert statistics_config["workflow_mode"] == "time_series_rolling"
    assert statistics_config["time_series"] == {
        "series_method": "ewma",
        "time_column": "t",
        "window_size": 7,
        "min_periods": 3,
        "alignment": "center",
        "denominator": "population",
        "ewma_parameter": "span",
        "ewma_value": "5",
        "adjust": True,
    }

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.stats_workflow_combo.currentData() == "time_series_rolling"
    assert target.stats_value_column_edit.text() == "A, B"
    assert target.stats_sigma_column_edit.text() == "sA, sB"
    assert target.stats_time_series_method_combo.currentData() == "ewma"
    assert target.stats_time_series_time_column_edit.text() == "t"
    assert target.stats_time_series_window_size_spin.value() == 7
    assert target.stats_time_series_min_periods_spin.value() == 3
    assert target.stats_time_series_alignment_combo.currentData() == "center"
    assert target.stats_time_series_denominator_combo.currentData() == "population"
    assert target.stats_time_series_ewma_parameter_combo.currentData() == "span"
    assert target.stats_time_series_ewma_value_edit.text() == "5"
    assert target.stats_time_series_ewma_adjust_checkbox.isChecked() is True


def test_workspace_restores_file_backed_data_for_statistics_time_series(qtbot, tmp_path: Path) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    data_path = tmp_path / "series.txt"
    data_path.write_text("t A\np1 1\np2 3\np3 5\n", encoding="utf-8")

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source.use_file_checkbox.setChecked(True)
    source.data_file_edit.setText(str(data_path))
    _set_combo_data(source.stats_workflow_combo, "time_series_rolling")
    source.stats_value_column_edit.setText("A")
    source.stats_time_series_time_column_edit.setText("t")
    source.stats_time_series_window_size_spin.setValue(2)
    source.stats_time_series_min_periods_spin.setValue(2)

    bundle = capture_workspace(source, title="file backed time series")
    data_path.unlink()

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.use_file_checkbox.isChecked() is False
    assert target._data_stack.currentIndex() == 1
    assert "p1 1" in target.manual_data_edit.toPlainText()

    target._run_statistics_mode(False, "")

    assert target._last_result_kind == "statistics_time_series"
    assert target._last_result_semantic_snapshot["source"]["time_column"] == "t"
    assert any(row["time"] == "p2" for row in target._csv_rows)


def test_desktop_statistics_hypothesis_controls_mark_workspace_dirty(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    def reset_snapshot_state() -> None:
        window._workspace_dirty = False
        window._workspace_snapshot_only = True
        window._workspace_snapshot_stale = False

    reset_snapshot_state()
    _set_combo_data(window.stats_workflow_combo, "hypothesis_tests")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    _set_combo_data(window.stats_hypothesis_test_combo, "welch_t")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    window.stats_hypothesis_b_column_edit.setText("C")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    window.stats_hypothesis_null_edit.setText("0.25")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    window.stats_hypothesis_alpha_edit.setText("0.01")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True


def test_desktop_statistics_time_series_controls_mark_workspace_dirty(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)

    def reset_snapshot_state() -> None:
        window._workspace_dirty = False
        window._workspace_snapshot_only = True
        window._workspace_snapshot_stale = False

    reset_snapshot_state()
    _set_combo_data(window.stats_workflow_combo, "time_series_rolling")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    _set_combo_data(window.stats_time_series_method_combo, "rolling_std")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    window.stats_time_series_time_column_edit.setText("t")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    window.stats_time_series_window_size_spin.setValue(5)
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    window.stats_time_series_min_periods_spin.setValue(2)
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    _set_combo_data(window.stats_time_series_alignment_combo, "center")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    _set_combo_data(window.stats_time_series_denominator_combo, "population")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    _set_combo_data(window.stats_time_series_ewma_parameter_combo, "span")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    window.stats_time_series_ewma_value_edit.setText("0.25")
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True

    reset_snapshot_state()
    window.stats_time_series_ewma_adjust_checkbox.setChecked(True)
    assert window._workspace_dirty is True
    assert window._workspace_snapshot_stale is True


def test_workspace_preserves_statistics_bootstrap_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    source.manual_data_edit.setPlainText("A\n1\n2\n3\n4\n")
    source._data_stack.setCurrentIndex(1)
    _set_combo_data(source.stats_workflow_combo, "bootstrap_confidence_intervals")
    source.stats_value_column_edit.setText("A")
    source.stats_bootstrap_resamples_spin.setValue(100)
    source.stats_bootstrap_seed_edit.setText("42")

    source._run_statistics_mode(False, "")

    bundle = capture_workspace(source, title="statistics bootstrap semantic")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]

    assert snapshot["kind"] == "statistics_bootstrap"
    assert semantic["compatibility"]["result_cache_kind"] == "statistics_bootstrap"
    assert semantic["bootstrap"]["seed"] == 42

    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target._last_result_semantic_snapshot_kind == "statistics_bootstrap"
    assert any(row["metric"] == "bootstrap_ci_lower" for row in target._csv_rows)
    assert "Bootstrap CI lower" in target.result_edit.toPlainText()

    recaptured = capture_workspace(target, title="statistics bootstrap semantic restored")
    assert recaptured.manifest["workspace"]["result_snapshot"]["semantic"] == semantic


def test_workspace_preserves_statistics_hypothesis_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    source.manual_data_edit.setPlainText("A\n2\n3\n4\n5\n6\n")
    source._data_stack.setCurrentIndex(1)
    _set_combo_data(source.stats_workflow_combo, "hypothesis_tests")
    _set_combo_data(source.stats_hypothesis_test_combo, "one_sample_t")
    source.stats_value_column_edit.setText("A")
    source.stats_hypothesis_null_edit.setText("3")
    source._run_statistics_mode(False, "")

    bundle = capture_workspace(source, title="statistics hypothesis semantic")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]

    assert snapshot["kind"] == "statistics_hypothesis_test"
    assert semantic["compatibility"]["result_cache_kind"] == "statistics_hypothesis_test"
    assert semantic["hypothesis_test"]["test_kind"] == "one_sample_t"

    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target._last_result_semantic_snapshot_kind == "statistics_hypothesis_test"
    assert any(row["metric"] == "p_value" for row in target._csv_rows)
    assert "Hypothesis Test" in target.result_edit.toPlainText()

    recaptured = capture_workspace(target, title="statistics hypothesis semantic restored")
    assert recaptured.manifest["workspace"]["result_snapshot"]["semantic"] == semantic


def test_workspace_preserves_statistics_matrix_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    source.manual_data_edit.setPlainText("A B\n1 2\n2 4\n3 6\n")
    source._data_stack.setCurrentIndex(1)
    _set_combo_data(source.stats_workflow_combo, "covariance_correlation")
    source.stats_value_column_edit.setText("A, B")
    source._run_statistics_mode(False, "")

    bundle = capture_workspace(source, title="statistics matrix semantic")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]

    assert snapshot["kind"] == "statistics_matrix"
    assert semantic["compatibility"]["result_cache_kind"] == "statistics_matrix"
    assert semantic["statistics_matrix"]["columns"] == ["A", "B"]

    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target._last_result_semantic_snapshot_kind == "statistics_matrix"
    assert any(row["matrix"] == "correlation" and row["row_column"] == "A" for row in target._csv_rows)
    assert "Covariance/correlation matrix" in target.result_edit.toPlainText()

    recaptured = capture_workspace(target, title="statistics matrix semantic restored")
    assert recaptured.manifest["workspace"]["result_snapshot"]["semantic"] == semantic


def test_workspace_preserves_statistics_grouped_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    source.manual_data_edit.setPlainText("Group A\ncontrol 1\ncontrol 3\ntreated 2\ntreated 4\n")
    source._data_stack.setCurrentIndex(1)
    _set_combo_data(source.stats_workflow_combo, "grouped_statistics")
    source.stats_group_column_edit.setText("Group")
    source.stats_value_column_edit.setText("A")
    source._run_statistics_mode(False, "")

    bundle = capture_workspace(source, title="statistics grouped semantic")
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    semantic = snapshot["semantic"]

    assert snapshot["kind"] == "statistics_grouped"
    assert semantic["compatibility"]["result_cache_kind"] == "statistics_grouped"
    assert semantic["statistics_grouped"]["group_order"] == ["control", "treated"]

    snapshot["markdown"] = ""
    snapshot["markdown_format"] = "plain"
    snapshot["csv"] = {"headers": [], "rows": []}

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target._last_result_semantic_snapshot_kind == "statistics_grouped"
    assert any(row["group"] == "control" and row["metric"] == "mean" for row in target._csv_rows)
    assert "Grouped statistics" in target.result_edit.toPlainText()

    recaptured = capture_workspace(target, title="statistics grouped semantic restored")
    assert recaptured.manifest["workspace"]["result_snapshot"]["semantic"] == semantic


def test_workspace_preserves_statistics_plot_gallery(qtbot, tmp_path) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace
    from PySide6.QtGui import QImage

    first_plot = tmp_path / "stats-b.png"
    second_plot = tmp_path / "stats-a.png"
    image = QImage(1, 1, QImage.Format.Format_ARGB32)
    image.fill(0xFF336699)
    assert image.save(str(first_plot), "PNG")
    image.fill(0xFF993366)
    assert image.save(str(second_plot), "PNG")
    first_plot_bytes = first_plot.read_bytes()
    second_plot_bytes = second_plot.read_bytes()

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    source.result_edit.setPlainText("multi-column statistics")
    source._last_result_text = "multi-column statistics"
    source._last_result_text_format = "plain"
    source._last_result_rendered_text = "multi-column statistics"
    source._last_result_kind = "statistics_batches"
    source._last_result_payloads = {
        "statistics_batches": {
            "value_col": "B, A",
            "value_columns": ["B", "A"],
            "batches": [
                {
                    "index": 1,
                    "column_index": 1,
                    "batch_index": 1,
                    "row_count": 2,
                    "value_col": "B",
                    "result": {
                        "mode": "mean",
                        "mean": mp.mpf("10"),
                        "std_mean": mp.mpf("1"),
                        "std": mp.mpf("1.4142135623730951"),
                        "v_min": mp.mpf("9"),
                        "v_max": mp.mpf("11"),
                        "method_label": "Arithmetic mean (sample)",
                        "dropped": 0,
                        "source_row_ids": ("b1", "b2"),
                    },
                },
                {
                    "index": 2,
                    "column_index": 2,
                    "batch_index": 1,
                    "row_count": 2,
                    "value_col": "A",
                    "result": {
                        "mode": "mean",
                        "mean": mp.mpf("1.5"),
                        "std_mean": mp.mpf("0.5"),
                        "std": mp.mpf("0.7071067811865475"),
                        "v_min": mp.mpf("1"),
                        "v_max": mp.mpf("2"),
                        "method_label": "Arithmetic mean (sample)",
                        "dropped": 0,
                        "source_row_ids": ("a1", "a2"),
                    },
                },
            ],
        }
    }
    source._set_image_list("stats", [first_plot, second_plot])
    source._current_stats_plot_metadata = [
        {"column": "B", "batch": 1, "plot_index": 1, "title": "B statistics"},
        {"column": "A", "batch": 1, "plot_index": 1, "title": "A statistics"},
    ]

    bundle = capture_workspace(source, title="statistics plots", include_history=True)
    snapshot = bundle.manifest["workspace"]["result_snapshot"]
    current_history = bundle.manifest["workspace"]["history"]["current"]

    assert [plot["path"] for plot in snapshot["plots"]] == [
        "attachments/plots/plot-001.png",
        "attachments/plots/plot-002.png",
    ]
    assert [plot["path"] for plot in current_history["rendered_cache"]["plots"]] == [
        "attachments/plots/plot-001.png",
        "attachments/plots/plot-002.png",
    ]
    assert [plot["column"] for plot in snapshot["plots"]] == ["B", "A"]
    assert [plot["image_mode"] for plot in snapshot["plots"]] == ["stats", "stats"]
    assert bundle.attachments["attachments/plots/plot-001.png"] == first_plot_bytes
    assert bundle.attachments["attachments/plots/plot-002.png"] == second_plot_bytes

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target._image_mode == "stats"
    assert len(target.current_stats_figures) == 2
    assert target.result_plot_bytes == first_plot_bytes
    assert target.image_page_spin.maximum() == 2


def test_restored_statistics_semantic_snapshot_does_not_leak_to_new_result(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    result = {
        "mode": "mean",
        "mean": mp.mpf("1.5"),
        "std_mean": mp.mpf("0.5"),
        "std": mp.mpf("0.7071067811865475"),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("2"),
        "method_label": "Arithmetic mean (sample)",
        "dropped": 0,
        "source_row_ids": ("1", "2"),
    }
    source._display_statistics_result(result, "A", 2, render_plots=False)
    bundle = capture_workspace(source, title="semantic statistics")

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)
    assert target._last_result_semantic_snapshot is not None

    target._set_result_text("root result", final_result=True)
    target._set_csv_data([{"root": "2"}], ["root"])
    target._remember_last_result("root_solving", {"markdown": "root result"})
    assert target._last_result_semantic_snapshot is None

    recaptured = capture_workspace(target, title="root after stats")
    recaptured_snapshot = recaptured.manifest["workspace"]["result_snapshot"]
    assert recaptured_snapshot["kind"] == "root_solving"
    assert "semantic" not in recaptured_snapshot
    assert recaptured_snapshot["csv"] == {"headers": ["root"], "rows": [{"root": "2"}]}


def test_full_result_reset_clears_restored_statistics_semantic_snapshot(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    source._apply_language("en")
    result = {
        "mode": "mean",
        "mean": mp.mpf("1.5"),
        "std_mean": mp.mpf("0.5"),
        "std": mp.mpf("0.7071067811865475"),
        "v_min": mp.mpf("1"),
        "v_max": mp.mpf("2"),
        "method_label": "Arithmetic mean (sample)",
        "dropped": 0,
        "source_row_ids": ("1", "2"),
    }
    source._display_statistics_result(result, "A", 2, render_plots=False)
    bundle = capture_workspace(source, title="semantic statistics")

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)
    assert target._last_result_semantic_snapshot is not None

    target._reset_csv_data(clear_non_tabular_result=True)
    assert target._last_result_semantic_snapshot is None
    assert target._last_result_semantic_snapshot_kind is None
    target._set_result_text("calculation failed before a new result payload", final_result=True)

    recaptured = capture_workspace(target, title="failed before remembered result")
    recaptured_snapshot = recaptured.manifest["workspace"]["result_snapshot"]
    assert recaptured_snapshot["present"] is True
    assert "semantic" not in recaptured_snapshot


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
    assert restored._last_result_semantic_snapshot is None

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


def test_v2_workspace_fixture_restores_and_saves_back_as_v1(qtbot, tmp_path) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import restore_workspace
    from shared.workspace_io import read_workspace

    fixture_path = Path(__file__).parent / "fixtures" / "workspaces" / "model_native_v2_minimal.datalab"
    loaded = read_workspace(fixture_path)

    restored = ExtrapolationWindow()
    qtbot.addWidget(restored)
    restore_workspace(restored, loaded.manifest, loaded.attachments)

    assert restored.mode_combo.currentData() == "fitting"
    assert restored.fit_expr_edit.toPlainText() == "a*x"
    assert restored.fit_target_edit.text() == "y"
    assert restored.custom_params_table.rows()[0]["name"] == "a"
    assert not hasattr(restored, "_workbench_formula_preview_languages")
    assert restored._csv_rows == [{"name": "a", "value": "2.0"}]
    assert restored.result_plot_bytes == loaded.attachments["attachments/plots/plot-001.png"]
    assert getattr(restored, "_workspace_snapshot_only", False) is True

    saved_path = tmp_path / "saved-from-v2.datalab"
    assert restored._save_workspace_to_path(saved_path)
    saved = read_workspace(saved_path)

    assert saved.manifest["schema"] == "datalab.workspace.v1"
    assert saved.manifest["schema_version"] == 1
    assert "formula_preview" not in saved.manifest["workspace"]["ui"]
    assert saved.manifest["workspace"]["config"]["fitting"]["expression"] == "a*x"
    assert saved.manifest["workspace"]["result_snapshot"]["present"] is True


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


def test_workspace_preserves_desktop_fitting_comparison_candidates(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    candidates = (
        "[\n"
        '  {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1}\n'
        "]"
    )
    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    _set_combo_data(source.mode_combo, "fitting")
    _set_combo_data(source.fit_model_combo, "comparison")
    source.fit_comparison_candidates_edit.setPlainText(candidates)

    bundle = capture_workspace(source, title="comparison")
    fitting = bundle.manifest["workspace"]["config"]["fitting"]

    assert fitting["model"] == "comparison"
    assert fitting["comparison_candidates"] == candidates

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.fit_model_combo.currentData() == "comparison"
    assert target.fit_comparison_candidates_edit.toPlainText() == candidates


def test_desktop_fitting_comparison_candidates_mark_workspace_dirty(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow

    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    _set_combo_data(window.mode_combo, "fitting")
    _set_combo_data(window.fit_model_combo, "comparison")
    window._workspace_dirty = False

    window.fit_comparison_candidates_edit.setPlainText(
        '[{"candidate_id":"linear","label":"Linear","model_type":"polynomial","poly_degree":1}]'
    )

    assert window._workspace_dirty is True


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
    bundle.manifest["workspace"]["constants"] = {
        "enabled": False,
        "source_kind": "manual_table",
        "decoded_text": "",
        "canonical_table": {"headers": ["Name", "Value"], "rows": []},
    }
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


def test_workspace_restore_migrates_only_active_legacy_constants(qtbot) -> None:
    from app_desktop.window import ExtrapolationWindow
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    source = ExtrapolationWindow()
    qtbot.addWidget(source)
    bundle = capture_workspace(source, title="legacy active constants")
    workspace = bundle.manifest["workspace"]
    workspace["current_mode"] = "root_solving"
    workspace["constants"] = {
        "enabled": False,
        "source_kind": "manual_table",
        "decoded_text": "",
        "canonical_table": {"headers": ["Name", "Value"], "rows": []},
    }
    config = workspace["config"]
    config["fitting"]["model"] = "custom"
    config["fitting"]["custom_constants"] = {
        "enabled": True,
        "view": "table",
        "rows": [{"name": "K", "value": "1"}],
        "text": "",
        "numeric_mode": "mpmath",
    }
    config["fitting"]["implicit"] = {
        "schema": 2,
        "constants": [{"name": "I", "value": "2"}],
        "constants_enabled": True,
        "constants_view": "table",
        "constants_text": "",
        "constants_numeric_mode": "mpmath",
    }
    config["root_solving"]["constants"] = {
        "enabled": True,
        "view": "table",
        "rows": [{"name": "R", "value": "3"}],
        "text": "",
        "numeric_mode": "uncertainty",
    }

    target = ExtrapolationWindow()
    qtbot.addWidget(target)
    restore_workspace(target, bundle.manifest, bundle.attachments)

    assert target.mode_combo.currentData() == "root_solving"
    assert target.input_constants_editor.numeric_mode() == "uncertainty"
    assert target.input_constants_editor.rows() == [{"name": "R", "value": "3"}]


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
