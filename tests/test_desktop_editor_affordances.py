from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QLabel, QTableWidgetItem

from app_desktop.constants_editor import ConstantsEditor
from app_desktop.detected_rows_table import DetectedRowsTable, SOURCE_DETECTED
from app_desktop.parameter_table import ParameterTable


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    win.show()
    QApplication.processEvents()
    return win


def _headers(table: Any) -> list[str]:
    return [
        table.horizontalHeaderItem(index).text()
        for index in range(table.columnCount())
    ]


def _schema_label(window: Any, key: str) -> QLabel:
    matches = [
        label
        for label in window.findChildren(QLabel)
        if label.property("datalab_schema_key") == key
    ]
    assert len(matches) == 1, [label.text() for label in matches]
    return matches[0]


def test_parameter_table_rows_api_remains_intact(qtbot: Any) -> None:
    table = ParameterTable()
    qtbot.addWidget(table)

    table.add_parameter_row({"name": "a", "initial": "1"})

    assert table.rows()[0]["name"] == "a"

    table.set_detected_names(["b"], keep_orphans=False)

    assert [row["name"] for row in table.rows() if row["name"]] == ["b", "a"]


def test_parameter_table_set_headers_preserves_rows_and_constraints(qtbot: Any) -> None:
    table = ParameterTable()
    qtbot.addWidget(table)
    table.set_constraints_enabled(True)
    table.add_parameter_row({"name": "a", "initial": "1", "fixed": "2", "min": "0", "max": "3"})

    table.set_headers(("参数", "初值", "固定", "最小", "最大"))

    assert _headers(table.table_view) == ["参数", "初值", "固定", "最小", "最大"]
    assert table.rows() == [
        {"name": "a", "initial": "1", "fixed": "2", "min": "0", "max": "3"}
    ]
    assert table.constraints_enabled() is True
    assert table.parameter_config(validate=True) == {
        "a": {"initial": "1", "fixed": "2", "min": "0", "max": "3"}
    }


def test_constants_editor_table_text_draft_preservation_still_works(qtbot: Any) -> None:
    editor = ConstantsEditor()
    qtbot.addWidget(editor)
    editor.set_rows([{"name": "PI", "value": "3"}])

    editor.use_text_view(True)
    editor.text_view.setPlainText("ALPHA = 7.2973525693(11)[-3]\nBETA 2.5")
    editor.use_text_view(False)
    editor.use_text_view(True)

    assert editor.raw_text() == "ALPHA = 7.2973525693(11)[-3]\nBETA 2.5"
    assert editor.rows() == [
        {"name": "ALPHA", "value": "7.2973525693(11)[-3]"},
        {"name": "BETA", "value": "2.5"},
    ]


def test_detected_rows_table_preserves_manual_and_detected_sources(qtbot: Any) -> None:
    table = DetectedRowsTable(
        columns=("name", "initial", "lower", "upper"),
        headers=("Name", "Initial", "Lower", "Upper"),
    )
    qtbot.addWidget(table)

    table.set_detected_names(["x"], keep_orphans=False)
    assert table.rows() == [{"name": "x", "initial": "", "lower": "", "upper": "", "source": SOURCE_DETECTED}]

    table.table_view.setItem(0, 1, QTableWidgetItem("1"))
    QApplication.processEvents()
    table.set_detected_names(["y"], keep_orphans=False)

    assert table.rows() == [
        {"name": "y", "initial": "", "lower": "", "upper": "", "source": SOURCE_DETECTED},
        {"name": "x", "initial": "1", "lower": "", "upper": ""},
    ]


def test_formula_fields_keep_real_defaults_separate_from_placeholders(window: Any) -> None:
    assert window.custom_formula_edit.toPlainText() == "(C - B)^2/(B - A) + C"
    assert "(C - B)^2/(B - A) + C" in window.custom_formula_edit.placeholderText()

    assert window.formula_edit.toPlainText() == ""
    assert window.formula_edit.placeholderText()

    assert window.fit_expr_edit.toPlainText() == ""
    assert "A*x**(-p) + C" in window.fit_expr_edit.placeholderText()

    assert window.implicit_equation_edit.toPlainText() == ""
    assert "a + b*Cos[u] + c*x" in window.implicit_equation_edit.placeholderText()
    assert window.implicit_output_edit.toPlainText() == ""
    assert "u" in window.implicit_output_edit.placeholderText()

    assert window.root_equations_edit.toPlainText() == ""
    assert "x^2 - A" in window.root_equations_edit.placeholderText()


def test_preview_function_and_help_buttons_keep_affordances(window: Any) -> None:
    buttons = [
        window.custom_formula_preview_button,
        window.custom_formula_function_button,
        window.error_formula_preview_button,
        window.func_help_btn,
        window.fit_formula_preview_button,
        window.fit_func_help_btn,
        window.implicit_equation_preview_button,
        window.implicit_output_preview_button,
        window.root_equations_help_button,
        window.root_formula_preview_button,
    ]

    for button in buttons:
        assert not button.isHidden()
        assert button.toolTip()
        assert button.accessibleName() or button.text()

    assert window.custom_formula_preview_button.property("datalab_schema_key") == "extrapolation.custom.formula"
    assert window.custom_formula_function_button.property("datalab_schema_key") == "extrapolation.custom.functions"
    assert window.root_equations_help_button.property("datalab_schema_key") == "root.equations"
    assert window.root_formula_preview_button.accessibleDescription()


def test_editor_table_headers_follow_language_registration(window: Any) -> None:
    window._apply_language("zh")

    assert _headers(window.custom_params_table.table_view) == ["名称", "初值", "固定", "下界", "上界"]
    assert _headers(window.implicit_params_table.table_view) == ["名称", "初值", "固定", "下界", "上界"]
    assert _headers(window.root_unknowns_table.table_view) == ["名称", "初始值", "下界", "上界"]
    assert _headers(window.error_constants_editor.table_view) == ["名称", "值"]

    window._apply_language("en")

    assert _headers(window.custom_params_table.table_view) == ["Name", "Init", "Fixed", "Min", "Max"]
    assert _headers(window.implicit_params_table.table_view) == ["Name", "Init", "Fixed", "Min", "Max"]
    assert _headers(window.root_unknowns_table.table_view) == ["Name", "Initial", "Lower", "Upper"]
    assert _headers(window.error_constants_editor.table_view) == ["Name", "Value"]


def test_editor_header_tooltips_follow_canonical_widget_specs_after_language_switch(window: Any) -> None:
    pairs = [
        ("extrapolation.custom.formula", window.custom_formula_edit),
        ("error.formula", window.formula_edit),
        ("fitting.custom.expression", window.fit_expr_edit),
        ("fitting.implicit.equation", window.implicit_equation_edit),
        ("fitting.implicit.output_expression", window.implicit_output_edit),
        ("root.equations", window.root_equations_edit),
    ]

    for language in ("zh", "en"):
        window._apply_language(language)
        QApplication.processEvents()
        for key, widget in pairs:
            label = _schema_label(window, key)
            assert label.toolTip()
            assert label.toolTip() == widget.toolTip(), key
