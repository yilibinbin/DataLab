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
WORKBENCH_FORMULA_PANEL_SINGLE_MAX_HEIGHT = 268
WORKBENCH_FORMULA_PANEL_MULTI_MAX_HEIGHT = 392
WORKBENCH_FORMULA_TITLE_ROW_MAX_HEIGHT = 42
WORKBENCH_FORMULA_EDITOR_MAX_HEIGHT = 118


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


def workbench_title_text_style() -> str:
    return "font-weight: 600;"


def workbench_muted_text_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    color = "#9aa4b2" if dark else "#4b5563"
    return f"color: {color};"


def workbench_warning_text_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    color = "#f59e0b" if dark else "#aa5500"
    return f"color: {color};"


def workbench_formula_caption_style(*, dark: bool | None = None) -> str:
    return f"{workbench_title_text_style()} {workbench_muted_text_style(dark=dark)}"


def workbench_message_surface_style(
    *,
    kind: str = "description",
    dark: bool | None = None,
) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    if kind == "error":
        color = "#fed7aa" if dark else "#9a3412"
        background = "#431407" if dark else "#fff7ed"
        border = "#9a3412" if dark else "#fed7aa"
    elif kind == "description":
        color = "#9aa4b2" if dark else "#4b5563"
        background = "#20242b" if dark else "#f9fafb"
        border = "rgba(255, 255, 255, 0.10)" if dark else "#e5e7eb"
    else:
        raise ValueError(f"Unknown workbench message surface kind: {kind}")
    return f"color: {color}; background: {background}; border: 1px solid {border}; border-radius: 6px; padding: 6px;"


def workbench_section_card_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    if dark:
        card_bg = "#20242b"
        border = "rgba(255, 255, 255, 0.10)"
        title_fg = "#e5e7eb"
        muted_fg = "#a5b4c3"
    else:
        card_bg = "#ffffff"
        border = "#d8dee8"
        title_fg = "#0f172a"
        muted_fg = "#64748b"
    return f"""
QGroupBox[datalab_workbench_section_host="true"] {{
    border: none;
    margin: 0;
    padding: 0;
}}
QFrame[datalab_workbench_section_card="true"] {{
    background: {card_bg};
    border: 1px solid {border};
    border-radius: {REGION_RADIUS}px;
}}
QLabel[datalab_workbench_section_title="true"] {{
    color: {title_fg};
    font-weight: 600;
}}
QLabel[datalab_workbench_section_description="true"] {{
    color: {muted_fg};
}}
"""


def formula_preview_surface_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    background = "#1f2328" if dark else "#ffffff"
    color = "#f8fafc" if dark else "#111111"
    border = "rgba(255, 255, 255, 0.16)" if dark else "#d0d7de"
    return f"background: {background}; color: {color}; border: 1px solid {border}; border-radius: 4px; padding: 12px;"


def formula_preview_error_surface_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    background = "#431407" if dark else "#fff4f2"
    color = "#fed7aa" if dark else "#8a1c13"
    border = "#9a3412" if dark else "#f2b8b5"
    return f"background: {background}; color: {color}; border: 1px solid {border}; border-radius: 4px; padding: 8px;"


def formula_preview_source_edit_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    background = "#1f2328" if dark else "#ffffff"
    color = "#f8fafc" if dark else "#111111"
    border = "rgba(255, 255, 255, 0.16)" if dark else "#d0d7de"
    return f"background: {background}; color: {color}; border: 1px solid {border};"


def formula_inline_preview_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    background = "#20242b" if dark else "#f8fafc"
    color = "#f8fafc" if dark else "#111827"
    border = "rgba(255, 255, 255, 0.14)" if dark else "#cbd5e1"
    return f"background: {background}; color: {color}; border: 1px solid {border}; border-radius: 6px; padding: 12px;"


def pdf_preview_viewport_style(*, inverted: bool = False) -> str:
    background = "#1b1b1b" if inverted else "#f7f7f7"
    return f"background: {background};"


def pdf_preview_caption_style() -> str:
    return "font-weight: bold; margin-top: 12px;"


def tutorial_overlay_style() -> str:
    return """
TutorialOverlay {
    background: rgba(0, 0, 0, 120);
}
QWidget#card {
    background: white;
    border-radius: 10px;
}
"""


def tutorial_overlay_title_style() -> str:
    return "font-size: 16pt; font-weight: 600;"


def tutorial_overlay_body_style() -> str:
    return "font-size: 11pt; color: #333;"


def result_tab_pane_style() -> str:
    return """
QTabWidget::pane {
    border: none;
}
"""


def config_card_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    if dark:
        panel_bg = "#20242b"
        border = "rgba(255, 255, 255, 0.10)"
        title_fg = "#e5e7eb"
    else:
        panel_bg = "#ffffff"
        border = "#d8dee8"
        title_fg = "#1f2328"
    return f"""
QWidget[datalab_config_card="true"] {{
    background: {panel_bg};
    border: 1px solid {border};
    border-radius: {REGION_RADIUS}px;
}}
QWidget[datalab_config_card="true"] QGroupBox {{
    background: transparent;
    border: none;
    margin-top: 18px;
    padding: 0px;
    color: {title_fg};
    font-weight: 600;
}}
QWidget[datalab_config_card="true"] QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 0px;
    top: 0px;
    padding: 0px;
}}
QWidget[datalab_config_card="true"] QPushButton[datalab_primary_run_button="true"] {{
    min-height: 28px;
    padding: 4px 10px;
    color: #ffffff;
    background: #2563eb;
    border: 1px solid #2563eb;
    border-radius: 6px;
    font-weight: 600;
}}
QWidget[datalab_config_card="true"] QPushButton[datalab_primary_run_button="true"]:hover {{
    background: #1d4ed8;
    border-color: #1d4ed8;
}}
QWidget[datalab_config_card="true"] QPushButton[datalab_primary_run_button="true"][datalab_run_state="stop"] {{
    background: #dc2626;
    border-color: #dc2626;
}}
QWidget[datalab_config_card="true"] QPushButton[datalab_primary_run_button="true"][datalab_run_state="stop"]:hover {{
    background: #b91c1c;
    border-color: #b91c1c;
}}
"""


def result_detail_card_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    if dark:
        panel_bg = "#20242b"
        tab_bg = "#262b34"
        tab_hover = "#303746"
        selected_bg = "#1f2937"
        border = "rgba(255, 255, 255, 0.10)"
        title_fg = "#e5e7eb"
        muted_fg = "#a5b4c3"
        selected_fg = "#f8fafc"
    else:
        panel_bg = "#ffffff"
        tab_bg = "#f6f8fb"
        tab_hover = "#eef2f7"
        selected_bg = "#ffffff"
        border = "#d8dee8"
        title_fg = "#0f172a"
        muted_fg = "#64748b"
        selected_fg = "#0f172a"
    return f"""
QWidget#workbench_result_details_panel {{
    background: {panel_bg};
    border: 1px solid {border};
    border-radius: {REGION_RADIUS}px;
}}
QLabel#workbench_result_details_title {{
    color: {title_fg};
    font-weight: 600;
}}
QWidget#workbench_result_details_empty_panel {{
    background: transparent;
}}
QLabel#workbench_result_details_empty_label {{
    color: {muted_fg};
    font-size: 13px;
}}
QTabWidget#result_detail_tabs::pane {{
    border: 1px solid {border};
    border-radius: 6px;
    background: {panel_bg};
    top: -1px;
}}
QTabWidget#result_detail_tabs QTabBar::tab {{
    min-width: 28px;
    padding: 5px 5px;
    font-size: 12px;
    color: {muted_fg};
    background: {tab_bg};
    border: 1px solid {border};
    border-bottom: none;
}}
QTabWidget#result_detail_tabs QTabBar::tab:selected {{
    color: {selected_fg};
    background: {selected_bg};
    font-weight: 600;
}}
QTabWidget#result_detail_tabs QTabBar::tab:hover {{
    background: {tab_hover};
}}
QTabWidget#result_detail_tabs QTabBar::scroller {{
    width: 18px;
}}
"""


def result_overview_card_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    if dark:
        panel_bg = "#20242b"
        summary_bg = "#262b34"
        border = "rgba(255, 255, 255, 0.10)"
        title_fg = "#e5e7eb"
        body_fg = "#f8fafc"
        muted_fg = "#a5b4c3"
        waiting_bg = "#334155"
        waiting_fg = "#cbd5e1"
        running_bg = "#1e3a8a"
        running_fg = "#bfdbfe"
        ready_bg = "#14532d"
        ready_fg = "#bbf7d0"
        failed_bg = "#7f1d1d"
        failed_fg = "#fecaca"
        complete_bg = "#78350f"
        complete_fg = "#fde68a"
    else:
        panel_bg = "#ffffff"
        summary_bg = "#f8fafc"
        border = "#d0d7de"
        title_fg = "#0f172a"
        body_fg = "#111827"
        muted_fg = "#64748b"
        waiting_bg = "#f1f5f9"
        waiting_fg = "#475569"
        running_bg = "#dbeafe"
        running_fg = "#1d4ed8"
        ready_bg = "#dcfce7"
        ready_fg = "#166534"
        failed_bg = "#fee2e2"
        failed_fg = "#b91c1c"
        complete_bg = "#fef3c7"
        complete_fg = "#92400e"
    return f"""
QWidget#workbench_result_overview_panel {{
    background: {panel_bg};
    border: 1px solid {border};
    border-radius: {REGION_RADIUS}px;
}}
QLabel#workbench_result_overview_title {{
    color: {title_fg};
    font-weight: 600;
}}
QLabel#workbench_result_status_badge {{
    border-radius: 8px;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 7px;
}}
QLabel#workbench_result_status_badge[datalab_result_status="waiting"] {{
    background: {waiting_bg};
    color: {waiting_fg};
}}
QLabel#workbench_result_status_badge[datalab_result_status="running"] {{
    background: {running_bg};
    color: {running_fg};
}}
QLabel#workbench_result_status_badge[datalab_result_status="ready"] {{
    background: {ready_bg};
    color: {ready_fg};
}}
QLabel#workbench_result_status_badge[datalab_result_status="failed"] {{
    background: {failed_bg};
    color: {failed_fg};
}}
QLabel#workbench_result_status_badge[datalab_result_status="complete"] {{
    background: {complete_bg};
    color: {complete_fg};
}}
QLabel#workbench_result_overview {{
    color: {body_fg};
}}
QLabel#workbench_result_overview_meta {{
    color: {muted_fg};
}}
QWidget#workbench_result_summary_grid {{
    background: {summary_bg};
    border: 1px solid {border};
    border-radius: 5px;
}}
QLabel[datalab_result_summary_label="true"] {{
    color: {muted_fg};
    font-size: 11px;
}}
QLabel[datalab_result_summary_value="true"] {{
    color: {body_fg};
    font-weight: 600;
}}
"""


def data_input_card_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    if dark:
        panel_bg = "#20242b"
        button_bg = "#262b34"
        button_hover = "#303746"
        border = "rgba(255, 255, 255, 0.10)"
        title_fg = "#e5e7eb"
        muted_fg = "#a5b4c3"
        button_fg = "#e5e7eb"
    else:
        panel_bg = "#ffffff"
        button_bg = "#f8fafc"
        button_hover = "#eef2f7"
        border = "#d8dee8"
        title_fg = "#0f172a"
        muted_fg = "#64748b"
        button_fg = "#1f2328"
    return f"""
QGroupBox#manual_box {{
    background: {panel_bg};
    border: 1px solid {border};
    border-radius: {REGION_RADIUS}px;
    margin-top: 0px;
}}
QLabel#manual_data_title {{
    color: {title_fg};
    font-weight: 600;
}}
QLabel#manual_data_summary {{
    color: {muted_fg};
}}
QPushButton[datalab_data_toolbar_button="true"] {{
    min-height: 24px;
    padding: 2px 8px;
    color: {button_fg};
    background: {button_bg};
    border: 1px solid {border};
    border-radius: 5px;
}}
QPushButton[datalab_data_toolbar_button="true"]:hover {{
    background: {button_hover};
}}
"""


def variable_panel_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    if dark:
        panel_bg = "#20242b"
        card_bg = "#20242b"
        button_bg = "#262b34"
        button_hover = "#303746"
        border = "rgba(255, 255, 255, 0.10)"
        title_fg = "#e5e7eb"
        muted_fg = "#a5b4c3"
        button_fg = "#e5e7eb"
    else:
        panel_bg = "#f3f5f7"
        card_bg = "#ffffff"
        button_bg = "#f8fafc"
        button_hover = "#eef2f7"
        border = "#d8dee8"
        title_fg = "#0f172a"
        muted_fg = "#64748b"
        button_fg = "#1f2328"
    return f"""
QWidget#workbench_variable_panel {{
    background: {panel_bg};
}}
QLabel#workbench_variable_title {{
    color: {title_fg};
    font-weight: 600;
}}
QFrame[datalab_variable_section_card="true"] {{
    background: {card_bg};
    border: 1px solid {border};
    border-radius: {REGION_RADIUS}px;
}}
QFrame[datalab_variable_section_card="true"] QLabel {{
    color: {title_fg};
}}
QLabel[datalab_variable_section_title="true"] {{
    color: {muted_fg};
    font-weight: 600;
}}
QPushButton[datalab_variable_toolbar_button="true"] {{
    min-height: 24px;
    padding: 2px 8px;
    color: {button_fg};
    background: {button_bg};
    border: 1px solid {border};
    border-radius: 5px;
}}
QPushButton[datalab_variable_toolbar_button="true"]:hover {{
    background: {button_hover};
}}
"""


def constants_editor_style(
    *,
    embedded: bool = False,
    dark: bool | None = None,
) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    if dark:
        card_bg = "#20242b"
        button_bg = "#262b34"
        button_hover = "#303746"
        border = "rgba(255, 255, 255, 0.10)"
        button_fg = "#e5e7eb"
    else:
        card_bg = "#f8fafc"
        button_bg = "#f8fafc"
        button_hover = "#eef2f7"
        border = "#d8dee8"
        button_fg = "#1f2328"
    if embedded:
        return f"""
QWidget[datalab_constants_card="true"] {{
    background: transparent;
    border: none;
    border-radius: 0px;
}}
QWidget[datalab_constants_card="true"] QCheckBox {{
    font-weight: 600;
}}
QWidget[datalab_constants_card="true"] QPushButton {{
    min-height: 24px;
    padding: 2px 8px;
    color: {button_fg};
    background: {button_bg};
    border: 1px solid {border};
    border-radius: 5px;
}}
QWidget[datalab_constants_card="true"] QPushButton:hover {{
    background: {button_hover};
}}
"""
    return f"""
QWidget[datalab_constants_card="true"] {{
    background: {card_bg};
    border: 1px solid {border};
    border-radius: 6px;
}}
QWidget[datalab_constants_card="true"] QCheckBox {{
    font-weight: 600;
}}
QWidget[datalab_constants_card="true"] QPushButton {{
    min-height: 24px;
    padding: 2px 8px;
    color: {button_fg};
}}
"""


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


def round_icon_button_style() -> str:
    return """
QPushButton {
    border-radius: 6px;
    padding: 4px;
}
QPushButton:hover {
    background-color: rgba(0, 0, 0, 0.08);
}
QPushButton:pressed {
    background-color: rgba(0, 0, 0, 0.16);
}
"""
