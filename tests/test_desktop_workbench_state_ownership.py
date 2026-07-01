from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QPlainTextEdit, QStackedWidget, QTableWidget, QWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def _widgets_by_role(window: QWidget) -> dict[str, list[QWidget]]:
    roles: dict[str, list[QWidget]] = defaultdict(list)
    for widget in window.findChildren(QWidget):
        role = widget.property("datalab_state_role")
        if isinstance(role, str) and role:
            roles[role].append(widget)
    return roles


def test_workbench_has_one_owner_for_primary_editable_state(qtbot: Any) -> None:
    window = _window(qtbot)
    roles = _widgets_by_role(window)

    expected_singletons = {
        "manual_data_owner": window.manual_box,
        "mode_stack_owner": window.mode_stack,
        "result_tabs_owner": window.tabs,
        "custom_parameters_owner": window.custom_params_table,
        "implicit_parameters_owner": window.implicit_params_table,
        "root_unknowns_owner": window.root_unknowns_table,
        "input_constants_owner": window.input_constants_editor,
    }
    for role, expected in expected_singletons.items():
        assert roles[role] == [expected], (role, [widget.objectName() for widget in roles[role]])


def test_no_mirrored_editable_data_or_result_widgets(qtbot: Any) -> None:
    window = _window(qtbot)

    mirrored_names = {
        "workbench_data_preview_table",
        "workbench_editor_stack",
        "workbench_result_model_table",
    }
    assert {widget.objectName() for widget in window.findChildren(QWidget)}.isdisjoint(mirrored_names)

    manual_tables = [
        widget
        for widget in window.findChildren(QTableWidget)
        if widget.property("datalab_state_role") == "manual_data_owner"
    ]
    assert manual_tables == []
    assert window.manual_box.property("datalab_state_role") == "manual_data_owner"
    assert window.manual_table.property("datalab_state_role") == "manual_table_editor"
    assert window.manual_data_edit.property("datalab_state_role") == "manual_text_editor"
    assert isinstance(window.manual_data_edit, QPlainTextEdit)
    assert isinstance(window.mode_stack, QStackedWidget)


def test_manual_data_has_only_existing_child_editors(qtbot: Any) -> None:
    window = _window(qtbot)

    manual_tables = [
        widget
        for widget in window.findChildren(QTableWidget)
        if widget.property("datalab_state_role") == "manual_table_editor"
    ]
    manual_text_edits = [
        widget
        for widget in window.findChildren(QPlainTextEdit)
        if widget.property("datalab_state_role") == "manual_text_editor"
    ]

    assert manual_tables == [window.manual_table]
    assert manual_text_edits == [window.manual_data_edit]
    assert window.manual_table.parentWidget() is window._data_stack
    assert window.manual_data_edit.parentWidget() is window._data_stack


def test_no_extra_manual_data_table_inside_data_owner(qtbot: Any) -> None:
    window = _window(qtbot)

    manual_tables = [
        widget
        for widget in window.manual_box.findChildren(QTableWidget)
        if widget is not window.manual_table
    ]

    assert manual_tables == []


def test_no_unowned_parameter_or_constant_state_widgets(qtbot: Any) -> None:
    from app_desktop.constants_editor import ConstantsEditor
    from app_desktop.detected_rows_table import DetectedRowsTable
    from app_desktop.parameter_table import ParameterTable

    window = _window(qtbot)
    expected_by_attr = {
        "custom_params_table": "custom_parameters_owner",
        "implicit_params_table": "implicit_parameters_owner",
        "root_unknowns_table": "root_unknowns_owner",
        "input_constants_editor": "input_constants_owner",
    }
    owner_types = (ParameterTable, ConstantsEditor, DetectedRowsTable)
    expected_widgets = {getattr(window, attr) for attr in expected_by_attr}
    owner_widgets = []
    for owner_type in owner_types:
        owner_widgets.extend(window.findChildren(owner_type))
    for widget in owner_widgets:
        # Units editors reuse the ConstantsEditor widget to map symbols → units;
        # they are not constant/parameter *state* owners (they carry a
        # ``*.units.*`` schema key and never a ``datalab_state_role``), so they
        # are outside this ownership guard.
        schema_key = str(widget.property("datalab_schema_key") or "")
        if ".units." in schema_key:
            continue
        assert widget in expected_widgets, (
            "unexpected editable state owner",
            widget.__class__.__name__,
            widget.objectName(),
        )
    for attr, role in expected_by_attr.items():
        assert getattr(window, attr).property("datalab_state_role") == role


def test_workbench_state_and_formula_widgets_have_model_paths(qtbot: Any) -> None:
    from app_desktop.workbench_model_bindings import (
        MODEL_PATH_PROPERTY,
        STATE_ROLE_MODEL_PATHS,
        model_path_for_formula_schema_key,
        model_path_for_state_role,
    )
    from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS

    window = _window(qtbot)

    for role, expected_path in STATE_ROLE_MODEL_PATHS.items():
        widgets = [
            widget
            for widget in window.findChildren(QWidget)
            if widget.property("datalab_state_role") == role
        ]
        assert widgets, role
        for widget in widgets:
            schema_key = str(widget.property("datalab_schema_key") or "")
            assert widget.property(MODEL_PATH_PROPERTY) == model_path_for_state_role(
                role,
                schema_key=schema_key or None,
            )
            if not schema_key:
                assert widget.property(MODEL_PATH_PROPERTY) == expected_path

    for spec in MODE_WORKBENCH_SPECS.values():
        for formula in spec.formulas:
            editor = getattr(window, formula.editor_attr)
            assert editor.property(MODEL_PATH_PROPERTY) == model_path_for_formula_schema_key(
                formula.schema_key
            )
