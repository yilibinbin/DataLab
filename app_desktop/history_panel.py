"""Compact desktop history panel for the result rail."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from datalab_core.history import HistoryEntry, HistoryStore, HistoryValidationError, history_store_from_json
from datalab_core.history_compare import build_history_comparison

from app_desktop.budget_panel import build_budget_dashboard_for_history_entry
from app_desktop.history_compare_panel import (
    build_history_comparison_display,
    history_compare_selection_diagnostic,
    is_displayable_history_comparison,
)
from app_desktop.report_bundle_export import default_report_bundle_filename, write_history_entry_report_bundle
from app_desktop.theme import REGION_RADIUS, is_dark_theme
from app_desktop.workspace_controller import restore_history_entry_result

_ROLE_ENTRY_ID = int(Qt.ItemDataRole.UserRole)
_ROLE_IS_CURRENT = int(Qt.ItemDataRole.UserRole) + 1


class HistoryPanel(QWidget):
    def __init__(self, owner: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._owner = owner
        self.setObjectName("workbench_history_panel")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setStyleSheet(_history_panel_style())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(5)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel(self._tr("历史", "History"))
        self.title_label.setObjectName("workbench_history_title")
        title_row.addWidget(self.title_label, 1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("workbench_history_count")
        title_row.addWidget(self.count_label, 0)
        layout.addLayout(title_row)

        self.entry_list = QListWidget()
        self.entry_list.setObjectName("workbench_history_list")
        self.entry_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.entry_list.setMaximumHeight(118)
        self.entry_list.setUniformItemSizes(False)
        self.entry_list.currentItemChanged.connect(lambda *_args: self._refresh_actions())
        layout.addWidget(self.entry_list)

        first_button_row = QHBoxLayout()
        first_button_row.setContentsMargins(0, 0, 0, 0)
        first_button_row.setSpacing(4)
        second_button_row = QHBoxLayout()
        second_button_row.setContentsMargins(0, 0, 0, 0)
        second_button_row.setSpacing(4)
        third_button_row = QHBoxLayout()
        third_button_row.setContentsMargins(0, 0, 0, 0)
        third_button_row.setSpacing(4)
        self.restore_button = QPushButton(self._tr("恢复", "Restore"))
        self.compare_button = QPushButton(self._tr("比较", "Compare"))
        self.budget_button = QPushButton(self._tr("预算", "Budget"))
        self.rename_button = QPushButton(self._tr("重命名", "Rename"))
        self.pin_button = QPushButton(self._tr("固定", "Pin"))
        self.delete_button = QPushButton(self._tr("删除", "Delete"))
        for button in (
            self.restore_button,
            self.compare_button,
            self.budget_button,
            self.rename_button,
            self.pin_button,
            self.delete_button,
        ):
            button.setMinimumWidth(0)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        first_button_row.addWidget(self.restore_button)
        first_button_row.addWidget(self.compare_button)
        second_button_row.addWidget(self.budget_button)
        second_button_row.addWidget(self.rename_button)
        third_button_row.addWidget(self.pin_button)
        third_button_row.addWidget(self.delete_button)
        layout.addLayout(first_button_row)
        layout.addLayout(second_button_row)
        layout.addLayout(third_button_row)

        export_row = QHBoxLayout()
        export_row.setContentsMargins(0, 0, 0, 0)
        self.export_button = QPushButton(self._tr("导出到报告", "Export to report"))
        self.export_button.setObjectName("workbench_history_export_button")
        export_row.addWidget(self.export_button)
        layout.addLayout(export_row)

        self.message_label = QLabel(
            self._tr("选择一条历史记录后可导出报告包。", "Select a history entry to export a report bundle.")
        )
        self.message_label.setObjectName("workbench_history_message")
        self.message_label.setWordWrap(True)
        layout.addWidget(self.message_label)

        self.restore_button.clicked.connect(self.restore_selected)
        self.compare_button.clicked.connect(self.compare_selected)
        self.budget_button.clicked.connect(self.show_budget_selected)
        self.rename_button.clicked.connect(self.rename_selected)
        self.pin_button.clicked.connect(self.toggle_pin_selected)
        self.delete_button.clicked.connect(self.delete_selected)
        self.export_button.clicked.connect(self.export_selected)

        self._register_texts()
        self.refresh()

    def refresh(self) -> None:
        selected = self._selected_ref()
        self.setStyleSheet(_history_panel_style())
        self.entry_list.clear()
        store = self._store()
        rows: list[tuple[HistoryEntry, bool]] = []
        if store.current is not None:
            rows.append((store.current, True))
        rows.extend((entry, False) for entry in store.entries)

        for entry, is_current in rows:
            item = QListWidgetItem(self._entry_text(entry, is_current))
            item.setToolTip(self._entry_tooltip(entry, is_current))
            item.setData(_ROLE_ENTRY_ID, entry.entry_id)
            item.setData(_ROLE_IS_CURRENT, is_current)
            self.entry_list.addItem(item)

        self.count_label.setText(self._count_text(store))
        self.entry_list.setVisible(bool(rows))
        if not rows:
            self.message_label.setText(self._tr("暂无历史记录。", "No history yet."))
        elif (
            not self.message_label.text()
            or self.message_label.property("datalab_history_export_notice")
            or self.message_label.text() in {"暂无历史记录。", "No history yet."}
        ):
            self.message_label.setText(
                self._tr("选择一条历史记录后可导出报告包。", "Select a history entry to export a report bundle.")
            )
        self.message_label.setProperty("datalab_history_export_notice", bool(rows))

        self._restore_selection(selected)
        self._refresh_actions()

    def selected_entry(self) -> HistoryEntry | None:
        selected = self._selected_entry()
        return selected[0] if selected is not None else None

    def rename_selected(self, label: str | None = None) -> bool:
        selected = self._selected_entry()
        if selected is None:
            return False
        entry, is_current = selected
        if label is None:
            label, accepted = QInputDialog.getText(
                self,
                self._tr("重命名历史记录", "Rename history entry"),
                self._tr("名称：", "Name:"),
                text=entry.label,
            )
            if not accepted:
                return False
        label = str(label).strip()
        if not label or label == entry.label:
            return False
        return self._replace_selected(replace(entry, label=label), is_current)

    def toggle_pin_selected(self) -> bool:
        selected = self._selected_entry()
        if selected is None:
            return False
        entry, is_current = selected
        return self._replace_selected(replace(entry, pinned=not entry.pinned), is_current)

    def delete_selected(self) -> bool:
        selected = self._selected_entry()
        if selected is None:
            return False
        entry, is_current = selected
        store = self._store()
        current = None if is_current and store.current is not None and store.current.entry_id == entry.entry_id else store.current
        entries = tuple(item for item in store.entries if item.entry_id != entry.entry_id)
        return self._set_store(HistoryStore(current=current, entries=entries), select=None)

    def restore_selected(self) -> bool:
        selected = self._selected_entry()
        if selected is None:
            return False
        entry, is_current = selected
        before_store = self._store()
        before_store_json = before_store.to_json()
        before_semantic = getattr(self._owner, "_last_result_semantic_snapshot", None)
        before_kind = getattr(self._owner, "_last_result_semantic_snapshot_kind", "")

        restore_history_entry_result(self._owner, entry)

        store_changed = False
        if not is_current:
            restored = before_store.with_current(entry)
            self._owner._workspace_history_store = restored
            self._owner._workspace_history_enabled = True
            store_changed = restored.to_json() != before_store_json

        after_semantic = getattr(self._owner, "_last_result_semantic_snapshot", None)
        after_kind = getattr(self._owner, "_last_result_semantic_snapshot_kind", "")
        display_changed = before_semantic != after_semantic or before_kind != after_kind
        if store_changed or display_changed:
            self._mark_dirty()
        self.refresh()
        return True

    def compare_selected(self) -> bool:
        selected = self._selected_entry()
        entry = selected[0] if selected is not None else None
        is_current = selected[1] if selected is not None else False
        current = self._store().current
        diagnostic = history_compare_selection_diagnostic(
            current,
            entry,
            selected_is_current=is_current,
            language=self._language(),
        )
        if diagnostic is not None:
            self.message_label.setText(diagnostic)
            return False
        if current is None or entry is None:
            return False

        payload = build_history_comparison(
            entry.semantic_snapshot,
            current.semantic_snapshot,
            left_label=entry.label,
            right_label=current.label,
            left_id=entry.entry_id,
            right_id=current.entry_id,
        )
        if not is_displayable_history_comparison(payload):
            self.message_label.setText(
                self._tr("所选历史记录无法比较。", "The selected history entry cannot be compared.")
            )
            return False

        display = build_history_comparison_display(payload, language=self._language())
        return self._show_display_in_results(
            display,
            result_kind="history_comparison",
            success_message=self._tr("历史比较已显示在结果区域。", "History comparison is shown in results."),
        )

    def show_budget_selected(self) -> bool:
        selected = self._selected_entry()
        if selected is None:
            self.message_label.setText(self._tr("请先选择一条历史记录。", "Select a history entry first."))
            return False
        entry, _is_current = selected
        display = build_budget_dashboard_for_history_entry(entry, language=self._language())
        return self._show_display_in_results(
            display,
            result_kind="uncertainty_budget",
            success_message=self._tr("不确定度预算已显示在结果区域。", "Uncertainty budget is shown in results."),
        )

    def _show_display_in_results(self, display: Any, *, result_kind: str, success_message: str) -> bool:
        previous_dirty = getattr(self._owner, "_workspace_dirty", None)
        previous_restoring = getattr(self._owner, "_workspace_restoring", None)
        previous_snapshot_stale = getattr(self._owner, "_workspace_snapshot_stale", None)
        result_edit = getattr(self._owner, "result_edit", None)
        export_csv_btn = getattr(self._owner, "export_csv_btn", None)
        previous_result_state = {
            "_last_result_kind": getattr(self._owner, "_last_result_kind", None),
            "_last_result_payloads": getattr(self._owner, "_last_result_payloads", None),
            "_last_result_semantic_snapshot": getattr(self._owner, "_last_result_semantic_snapshot", None),
            "_last_result_semantic_snapshot_kind": getattr(
                self._owner,
                "_last_result_semantic_snapshot_kind",
                None,
            ),
            "_last_result_text": getattr(self._owner, "_last_result_text", None),
            "_last_result_text_format": getattr(self._owner, "_last_result_text_format", None),
            "_last_result_rendered_text": getattr(self._owner, "_last_result_rendered_text", None),
            "_csv_rows": getattr(self._owner, "_csv_rows", None),
            "_csv_headers": getattr(self._owner, "_csv_headers", None),
            "_csv_suggest_name": getattr(self._owner, "_csv_suggest_name", None),
            "_workbench_result_state": getattr(self._owner, "_workbench_result_state", None),
        }
        result_to_html = getattr(result_edit, "toHtml", None)
        result_to_plain = getattr(result_edit, "toPlainText", None)
        export_is_enabled = getattr(export_csv_btn, "isEnabled", None)
        previous_result_html = result_to_html() if callable(result_to_html) else None
        previous_result_plain = result_to_plain() if callable(result_to_plain) else None
        previous_export_enabled = export_is_enabled() if callable(export_is_enabled) else None
        self._owner._last_result_kind = result_kind
        self._owner._last_result_payloads = {}
        self._owner._last_result_semantic_snapshot = None
        self._owner._last_result_semantic_snapshot_kind = None
        set_result_text = getattr(self._owner, "_set_result_text", None)
        set_csv_data = getattr(self._owner, "_set_csv_data", None)
        if previous_restoring is not None:
            self._owner._workspace_restoring = True
        display_succeeded = False
        try:
            if callable(set_result_text):
                set_result_text(display.text, final_result=True)
            if callable(set_csv_data):
                set_csv_data(
                    display.csv_rows,
                    display.csv_headers,
                    display.suggestion,
                    final_result=True,
                )
            display_succeeded = True
        finally:
            if not display_succeeded:
                for name, value in previous_result_state.items():
                    setattr(self._owner, name, value)
                result_set_html = getattr(result_edit, "setHtml", None)
                result_set_plain = getattr(result_edit, "setPlainText", None)
                export_set_enabled = getattr(export_csv_btn, "setEnabled", None)
                if previous_result_html is not None and callable(result_set_html):
                    result_set_html(previous_result_html)
                elif previous_result_plain is not None and callable(result_set_plain):
                    result_set_plain(previous_result_plain)
                if previous_export_enabled is not None and callable(export_set_enabled):
                    export_set_enabled(previous_export_enabled)
            if previous_restoring is not None:
                self._owner._workspace_restoring = previous_restoring
            if previous_dirty is not None:
                self._owner._workspace_dirty = previous_dirty
            if previous_snapshot_stale is not None:
                self._owner._workspace_snapshot_stale = previous_snapshot_stale
            update_title = getattr(self._owner, "_update_workspace_window_title", None)
            if callable(update_title):
                update_title()
            if not display_succeeded:
                refresher = getattr(self._owner, "refresh_workbench_result_rail", None)
                if callable(refresher):
                    refresher()
        mark_complete = getattr(self._owner, "_mark_workbench_result_complete", None)
        if callable(mark_complete):
            mark_complete()
        refresher = getattr(self._owner, "refresh_workbench_result_rail", None)
        if callable(refresher):
            refresher()
        self.message_label.setText(success_message)
        return True

    def export_selected(self) -> bool:
        selected = self._selected_entry()
        if selected is None:
            self.message_label.setText(self._tr("请先选择一条历史记录。", "Select a history entry first."))
            return False
        entry, _is_current = selected
        filename, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("导出报告包", "Export Report Bundle"),
            default_report_bundle_filename(entry),
            self._tr("DataLab 报告包 (*.datalab-report.zip);;ZIP 文件 (*.zip);;所有文件 (*)", "DataLab Report Bundle (*.datalab-report.zip);;ZIP Files (*.zip);;All Files (*)"),
        )
        if not filename:
            return False
        try:
            target = write_history_entry_report_bundle(
                filename,
                entry,
                owner=self._owner,
                language=self._language(),
            )
        except Exception as exc:
            self.message_label.setText(self._tr(f"报告包导出失败：{exc}", f"Report bundle export failed: {exc}"))
            return False
        self.message_label.setText(self._tr(f"报告包已导出：{target}", f"Report bundle exported: {target}"))
        return True

    def _replace_selected(self, replacement: HistoryEntry, is_current: bool) -> bool:
        store = self._store()
        current = store.current
        if is_current and current is not None and current.entry_id == replacement.entry_id:
            current = replacement
        entries = tuple(replacement if entry.entry_id == replacement.entry_id else entry for entry in store.entries)
        return self._set_store(HistoryStore(current=current, entries=entries), select=(replacement.entry_id, is_current))

    def _set_store(self, store: HistoryStore, *, select: tuple[str, bool] | None) -> bool:
        before = self._store().to_json()
        if store.to_json() == before:
            return False
        self._owner._workspace_history_store = store
        self._owner._workspace_history_enabled = True
        self._mark_dirty()
        self.refresh()
        if select is not None:
            self._select_ref(select)
        return True

    def _store(self) -> HistoryStore:
        history = getattr(self._owner, "_workspace_history_store", None)
        if history is None:
            return HistoryStore()
        if isinstance(history, HistoryStore):
            return history
        if isinstance(history, dict):
            return history_store_from_json(history)
        raise HistoryValidationError("_workspace_history_store must be a HistoryStore or mapping.")

    def _selected_entry(self) -> tuple[HistoryEntry, bool] | None:
        item = self.entry_list.currentItem()
        if item is None:
            return None
        entry_id = str(item.data(_ROLE_ENTRY_ID) or "")
        is_current = bool(item.data(_ROLE_IS_CURRENT))
        store = self._store()
        if is_current and store.current is not None and store.current.entry_id == entry_id:
            return store.current, True
        for entry in store.entries:
            if entry.entry_id == entry_id:
                return entry, False
        return None

    def _selected_ref(self) -> tuple[str, bool] | None:
        item = self.entry_list.currentItem()
        if item is None:
            return None
        return str(item.data(_ROLE_ENTRY_ID) or ""), bool(item.data(_ROLE_IS_CURRENT))

    def _restore_selection(self, selected: tuple[str, bool] | None) -> None:
        if selected is not None and self._select_ref(selected):
            return
        if self.entry_list.count():
            self.entry_list.setCurrentRow(0)

    def _select_ref(self, selected: tuple[str, bool]) -> bool:
        entry_id, is_current = selected
        for index in range(self.entry_list.count()):
            item = self.entry_list.item(index)
            if str(item.data(_ROLE_ENTRY_ID) or "") == entry_id and bool(item.data(_ROLE_IS_CURRENT)) == is_current:
                self.entry_list.setCurrentRow(index)
                return True
        return False

    def _refresh_actions(self) -> None:
        selected = self._selected_entry()
        has_selection = selected is not None
        self.restore_button.setEnabled(has_selection)
        self.rename_button.setEnabled(has_selection)
        self.pin_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection)
        self.export_button.setEnabled(has_selection)
        self.budget_button.setEnabled(has_selection)
        diagnostic = history_compare_selection_diagnostic(
            self._store().current,
            selected[0] if selected is not None else None,
            selected_is_current=selected[1] if selected is not None else False,
            language=self._language(),
        )
        self.compare_button.setEnabled(diagnostic is None)
        self.compare_button.setToolTip(
            diagnostic
            or self._tr(
                "比较当前结果和所选最近历史记录。",
                "Compare the current result with the selected recent history entry.",
            )
        )
        if selected is None:
            self.pin_button.setText(self._tr("固定", "Pin"))
            return
        entry, _is_current = selected
        self.pin_button.setText(self._tr("取消固定", "Unpin") if entry.pinned else self._tr("固定", "Pin"))

    def _entry_text(self, entry: HistoryEntry, is_current: bool) -> str:
        prefix = self._tr("当前", "Current") if is_current else self._tr("最近", "Recent")
        pinned = self._tr("，已固定", ", pinned") if entry.pinned else ""
        title = _compact(entry.label, 34)
        return f"{prefix}: {title}{pinned}"

    def _entry_tooltip(self, entry: HistoryEntry, is_current: bool) -> str:
        state = self._tr("当前结果", "Current result") if is_current else self._tr("历史结果", "History result")
        pin = self._tr("已固定", "Pinned") if entry.pinned else self._tr("未固定", "Not pinned")
        return f"{state}\n{entry.label}\n{entry.family} / {entry.kind}\n{entry.created_at}\n{pin}"

    def _count_text(self, store: HistoryStore) -> str:
        total = (1 if store.current is not None else 0) + len(store.entries)
        pinned = sum(1 for entry in ((store.current,) if store.current is not None else ()) + store.entries if entry.pinned)
        if pinned:
            return self._tr(f"{total} 条 / {pinned} 固定", f"{total} items / {pinned} pinned")
        return self._tr(f"{total} 条", f"{total} items")

    def _register_texts(self) -> None:
        register = getattr(self._owner, "_register_text", None)
        if not callable(register):
            return
        register(self.title_label, "历史", "History")
        register(self.restore_button, "恢复", "Restore")
        register(self.compare_button, "比较", "Compare")
        register(self.budget_button, "预算", "Budget")
        register(self.rename_button, "重命名", "Rename")
        register(self.delete_button, "删除", "Delete")
        register(self.export_button, "导出到报告", "Export to report")
        register(self.restore_button, "从语义快照恢复所选结果。", "Restore the selected result from its semantic snapshot.", "setToolTip")
        register(
            self.compare_button,
            "比较当前结果和所选最近历史记录。",
            "Compare the current result with the selected recent history entry.",
            "setToolTip",
        )
        register(
            self.budget_button,
            "显示所选历史记录的预算和诊断行。",
            "Show budget and diagnostic rows for the selected history entry.",
            "setToolTip",
        )
        register(self.rename_button, "重命名所选历史记录。", "Rename the selected history entry.", "setToolTip")
        register(self.pin_button, "固定或取消固定所选历史记录。", "Pin or unpin the selected history entry.", "setToolTip")
        register(self.delete_button, "删除所选历史记录。", "Delete the selected history entry.", "setToolTip")
        register(
            self.export_button,
            "将所选历史记录导出为自包含报告包。",
            "Export the selected history entry as a self-contained report bundle.",
            "setToolTip",
        )

    def _tr(self, zh: str, en: str) -> str:
        translator = getattr(self._owner, "_tr", None)
        if callable(translator):
            return str(translator(zh, en))
        return en

    def _language(self) -> str:
        current_language = getattr(self._owner, "_current_output_language", None)
        if callable(current_language):
            return str(current_language())
        return "zh" if self._tr("语言", "Language") == "语言" else "en"

    def _mark_dirty(self) -> None:
        marker = getattr(self._owner, "_mark_workspace_dirty", None)
        if callable(marker):
            marker()


def build_history_panel(owner: Any) -> HistoryPanel:
    panel = HistoryPanel(owner)
    owner.workbench_history_panel = panel
    owner.history_panel = panel
    return panel


def _compact(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)] + "…"


def _history_panel_style() -> str:
    dark = is_dark_theme()
    if dark:
        panel_bg = "#20242b"
        field_bg = "#262b34"
        border = "rgba(255, 255, 255, 0.10)"
        title_fg = "#e5e7eb"
        body_fg = "#f8fafc"
        muted_fg = "#a5b4c3"
        selected_bg = "#1f2937"
    else:
        panel_bg = "#ffffff"
        field_bg = "#f8fafc"
        border = "#d0d7de"
        title_fg = "#0f172a"
        body_fg = "#111827"
        muted_fg = "#64748b"
        selected_bg = "#e8f1ff"
    return f"""
QWidget#workbench_history_panel {{
    background: {panel_bg};
    border: 1px solid {border};
    border-radius: {REGION_RADIUS}px;
}}
QLabel#workbench_history_title {{
    color: {title_fg};
    font-weight: 600;
}}
QLabel#workbench_history_count,
QLabel#workbench_history_message {{
    color: {muted_fg};
    font-size: 11px;
}}
QListWidget#workbench_history_list {{
    background: {field_bg};
    color: {body_fg};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 2px;
}}
QListWidget#workbench_history_list::item {{
    padding: 3px 4px;
}}
QListWidget#workbench_history_list::item:selected {{
    background: {selected_bg};
}}
"""
