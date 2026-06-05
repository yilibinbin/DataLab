from __future__ import annotations

import base64
from importlib import import_module
import json
import os
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


MODES = ("extrapolation", "error", "fitting", "root_solving", "statistics")
ROOT_SOLVING_SUBMODES = ("scalar", "scan_multiple", "polynomial", "system")
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4////fwAJ+wP9KobjigAAAABJRU5ErkJggg=="
)


def _combo_index_for_data(combo: Any, data: object) -> int:
    index = combo.findData(data)
    if index < 0:
        raise AssertionError(f"missing combo data {data!r}")
    return int(index)


def _find_unbound_required_widgets(root: Any) -> list[Any]:
    finder = cast(Any, import_module("app_desktop.ui_schema_binder").find_unbound_required_widgets)
    return cast(list[Any], finder(root))


def _capture_workspace(window: Any, *, title: str) -> Any:
    capture = cast(Any, import_module("app_desktop.workspace_controller").capture_workspace)
    return capture(window, title=title)


def _restore_workspace(window: Any, manifest: dict[str, Any], attachments: dict[str, bytes]) -> None:
    restore = cast(Any, import_module("app_desktop.workspace_controller").restore_workspace)
    restore(window, manifest, attachments)


def _create_window() -> Any:
    window_cls = cast(Any, import_module("app_desktop.window").ExtrapolationWindow)
    return window_cls()


def _has_no_horizontal_scrollbar(window: Any) -> bool:
    for scenario in _left_panel_scrollbar_scenarios(window):
        scenario()
        QApplication.processEvents()
        _force_smallest_left_splitter(window)
        bar = window._left_scroll.horizontalScrollBar()
        if bar.maximum() != 0 or bar.isVisible():
            return False
    return True


def _left_panel_scrollbar_scenarios(window: Any) -> list[Any]:
    scenarios: list[Any] = []

    def main_mode(mode: str) -> Any:
        def apply() -> None:
            window.mode_combo.setCurrentIndex(_combo_index_for_data(window.mode_combo, mode))

        return apply

    scenarios.extend(main_mode(mode) for mode in MODES if mode != "root_solving")

    for root_mode in ROOT_SOLVING_SUBMODES:
        scenarios.append(lambda root_mode=root_mode: _configure_root_scrollbar_scenario(window, root_mode))
    return scenarios


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
    window._main_splitter.setSizes([1, max(1, window.width() - 1)])
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


def scan_window(window: Any, *, refresh_language: bool = True) -> dict[str, Any]:
    issues: list[str] = []
    languages = ("zh", "en") if refresh_language else ("current",)
    for lang in languages:
        if refresh_language:
            window._apply_language(lang)
            QApplication.processEvents()
        if not window.root_equations_help_button.toolTip():
            issues.append(f"{lang}: root equations help tooltip missing")
        if not window.root_formula_preview_button.toolTip():
            issues.append(f"{lang}: root formula preview tooltip missing")
        if _find_unbound_required_widgets(window.root_box):
            issues.append(f"{lang}: root box has unbound required schema widgets")
        if _find_unbound_required_widgets(window.options_box):
            issues.append(f"{lang}: options box has unbound required schema widgets")

    left_ok = _has_no_horizontal_scrollbar(window)
    if not left_ok:
        issues.append("left panel horizontal scrollbar is visible after splitter clamp")

    root_plot_display = _root_plot_display_ok(window)
    if not root_plot_display:
        issues.append("root plot display failed to render PNG through result image widget")

    workspace_result_restore = _workspace_result_round_trip_ok(window)
    if not workspace_result_restore:
        issues.append("workspace result snapshot failed capture/restore round trip")

    return {
        "issues": issues,
        "checks": {
            "languages": ["zh", "en"],
            "left_panel_no_horizontal_scrollbar": left_ok,
            "root_plot_display": root_plot_display,
            "workspace_result_restore": workspace_result_restore,
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
