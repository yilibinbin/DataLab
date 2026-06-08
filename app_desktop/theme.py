from __future__ import annotations

from PySide6.QtWidgets import QApplication

PANEL_MARGIN = 10
SECTION_SPACING = 8
CONTROL_SPACING = 6
MIN_LEFT_PANEL_WIDTH = 420
SUPPORTED_MIN_WINDOW_WIDTH = 1280
TOOLBAR_HEIGHT = 54
STATUS_STRIP_HEIGHT = 26
CONFIG_RAIL_WIDTH = 320
RESULT_RAIL_WIDTH = 380
WORKSPACE_GUTTER = 12
REGION_RADIUS = 8


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


def workbench_toolbar_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    border = "rgba(255, 255, 255, 0.10)" if dark else "rgba(31, 35, 40, 0.12)"
    bg = "#20242b" if dark else "#f8fafc"
    fg = "#e5e7eb" if dark else "#1f2328"
    hover = "#2b313a" if dark else "#eef2f7"
    active = "#2563eb" if dark else "#2563eb"
    return f"""
QFrame#workbench_toolbar {{
    background: {bg};
    border-bottom: 1px solid {border};
}}
QFrame#workbench_toolbar QLabel {{
    color: {fg};
}}
QFrame#workbench_toolbar QToolButton,
QFrame#workbench_toolbar QPushButton {{
    min-height: 34px;
    padding: 4px 8px;
    border: 1px solid transparent;
    border-radius: 6px;
    color: {fg};
}}
QFrame#workbench_toolbar QToolButton:hover,
QFrame#workbench_toolbar QPushButton:hover {{
    background: {hover};
    border-color: {border};
}}
QFrame#workbench_toolbar QToolButton#workbench_run_button {{
    color: #ffffff;
    background: {active};
    border-color: {active};
}}
"""


def workbench_region_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    app_bg = "#181a1f" if dark else "#f3f5f7"
    panel_bg = "#20242b" if dark else "#ffffff"
    border = "rgba(255, 255, 255, 0.10)" if dark else "#d8dee8"
    fg = "#e5e7eb" if dark else "#1f2328"
    return f"""
QWidget#workbench_root {{
    background: {app_bg};
}}
QScrollArea#workbench_config_rail,
QScrollArea#workbench_workspace_canvas,
QFrame#workbench_result_rail {{
    background: {panel_bg};
    color: {fg};
    border: 1px solid {border};
    border-radius: {REGION_RADIUS}px;
}}
QFrame#workbench_workspace_canvas_content QGroupBox,
QFrame#workbench_result_rail QWidget#workbench_result_overview_panel {{
    border: 1px solid {border};
    border-radius: {REGION_RADIUS}px;
    background: {panel_bg};
}}
QFrame#workbench_workspace_canvas_content QLabel,
QFrame#workbench_config_rail_content QLabel,
QFrame#workbench_result_rail QLabel {{
    color: {fg};
}}
QFrame#workbench_status_strip {{
    background: {app_bg};
    color: {fg};
    border-top: 1px solid {border};
}}
""" + scrollbar_style(dark=dark)


def compact_button_style() -> str:
    return """
QPushButton {
    min-height: 24px;
    padding: 2px 8px;
}
"""
