from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QEvent
from PySide6.QtWidgets import QApplication, QTableWidget


def test_supported_left_panel_width_is_not_smaller_than_known_minimum() -> None:
    from app_desktop.theme import MIN_LEFT_PANEL_WIDTH, SUPPORTED_MIN_WINDOW_WIDTH

    assert MIN_LEFT_PANEL_WIDTH >= 420
    assert SUPPORTED_MIN_WINDOW_WIDTH >= 1280


def test_schema_scan_uses_theme_supported_width_constant() -> None:
    from app_desktop.theme import SUPPORTED_MIN_WINDOW_WIDTH
    from tools.scan_desktop_gui_schema import SCAN_WIDTHS

    assert SCAN_WIDTHS[0] == SUPPORTED_MIN_WINDOW_WIDTH


def test_apply_desktop_theme_does_not_reset_user_state(qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop.window import ExtrapolationWindow

    app = QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.show()
    app.processEvents()

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    window.formula_edit.setPlainText("A + B")
    window.result_edit.setPlainText("existing result")
    original_mode = window.mode_combo.currentData()
    refresh_calls = 0
    original_refresh = window._refresh_main_splitter_left_min_width

    def _count_refresh() -> None:
        nonlocal refresh_calls
        refresh_calls += 1
        original_refresh()

    monkeypatch.setattr(window, "_refresh_main_splitter_left_min_width", _count_refresh)

    window._apply_desktop_theme()
    app.sendEvent(window, QEvent(QEvent.Type.PaletteChange))
    app.processEvents()

    assert window.mode_combo.currentData() == original_mode
    assert window.formula_edit.toPlainText() == "A + B"
    assert window.result_edit.toPlainText() == "existing result"
    assert all(table.styleSheet() for table in window.findChildren(QTableWidget))
    assert window.workbench_root.styleSheet()
    assert window.workbench_bar.styleSheet()
    assert window.workbench_config_content.styleSheet() == ""
    assert window.workbench_workspace_content.styleSheet() == ""
    assert refresh_calls >= 2


def test_apply_desktop_theme_refreshes_workbench_cards(qtbot: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop.theme import workbench_section_card_style
    from app_desktop.window import ExtrapolationWindow

    app = QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.show()
    app.processEvents()

    window.stats_box.setStyleSheet(workbench_section_card_style(dark=False))
    monkeypatch.setattr("app_desktop.theme.is_dark_theme", lambda: True)
    monkeypatch.setattr("app_desktop.panels.is_dark_theme", lambda: True)

    window._apply_desktop_theme()
    app.processEvents()

    assert "#262b34" in window.workbench_result_overview_panel.styleSheet()
    assert "#20242b" in window.workbench_variable_panel.styleSheet()
    assert "#20242b" in window.stats_box.styleSheet()


def test_theme_toggle_restyles_formula_preview_and_input_tabs(
    qtbot: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex review P2/P3: the formula rendered-preview surface + input_data_tabs style are set
    once at construction, so a live light↔dark toggle must re-apply them via _apply_desktop_theme
    — else they keep a stale light style in a dark UI."""
    from app_desktop.window import ExtrapolationWindow

    app = QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    app.processEvents()

    monkeypatch.setattr("app_desktop.theme.is_dark_theme", lambda: True)
    monkeypatch.setattr("app_desktop.panels.is_dark_theme", lambda: True)
    window._apply_desktop_theme()
    app.processEvents()

    assert "#20242b" in window.workbench_formula_preview_label.styleSheet()  # dark surface
    assert "#1c2129" in window.input_data_tabs.styleSheet()  # dark tab pane


def test_theme_exposes_semantic_text_and_message_styles() -> None:
    from app_desktop import theme

    config_style = theme.config_card_style(dark=False)
    assert 'QWidget[datalab_config_card="true"] QGroupBox' in config_style
    assert "border: none" in config_style
    assert "background: transparent" in config_style
    assert "QGroupBox::title" in config_style
    assert "font-weight" in theme.workbench_title_text_style()
    # text_muted converged to the majority hex (#64748b light / #9aa4b2 dark) — design review P1.
    assert "#64748b" in theme.workbench_muted_text_style(dark=False)
    assert "#9aa4b2" in theme.workbench_muted_text_style(dark=True)
    assert "#aa5500" in theme.workbench_warning_text_style(dark=False)
    assert "font-weight" in theme.workbench_formula_caption_style(dark=False)
    assert "#64748b" in theme.workbench_formula_caption_style(dark=False)
    assert "border-radius" in theme.workbench_message_surface_style(kind="description", dark=False)
    assert "border-radius" in theme.workbench_message_surface_style(kind="error", dark=True)
    assert "border-radius" in theme.round_icon_button_style()
    assert "background-color" in theme.round_icon_button_style()
    assert "#f7f7f7" in theme.pdf_preview_viewport_style(inverted=False)
    assert "#1b1b1b" in theme.pdf_preview_viewport_style(inverted=True)
    assert "font-weight" in theme.pdf_preview_caption_style()
    assert "TutorialOverlay" in theme.tutorial_overlay_style()
    assert "font-size" in theme.tutorial_overlay_title_style()
    assert "color" in theme.tutorial_overlay_body_style()
    assert "QTabWidget::pane" in theme.result_tab_pane_style()


def test_window_i18n_mixin_does_not_embed_round_icon_button_qss() -> None:
    path = Path(__file__).resolve().parents[1] / "app_desktop" / "window_i18n_mixin.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_snippets = {
        """
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
    }
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert literals.isdisjoint(forbidden_snippets)


def test_window_latex_pdf_mixin_does_not_embed_pdf_preview_qss() -> None:
    path = Path(__file__).resolve().parents[1] / "app_desktop" / "window_latex_pdf_mixin.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_literals = {
        "font-weight: bold; margin-top: 12px;",
    }
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert literals.isdisjoint(forbidden_literals)
    assert "background:{bg_color};" not in source


def test_extracted_view_modules_do_not_embed_targeted_literal_qss() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    target_files = [
        repo_root / "app_desktop" / "views" / "fitting.py",
        repo_root / "app_desktop" / "views" / "extrapolation.py",
        repo_root / "app_desktop" / "workbench_formula_panel.py",
    ]
    forbidden_snippets = {
        "font-weight: 600;",
        "color:#aa5500;",
        "color:#666;",
        "font-weight: 600; color: #4b5563;",
        "border-radius: 6px; padding: 6px;",
    }

    literals: set[str] = set()
    for path in target_files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                literals.add(node.value)

    assert literals.isdisjoint(forbidden_snippets)


def test_formula_workbench_view_uses_theme_caption_helper() -> None:
    path = Path(__file__).resolve().parents[1] / "app_desktop" / "workbench_formula_panel.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert "workbench_formula_caption_style" in source
    assert "workbench_title_text_style()} {workbench_muted_text_style" not in source
    assert "font-weight: 600; color:" not in literals


def test_panels_does_not_embed_result_tab_pane_qss() -> None:
    path = Path(__file__).resolve().parents[1] / "app_desktop" / "panels.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    forbidden_snippets = {
        """
QTabWidget::pane {
    border: none;
}
"""
    }
    literals = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }

    assert literals.isdisjoint(forbidden_snippets)


def test_panels_does_not_define_duplicate_style_alias_wrappers() -> None:
    path = Path(__file__).resolve().parents[1] / "app_desktop" / "panels.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function_names = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }

    assert "_get_table_style" not in function_names
    assert "_get_result_style" not in function_names
