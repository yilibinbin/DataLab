from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1440, 900)
    window.show()
    QApplication.processEvents()
    return window


def test_variable_panel_mounts_existing_parameter_and_constant_widgets(qtbot: Any) -> None:
    window = _window(qtbot)
    panel = window.findChild(QWidget, "workbench_variable_panel")

    assert panel is not None
    assert window.custom_params_table in panel.findChildren(type(window.custom_params_table))
    assert window.custom_constants_editor in panel.findChildren(type(window.custom_constants_editor))
    assert window.custom_params_table.property("datalab_state_role") == "custom_parameters_owner"
    assert window.custom_constants_editor.property("datalab_state_role") == "custom_constants_owner"


def test_variable_panel_preserves_parameter_table_behavior(qtbot: Any) -> None:
    window = _window(qtbot)
    window.custom_params_table.set_rows([{"name": "A", "initial": "1"}])
    window.custom_params_table.add_parameter_row({"name": "B", "initial": "2"})

    rows = window.custom_params_table.rows()

    assert [row["name"] for row in rows if row["name"]] == ["A", "B"]


def test_variable_panel_preserves_constants_text_view(qtbot: Any) -> None:
    window = _window(qtbot)
    window.custom_constants_editor.setChecked(True)
    window.custom_constants_editor.use_text_view(True)
    window.custom_constants_editor.set_text("CR 3.2898419602500(36)[+9]")

    assert window.custom_constants_editor.constants_dict(validate=True)["CR"].startswith("3.289")


def test_variable_panel_tracks_fitting_submode_visibility(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))

    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    QApplication.processEvents()
    assert window.custom_params_table.isVisible()
    assert window.custom_constants_editor.isVisible()
    assert not window.implicit_params_table.isVisible()
    assert not window.implicit_constants_editor.isVisible()

    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    QApplication.processEvents()
    assert not window.custom_params_table.isVisible()
    assert not window.custom_constants_editor.isVisible()
    assert window.implicit_params_table.isVisible()
    assert window.implicit_constants_editor.isVisible()

    built_in_index = next(
        (
            index
            for index in range(window.fit_model_combo.count())
            if window.fit_model_combo.itemData(index) not in {"custom", "self_consistent"}
        ),
        None,
    )
    assert built_in_index is not None
    window.fit_model_combo.setCurrentIndex(built_in_index)
    QApplication.processEvents()

    assert not window.custom_params_table.isVisible()
    assert not window.custom_constants_editor.isVisible()
    assert not window.implicit_params_table.isVisible()
    assert not window.implicit_constants_editor.isVisible()
    assert not window.workbench_variable_panel.isVisible()


def test_root_variable_panel_orders_unknowns_before_constants(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    page = window.workbench_variable_stack.currentWidget()
    widgets = [
        page.layout().itemAt(index).widget()
        for index in range(page.layout().count())
        if page.layout().itemAt(index).widget() is not None
    ]

    assert widgets.index(window.root_unknowns_table) < widgets.index(window.root_constants_editor)


def test_fitting_variable_panel_orders_constraints_after_parameter_table(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    QApplication.processEvents()

    page = window.workbench_variable_stack.currentWidget()
    widgets = [
        page.layout().itemAt(index).widget()
        for index in range(page.layout().count())
        if page.layout().itemAt(index).widget() is not None
    ]

    assert widgets.index(window.custom_param_header_widget) < widgets.index(window.custom_params_table)
    assert widgets.index(window.custom_params_table) < widgets.index(window.custom_constraints_checkbox)
