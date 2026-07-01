from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from app_desktop.theme import CONTROL_SPACING, PANEL_MARGIN


class SectionPanel(QWidget):
    def __init__(
        self,
        title: str = "",
        *,
        help_text: str = "",
        collapsible: bool = False,
        collapsed: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._collapsed = False

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setMinimumWidth(0)

        self._title_label = QLabel(title, self)
        self._title_label.setWordWrap(True)
        self._title_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

        self._help_button = QPushButton("?", self)
        self._help_button.setFixedWidth(24)
        self._help_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._help_button.setAccessibleName("Section help")
        self._help_button.setVisible(bool(help_text))
        # Clicking "?" pops the help text (also available as a hover tooltip), so the
        # button does real work rather than being a no-op shell control.
        self._help_button.clicked.connect(self._show_help_popup)

        self._collapse_toggle: QPushButton | None = None
        if collapsible:
            self._collapse_toggle = QPushButton("v", self)
            self._collapse_toggle.setFixedWidth(24)
            self._collapse_toggle.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self._collapse_toggle.setAccessibleName("Toggle section")
            self._collapse_toggle.clicked.connect(lambda: self.set_collapsed(not self._collapsed))

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(CONTROL_SPACING)
        header_layout.addWidget(self._title_label, 1)
        header_layout.addWidget(self._help_button, 0)
        if self._collapse_toggle is not None:
            header_layout.addWidget(self._collapse_toggle, 0)

        self._body_widget = QWidget(self)
        self._body_widget.setMinimumWidth(0)
        self._body_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._body_layout = QVBoxLayout(self._body_widget)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(CONTROL_SPACING)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(PANEL_MARGIN, CONTROL_SPACING, PANEL_MARGIN, PANEL_MARGIN)
        main_layout.setSpacing(CONTROL_SPACING)
        main_layout.addLayout(header_layout)
        main_layout.addWidget(self._body_widget)

        self.set_help_text(help_text)
        self.set_collapsed(collapsed)

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = bool(collapsed)
        self._body_widget.setVisible(not self._collapsed)
        if self._collapse_toggle is not None:
            self._collapse_toggle.setText(">" if self._collapsed else "v")

    def is_collapsed(self) -> bool:
        return self._collapsed

    def set_title(self, title: str) -> None:
        self._title_label.setText(title)

    def set_help_text(self, help_text: str) -> None:
        self._help_text = help_text
        self._help_button.setToolTip(help_text)
        self._help_button.setAccessibleDescription(help_text)
        self._help_button.setVisible(bool(help_text))

    def _show_help_popup(self) -> None:
        text = getattr(self, "_help_text", "") or self._help_button.toolTip()
        if not text:
            return
        pos = self._help_button.mapToGlobal(self._help_button.rect().bottomLeft())
        QToolTip.showText(pos, text, self._help_button)
