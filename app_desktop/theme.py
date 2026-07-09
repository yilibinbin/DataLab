from __future__ import annotations

from PySide6.QtWidgets import QApplication

PANEL_MARGIN = 10
SECTION_SPACING = 8
CONTROL_SPACING = 6

# --- Unified spacing scale (px) ---
# One source of truth for inter-control / card / gutter spacing so panels stop
# hardcoding divergent literals. Legacy names above remain valid aliases.
SPACE_XS = 4    # deliberately tight control rows
SPACE_SM = 6    # default control-row gap   (== CONTROL_SPACING)
SPACE_MD = 8    # section/card row gap       (== SECTION_SPACING)
SPACE_LG = 12   # workspace gutter           (== WORKSPACE_GUTTER)

# Inner titled-box content margin (replaces ad-hoc 8,8,8,8).
INNER_BOX_MARGIN = SPACE_MD            # 8
# Card content margins (replaces ad-hoc 12,10,12,12).
CARD_MARGIN_H = SPACE_LG               # 12
CARD_MARGIN_V = PANEL_MARGIN           # 10

# Vertical space a *styled* QGroupBox (one whose QSS sets a border) must reserve
# above its content so the title band never overlaps the first control. Must be
# >= the rendered title height (~19px on this theme). Any QSS rule that gives a
# QGroupBox a border MUST pair it with `margin-top: {GROUPBOX_TITLE_CLEARANCE}px`
# and a `QGroupBox::title { subcontrol-origin: margin; ... }` block, or the
# title overlaps the content (see the canvas rule below).
GROUPBOX_TITLE_CLEARANCE = 18

MIN_LEFT_PANEL_WIDTH = 420
SUPPORTED_MIN_WINDOW_WIDTH = 1280
TOOLBAR_HEIGHT = 54
STATUS_STRIP_HEIGHT = 26
CONFIG_RAIL_WIDTH = 320
RESULT_RAIL_WIDTH = 380
WORKSPACE_GUTTER = 12
# --- Radius scale (design review R2) ---
# Three tiers instead of the previous 3/4/5/6/8 drift. Cards/panes/tab-panes = CARD; buttons +
# small controls + preview surfaces = CONTROL; status chips = PILL. (Scrollbar handle 3px and the
# tutorial overlay 10px stay bespoke; embedded constants stays 0px on purpose.)
REGION_RADIUS = 8
RADIUS_CARD = 8
RADIUS_CONTROL = 6
RADIUS_PILL = 100
WORKBENCH_FORMULA_PANEL_SINGLE_MAX_HEIGHT = 268
WORKBENCH_FORMULA_PANEL_MULTI_MAX_HEIGHT = 392
WORKBENCH_FORMULA_TITLE_ROW_MAX_HEIGHT = 42
WORKBENCH_FORMULA_EDITOR_MAX_HEIGHT = 118


def is_dark_theme() -> bool:
    app = QApplication.instance()
    if app is None:
        return True
    return app.palette().window().color().lightness() < 128


# --- Semantic color tokens (single source of truth per role) ---
# Each role had 3–4 near-duplicate hexes scattered across the *_style functions (design review P1).
# These collapse them to one value per (role, theme). Style functions resolve through _tok() so a
# role's color is defined exactly once. Values chosen to match the previous dominant hex per role.
_TOKENS: dict[str, tuple[str, str]] = {
    # role: (light, dark)
    "text_primary": ("#0f172a", "#e5e7eb"),   # titles + primary body (was #1f2328/#111827/#111111/#dfe1e5/#f8fafc)
    "text_muted": ("#64748b", "#9aa4b2"),      # secondary/caption text (was #4b5563/#475569/#57606a/#a5b4c3/#bfc1c5)
    "border": ("#d8dee8", "rgba(255, 255, 255, 0.10)"),  # card border (was #d0d7de/#cbd5e1/#e5e7eb/.14/.16)
    "card_bg": ("#ffffff", "#20242b"),         # base card background
    "card_bg_muted": ("#f8fafc", "#20242b"),   # inset/muted card background
    "region_bg": ("#f3f5f7", "#181a1f"),       # app/region background
    "surface_raised": ("#f8fafc", "#262b34"),  # buttons / tab base (was #303746/#2b313a/#2a313c/#222833 dark)
    "surface_hover": ("#eef2f7", "#303746"),   # button/tab hover
}


def _tok(name: str, dark: bool | None = None) -> str:
    """Resolve a semantic color token for the active (or forced) theme."""
    dark = is_dark_theme() if dark is None else bool(dark)
    light_value, dark_value = _TOKENS[name]
    return dark_value if dark else light_value


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
    return f"color: {_tok('text_muted', dark)};"


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
        color = _tok("text_muted", dark)
        background = _tok("card_bg", dark) if dark else "#f9fafb"
        border = _tok("border", dark)
    else:
        raise ValueError(f"Unknown workbench message surface kind: {kind}")
    return f"color: {color}; background: {background}; border: 1px solid {border}; border-radius: 6px; padding: 6px;"


def workbench_section_card_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    card_bg = _tok("card_bg", dark)
    border = _tok("border", dark)
    title_fg = _tok("text_primary", dark)
    muted_fg = _tok("text_muted", dark)
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
    background = "#1f2328" if dark else _tok("card_bg", dark)
    color = _tok("text_primary", dark)
    border = _tok("border", dark)
    return f"background: {background}; color: {color}; border: 1px solid {border}; border-radius: {RADIUS_CONTROL}px; padding: 12px;"


def formula_preview_error_surface_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    background = "#431407" if dark else "#fff4f2"
    color = "#fed7aa" if dark else "#8a1c13"
    border = "#9a3412" if dark else "#f2b8b5"
    return f"background: {background}; color: {color}; border: 1px solid {border}; border-radius: {RADIUS_CONTROL}px; padding: 8px;"


def formula_preview_source_edit_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    background = "#1f2328" if dark else _tok("card_bg", dark)
    color = _tok("text_primary", dark)
    border = _tok("border", dark)
    return f"background: {background}; color: {color}; border: 1px solid {border};"


def formula_inline_preview_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    background = _tok("card_bg_muted", dark)
    color = _tok("text_primary", dark)
    border = _tok("border", dark)
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
    return f"font-size: 11pt; color: {_tok('text_primary', True)};"


def result_tab_pane_style() -> str:
    return """
QTabWidget::pane {
    border: none;
}
"""


def config_card_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    panel_bg = _tok("card_bg", dark)
    border = _tok("border", dark)
    title_fg = _tok("text_primary", dark)
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
"""


def result_detail_card_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    panel_bg = _tok("card_bg", dark)
    border = _tok("border", dark)
    title_fg = _tok("text_primary", dark)
    muted_fg = _tok("text_muted", dark)
    selected_fg = _tok("text_primary", dark)
    tab_bg = _tok("surface_raised", dark)
    tab_hover = _tok("surface_hover", dark)
    selected_bg = "#1f2937" if dark else "#ffffff"
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
    border-radius: {RADIUS_CARD}px;
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


def input_data_tabs_style(*, dark: bool | None = None) -> str:
    """Rounded, modern styling for the 输入数据 / 常数 sheet tabs (input_data_tabs). Mirrors the
    result-detail tab chrome so the input area matches the rest of the workbench."""
    dark = is_dark_theme() if dark is None else bool(dark)
    border = _tok("border", dark)
    selected_fg = _tok("text_primary", dark)
    muted_fg = _tok("text_muted", dark)
    if dark:
        panel_bg = "#1c2129"
        tab_bg = "#161a21"
        tab_hover = "#222833"
        selected_bg = "#2a313c"
    else:
        panel_bg = "#ffffff"
        tab_bg = "#f1f5f9"
        tab_hover = "#e2e8f0"
        selected_bg = "#ffffff"
    return f"""
QTabWidget#input_data_tabs::pane {{
    border: 1px solid {border};
    border-radius: {RADIUS_CARD}px;
    background: {panel_bg};
    top: -1px;
}}
QTabWidget#input_data_tabs QTabBar::tab {{
    min-width: 60px;
    padding: 6px 14px;
    font-size: 13px;
    color: {muted_fg};
    background: {tab_bg};
    border: 1px solid {border};
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}}
QTabWidget#input_data_tabs QTabBar::tab:selected {{
    color: {selected_fg};
    background: {selected_bg};
    font-weight: 600;
}}
QTabWidget#input_data_tabs QTabBar::tab:hover {{
    background: {tab_hover};
}}
"""


def result_overview_card_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    panel_bg = _tok("card_bg", dark)
    border = _tok("border", dark)
    title_fg = _tok("text_primary", dark)
    body_fg = _tok("text_primary", dark)
    muted_fg = _tok("text_muted", dark)
    summary_bg = _tok("surface_raised", dark)
    if dark:
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
QLabel#workbench_result_status_badge,
QLabel#result_status_strip_status {{
    border-radius: 8px;
    font-size: 11px;
    font-weight: 600;
    padding: 2px 7px;
}}
QLabel#workbench_result_status_badge[datalab_result_status="waiting"],
QLabel#result_status_strip_status[datalab_result_status="waiting"] {{
    background: {waiting_bg};
    color: {waiting_fg};
}}
QLabel#workbench_result_status_badge[datalab_result_status="running"],
QLabel#result_status_strip_status[datalab_result_status="running"] {{
    background: {running_bg};
    color: {running_fg};
}}
QLabel#workbench_result_status_badge[datalab_result_status="ready"],
QLabel#result_status_strip_status[datalab_result_status="ready"] {{
    background: {ready_bg};
    color: {ready_fg};
}}
QLabel#workbench_result_status_badge[datalab_result_status="failed"],
QLabel#result_status_strip_status[datalab_result_status="failed"] {{
    background: {failed_bg};
    color: {failed_fg};
}}
QLabel#workbench_result_status_badge[datalab_result_status="complete"],
QLabel#result_status_strip_status[datalab_result_status="complete"] {{
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
    border-radius: {RADIUS_CONTROL}px;
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
    panel_bg = _tok("card_bg", dark)
    border = _tok("border", dark)
    title_fg = _tok("text_primary", dark)
    muted_fg = _tok("text_muted", dark)
    button_fg = _tok("text_primary", dark)
    button_bg = _tok("surface_raised", dark)
    button_hover = _tok("surface_hover", dark)
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
    border-radius: {RADIUS_CONTROL}px;
}}
QPushButton[datalab_data_toolbar_button="true"]:hover {{
    background: {button_hover};
}}
"""


def variable_panel_style(*, dark: bool | None = None) -> str:
    dark = is_dark_theme() if dark is None else bool(dark)
    card_bg = _tok("card_bg", dark)
    border = _tok("border", dark)
    title_fg = _tok("text_primary", dark)
    muted_fg = _tok("text_muted", dark)
    button_fg = _tok("text_primary", dark)
    panel_bg = _tok("card_bg", dark) if dark else _tok("region_bg", dark)
    button_bg = _tok("surface_raised", dark)
    button_hover = _tok("surface_hover", dark)
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
    border-radius: {RADIUS_CONTROL}px;
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
    card_bg = _tok("card_bg_muted", dark)
    border = _tok("border", dark)
    button_fg = _tok("text_primary", dark)
    button_bg = _tok("surface_raised", dark)
    button_hover = _tok("surface_hover", dark)
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
    border-radius: {RADIUS_CONTROL}px;
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
    hover = _tok("surface_hover", dark)
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
    app_bg = _tok("region_bg", dark)
    panel_bg = _tok("card_bg", dark)
    border = _tok("border", dark)
    fg = _tok("text_primary", dark)
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
/* A styled QGroupBox border drops Qt's native title-band reservation, so the
   title overlaps the first control. Reserve the band (mirrors the config_card
   rule) for every titled box reparented into the canvas. */
QFrame#workbench_workspace_canvas_content QGroupBox {{
    margin-top: {GROUPBOX_TITLE_CLEARANCE}px;
}}
QFrame#workbench_workspace_canvas_content QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 8px;
    top: 0px;
    padding: 0 3px;
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
