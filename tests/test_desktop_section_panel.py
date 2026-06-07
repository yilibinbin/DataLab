from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QSizePolicy

from app_desktop.section_panel import SectionPanel


def _assert_body_item_is(panel: SectionPanel, widget: QLineEdit) -> None:
    item = panel.body_layout().itemAt(0)
    assert item is not None
    assert item.widget() is widget


def test_section_panel_preserves_body_widget_when_collapsed(qtbot: Any) -> None:
    panel = SectionPanel("Inputs", collapsible=True)
    qtbot.addWidget(panel)
    edit = QLineEdit(panel)
    panel.body_layout().addWidget(edit)

    _assert_body_item_is(panel, edit)
    assert edit.parentWidget() is not None

    panel.set_collapsed(True)

    assert panel.is_collapsed()
    _assert_body_item_is(panel, edit)
    assert edit.parentWidget() is not None

    panel.set_collapsed(False)

    assert not panel.is_collapsed()
    _assert_body_item_is(panel, edit)
    assert edit.parentWidget() is not None


def test_section_panel_title_help_and_size_policy_contract(qtbot: Any) -> None:
    panel = SectionPanel("Initial", help_text="Initial help", collapsible=True)
    qtbot.addWidget(panel)

    panel.set_title("Updated")
    panel.set_help_text("Updated help")

    labels = [label.text() for label in panel.findChildren(QLabel)]
    assert "Updated" in labels
    assert panel.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert panel.minimumWidth() == 0
    assert any(button.toolTip() == "Updated help" for button in panel.findChildren(QPushButton))
