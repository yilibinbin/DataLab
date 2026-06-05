from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QComboBox, QPlainTextEdit, QPushButton, QWidget

from app_desktop.ui_schema_binder import bind_choices, bind_field, find_unbound_required_widgets
from shared.ui_schema import ChoiceSpec, FormFieldSpec, LocalizedText


def _app() -> QApplication:
    app = QApplication.instance()
    if isinstance(app, QApplication):
        return app
    return QApplication([])


def test_bind_field_applies_label_widget_and_help_metadata() -> None:
    _app()
    field = FormFieldSpec(
        key="fitting.custom.expression",
        widget_kind="textarea",
        label=LocalizedText("模型表达式：", "Model expression:"),
        placeholder=LocalizedText("例如 A*x + B", "e.g. A*x + B"),
        tooltip=LocalizedText("输入 y=f(x,p) 形式", "Enter y=f(x,p) form"),
        required=True,
    )
    label = QLabel("old")
    widget = QPlainTextEdit()
    help_button = QPushButton()

    bind_field(field=field, label=label, widget=widget, help_button=help_button, lang="en")

    assert label.text() == "Model expression:"
    assert label.toolTip() == "Enter y=f(x,p) form"
    assert label.property("datalab_schema_key") == "fitting.custom.expression"

    assert widget.property("datalab_schema_key") == "fitting.custom.expression"
    assert widget.property("datalab_schema_required") is True
    assert widget.toolTip() == "Enter y=f(x,p) form"
    assert widget.placeholderText() == "e.g. A*x + B"

    assert help_button.text() == "?"
    assert help_button.property("datalab_schema_key") == "fitting.custom.expression"
    assert help_button.toolTip() == "Enter y=f(x,p) form"
    assert help_button.accessibleName() == "Model expression: help"
    assert help_button.accessibleDescription() == "Enter y=f(x,p) form"


def test_bind_choices_populates_combo_labels_values_tooltips_and_marker() -> None:
    _app()
    combo = QComboBox()
    combo.addItem("stale", "stale")
    choices = [
        ChoiceSpec(
            value="scalar",
            label=LocalizedText("标量", "Scalar"),
            tooltip=LocalizedText("求解单个未知量", "Solve one unknown"),
        ),
        ChoiceSpec(value="system", label=LocalizedText("方程组", "System")),
    ]

    bind_choices(combo, choices, lang="zh")

    assert combo.count() == 2
    assert combo.itemText(0) == "标量"
    assert combo.itemData(0) == "scalar"
    assert combo.itemData(0, Qt.ItemDataRole.ToolTipRole) == "求解单个未知量"
    assert combo.itemText(1) == "方程组"
    assert combo.itemData(1) == "system"
    assert combo.itemData(1, Qt.ItemDataRole.ToolTipRole) is None
    assert combo.property("datalab_schema_choices") is True


def test_find_unbound_required_widgets_respects_scan_boundary() -> None:
    _app()
    root = QWidget()
    ordinary_child = QWidget(root)
    nested_ordinary_child = QWidget(ordinary_child)
    unbound_required_child = QPlainTextEdit(root)
    unbound_required_child.setProperty("datalab_schema_required", True)

    assert find_unbound_required_widgets(root) == [unbound_required_child]
    assert nested_ordinary_child not in find_unbound_required_widgets(root)

    field = FormFieldSpec(
        key="root.equations",
        widget_kind="textarea",
        label=LocalizedText("方程：", "Equations:"),
        required=True,
    )
    bind_field(field=field, widget=unbound_required_child)

    assert find_unbound_required_widgets(root) == []


def test_find_unbound_required_widgets_checks_root_itself() -> None:
    _app()
    root = QWidget()
    root.setProperty("datalab_schema_required", True)

    assert find_unbound_required_widgets(root) == [root]

    root.setProperty("datalab_schema_key", "root.required")

    assert find_unbound_required_widgets(root) == []


def test_bind_field_clears_required_marker_when_rebinding_optional_field() -> None:
    _app()
    widget = QPlainTextEdit()
    required = FormFieldSpec(
        key="root.equations",
        widget_kind="textarea",
        label=LocalizedText("方程：", "Equations:"),
        required=True,
    )
    optional = FormFieldSpec(
        key="root.notes",
        widget_kind="textarea",
        label=LocalizedText("备注：", "Notes:"),
        required=False,
    )

    bind_field(field=required, widget=widget)
    bind_field(field=optional, widget=widget)

    assert widget.property("datalab_schema_key") == "root.notes"
    assert widget.property("datalab_schema_required") is False
