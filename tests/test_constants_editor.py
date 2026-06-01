from __future__ import annotations

import os
import subprocess

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

import mpmath as mp
from PySide6.QtWidgets import QApplication

from app_desktop.constants_editor import ConstantsEditor
from app_desktop.workers_core import _execute_fit_job_payload


def _make_main_window(qtbot):
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def test_constants_editor_round_trips_table_rows(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)

    editor.set_rows([{"name": "K", "value": "1.23"}, {"name": "R", "value": "3.0"}])

    assert editor.rows() == [{"name": "K", "value": "1.23"}, {"name": "R", "value": "3.0"}]
    assert editor.constants_dict(validate=True) == {"K": "1.23", "R": "3.0"}


def test_constants_editor_text_view_round_trip(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)

    editor.set_text("K = 1.23\nR 3.0")
    editor.use_text_view(True)

    assert editor.constants_dict(validate=True) == {"K": "1.23", "R": "3.0"}


def test_constants_editor_preserves_draft_rows(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)

    editor.set_rows([{"name": "K", "value": ""}, {"name": "", "value": "3"}])

    assert editor.rows() == [{"name": "K", "value": ""}, {"name": "", "value": "3"}]
    assert editor.constants_dict(validate=False) == {}


def test_constants_editor_preserves_text_view_single_token_draft_rows(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)

    editor.set_text("K\n= 3\nR 2")
    editor.use_text_view(True)

    assert editor.rows() == [
        {"name": "K", "value": ""},
        {"name": "", "value": "3"},
        {"name": "R", "value": "2"},
    ]
    assert editor.constants_dict(validate=False) == {"R": "2"}


def test_production_code_has_no_legacy_constants_alias_references():
    result = subprocess.run(
        [
            "rg",
            "constants_checkbox|constants_table|manual_constants_edit|_constants_stack|implicit_constants_table",
            "app_desktop",
            "--glob",
            "!app_desktop/constants_editor.py",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1, result.stdout


@pytest.mark.parametrize(
    ("rows", "match"),
    [
        ([{"name": "", "value": "1"}], "name"),
        ([{"name": "K", "value": ""}], "value"),
        ([{"name": "bad-name", "value": "1"}], "Invalid|无效"),
        ([{"name": "K", "value": "1"}, {"name": "K", "value": "2"}], "Duplicate|重复"),
        ([{"name": "K", "value": "not-a-number"}], "Invalid value|取值无效"),
    ],
)
def test_constants_editor_validate_rejects_invalid_rows(qtbot, rows, match):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)
    editor.set_rows(rows)

    with pytest.raises(ValueError, match=match):
        editor.constants_dict(validate=True)


@pytest.mark.parametrize("name", ["Pi", "Sin"])
def test_constants_editor_rejects_reserved_expression_names(qtbot, name):
    editor = ConstantsEditor(numeric_mode="mpmath")
    qtbot.addWidget(editor)
    editor.set_rows([{"name": name, "value": "1"}])

    with pytest.raises(ValueError, match="reserved|保留"):
        editor.constants_dict(validate=True)


def test_all_constants_surfaces_use_constants_editor(qtbot):
    win = _make_main_window(qtbot)

    assert isinstance(win.error_constants_editor, ConstantsEditor)
    assert isinstance(win.custom_constants_editor, ConstantsEditor)
    assert isinstance(win.implicit_constants_editor, ConstantsEditor)


def test_legacy_constants_surface_aliases_are_not_public_window_api(qtbot):
    win = _make_main_window(qtbot)

    for name in (
        "constants_checkbox",
        "constants_table",
        "manual_constants_edit",
        "_constants_stack",
        "implicit_constants_table",
    ):
        assert not hasattr(win, name), name


def test_disabled_custom_constants_do_not_hide_parameter_detection(qtbot):
    win = _make_main_window(qtbot)
    win.custom_constants_editor.set_rows([{"name": "K", "value": "1"}])
    win.custom_constants_editor.setChecked(False)

    constants = (
        list(win.custom_constants_editor.constants_dict(validate=False))
        if win.custom_constants_editor.isChecked()
        else []
    )
    names = win._infer_parameter_names("A*x + K", ["x"], [], constants=constants)

    assert names == ["A", "K"]


def _prepare_custom_fit_window(qtbot, *, constants_enabled: bool = True, constant_value: str = "1"):
    win = _make_main_window(qtbot)
    win.mode_combo.setCurrentIndex(win.mode_combo.findData("fitting"))
    win.fit_model_combo.setCurrentIndex(win.fit_model_combo.findData("custom"))
    win._reset_variable_rows(default_var="x", default_column="x")
    win.fit_target_edit.setText("y")
    win.fit_expr_edit.setPlainText("A*x + K")
    win.custom_constraints_checkbox.setChecked(True)
    win._reset_custom_param_rows({"A": {"initial": "1"}})
    if not constants_enabled:
        win.custom_params_table.set_rows(
            [{"name": "A", "initial": "1"}, {"name": "K", "initial": "0"}]
        )
    win.custom_constants_editor.setChecked(constants_enabled)
    win.custom_constants_editor.set_rows([{"name": "K", "value": constant_value}])
    return win


def test_enabled_custom_constants_are_excluded_and_injected_into_fit_job(qtbot):
    win = _prepare_custom_fit_window(qtbot, constants_enabled=True, constant_value="1")
    dataset = (
        ["x", "y"],
        [(mp.mpf("0"), mp.mpf("1")), (mp.mpf("1"), mp.mpf("3")), (mp.mpf("2"), mp.mpf("5"))],
        [(None, None), (None, None), (None, None)],
    )

    job = win._prepare_fit_job(dataset, generate_latex=False, output_path="", verbose=False, render_plots=False)

    assert job.parameter_names == ["A"]
    assert job.custom_constants == {"K": "1"}

    payload = _execute_fit_job_payload(job)

    assert payload.fit_result is not None
    assert set(payload.fit_result.params) == {"A"}
    assert mp.almosteq(payload.fit_result.params["A"], mp.mpf("2"), abs_eps=mp.mpf("1e-20"))


def test_custom_constants_accept_compact_uncertainty_notation_through_backend(qtbot):
    win = _prepare_custom_fit_window(qtbot, constants_enabled=True, constant_value="1.0(2)")
    dataset = (
        ["x", "y"],
        [(mp.mpf("0"), mp.mpf("1")), (mp.mpf("1"), mp.mpf("3"))],
        [(None, None), (None, None)],
    )

    job = win._prepare_fit_job(dataset, generate_latex=False, output_path="", verbose=False, render_plots=False)

    assert job.custom_constants == {"K": "1.0(2)"}

    payload = _execute_fit_job_payload(job)

    assert payload.fit_result is not None
    assert mp.almosteq(payload.fit_result.params["A"], mp.mpf("2"), abs_eps=mp.mpf("1e-20"))


def test_disabled_custom_constants_remain_fit_parameters_in_job(qtbot):
    win = _prepare_custom_fit_window(qtbot, constants_enabled=False, constant_value="1")
    dataset = (
        ["x", "y"],
        [(mp.mpf("0"), mp.mpf("1")), (mp.mpf("1"), mp.mpf("3"))],
        [(None, None), (None, None)],
    )

    job = win._prepare_fit_job(dataset, generate_latex=False, output_path="", verbose=False, render_plots=False)

    assert job.parameter_names == ["A", "K"]
    assert job.custom_constants == {}
