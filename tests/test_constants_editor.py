from __future__ import annotations

import ast
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

import mpmath as mp
from PySide6.QtWidgets import QApplication

from app_desktop.constants_editor import ConstantsEditor
from app_desktop.workers_core import _execute_fit_job_payload


def _python_sources_under_app_desktop(*, exclude: set[str] | None = None) -> list[Path]:
    root = Path(__file__).resolve().parents[1] / "app_desktop"
    exclude = exclude or set()
    return [
        path
        for path in root.rglob("*.py")
        if path.relative_to(root).as_posix() not in exclude
    ]


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


def test_constants_editor_standalone_card_style_is_default(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)

    assert editor.property("datalab_constants_embedded") in {None, False}
    assert editor.layout().contentsMargins().left() == 8
    assert "border: 1px solid" in editor.styleSheet()


def test_constants_editor_can_use_embedded_workbench_style(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)

    editor.set_embedded_in_workbench(True)

    assert editor.property("datalab_constants_embedded") is True
    assert editor.layout().contentsMargins().left() == 0
    assert "border: none" in editor.styleSheet()


def test_constants_editor_style_is_owned_by_theme() -> None:
    from app_desktop.theme import constants_editor_style

    standalone = constants_editor_style(embedded=False, dark=False)
    embedded = constants_editor_style(embedded=True, dark=False)

    assert "datalab_constants_card" in standalone
    assert "border: 1px solid" in standalone
    assert "background: transparent" in embedded
    assert "border: none" in embedded


def test_constants_editor_module_no_longer_defines_local_style_helper() -> None:
    path = Path(__file__).resolve().parents[1] / "app_desktop" / "constants_editor.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "_constants_editor_style" not in function_names


def test_constants_editor_help_button_only_shows_when_tooltip_is_present(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)
    editor.show()
    QApplication.processEvents()

    assert editor.help_button.isVisible() is False

    editor.help_button.setToolTip("Constants help")
    QApplication.processEvents()

    assert editor.help_button.isVisible() is True


def test_constants_editor_tooltip_updates_accessible_descriptions(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)

    editor.setToolTip("Constants help")

    for widget in (
        editor,
        editor.checkbox,
        editor.help_button,
        editor.table_view,
        editor.text_view,
    ):
        assert widget.accessibleDescription() == "Constants help"


def test_constants_editor_enable_checkbox_is_hidden_compatibility_only(qtbot):
    editor = ConstantsEditor()
    qtbot.addWidget(editor)

    assert editor.checkbox.isHidden()

    editor.set_rows([{"name": "K", "value": "1"}])
    editor.setChecked(False)

    assert editor.isChecked() is True
    assert editor.constants_dict(validate=True) == {"K": "1"}


def test_constants_editor_numeric_mode_setter_validates_and_emits(qtbot):
    editor = ConstantsEditor(numeric_mode="uncertainty")
    qtbot.addWidget(editor)
    emissions = []
    editor.changed.connect(lambda: emissions.append(True))

    editor.set_numeric_mode("mpmath")

    assert editor.numeric_mode() == "mpmath"
    assert emissions
    with pytest.raises(ValueError, match="Unsupported constants numeric mode"):
        editor.set_numeric_mode("float")


def test_shared_constants_editor_control_labels_follow_window_language(qtbot):
    win = _make_main_window(qtbot)
    win.mode_combo.setCurrentIndex(win.mode_combo.findData("root_solving"))

    win._apply_language("en")

    assert win.input_constants_editor.add_button.text() == "+ Row"
    assert win.input_constants_editor.remove_button.text() == "- Row"
    assert win.input_constants_editor.clear_button.text() == "Clear"
    assert win.input_constants_editor.view_toggle_button.text() == "Text View"

    win.input_constants_editor.use_text_view(True)
    assert win.input_constants_editor.view_toggle_button.text() == "Table View"

    win._apply_language("zh")

    assert win.input_constants_editor.add_button.text() == "+ 行"
    assert win.input_constants_editor.remove_button.text() == "- 行"
    assert win.input_constants_editor.clear_button.text() == "清除"
    assert win.input_constants_editor.view_toggle_button.text() == "表格视图"


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
    pattern = re.compile(r"constants_checkbox|constants_table|manual_constants_edit|_constants_stack|implicit_constants_table")
    matches = [
        f"{path}:{line_no}:{line}"
        for path in _python_sources_under_app_desktop(exclude={"constants_editor.py"})
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]

    assert matches == []


def test_production_code_uses_public_constants_numeric_mode_setter():
    pattern = re.compile(r"\._numeric_mode\s*=")
    matches = [
        f"{path}:{line_no}:{line}"
        for path in _python_sources_under_app_desktop(exclude={"constants_editor.py"})
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]

    assert matches == []


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


def test_content_driven_custom_constants_hide_parameter_detection_even_after_legacy_disable(qtbot):
    win = _make_main_window(qtbot)
    win.custom_constants_editor.set_rows([{"name": "K", "value": "1"}])
    win.custom_constants_editor.setChecked(False)

    constants = list(win.custom_constants_editor.constants_dict(validate=False))
    names = win._infer_parameter_names("A*x + K", ["x"], [], constants=constants)

    assert names == ["A"]


def test_draft_constant_name_remains_detected_parameter(qtbot):
    win = _make_main_window(qtbot)
    win.custom_constants_editor.set_rows([{"name": "K", "value": ""}])

    names = win._infer_parameter_names(
        "A*x + K",
        ["x"],
        [],
        constants=list(win._raw_constant_names_from_editor(win.custom_constants_editor)),
    )

    assert names == ["A", "K"]


def test_enabled_custom_constants_are_excluded_when_collecting_parameter_config(qtbot):
    win = _make_main_window(qtbot)
    win.mode_combo.setCurrentIndex(win.mode_combo.findData("fitting"))
    win.fit_model_combo.setCurrentIndex(win.fit_model_combo.findData("custom"))
    win._reset_variable_rows(default_var="x", default_column="x")
    win.fit_expr_edit.setPlainText("A*x + K")
    win.custom_constraints_checkbox.setChecked(True)
    win._reset_custom_param_rows({"A": {"initial": "1"}})
    win.custom_constants_editor.setChecked(True)
    win.custom_constants_editor.set_rows([{"name": "K", "value": "1"}])

    assert win._collect_custom_parameter_config() == {"A": {"initial": "1"}}


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


def test_prepare_fit_job_uses_normalized_weighted_custom_inputs(qtbot):
    from datalab_core.jobs import JobMode

    win = _prepare_custom_fit_window(qtbot, constants_enabled=True, constant_value="1")
    win.fit_weighted_checkbox.setChecked(True)
    dataset = (
        ["x", "y", "y_sigma"],
        [
            (mp.mpf("0"), mp.mpf("1"), mp.mpf("0.5")),
            (mp.mpf("1"), mp.mpf("3"), mp.mpf("0.25")),
            (mp.mpf("2"), mp.mpf("5"), mp.mpf("0.125")),
        ],
        [(None, None, None), (None, None, None), (None, None, None)],
    )

    job = win._prepare_fit_job(dataset, generate_latex=False, output_path="", verbose=False, render_plots=False)

    assert job.variable_map == {"x": "x"}
    assert job.variable_data == {"x": [mp.mpf("0"), mp.mpf("1"), mp.mpf("2")]}
    assert job.target_series == [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")]
    assert job.sigma_series == [mp.mpf("0.5"), mp.mpf("0.25"), mp.mpf("0.125")]
    assert job.weights == [mp.mpf("4"), mp.mpf("16"), mp.mpf("64")]
    assert job.custom_constants == {"K": "1"}
    assert job.parameter_config == {"A": {"initial": "1"}}
    assert job.core_request is not None
    assert job.core_request.mode is JobMode.FITTING
    assert job.core_request.inputs["model_type"] == "custom"
    assert job.core_request.inputs["variable_map"] == {"x": "x"}
    assert job.core_request.inputs["target_column"] == "y"
    assert job.core_request.inputs["target_series"] == ["1.0", "3.0", "5.0"]
    assert job.core_request.inputs["sigma_series"] == ["0.5", "0.25", "0.125"]
    assert job.core_request.inputs["weights"] == ["4.0", "16.0", "64.0"]
    assert job.core_request.inputs["custom_constants"] == {"K": "1"}
    assert job.core_request.inputs["parameter_config"] == {"A": {"initial": "1"}}


def test_custom_constants_accept_uncertainty_notation_nominal_values(qtbot):
    win = _prepare_custom_fit_window(qtbot, constants_enabled=True, constant_value="1.0(2)")
    dataset = (
        ["x", "y"],
        [(mp.mpf("0"), mp.mpf("1")), (mp.mpf("1"), mp.mpf("3")), (mp.mpf("2"), mp.mpf("5"))],
        [(None, None), (None, None), (None, None)],
    )

    job = win._prepare_fit_job(dataset, generate_latex=False, output_path="", verbose=False, render_plots=False)
    payload = _execute_fit_job_payload(job)

    assert payload.fit_result is not None
    assert job.custom_constants == {"K": "1.0(2)"}
    assert mp.almosteq(payload.fit_result.params["A"], mp.mpf("2"), abs_eps=mp.mpf("1e-20"))


def test_content_driven_custom_constants_remain_active_in_fit_job_after_legacy_disable(qtbot):
    win = _prepare_custom_fit_window(qtbot, constants_enabled=False, constant_value="1")
    dataset = (
        ["x", "y"],
        [(mp.mpf("0"), mp.mpf("1")), (mp.mpf("1"), mp.mpf("3"))],
        [(None, None), (None, None)],
    )

    job = win._prepare_fit_job(dataset, generate_latex=False, output_path="", verbose=False, render_plots=False)

    assert job.parameter_names == ["A"]
    assert job.custom_constants == {"K": "1"}


def test_bracket_constant_survives_switch_from_root_to_custom_fit(qtbot):
    win = _make_main_window(qtbot)
    win.mode_combo.setCurrentIndex(win.mode_combo.findData("root_solving"))
    win.root_constants_editor.set_rows([{"name": "K", "value": "1.23(4)"}])
    assert win.input_constants_editor.numeric_mode() == "uncertainty"
    assert win.root_constants_editor.constants_dict(validate=True) == {"K": "1.23(4)"}

    win.mode_combo.setCurrentIndex(win.mode_combo.findData("fitting"))
    win.fit_model_combo.setCurrentIndex(win.fit_model_combo.findData("custom"))
    QApplication.processEvents()

    assert win.input_constants_editor.numeric_mode() == "mpmath"
    assert win.custom_constants_editor.rows() == [{"name": "K", "value": "1.23(4)"}]
    assert win.custom_constants_editor.constants_dict(validate=True) == {"K": "1.23(4)"}


def test_constants_editor_numeric_mode_tracks_the_active_mode(qtbot):
    # The workbench redesign removed the error-mode "use constants file" checkbox
    # (use_constants_file_checkbox); this test now covers the surviving contract:
    # switching modes keeps the shared input_constants_editor visible and updates
    # its numeric mode (uncertainty for root_solving, mpmath for custom fitting).
    win = _make_main_window(qtbot)
    win.mode_combo.setCurrentIndex(win.mode_combo.findData("error"))
    QApplication.processEvents()
    assert win.input_constants_editor.inputs_visible()

    win.mode_combo.setCurrentIndex(win.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    assert win.input_constants_editor.inputs_visible()
    assert win.input_constants_editor.numeric_mode() == "uncertainty"

    win.mode_combo.setCurrentIndex(win.mode_combo.findData("fitting"))
    win.fit_model_combo.setCurrentIndex(win.fit_model_combo.findData("custom"))
    QApplication.processEvents()

    assert win.input_constants_editor.inputs_visible()
    assert win.input_constants_editor.numeric_mode() == "mpmath"


def test_shared_constants_tooltip_tracks_current_mode(qtbot):
    win = _make_main_window(qtbot)
    win._apply_language("en")

    win.mode_combo.setCurrentIndex(win.mode_combo.findData("root_solving"))
    QApplication.processEvents()
    assert "equations" in win.input_constants_editor.toolTip()

    win.mode_combo.setCurrentIndex(win.mode_combo.findData("fitting"))
    win.fit_model_combo.setCurrentIndex(win.fit_model_combo.findData("custom"))
    win._apply_language("en")
    QApplication.processEvents()
    assert "custom fit expression" in win.input_constants_editor.toolTip()

    win.fit_model_combo.setCurrentIndex(win.fit_model_combo.findData("self_consistent"))
    QApplication.processEvents()
    assert "implicit model" in win.input_constants_editor.toolTip()


def test_shared_constants_editor_marks_workspace_dirty_once_per_edit(qtbot):
    win = _make_main_window(qtbot)
    calls = []
    win._workspace_dirty = False
    win._workspace_snapshot_only = False
    win._workspace_snapshot_stale = False
    win._update_workspace_window_title = lambda *_args: calls.append(True)

    win.input_constants_editor.changed.emit()

    assert len(calls) == 1
