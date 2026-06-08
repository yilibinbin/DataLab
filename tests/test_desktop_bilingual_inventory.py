from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTabBar,
    QTableWidget,
    QTextEdit,
    QWidget,
)

from tools.scan_desktop_gui_schema import (
    ROOT_SOLVING_SUBMODES,
    ScreenScenario,
    _apply_screen_scenario,
)


MODES = ("extrapolation", "error", "fitting", "root_solving", "statistics")
TECHNICAL_TEXT_ALLOWLIST = {
    "",
    "?",
    "+",
    "-",
    "...",
    "A",
    "B",
    "C",
    "CSV",
    "PDF",
    "PNG",
    "SVG",
    "LaTeX",
    "Markdown",
    "HTML",
    "JSON",
    "UTF-8",
    "SciPy",
    "mpmath",
    "Monte Carlo",
    "Levin u-transform",
    "Brent",
    "Newton",
    "Halley",
    "Muller",
    "Secant",
    "Ridder",
    "Bisection",
    "Levenberg-Marquardt",
    "Nelder-Mead",
    "BFGS",
    "Powell",
    "emcee",
    "Auto",
    "auto",
    "adaptive",
    "deterministic",
    "parallel",
    "DataLab",
    "sequential",
    "fork",
    "spawn",
    "forkserver",
    "thread",
    "process",
    "threads",
    "processes",
    "x",
    "y",
    "u",
    "p",
    "n",
    "0 = auto",
    "blank=random",
    "None",
    "Chinese",
    "English",
    "pdflatex",
    "xelatex",
    "tectonic",
}
TECHNICAL_TEXT_PATTERNS = (
    re.compile(r"^[A-Z](?:, [A-Z])*$"),
    re.compile(r"^[a-z](?:, [a-z])*$"),
    re.compile(r"^[0-9.eE+\-*/^_ ()\[\],=]+$"),
    re.compile(r"^[-+*/^=<>()[\]{}.,:;|\\%]+$"),
)


@dataclass(frozen=True)
class InventoryItem:
    language: str
    scenario_key: str
    scenario_axis: tuple[str, str, str]
    widget_id: int
    widget_name: str
    kind: str
    role: str
    text: str


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("&&", "&").replace("&", "")).strip()


def _is_technical_text(text: str) -> bool:
    normalized = _normalize_text(text)
    if normalized in TECHNICAL_TEXT_ALLOWLIST:
        return True
    return any(pattern.fullmatch(normalized) for pattern in TECHNICAL_TEXT_PATTERNS)


def _widget_name(widget: Any) -> str:
    schema_key = widget.property("datalab_schema_key") if hasattr(widget, "property") else None
    if schema_key:
        return str(schema_key)
    object_name = widget.objectName() if hasattr(widget, "objectName") else ""
    if object_name:
        return str(object_name)
    accessible_name = widget.accessibleName() if hasattr(widget, "accessibleName") else ""
    if accessible_name:
        return str(accessible_name)
    return widget.__class__.__name__


def _append(
    items: list[InventoryItem],
    *,
    scenario: ScreenScenario,
    widget: Any,
    kind: str,
    role: str,
    text: str,
    identity_suffix: int = 0,
) -> None:
    normalized = _normalize_text(text)
    if not normalized:
        return
    items.append(
        InventoryItem(
            language=scenario.language,
            scenario_key=scenario.key,
            scenario_axis=(scenario.mode, scenario.root_mode, scenario.result_tab),
            widget_id=(id(widget) * 1000) + identity_suffix,
            widget_name=_widget_name(widget),
            kind=kind,
            role=role,
            text=normalized,
        )
    )


def _visible_text_inventory(window: Any, scenario: ScreenScenario) -> list[InventoryItem]:
    items: list[InventoryItem] = []
    for label in window.findChildren(QLabel):
        if label.isVisible():
            _append(items, scenario=scenario, widget=label, kind="QLabel", role="text", text=label.text())
            _append(items, scenario=scenario, widget=label, kind="QLabel", role="tooltip", text=label.toolTip())
    for button in window.findChildren(QPushButton):
        if button.isVisible():
            _append(items, scenario=scenario, widget=button, kind="QPushButton", role="text", text=button.text())
            _append(items, scenario=scenario, widget=button, kind="QPushButton", role="tooltip", text=button.toolTip())
    for checkbox in window.findChildren(QCheckBox):
        if checkbox.isVisible():
            _append(items, scenario=scenario, widget=checkbox, kind="QCheckBox", role="text", text=checkbox.text())
            _append(
                items,
                scenario=scenario,
                widget=checkbox,
                kind="QCheckBox",
                role="tooltip",
                text=checkbox.toolTip(),
            )
    for action in window.findChildren(QAction):
        if action.isVisible():
            _append(items, scenario=scenario, widget=action, kind="QAction", role="text", text=action.text())
            _append(items, scenario=scenario, widget=action, kind="QAction", role="tooltip", text=action.toolTip())
    for tab_bar in window.findChildren(QTabBar):
        if tab_bar.isVisible():
            for index in range(tab_bar.count()):
                _append(
                    items,
                    scenario=scenario,
                    widget=tab_bar,
                    kind="QTabBar",
                    role=f"tab:{index}",
                    text=tab_bar.tabText(index),
                    identity_suffix=index,
                )
                _append(
                    items,
                    scenario=scenario,
                    widget=tab_bar,
                    kind="QTabBar",
                    role=f"tab_tooltip:{index}",
                    text=tab_bar.tabToolTip(index),
                    identity_suffix=100 + index,
                )
    for line_edit in window.findChildren(QLineEdit):
        if line_edit.isVisible() and not _has_ancestor(line_edit, (QAbstractSpinBox, QComboBox)):
            _append(
                items,
                scenario=scenario,
                widget=line_edit,
                kind="QLineEdit",
                role="placeholder",
                text=line_edit.placeholderText(),
            )
            _append(items, scenario=scenario, widget=line_edit, kind="QLineEdit", role="tooltip", text=line_edit.toolTip())
    for text_edit in window.findChildren(QPlainTextEdit):
        if text_edit.isVisible():
            _append(
                items,
                scenario=scenario,
                widget=text_edit,
                kind="QPlainTextEdit",
                role="placeholder",
                text=text_edit.placeholderText(),
            )
            _append(
                items,
                scenario=scenario,
                widget=text_edit,
                kind="QPlainTextEdit",
                role="tooltip",
                text=text_edit.toolTip(),
            )
    for combo in window.findChildren(QComboBox):
        if combo.isVisible():
            _append(items, scenario=scenario, widget=combo, kind="QComboBox", role="tooltip", text=combo.toolTip())
            for index in range(combo.count()):
                _append(
                    items,
                    scenario=scenario,
                    widget=combo,
                    kind="QComboBox",
                    role=f"item:{index}",
                    text=combo.itemText(index),
                    identity_suffix=index,
                )
                tooltip = combo.itemData(index, Qt.ItemDataRole.ToolTipRole)
                if tooltip:
                    _append(
                        items,
                        scenario=scenario,
                        widget=combo,
                        kind="QComboBox",
                        role=f"item_tooltip:{index}",
                        text=str(tooltip),
                        identity_suffix=100 + index,
                    )
    for spinbox in window.findChildren(QAbstractSpinBox):
        if spinbox.isVisible():
            _append(
                items,
                scenario=scenario,
                widget=spinbox,
                kind="QAbstractSpinBox",
                role="tooltip",
                text=spinbox.toolTip(),
            )
            _append(
                items,
                scenario=scenario,
                widget=spinbox,
                kind="QAbstractSpinBox",
                role="prefix",
                text=spinbox.prefix(),
                identity_suffix=1,
            )
            _append(
                items,
                scenario=scenario,
                widget=spinbox,
                kind="QAbstractSpinBox",
                role="suffix",
                text=spinbox.suffix(),
                identity_suffix=2,
            )
    for table in window.findChildren(QTableWidget):
        if table.isVisible():
            _append(items, scenario=scenario, widget=table, kind="QTableWidget", role="tooltip", text=table.toolTip())
            for column in range(table.columnCount()):
                header = table.horizontalHeaderItem(column)
                if header is not None:
                    _append(
                        items,
                        scenario=scenario,
                        widget=table,
                        kind="QTableWidget",
                        role=f"horizontal_header:{column}",
                        text=header.text(),
                        identity_suffix=column,
                    )
    return items


def _has_ancestor(widget: QWidget, ancestor_types: tuple[type[Any], ...]) -> bool:
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, ancestor_types):
            return True
        parent = parent.parentWidget()
    return False


def _has_direct_affordance(widget: Any) -> bool:
    return bool(
        (hasattr(widget, "toolTip") and _normalize_text(widget.toolTip()))
        or (hasattr(widget, "accessibleDescription") and _normalize_text(widget.accessibleDescription()))
    )


def _nearby_schema_help_button(widget: Any) -> bool:
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
            if _has_direct_affordance(button):
                return True
        parent = parent.parentWidget()
        depth += 1
    return False


def _is_read_only_result_display(widget: Any) -> bool:
    schema_key = str(widget.property("datalab_schema_key") or "") if hasattr(widget, "property") else ""
    if schema_key.startswith("results."):
        return True
    return isinstance(widget, (QPlainTextEdit, QTextEdit)) and widget.isReadOnly()


def _visible_user_input_controls(window: Any) -> list[Any]:
    controls: list[Any] = []
    controls.extend(
        line_edit
        for line_edit in window.findChildren(QLineEdit)
        if line_edit.isVisible() and not _has_ancestor(line_edit, (QAbstractSpinBox, QComboBox))
    )
    controls.extend(text_edit for text_edit in window.findChildren(QPlainTextEdit) if text_edit.isVisible())
    controls.extend(text_edit for text_edit in window.findChildren(QTextEdit) if text_edit.isVisible())
    controls.extend(combo for combo in window.findChildren(QComboBox) if combo.isVisible())
    controls.extend(spin for spin in window.findChildren(QAbstractSpinBox) if spin.isVisible())
    controls.extend(
        table
        for table in window.findChildren(QTableWidget)
        if table.isVisible() and table.editTriggers() != QAbstractItemView.EditTrigger.NoEditTriggers
    )
    controls.extend(checkbox for checkbox in window.findChildren(QCheckBox) if checkbox.isVisible())
    return controls


def _missing_affordances(window: Any, scenario: ScreenScenario) -> list[str]:
    missing: list[str] = []
    seen: set[int] = set()
    for control in _visible_user_input_controls(window):
        if id(control) in seen:
            continue
        seen.add(id(control))
        if _is_read_only_result_display(control):
            continue
        if (
            _has_direct_affordance(control)
            or _nearby_schema_help_button(control)
        ):
            continue
        missing.append(
            f"{scenario.key}: {_widget_name(control)} ({control.__class__.__name__}) lacks tooltip, "
            "accessibility description, or same-schema help button"
        )
    return missing


def _result_tabs(window: Any) -> tuple[str, ...]:
    indices = getattr(window, "result_tabs_indices", {})
    if indices:
        return tuple(str(key) for key in indices)
    return ("numeric", "image", "log", "latex", "pdf")


def _scenarios(window: Any) -> list[ScreenScenario]:
    result_tabs = _result_tabs(window)
    scenarios: list[ScreenScenario] = []
    for language in ("zh", "en"):
        for mode in MODES:
            root_modes = ROOT_SOLVING_SUBMODES if mode == "root_solving" else ("",)
            for root_mode in root_modes:
                for result_tab in result_tabs:
                    scenarios.append(
                        ScreenScenario(
                            key=":".join(part for part in (language, mode, root_mode, result_tab) if part),
                            language=language,
                            mode=mode,
                            root_mode=root_mode,
                            result_tab=result_tab,
                            width=1400,
                            height=900,
                        )
                    )
    return scenarios


def _unchanged_bilingual_texts(items: list[InventoryItem]) -> list[str]:
    grouped: dict[tuple[tuple[str, str, str], int, str, str], dict[str, InventoryItem]] = {}
    for item in items:
        key = (item.scenario_axis, item.widget_id, item.kind, item.role)
        grouped.setdefault(key, {})[item.language] = item

    failures: list[str] = []
    for by_language in grouped.values():
        zh = by_language.get("zh")
        en = by_language.get("en")
        if zh is None or en is None:
            continue
        if zh.text != en.text or _is_technical_text(zh.text):
            continue
        failures.append(
            f"{zh.scenario_axis}: {zh.widget_name} {zh.kind}.{zh.role} remains {zh.text!r} in zh/en"
        )
    return sorted(set(failures))


def test_desktop_runtime_bilingual_inventory_and_accessibility_gate(qtbot: Any) -> None:
    from app_desktop.window import ExtrapolationWindow

    app = QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    window.resize(1400, 900)
    window.show()
    app.processEvents()

    inventory: list[InventoryItem] = []
    missing_affordances: list[str] = []
    visited: set[tuple[str, str, str, str]] = set()
    try:
        scenarios = _scenarios(window)
        assert {"numeric", "image", "log", "latex", "pdf"} <= set(_result_tabs(window))
        for scenario in scenarios:
            _apply_screen_scenario(window, scenario)
            app.processEvents()
            visited.add((scenario.language, scenario.mode, scenario.root_mode, scenario.result_tab))
            inventory.extend(_visible_text_inventory(window, scenario))
            missing_affordances.extend(_missing_affordances(window, scenario))
    finally:
        window.deleteLater()

    assert len(visited) == len(scenarios)
    assert {item.language for item in inventory} == {"zh", "en"}
    assert {item.kind for item in inventory}.issuperset(
        {
            "QLabel",
            "QPushButton",
            "QCheckBox",
            "QAction",
            "QTabBar",
            "QLineEdit",
            "QPlainTextEdit",
            "QComboBox",
            "QAbstractSpinBox",
            "QTableWidget",
        }
    )

    assert sorted(set(missing_affordances)) == []
    assert _unchanged_bilingual_texts(inventory) == []
