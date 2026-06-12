from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFrame, QWidget


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


def test_variable_panel_wraps_mounts_in_section_cards(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    QApplication.processEvents()

    page = window.workbench_variable_stack.currentWidget()
    sections = [
        page.layout().itemAt(index).widget()
        for index in range(page.layout().count())
        if isinstance(page.layout().itemAt(index).widget(), QFrame)
        and page.layout().itemAt(index).widget().isVisibleTo(page)
    ]

    assert [section.property("datalab_variable_section_role") for section in sections[:2]] == [
        "parameters",
        "constants",
    ]
    assert window.custom_param_header_widget.parentWidget() in sections[0].findChildren(QWidget)
    assert window.custom_params_table.parentWidget() in sections[0].findChildren(QWidget)
    assert window.custom_constants_editor.parentWidget() in sections[1].findChildren(QWidget)


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


def test_variable_panel_constants_editor_is_visible_card(qtbot: Any) -> None:
    window = _window(qtbot)
    editor = window.custom_constants_editor

    assert editor.property("datalab_constants_card") is True
    assert editor.property("datalab_constants_embedded") is True
    assert editor.testAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    assert editor.minimumHeight() >= 52
    assert editor.layout().contentsMargins().left() == 0
    assert "border: none" in editor.styleSheet()
    assert "QPushButton" in editor.styleSheet()


def test_variable_panel_summary_tracks_visible_parameter_and_constant_rows(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.custom_params_table.set_rows([{"name": "A", "initial": "1"}])
    window.custom_constants_editor.setChecked(True)
    window.custom_constants_editor.set_rows([{"name": "K", "value": "2"}])
    QApplication.processEvents()

    window._apply_language("en")
    assert window.workbench_variable_summary.text() == "1 parameter / 1 constant"

    window._apply_language("zh")
    assert window.workbench_variable_summary.text() == "1 个参数 / 1 个常数"


def test_variable_panel_summary_ignores_hidden_fitting_submode_rows(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.custom_params_table.set_rows([{"name": "A", "initial": "1"}])
    window.custom_constants_editor.setChecked(True)
    window.custom_constants_editor.set_rows([{"name": "K", "value": "2"}])
    window.implicit_params_table.set_rows([{"name": "d0", "initial": "0"}])
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("self_consistent"))
    QApplication.processEvents()

    window._apply_language("en")

    assert window.workbench_variable_summary.text() == "1 parameter"
    assert "constant" not in window.workbench_variable_summary.text()


def test_variable_panel_title_tracks_visible_root_sections(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    window._apply_language("en")

    assert window.workbench_variable_title.text() == "Unknowns and constants"


def test_variable_panel_summary_updates_when_rows_change(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window._apply_language("en")
    assert window.workbench_variable_summary.text() == "No entries"

    window.custom_params_table.set_rows([{"name": "A", "initial": "1"}])
    QApplication.processEvents()

    assert window.workbench_variable_summary.text() == "1 parameter"


def test_variable_panel_can_collapse_without_losing_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    window.custom_params_table.set_rows([{"name": "A", "initial": "1"}])
    QApplication.processEvents()

    button = window.workbench_variable_toggle_button
    assert window.workbench_variable_stack.isVisible()

    button.click()
    QApplication.processEvents()

    assert not window.workbench_variable_stack.isVisible()
    assert window.workbench_variable_summary.isVisible()
    rows = window.custom_params_table.rows()
    assert rows[0]["name"] == "A"
    assert rows[0]["initial"] == "1"

    button.click()
    QApplication.processEvents()

    assert window.workbench_variable_stack.isVisible()
    rows = window.custom_params_table.rows()
    assert rows[0]["name"] == "A"
    assert rows[0]["initial"] == "1"


def test_variable_panel_population_is_idempotent(qtbot: Any) -> None:
    from app_desktop.workbench_variable_panel import populate_variable_workspace_panel

    window = _window(qtbot)
    initial_stack_count = window.workbench_variable_stack.count()
    initial_callbacks = tuple(window._workbench_variable_changed_callbacks)

    populate_variable_workspace_panel(window)
    populate_variable_workspace_panel(window)

    assert window.workbench_variable_stack.count() == initial_stack_count
    assert tuple(window._workbench_variable_changed_callbacks) == initial_callbacks


def test_variable_panel_embeds_parameter_tables_with_shared_table_style(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    QApplication.processEvents()

    table = window.custom_params_table

    assert table.property("datalab_parameter_table_embedded") is True
    assert table.table_view.property("datalab_workbench_embedded_table") is True
    assert "QTableWidget" in table.table_view.styleSheet()
    assert "font-family" in table.table_view.styleSheet()
    assert window.custom_param_refresh_btn.property("datalab_variable_toolbar_button") is True
    assert window.custom_param_add_btn.property("datalab_variable_toolbar_button") is True
    assert window.custom_param_remove_btn.property("datalab_variable_toolbar_button") is True
    assert 'QPushButton[datalab_variable_toolbar_button="true"]' in window.workbench_variable_panel.styleSheet()


def test_variable_panel_embeds_unknown_table_with_shared_table_style(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()

    table = window.root_unknowns_table

    assert table.property("datalab_detected_rows_table_embedded") is True
    assert table.table_view.property("datalab_workbench_embedded_table") is True
    assert "QTableWidget" in table.table_view.styleSheet()
    assert window.root_detect_unknowns_button.property("datalab_variable_toolbar_button") is True
    assert window.root_add_unknown_button.property("datalab_variable_toolbar_button") is True
    assert window.root_remove_unknown_button.property("datalab_variable_toolbar_button") is True


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
    sections = [
        page.layout().itemAt(index).widget()
        for index in range(page.layout().count())
        if isinstance(page.layout().itemAt(index).widget(), QFrame)
        and page.layout().itemAt(index).widget().isVisibleTo(page)
    ]

    assert [section.property("datalab_variable_section_role") for section in sections[:2]] == [
        "unknowns",
        "constants",
    ]


def test_root_variable_panel_summary_counts_unknowns_and_constants(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    window.root_unknowns_table.set_rows(
        [
            {"name": "x", "initial": "1", "lower": "", "upper": ""},
            {"name": "y", "initial": "2", "lower": "", "upper": ""},
        ]
    )
    window.root_constants_editor.setChecked(True)
    window.root_constants_editor.set_rows([{"name": "A", "value": "4.0(2)"}])
    QApplication.processEvents()

    window._apply_language("en")
    assert window.workbench_variable_summary.text() == "2 unknowns / 1 constant"

    window._apply_language("zh")
    assert window.workbench_variable_summary.text() == "2 个未知量 / 1 个常数"


def test_fitting_variable_panel_orders_constraints_after_parameter_table(qtbot: Any) -> None:
    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window.fit_model_combo.setCurrentIndex(window.fit_model_combo.findData("custom"))
    QApplication.processEvents()

    section = window.custom_params_table.parentWidget().parentWidget()
    widgets = section.findChildren(QWidget)

    assert widgets.index(window.custom_param_header_widget) < widgets.index(window.custom_params_table)
    assert widgets.index(window.custom_params_table) < widgets.index(window.custom_constraints_checkbox)

    page = window.workbench_variable_stack.currentWidget()
    sections = [
        page.layout().itemAt(index).widget()
        for index in range(page.layout().count())
        if isinstance(page.layout().itemAt(index).widget(), QFrame)
        and page.layout().itemAt(index).widget().isVisibleTo(page)
    ]
    assert [section.property("datalab_variable_section_role") for section in sections[:2]] == [
        "parameters",
        "constants",
    ]
