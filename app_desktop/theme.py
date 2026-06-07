from __future__ import annotations

from PySide6.QtWidgets import QApplication

PANEL_MARGIN = 10
SECTION_SPACING = 8
CONTROL_SPACING = 6
MIN_LEFT_PANEL_WIDTH = 420
SUPPORTED_MIN_WINDOW_WIDTH = 1280


def is_dark_theme() -> bool:
    app = QApplication.instance()
    if app is None:
        return True
    return app.palette().window().color().lightness() < 128


def scrollbar_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    handle = "rgba(255, 255, 255, 0.12)" if dark else "rgba(0, 0, 0, 0.12)"
    hover = "rgba(255, 255, 255, 0.25)" if dark else "rgba(0, 0, 0, 0.28)"
    return f"""
QScrollBar:vertical, QScrollBar:horizontal {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{ width: 6px; }}
QScrollBar:horizontal {{ height: 6px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {handle};
    border-radius: 3px;
    min-height: 24px; min-width: 24px;
}}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
    background: {hover};
}}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
    height: 0px; width: 0px;
}}
"""


def table_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    if dark:
        style = """
QTableWidget {
    background-color: #2b2d30;
    alternate-background-color: #313335;
    gridline-color: #43454a;
    color: #dfe1e5;
    font-family: Menlo, Consolas, monospace;
    font-size: 13px;
    selection-background-color: #2d5a88;
    selection-color: #ffffff;
    border: none;
}
QTableWidget::item { padding: 4px 8px; border-bottom: 1px solid #3c3e42; }
QTableWidget::item:focus { background-color: #37506b; }
QHeaderView::section {
    background-color: #3c3e42; color: #bfc1c5; font-weight: 600;
    padding: 6px 8px; border: none;
    border-right: 1px solid #4e5157; border-bottom: 2px solid #4e5157;
}
QHeaderView::section:hover { background-color: #454749; }
QTableCornerButton::section {
    background-color: #3c3e42; border: none;
    border-right: 1px solid #4e5157; border-bottom: 2px solid #4e5157;
}
"""
    else:
        style = """
QTableWidget {
    background-color: #ffffff;
    alternate-background-color: #f5f6f8;
    gridline-color: #e2e4e8;
    color: #1f2328;
    font-family: Menlo, Consolas, monospace;
    font-size: 13px;
    selection-background-color: #dbeafe;
    selection-color: #1f2328;
    border: none;
}
QTableWidget::item { padding: 4px 8px; border-bottom: 1px solid #e8eaed; }
QTableWidget::item:focus { background-color: #e0ecff; }
QHeaderView::section {
    background-color: #f0f1f3; color: #57606a; font-weight: 600;
    padding: 6px 8px; border: none;
    border-right: 1px solid #e2e4e8; border-bottom: 2px solid #d1d5db;
}
QHeaderView::section:hover { background-color: #e8eaed; }
QTableCornerButton::section {
    background-color: #f0f1f3; border: none;
    border-right: 1px solid #e2e4e8; border-bottom: 2px solid #d1d5db;
}
"""
    return style + scrollbar_style(dark=dark)


def result_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    if dark:
        style = """
QTextBrowser {
    background-color: #2b2d30; color: #dfe1e5;
    font-size: 14px; border: none; padding: 10px 12px;
    selection-background-color: #2d5a88; selection-color: #ffffff;
}
"""
    else:
        style = """
QTextBrowser {
    background-color: #ffffff; color: #1f2328;
    font-size: 14px; border: none; padding: 10px 12px;
    selection-background-color: #dbeafe; selection-color: #1f2328;
}
"""
    return style + scrollbar_style(dark=dark)


def compact_button_style() -> str:
    return """
QPushButton {
    min-height: 24px;
    padding: 2px 8px;
}
"""
