from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _window(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def _legacy_manifest(
    *,
    current_mode: str = "fitting",
    config: dict[str, object] | None = None,
    result_snapshot: dict[str, object] | None = None,
    ui: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "current_mode": current_mode,
        "ui": ui or {},
        "data": {"input": {"canonical_table": {"headers": ["A", "B"], "rows": [["1", "2"]]}}},
        "constants": {},
        "config": config or {},
        "result_snapshot": result_snapshot or {"present": False},
    }


def _set_combo_data(combo, value: str) -> None:
    index = combo.findData(value)
    assert index >= 0
    combo.setCurrentIndex(index)


def test_legacy_auto_fit_workspace_degrades_once_and_saves_current_schema(qtbot) -> None:
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    win = _window(qtbot)
    manifest = _legacy_manifest(
        config={
            "fitting": {
                "model": "auto",
                "auto_fit": {"enabled": True, "candidate_models": ["poly2"]},
            }
        }
    )

    restore_workspace(win, manifest, {})

    assert win.fit_model_combo.currentData() != "auto"
    assert getattr(win, "_workspace_degraded", False) is True
    assert "automatic" in " ".join(getattr(win, "_workspace_migration_warnings", [])).lower()

    saved = capture_workspace(win, title="migrated auto fit").manifest["workspace"]
    fitting = saved["config"]["fitting"]
    assert fitting["model"] != "auto"
    assert "auto_fit" not in fitting


@pytest.mark.parametrize(
    ("implicit_config", "expected_constants", "expected_rows"),
    [
        (
            {
                "implicit_variable": "delta",
                "equation": "d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
                "output_expression": "En - R*c/(n-delta)^2",
                "parameters": [
                    {"name": "d0", "initial": "0"},
                    {"name": "d2", "initial": "0"},
                    {"name": "d4", "initial": "0"},
                    {"name": "En", "initial": "0"},
                ],
            },
            [{"name": "R", "value": "10973731.568160"}, {"name": "c", "value": "299792458"}],
            [
                {"name": "d0", "initial": "0", "fixed": "", "min": "", "max": ""},
                {"name": "d2", "initial": "0", "fixed": "", "min": "", "max": ""},
                {"name": "d4", "initial": "0", "fixed": "", "min": "", "max": ""},
                {"name": "En", "initial": "0", "fixed": "", "min": "", "max": ""},
            ],
        ),
        (
            {
                "schema": 2,
                "implicit_variable": "u",
                "equation": "a + b*x",
                "output_expression": "u",
                "parameters": [
                    {"name": "a", "initial": "1", "fixed": "", "min": "", "max": ""},
                    {"name": "b", "initial": "2", "fixed": "", "min": "0", "max": "3"},
                ],
                "constants": [{"name": "K", "value": "1.0(2)"}],
                "constants_enabled": True,
            },
            [{"name": "K", "value": "1.0(2)"}],
            [
                {"name": "a", "initial": "1", "fixed": "", "min": "", "max": ""},
                {"name": "b", "initial": "2", "fixed": "", "min": "0", "max": "3"},
            ],
        ),
    ],
)
def test_old_implicit_workspace_schema_migrates_or_preserves_rows(
    qtbot,
    implicit_config,
    expected_constants,
    expected_rows,
) -> None:
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    win = _window(qtbot)
    manifest = _legacy_manifest(
        config={
            "fitting": {
                "model": "self_consistent",
                "implicit": implicit_config,
            }
        }
    )

    restore_workspace(win, manifest, {})

    assert win.fit_model_combo.currentData() == "self_consistent"
    assert win.implicit_constants_editor.rows() == expected_constants
    assert win.implicit_params_table.rows() == expected_rows

    saved = capture_workspace(win, title="implicit legacy").manifest["workspace"]
    saved_implicit = saved["config"]["fitting"]["implicit"]
    assert saved_implicit["schema"] == 2
    assert saved_implicit["parameters"] == expected_rows
    assert saved_implicit["constants"] == expected_constants


def test_legacy_root_solving_auto_mode_restores_as_scalar_and_saves_scalar(qtbot) -> None:
    from app_desktop.workspace_controller import capture_workspace, restore_workspace

    win = _window(qtbot)
    manifest = _legacy_manifest(
        current_mode="root_solving",
        config={
            "root_solving": {
                "equations": "x^2 - A",
                "mode": "auto",
                "unknowns": [{"name": "x", "initial": "1", "lower": "0", "upper": "2"}],
            }
        },
    )

    restore_workspace(win, manifest, {})

    assert win.mode_combo.currentData() == "root_solving"
    assert win.root_mode_combo.currentData() == "scalar"
    assert win.root_unknowns_table.rows() == [{"name": "x", "initial": "1", "lower": "0", "upper": "2"}]

    saved = capture_workspace(win, title="root auto legacy").manifest["workspace"]
    assert saved["config"]["root_solving"]["mode"] == "scalar"


@pytest.mark.parametrize("overview_state", ["complete", "failed"])
def test_legacy_snapshot_only_result_preserves_durable_overview_state(qtbot, overview_state: str) -> None:
    from app_desktop.workspace_controller import restore_workspace

    win = _window(qtbot)
    manifest = _legacy_manifest(
        result_snapshot={
            "present": True,
            "overview_state": overview_state,
            "markdown": "legacy snapshot result",
            "markdown_format": "plain",
            "log": "legacy log",
            "csv": {"headers": ["name", "value"], "rows": [{"name": "a", "value": "1.0(2)"}]},
            "latex_source": "\\begin{tabular}{cc}a&1\\end{tabular}",
            "plots": [],
        }
    )

    restore_workspace(win, manifest, {})

    assert win._workspace_snapshot_only is True
    assert win._workbench_result_state == overview_state
    assert win.result_edit.toPlainText() == "legacy snapshot result"
    assert win.log_edit.toPlainText() == "legacy log"
    assert win._csv_rows == [{"name": "a", "value": "1.0(2)"}]
    assert "\\begin{tabular}" in win.latex_edit.toPlainText()
