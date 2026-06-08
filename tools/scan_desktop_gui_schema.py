from __future__ import annotations

import base64
from dataclasses import dataclass
from importlib import import_module
import json
import os
from pathlib import Path
import sys
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _ensure_repo_root_on_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))


_ensure_repo_root_on_path()

from PySide6.QtGui import QAction  # noqa: E402
from PySide6.QtWidgets import (  # noqa: E402
    QApplication,
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QTableWidget,
    QTabWidget,
    QTextEdit,
    QWidget,
)

from app_desktop.theme import SUPPORTED_MIN_WINDOW_WIDTH  # noqa: E402
from app_desktop.workbench_visual_contract import visual_contract_issues  # noqa: E402


@dataclass(frozen=True)
class ScreenScenario:
    key: str
    language: str
    mode: str
    root_mode: str = ""
    result_tab: str = ""
    width: int = 1400
    height: int = 900


MODES = ("extrapolation", "error", "fitting", "root_solving", "statistics")
ROOT_SOLVING_SUBMODES = ("scalar", "scan_multiple", "polynomial", "system")
SCAN_WIDTHS = (SUPPORTED_MIN_WINDOW_WIDTH, 1440, 1680)
RESULT_TABS = ("numeric", "image", "log", "latex", "pdf")
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="
)


def _combo_index_for_data(combo: Any, data: object) -> int:
    index = combo.findData(data)
    if index < 0:
        raise AssertionError(f"missing combo data {data!r}")
    return int(index)


def _find_unbound_required_widgets(root: Any) -> list[Any]:
    _ensure_repo_root_on_path()
    finder = cast(Any, import_module("app_desktop.ui_schema_binder").find_unbound_required_widgets)
    return cast(list[Any], finder(root))


def _capture_workspace(window: Any, *, title: str) -> Any:
    _ensure_repo_root_on_path()
    capture = cast(Any, import_module("app_desktop.workspace_controller").capture_workspace)
    return capture(window, title=title)


def _restore_workspace(window: Any, manifest: dict[str, Any], attachments: dict[str, bytes]) -> None:
    _ensure_repo_root_on_path()
    restore = cast(Any, import_module("app_desktop.workspace_controller").restore_workspace)
    restore(window, manifest, attachments)


def _create_window() -> Any:
    _ensure_repo_root_on_path()
    window_cls = cast(Any, import_module("app_desktop.window").ExtrapolationWindow)
    return window_cls()


def _issue(kind: str, scenario: ScreenScenario | None, widget: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "kind": kind,
        "scenario": scenario.key if scenario is not None else "",
        "language": scenario.language if scenario is not None else "",
        "widget": widget,
        "message": message,
        "details": details,
    }


def _issue_to_legacy_text(issue: dict[str, Any]) -> str:
    message = str(issue.get("message", ""))
    language = str(issue.get("language", ""))
    scenario = str(issue.get("scenario", ""))
    if language and scenario.endswith(":legacy"):
        return f"{language}: {message}"
    return message


def _screen_scenarios(*, refresh_language: bool) -> list[ScreenScenario]:
    languages = ("zh", "en") if refresh_language else ("current",)
    modes: list[tuple[str, str]] = [(mode, "") for mode in MODES if mode != "root_solving"]
    modes.extend(("root_solving", root_mode) for root_mode in ROOT_SOLVING_SUBMODES)

    scenarios: list[ScreenScenario] = []
    for language in languages:
        for width in SCAN_WIDTHS:
            for mode, root_mode in modes:
                for result_tab in RESULT_TABS:
                    parts = [language, str(width), mode]
                    if root_mode:
                        parts.append(root_mode)
                    parts.append(result_tab)
                    scenarios.append(
                        ScreenScenario(
                            key=":".join(parts),
                            language=language,
                            mode=mode,
                            root_mode=root_mode,
                            result_tab=result_tab,
                            width=width,
                        )
                    )
    return scenarios


def _apply_screen_scenario(window: Any, scenario: ScreenScenario) -> None:
    window.resize(scenario.width, scenario.height)
    if scenario.language != "current":
        window._apply_language(scenario.language)
    window.mode_combo.setCurrentIndex(_combo_index_for_data(window.mode_combo, scenario.mode))
    if scenario.mode == "root_solving":
        _configure_root_scrollbar_scenario(window, scenario.root_mode or ROOT_SOLVING_SUBMODES[0])
    result_tabs = getattr(window, "result_tabs", None)
    result_tab_indices = getattr(window, "result_tabs_indices", {})
    if isinstance(result_tabs, QTabWidget) and scenario.result_tab in result_tab_indices:
        tabs = getattr(window, "tabs", None)
        result_tab_index = getattr(window, "result_tab_index", -1)
        if isinstance(tabs, QTabWidget) and result_tab_index >= 0:
            tabs.setCurrentIndex(result_tab_index)
        result_tabs.setCurrentIndex(int(result_tab_indices[scenario.result_tab]))
    QApplication.processEvents()


def _horizontal_scrollbar_issues(window: Any, scenarios: list[ScreenScenario]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for scenario in scenarios:
        _apply_screen_scenario(window, scenario)
        QApplication.processEvents()
        _force_smallest_left_splitter(window)
        scroll = window.findChild(QScrollArea, "workbench_config_rail")
        kind = "workbench_config_horizontal_scrollbar"
        widget = "workbench_config_rail"
        if scroll is None:
            scroll = window._left_scroll
            kind = "horizontal_scrollbar"
            widget = "_left_scroll"
        bar = scroll.horizontalScrollBar()
        content = scroll.widget()
        content_width = content.minimumSizeHint().width() if content is not None else 0
        viewport_width = scroll.viewport().width()
        if (
            bar.maximum() != 0
            or bar.isVisible()
            or content_width > viewport_width
            or content_width > window.width()
        ):
            issues.append(
                _issue(
                    kind,
                    scenario,
                    widget,
                    "config rail overflows horizontally after splitter clamp",
                    maximum=int(bar.maximum()),
                    visible=bool(bar.isVisible()),
                    content_width=int(content_width),
                    viewport_width=int(viewport_width),
                )
            )
    return issues


def _workbench_visual_contract_issues(window: Any, scenarios: list[ScreenScenario]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    for scenario in scenarios:
        _apply_screen_scenario(window, scenario)
        QApplication.processEvents()
        _force_smallest_left_splitter(window)
        for issue in visual_contract_issues(window):
            widget = str(issue.get("widget", "workbench"))
            kind = str(issue.get("kind", "visual_contract"))
            issues.append(
                _issue(
                    kind,
                    scenario,
                    widget,
                    f"visual workbench contract issue: {kind}",
                    contract_issue=issue,
                )
            )
    return issues


def _configure_root_scrollbar_scenario(window: Any, root_mode: str) -> None:
    window.mode_combo.setCurrentIndex(_combo_index_for_data(window.mode_combo, "root_solving"))
    window.root_mode_combo.setCurrentIndex(_combo_index_for_data(window.root_mode_combo, root_mode))
    if root_mode == "system":
        window.root_equations_edit.setPlainText("x + y - 3\nx - y - 1")
        window.root_unknowns_table.set_rows(
            [
                {"name": "x", "initial": "2", "lower": "0", "upper": "4"},
                {"name": "y", "initial": "1", "lower": "0", "upper": "4"},
            ]
        )
    elif root_mode == "scan_multiple":
        window.root_equations_edit.setPlainText("x^2-A")
        window.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "-2", "upper": "2"}])
        window.generate_plots_checkbox.setChecked(True)
        window._update_result_plot(PNG_1X1)
        window.tabs.setCurrentIndex(window.result_tab_index)
        window.result_tabs.setCurrentIndex(window.result_tabs.indexOf(window.result_plot_scroll.parentWidget()))
    else:
        window.root_equations_edit.setPlainText("x^2-A")
        window.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "", "upper": ""}])


def _force_smallest_left_splitter(window: Any) -> None:
    window._refresh_main_splitter_left_min_width()
    splitter = window._main_splitter
    if splitter.count() >= 3:
        splitter.setSizes([1, max(1, window.width() - 321), 320])
    else:
        splitter.setSizes([1, max(1, window.width() - 1)])
    QApplication.processEvents()
    window._refresh_main_splitter_left_min_width()
    QApplication.processEvents()


def _workspace_result_round_trip_ok(window: Any) -> bool:
    window._set_result_text("| root | value |\n|---|---|\n| x | 1.414 |")
    window.log_edit.setPlainText("scan restore check")
    window.latex_edit.setPlainText("\\begin{table}\\end{table}")
    window._set_csv_data([{"root": "x", "value": "1.414"}], ["root", "value"], "root.csv")
    window.result_plot_bytes = PNG_1X1
    bundle = _capture_workspace(window, title="gui schema scan")

    restored = _create_window()
    try:
        _restore_workspace(restored, bundle.manifest, bundle.attachments)
        QApplication.processEvents()
        return (
            "1.414" in restored.result_edit.toPlainText()
            and restored.log_edit.toPlainText() == "scan restore check"
            and restored.result_plot_bytes == PNG_1X1
            and window.result_plot_bytes == PNG_1X1
        )
    finally:
        restored.deleteLater()


def _root_plot_display_ok(window: Any) -> bool:
    label = getattr(window, "result_plot_label", None)
    update_result_plot = getattr(window, "_update_result_plot", None)
    if label is None or update_result_plot is None:
        return False
    try:
        update_result_plot(PNG_1X1)
        QApplication.processEvents()
    except Exception:
        return False
    pixmap = label.pixmap()
    return bool(window.result_plot_bytes == PNG_1X1 and pixmap is not None and not pixmap.isNull())


def _widget_name(widget: Any) -> str:
    name = widget.objectName()
    if name:
        return str(name)
    schema_key = widget.property("datalab_schema_key") if hasattr(widget, "property") else None
    if schema_key:
        return str(schema_key)
    return widget.__class__.__name__


def _append_inventory_item(items: list[dict[str, str]], kind: str, widget: Any, text: str) -> None:
    if text:
        items.append({"kind": kind, "widget": _widget_name(widget), "text": str(text)})


def _visible_text_inventory(window: Any) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for label in window.findChildren(QLabel):
        if label.isVisible():
            _append_inventory_item(items, "label", label, label.text())
            _append_inventory_item(items, "tooltip", label, label.toolTip())
    for button in window.findChildren(QAbstractButton):
        if button.isVisible():
            _append_inventory_item(items, "button", button, button.text())
            _append_inventory_item(items, "tooltip", button, button.toolTip())
    for action in window.findChildren(QAction):
        if action.isVisible():
            _append_inventory_item(items, "action", action, action.text())
            _append_inventory_item(items, "tooltip", action, action.toolTip())
    for tabs in window.findChildren(QTabWidget):
        if tabs.isVisible():
            for index in range(tabs.count()):
                text = tabs.tabText(index)
                if text:
                    items.append({"kind": "tab", "widget": _widget_name(tabs), "text": str(text)})
                tooltip = tabs.tabToolTip(index)
                if tooltip:
                    items.append({"kind": "tooltip", "widget": _widget_name(tabs), "text": str(tooltip)})
    for widget in window.findChildren(QWidget):
        if not widget.isVisible():
            continue
        placeholder = ""
        if hasattr(widget, "placeholderText"):
            placeholder = str(widget.placeholderText())
        _append_inventory_item(items, "placeholder", widget, placeholder)
        tooltip = str(widget.toolTip()) if hasattr(widget, "toolTip") else ""
        _append_inventory_item(items, "tooltip", widget, tooltip)
    return items


def _is_read_only_result_display(widget: Any) -> bool:
    if isinstance(widget, (QPlainTextEdit, QTextEdit)) and widget.isReadOnly():
        return True
    schema_key = str(widget.property("datalab_schema_key") or "") if hasattr(widget, "property") else ""
    return schema_key.startswith("results.")


def _has_help_affordance(widget: Any) -> bool:
    if getattr(widget, "toolTip", lambda: "")():
        return True
    if getattr(widget, "accessibleDescription", lambda: "")():
        return True
    schema_key = str(widget.property("datalab_schema_key") or "") if hasattr(widget, "property") else ""
    if not schema_key:
        return False
    parent = widget.parentWidget() if hasattr(widget, "parentWidget") else None
    depth = 0
    while parent is not None and depth < 5:
        for button in parent.findChildren(QAbstractButton):
            if button is widget or not button.isVisible():
                continue
            if str(button.property("datalab_schema_key") or "") != schema_key:
                continue
            if getattr(button, "toolTip", lambda: "")() or getattr(button, "accessibleDescription", lambda: "")():
                return True
        parent = parent.parentWidget() if hasattr(parent, "parentWidget") else None
        depth += 1
    return False


def _input_widgets(window: Any) -> list[Any]:
    widgets: list[Any] = []
    widgets.extend(
        line_edit
        for line_edit in window.findChildren(QLineEdit)
        if not isinstance(line_edit.parentWidget(), QAbstractSpinBox)
    )
    widgets.extend(window.findChildren(QPlainTextEdit))
    widgets.extend(window.findChildren(QTextEdit))
    widgets.extend(window.findChildren(QComboBox))
    widgets.extend(window.findChildren(QAbstractSpinBox))
    widgets.extend(
        table
        for table in window.findChildren(QTableWidget)
        if table.editTriggers() != QAbstractItemView.EditTrigger.NoEditTriggers
    )
    widgets.extend(button for button in window.findChildren(QAbstractButton) if button.isCheckable())
    return widgets


def _missing_help_affordances(window: Any, scenario: ScreenScenario) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen: set[int] = set()
    for widget in _input_widgets(window):
        widget_id = id(widget)
        if widget_id in seen:
            continue
        seen.add(widget_id)
        if not widget.isVisible() or _is_read_only_result_display(widget):
            continue
        if _has_help_affordance(widget):
            continue
        issues.append(
            _issue(
                "missing_help_affordance",
                scenario,
                _widget_name(widget),
                "visible user-input control lacks tooltip, accessible description, or adjacent help button",
                class_name=widget.__class__.__name__,
            )
        )
    return issues


def _legacy_language_issues(window: Any, lang: str) -> list[dict[str, Any]]:
    scenario = ScreenScenario(key=f"{lang}:legacy", language=lang, mode=str(window.mode_combo.currentData() or ""))
    issues: list[dict[str, Any]] = []
    if not window.root_equations_help_button.toolTip():
        issues.append(
            _issue("missing_tooltip", scenario, "root_equations_help_button", "root equations help tooltip missing")
        )
    if not window.root_formula_preview_button.toolTip():
        issues.append(
            _issue(
                "missing_tooltip",
                scenario,
                "root_formula_preview_button",
                "root formula preview tooltip missing",
            )
        )
    if _find_unbound_required_widgets(window.root_box):
        issues.append(_issue("schema_binding", scenario, "root_box", "root box has unbound required schema widgets"))
    if _find_unbound_required_widgets(window.options_box):
        issues.append(
            _issue("schema_binding", scenario, "options_box", "options box has unbound required schema widgets")
        )
    return issues


def scan_window(window: Any, *, refresh_language: bool = True, strict: bool = False) -> dict[str, Any]:
    structured_issues: list[dict[str, Any]] = []
    if hasattr(window, "show") and not window.isVisible():
        window.show()
        QApplication.processEvents()
    languages = ("zh", "en") if refresh_language else ("current",)
    scenarios = _screen_scenarios(refresh_language=refresh_language)
    text_inventory: list[dict[str, str]] = []
    for lang in languages:
        if refresh_language:
            window._apply_language(lang)
            QApplication.processEvents()
        structured_issues.extend(_legacy_language_issues(window, lang))

    layout_issues = _horizontal_scrollbar_issues(window, scenarios)
    structured_issues.extend(layout_issues)
    left_ok = not layout_issues
    structured_issues.extend(_workbench_visual_contract_issues(window, scenarios))

    help_issues: list[dict[str, Any]] = []
    if strict:
        for scenario in scenarios:
            _apply_screen_scenario(window, scenario)
            text_inventory.extend(_visible_text_inventory(window))
            help_issues.extend(_missing_help_affordances(window, scenario))
        structured_issues.extend(help_issues)

    root_plot_display = _root_plot_display_ok(window)
    if not root_plot_display:
        structured_issues.append(
            _issue(
                "root_plot_display",
                None,
                "result_plot_label",
                "root plot display failed to render PNG through result image widget",
            )
        )

    workspace_result_restore = _workspace_result_round_trip_ok(window)
    if not workspace_result_restore:
        structured_issues.append(
            _issue(
                "workspace_result_restore",
                None,
                "workspace",
                "workspace result snapshot failed capture/restore round trip",
            )
        )

    issues: list[dict[str, Any]] | list[str]
    if strict:
        issues = structured_issues
    else:
        issues = [_issue_to_legacy_text(issue) for issue in structured_issues]

    return {
        "issues": issues,
        "structured_issues": structured_issues,
        "checks": {
            "languages": ["zh", "en"],
            "scenario_count": len(scenarios),
            "scenario_widths": list(SCAN_WIDTHS),
            "strict": strict,
            "left_panel_no_horizontal_scrollbar": left_ok,
            "root_plot_display": root_plot_display,
            "workspace_result_restore": workspace_result_restore,
            "visible_text_inventory_count": len(text_inventory),
            "missing_help_affordance_count": len(help_issues),
        },
    }


def main() -> int:
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        app = QApplication([])
    window = _create_window()
    window.resize(1400, 900)
    window.show()
    QApplication.processEvents()
    report = scan_window(window)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
