"""UI construction helpers for `ExtrapolationWindow`.

This module intentionally provides top-level `build_*` functions that accept the
window instance as the first argument (named `self`) and populate widgets on it.
It acts like a function-based mixin extracted from `window.py` to reduce file
size while keeping behavior unchanged.
"""

from __future__ import annotations

import mpmath as mp

from PySide6.QtCore import Qt, QSize, QObject, QEvent
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from data_extrapolation_latex_latest import DEFAULT_THREE_POINT_FORMULA
from fitting.auto_models import AUTO_MODELS
from formula_help import (
    EXTRAPOLATION_METHODS,
    get_function_help,
    get_function_tooltip,
    get_method_description,
    get_method_name,
    get_method_parameters,
)
from shared.ui_specs import (
    CUSTOM_FORMULA_PARAMS,
    EXTRAPOLATION_METHOD_SPECS,
    LEVIN_U_PARAMS,
    METHOD_HELP_BUTTON,
    POWER_LAW_PARAMS,
    RICHARDSON_PARAMS,
    get_method_options,
    get_parameter_visibility_rules,
)
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS

_LANG_ZH = "zh"
_LANG_EN = "en"
_LANG_AUTO = "auto"

_REFCOL_AUTO_MAX_DIFF_KEY = "auto_max_diff"
_REFCOL_AUTO_MAX_DIFF_ZH = "最大差异列"
_REFCOL_AUTO_MAX_DIFF_EN = "Max-diff column"

# Stack-page indices for the two QStackedWidgets used by the left panel (the
# data table / manual editor, and the constants table / text editor). Both
# stacks share the same convention: table view on page 0, free-form text on
# page 1. Centralised here so the toggle helpers and the worker-facing
# serialiser agree on the mapping.
_STACK_PAGE_TABLE = 0
_STACK_PAGE_TEXT = 1


def _apply_equal_column_stretch(table: QTableWidget) -> None:
    """Make every column share the table width equally.

    ``setStretchLastSection(True)`` only stretches the last column —
    after the user adds / removes rows or columns, the leading
    columns retain their default narrow width and the table looks
    lopsided. ``QHeaderView.Stretch`` resize-mode for *all* sections
    distributes the available width evenly, which is what users
    expect from a CSV-style data grid. Re-apply this after any
    ``setColumnCount`` change because Qt resets the resize mode for
    new columns to the header default (Interactive).
    """
    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Stretch)
    # Stretch already fills the table width; the legacy
    # ``setStretchLastSection`` flag is now redundant and would
    # otherwise interact oddly with Stretch mode.
    header.setStretchLastSection(False)

# --- Theme-aware stylesheets ---

# Thin overlay scrollbar — fades to near-invisible when idle
_SCROLLBAR_DARK = """
QScrollBar:vertical, QScrollBar:horizontal {
    background: transparent;
    border: none;
}
QScrollBar:vertical { width: 6px; }
QScrollBar:horizontal { height: 6px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: rgba(255, 255, 255, 0.12);
    border-radius: 3px;
    min-height: 24px; min-width: 24px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: rgba(255, 255, 255, 0.25);
}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
    height: 0px; width: 0px;
}
"""

_SCROLLBAR_LIGHT = """
QScrollBar:vertical, QScrollBar:horizontal {
    background: transparent;
    border: none;
}
QScrollBar:vertical { width: 6px; }
QScrollBar:horizontal { height: 6px; }
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: rgba(0, 0, 0, 0.12);
    border-radius: 3px;
    min-height: 24px; min-width: 24px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: rgba(0, 0, 0, 0.28);
}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
    height: 0px; width: 0px;
}
"""

_TABLE_STYLE_DARK = """
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

_TABLE_STYLE_LIGHT = """
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

_RESULT_STYLE_DARK = """
QTextBrowser {
    background-color: #2b2d30; color: #dfe1e5;
    font-size: 14px; border: none; padding: 10px 12px;
    selection-background-color: #2d5a88; selection-color: #ffffff;
}
"""

_RESULT_STYLE_LIGHT = """
QTextBrowser {
    background-color: #ffffff; color: #1f2328;
    font-size: 14px; border: none; padding: 10px 12px;
    selection-background-color: #dbeafe; selection-color: #1f2328;
}
"""


def _is_dark_theme() -> bool:
    """Detect whether the current system appearance is dark."""
    app = QApplication.instance()
    if app is None:
        return True
    palette = app.palette()
    return palette.window().color().lightness() < 128


def _get_table_style() -> str:
    dark = _is_dark_theme()
    return (_TABLE_STYLE_DARK if dark else _TABLE_STYLE_LIGHT) + (_SCROLLBAR_DARK if dark else _SCROLLBAR_LIGHT)


def _get_result_style() -> str:
    dark = _is_dark_theme()
    return (_RESULT_STYLE_DARK if dark else _RESULT_STYLE_LIGHT) + (_SCROLLBAR_DARK if dark else _SCROLLBAR_LIGHT)

def build_menu(self):
    menubar = self.menuBar()

    lang_menu = menubar.addMenu("语言")
    self._register_text(lang_menu, "语言", "Language", "setTitle")
    action_lang_auto = QAction("自动", self)
    action_lang_auto.triggered.connect(lambda: self._on_language_change(0))
    lang_menu.addAction(action_lang_auto)
    self._register_text(action_lang_auto, "自动", "Auto", "setText")
    action_lang_zh = QAction("中文", self)
    action_lang_zh.triggered.connect(lambda: self._on_language_change(1))
    lang_menu.addAction(action_lang_zh)
    self._register_text(action_lang_zh, "中文", "Chinese", "setText")
    action_lang_en = QAction("English", self)
    action_lang_en.triggered.connect(lambda: self._on_language_change(2))
    lang_menu.addAction(action_lang_en)
    self._register_text(action_lang_en, "English", "English", "setText")

    help_menu = menubar.addMenu("帮助")
    self._register_text(help_menu, "帮助", "Help", "setTitle")

    project_action = QAction("项目主页", self)
    project_action.setMenuRole(QAction.NoRole)
    project_action.triggered.connect(self._open_project_homepage)
    help_menu.addAction(project_action)
    self._register_text(project_action, "项目主页", "Project Homepage", "setText")

    update_action = QAction("检查更新", self)
    update_action.setMenuRole(QAction.NoRole)
    update_action.triggered.connect(self._check_for_updates)
    help_menu.addAction(update_action)
    self._register_text(update_action, "检查更新", "Check for Updates", "setText")

    help_menu.addSeparator()

    docs_action = QAction("文档", self)
    docs_action.setMenuRole(QAction.NoRole)
    docs_action.triggered.connect(self._show_docs)
    help_menu.addAction(docs_action)
    self._register_text(docs_action, "文档", "Documentation", "setText")

    help_menu.addSeparator()
    help_action = QAction("使用说明", self)
    help_action.setMenuRole(QAction.NoRole)
    help_action.triggered.connect(self._show_help)
    help_menu.addAction(help_action)
    self._register_text(help_action, "使用说明", "Help", "setText")
    about_action = QAction("关于", self)
    about_action.setMenuRole(QAction.NoRole)
    about_action.triggered.connect(self._show_about)
    help_menu.addAction(about_action)
    self._register_text(about_action, "关于", "About", "setText")

def build_ui(self):
    central = QWidget(self)
    self.setCentralWidget(central)
    layout = QVBoxLayout(central)
    splitter = QSplitter(Qt.Horizontal, self)
    splitter.setHandleWidth(8)
    splitter.setChildrenCollapsible(False)
    # Expose as an instance attribute so the close handler and the
    # QSettings restore path in ``main.py`` can reach it. Previously the
    # splitter was purely local and its geometry was lost on every close.
    self._main_splitter = splitter
    layout.addWidget(splitter)

    left_scroll = QScrollArea()
    left_scroll.setWidgetResizable(True)
    left_container = QWidget()
    self.left_container = left_container
    self.left_layout = QVBoxLayout(left_container)
    self.left_layout.setAlignment(Qt.AlignTop)
    left_scroll.setWidget(left_container)
    splitter.addWidget(left_scroll)

    right_container = QWidget()
    right_layout = QVBoxLayout(right_container)
    splitter.addWidget(right_container)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([520, 820])

    self._build_left_panel()
    # Prevent collapsing the left panel past its minimum
    try:
        min_left = max(360, self.left_container.sizeHint().width())
        left_scroll.setMinimumWidth(min_left)
    except Exception:
        pass
    self._build_right_panel(right_layout)
    # 初始化手动输入占位示例
    self._update_manual_placeholder(self.mode_combo.currentData())
    # 根据当前模式刷新可见性
    self._on_mode_change()

    # Restore persisted splitter geometry so the user's last-chosen
    # left/right proportions survive a restart. See
    # ``shared.settings_store`` for the key naming and on-failure
    # fallback policy (defaults to the [520, 820] setSizes above).
    # A single SettingsStore instance is cached on ``self`` and reused
    # by closeEvent's save path — avoids double-construction race on
    # Windows registry access and lets tests inject a fake via a
    # single monkeypatch point.
    try:
        from shared.settings_store import (
            KEY_MAIN_SPLITTER_STATE,
            SettingsStore,
            extract_splitter_pane_count,
        )

        settings = getattr(self, "_settings_store", None)
        if settings is None:
            settings = SettingsStore()
            self._settings_store = settings

        blob = settings.load_bytes(KEY_MAIN_SPLITTER_STATE)
        if blob is not None:
            # Snapshot pre-restore sizes so we can roll back if the
            # restore succeeds syntactically (returns True) but applies
            # semantically nonsensical sizes — e.g. a blob from an
            # older app version whose layout had 3 panes instead of 2,
            # which Qt will happily accept and silently truncate.
            pre_restore_sizes = splitter.sizes()
            pre_restore_count = splitter.count()
            # The blob header stores the pane count. Pre-check it
            # matches our splitter's count before letting Qt apply a
            # blob from a different layout.
            expected_count = pre_restore_count
            blob_count = extract_splitter_pane_count(bytes(blob))
            if blob_count is not None and blob_count != expected_count:
                # Stale blob from a layout change — drop it immediately.
                settings.save_bytes(KEY_MAIN_SPLITTER_STATE, None)
            else:
                restored_ok = splitter.restoreState(blob)
                sizes_after = splitter.sizes()
                # Accept the restore only if the pane count, minimum,
                # and total-width invariants still hold. Any failure
                # means the blob was from an incompatible layout.
                if (
                    restored_ok
                    and len(sizes_after) == splitter.count()
                    and all(s >= 0 for s in sizes_after)
                    and sum(sizes_after) > 0
                ):
                    # Good restore — leave it in place.
                    pass
                else:
                    # Bad restore — revert to pre-restore sizes and
                    # drop the stale blob.
                    splitter.setSizes(pre_restore_sizes)
                    settings.save_bytes(KEY_MAIN_SPLITTER_STATE, None)
    except Exception:
        # Persistence is a convenience; never block startup. Log at
        # debug so developers still see it in DATALAB_DEBUG=1 runs.
        import logging

        logging.getLogger(__name__).debug(
            "Splitter state restore skipped", exc_info=True
        )

def build_left_panel(self):
    # Mode selection
    self.mode_box = QGroupBox("计算模式")
    self._register_title(self.mode_box, "计算模式", "Mode")
    mode_layout = QHBoxLayout(self.mode_box)
    self.mode_combo = QComboBox()
    mode_items = [
        ("外推", "Extrapolation", "extrapolation"),
        ("误差传递", "Error propagation", "error"),
        ("拟合", "Fitting", "fitting"),
        ("统计平均", "Statistics", "statistics"),
    ]
    for zh, en, data in mode_items:
        self.mode_combo.addItem(zh, data)
    self._register_combo(self.mode_combo, mode_items)
    self.mode_combo.currentIndexChanged.connect(self._on_mode_change)
    mode_layout.addWidget(self.mode_combo)
    self.left_layout.addWidget(self.mode_box)

    # Data file
    self.file_box = QGroupBox("")
    file_layout = QHBoxLayout(self.file_box)
    file_layout.setSpacing(6)
    self.data_file_edit = QLineEdit()
    file_layout.addWidget(self.data_file_edit)
    browse_btn = QPushButton("浏览…")
    browse_btn.clicked.connect(self.browse_data_file)
    self._register_text(browse_btn, "浏览…", "Browse…")
    file_layout.addWidget(browse_btn)
    self.use_file_hint_btn = QPushButton("?")
    self.use_file_hint_btn.setFlat(True)
    self.use_file_hint_btn.setFixedWidth(22)
    self.use_file_hint_btn.setFocusPolicy(Qt.NoFocus)
    self.use_file_hint_btn.setToolTip("")
    self.use_file_hint_btn.clicked.connect(self._show_data_file_hint)
    self.use_file_hint_btn.hide()
    file_layout.addWidget(self.use_file_hint_btn)
    # 数据来源切换
    self.use_file_checkbox = QCheckBox("使用数据文件")
    self.use_file_checkbox.setChecked(False)
    self._register_text(self.use_file_checkbox, "使用数据文件", "Use data file")
    self.use_file_checkbox.toggled.connect(self._on_data_source_toggle)
    source_row = QHBoxLayout()
    source_row.setSpacing(6)
    source_row.addWidget(self.use_file_checkbox)
    source_row.addStretch()
    self.left_layout.addLayout(source_row)
    self.left_layout.addWidget(self.file_box)
    self.file_box.hide()

    # Manual data — table editor + text fallback
    self.manual_box = QGroupBox("")
    manual_layout = QVBoxLayout(self.manual_box)
    manual_layout.setSpacing(6)

    # Toolbar
    table_toolbar = QHBoxLayout()
    table_toolbar.setSpacing(6)
    add_col_btn = QPushButton("+ 列")
    self._register_text(add_col_btn, "+ 列", "+ Column")
    add_col_btn.clicked.connect(lambda: _add_table_column(self))
    remove_col_btn = QPushButton("- 列")
    self._register_text(remove_col_btn, "- 列", "- Column")
    remove_col_btn.setToolTip(
        self._tr("删除最后一列（含数据）", "Remove the last column (and its data)")
    )
    remove_col_btn.clicked.connect(lambda: _remove_table_column(self))
    add_row_btn = QPushButton("+ 行")
    self._register_text(add_row_btn, "+ 行", "+ Row")
    add_row_btn.clicked.connect(lambda: _add_table_row(self))
    remove_row_btn = QPushButton("- 行")
    self._register_text(remove_row_btn, "- 行", "- Row")
    remove_row_btn.setToolTip(
        self._tr("删除最后一行（含数据）", "Remove the last row (and its data)")
    )
    remove_row_btn.clicked.connect(lambda: _remove_table_row(self))
    clear_btn = QPushButton("清除")
    self._register_text(clear_btn, "清除", "Clear")
    clear_btn.clicked.connect(lambda: _clear_table(self))
    self._data_view_toggle = QPushButton("文本视图")
    self._register_text(self._data_view_toggle, "文本视图", "Text View")
    self._data_view_toggle.clicked.connect(lambda: _toggle_data_view(self))
    table_toolbar.addWidget(add_col_btn)
    table_toolbar.addWidget(remove_col_btn)
    table_toolbar.addWidget(add_row_btn)
    table_toolbar.addWidget(remove_row_btn)
    table_toolbar.addWidget(clear_btn)
    table_toolbar.addWidget(self._data_view_toggle)
    table_toolbar.addStretch()
    manual_layout.addLayout(table_toolbar)

    # Stacked widget: table view (0) / text view (1)
    self._data_stack = QStackedWidget()

    self.manual_table = QTableWidget(6, 3)
    self.manual_table.setHorizontalHeaderLabels(["A", "B", "C"])
    self.manual_table.verticalHeader().setVisible(True)
    _apply_equal_column_stretch(self.manual_table)
    self.manual_table.setAlternatingRowColors(True)
    self.manual_table.setStyleSheet(_get_table_style())
    self.manual_table.setMinimumHeight(180)
    self.manual_table.installEventFilter(_TablePasteFilter(self.manual_table, self))
    self._data_stack.addWidget(self.manual_table)

    self.manual_data_edit = QPlainTextEdit()
    self._data_stack.addWidget(self.manual_data_edit)

    self._data_stack.setCurrentIndex(_STACK_PAGE_TABLE)  # table view by default
    manual_layout.addWidget(self._data_stack)
    self.left_layout.addWidget(self.manual_box)

    # Extrapolation settings
    self.extrap_box = QGroupBox("外推设置")
    self._register_title(self.extrap_box, "外推设置", "Extrapolation")
    extrap_layout = QVBoxLayout(self.extrap_box)
    method_layout = QHBoxLayout()
    method_label = QLabel("外推方法：")
    self._register_text(method_label, "外推方法：", "Method:")
    self.method_combo = QComboBox()
    # Use shared specs instead of hardcoded _candidate_methods
    method_options_zh = get_method_options("zh")
    method_options_en = get_method_options("en")
    # Build combo items
    combo_items = []
    for (name_zh, key), (name_en, _) in zip(method_options_zh, method_options_en):
        self.method_combo.addItem(name_zh, key)
        combo_items.append((name_zh, name_en, key))
    self._register_combo(self.method_combo, combo_items)
    self.method_combo.currentIndexChanged.connect(self._update_method_state)
    method_layout.addWidget(method_label)
    method_layout.addWidget(self.method_combo)
    # Add help button for extrapolation method
    method_help_btn = QPushButton("?")
    method_help_btn.setFlat(True)
    method_help_btn.setFocusPolicy(Qt.NoFocus)
    method_help_btn.setMaximumWidth(30)
    method_help_btn.clicked.connect(self._show_method_help)
    method_help_btn.setToolTip(self._tr(
        "点击查看当前外推方法的详细说明、适用场景和参数解释",
        "Click to view detailed description, applicable scenarios, and parameter explanations for the current method"
    ))
    self._register_text(method_help_btn, "?", "?")
    self.method_help_btn = method_help_btn
    method_layout.addWidget(method_help_btn)
    method_layout.addStretch()
    extrap_layout.addLayout(method_layout)

    self.custom_formula_widget = QWidget()
    custom_layout = QVBoxLayout(self.custom_formula_widget)
    lbl_custom = QLabel("自定义公式：")
    self._register_text(lbl_custom, "自定义公式：", "Custom formula:")
    custom_layout.addWidget(lbl_custom)
    self.custom_formula_edit = QPlainTextEdit("(C - B)^2/(B - A) + C")
    self.custom_formula_edit.setPlaceholderText(
        self._tr(
            "示例: (C - B)^2/(B - A) + C 或 Exp[-x1]*Sin[x2]",
            "Example: (C - B)^2/(B - A) + C or Exp[-x1]*Sin[x2]",
        )
    )
    # Allow the editor to resize with window, but set a reasonable minimum height
    self.custom_formula_edit.setMinimumHeight(80)
    self.custom_formula_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    custom_layout.addWidget(self.custom_formula_edit, stretch=1)
    # Formula preview label
    self.formula_preview_label = QLabel()
    self.formula_preview_label.setWordWrap(True)
    self.formula_preview_label.setStyleSheet("color: var(--muted, #8b949e); font-family: serif; font-size: 16px; padding: 4px 8px;")
    custom_layout.addWidget(self.formula_preview_label)
    self.custom_formula_edit.textChanged.connect(lambda: _update_formula_preview(self, self.custom_formula_edit, self.formula_preview_label))
    custom_hint_row = QHBoxLayout()
    custom_hint_row.setContentsMargins(0, 0, 0, 0)
    custom_hint_row.setSpacing(6)
    func_btn = QPushButton("函数支持")
    func_btn.setFlat(True)
    func_btn.setFocusPolicy(Qt.NoFocus)
    func_btn.clicked.connect(self._show_error_functions)
    self._register_text(func_btn, "函数支持", "Functions")
    custom_hint_row.addWidget(func_btn)
    hint_lbl = QLabel(
        self._tr(
            "支持 Sin[x], Cos[x], Log[x], Exp[x], Sqrt[x]，可用 A/B/C、列名或 x1/x2。",
            "Supports Sin[x], Cos[x], Log[x], Exp[x], Sqrt[x]; use A/B/C, headers, or x1/x2.",
        )
    )
    hint_lbl.setWordWrap(True)
    hint_lbl.setStyleSheet("color:#666;")
    custom_hint_row.addWidget(hint_lbl)
    custom_hint_row.addStretch()
    custom_layout.addLayout(custom_hint_row)
    extrap_layout.addWidget(self.custom_formula_widget)

    # Power law parameters
    self.power_box = QGroupBox("幂律参数")
    self._register_title(self.power_box, "幂律参数", "Power-law parameters")
    power_layout = QFormLayout(self.power_box)
    self.power_x_edits: list[QLineEdit] = []
    for idx, default in enumerate((10, 20, 40), start=1):
        edit = QLineEdit(str(default))
        self.power_x_edits.append(edit)
        lbl_x = QLabel(f"x{idx}：")
        self._register_text(lbl_x, f"x{idx}：", f"x{idx}:")
        power_layout.addRow(lbl_x, edit)
    self.power_p_edit = QLineEdit()
    self.power_p_edit.setPlaceholderText(self._tr("留空则自动求解 p", "Leave blank to solve p automatically"))
    lbl_p = QLabel("自定义 p（可选）：")
    self._register_text(lbl_p, "自定义 p（可选）：", "Custom p (optional):")
    power_layout.addRow(lbl_p, self.power_p_edit)
    self.power_seed_guesses_edit = QLineEdit()
    self.power_seed_guesses_edit.setPlaceholderText(
        self._tr("如 0.5, 1, 2, -1", "e.g. 0.5, 1, 2, -1")
    )
    lbl_seed = QLabel("p 种子列表（可选）：")
    self._register_text(lbl_seed, "p 种子列表（可选）：", "p seed list (optional):")
    power_layout.addRow(lbl_seed, self.power_seed_guesses_edit)
    extrap_layout.addWidget(self.power_box)

    # Levin u-transform parameters
    self.levin_box = QGroupBox("Levin u 变换参数")
    self._register_title(self.levin_box, "Levin u 变换参数", "Levin u-transform parameters")
    levin_layout = QFormLayout(self.levin_box)

    # Variant selection
    lbl_variant = QLabel("变换类型：")
    self._register_text(lbl_variant, "变换类型：", "Variant:")
    self.levin_variant_combo = QComboBox()
    self.levin_variant_combo.addItem("u (最常用)", "u")
    self.levin_variant_combo.addItem("t (级数)", "t")
    self.levin_variant_combo.addItem("v (积分)", "v")
    self._register_combo(self.levin_variant_combo, [
        ("u (最常用)", "u (most common)", "u"),
        ("t (级数)", "t (series)", "t"),
        ("v (积分)", "v (integrals)", "v"),
    ])
    levin_layout.addRow(lbl_variant, self.levin_variant_combo)

    # Order/terms
    lbl_order = QLabel("变换阶数：")
    self._register_text(lbl_order, "变换阶数：", "Transform order:")
    self.levin_order_spin = QSpinBox()
    self.levin_order_spin.setRange(1, 10)
    self.levin_order_spin.setValue(2)
    self.levin_order_spin.setToolTip(self._tr(
        "变换阶数（越高越精确但需要更多项，至少需要 2N+1 项数据）",
        "Transform order (higher = more accurate but needs more terms, requires at least 2N+1 data points)"
    ))
    levin_layout.addRow(lbl_order, self.levin_order_spin)

    # Weight function / omega
    lbl_weight = QLabel("权重函数：")
    self._register_text(lbl_weight, "权重函数：", "Weight function:")
    self.levin_weight_combo = QComboBox()
    self.levin_weight_combo.addItem("默认 (1)", "default")
    self.levin_weight_combo.addItem("1/(n+1)", "reciprocal")
    self.levin_weight_combo.addItem("1/(n+β)", "reciprocal_beta")
    self._register_combo(self.levin_weight_combo, [
        ("默认 (1)", "Default (1)", "default"),
        ("1/(n+1)", "1/(n+1)", "reciprocal"),
        ("1/(n+β)", "1/(n+β)", "reciprocal_beta"),
    ])
    self.levin_weight_combo.currentIndexChanged.connect(self._update_levin_weight_state)
    levin_layout.addRow(lbl_weight, self.levin_weight_combo)

    # Beta parameter (shown only when weight = 1/(n+β))
    lbl_beta = QLabel("β 参数：")
    self._register_text(lbl_beta, "β 参数：", "β parameter:")
    self.levin_beta_spin = QDoubleSpinBox()
    self.levin_beta_spin.setRange(0.01, 100.0)
    self.levin_beta_spin.setValue(1.0)
    self.levin_beta_spin.setSingleStep(0.1)
    self.levin_beta_spin.setDecimals(2)
    self.levin_beta_spin.setToolTip(self._tr(
        "权重函数 ω(n) = 1/(n+β) 中的 β 参数",
        "β parameter in weight function ω(n) = 1/(n+β)"
    ))
    levin_layout.addRow(lbl_beta, self.levin_beta_spin)
    # Initially hide beta (shown only when weight type is reciprocal_beta)
    lbl_beta.setVisible(False)
    self.levin_beta_spin.setVisible(False)
    # Store label reference for show/hide
    self.levin_beta_label = lbl_beta

    extrap_layout.addWidget(self.levin_box)

    # Richardson sequence acceleration parameters
    self.richardson_box = QGroupBox("Richardson 序列加速参数")
    self._register_title(self.richardson_box, "Richardson 序列加速参数", "Richardson acceleration parameters")
    richardson_layout = QFormLayout(self.richardson_box)

    # Power exponent p
    lbl_richardson_p = QLabel("收敛幂指数 p：")
    self._register_text(lbl_richardson_p, "收敛幂指数 p：", "Convergence power p:")
    self.richardson_p_spin = QDoubleSpinBox()
    self.richardson_p_spin.setRange(0.1, 10.0)
    self.richardson_p_spin.setValue(2.0)
    self.richardson_p_spin.setSingleStep(0.1)
    self.richardson_p_spin.setDecimals(2)
    self.richardson_p_spin.setToolTip(self._tr(
        "误差展开的幂指数（f(h) ≈ f∞ + c·h^p），常见值 p=2（二阶方法）",
        "Power exponent in error expansion (f(h) ≈ f∞ + c·h^p), common value p=2 (second-order method)"
    ))
    richardson_layout.addRow(lbl_richardson_p, self.richardson_p_spin)

    extrap_layout.addWidget(self.richardson_box)

    # Uncertainty selector
    uncert_layout = QHBoxLayout()
    lbl_uncert = QLabel("不确定度参考列：")
    self._register_text(lbl_uncert, "不确定度参考列：", "Uncertainty ref column:")
    uncert_layout.addWidget(lbl_uncert)
    self.uncertainty_combo = QComboBox()
    self._refresh_uncertainty_selector(["A", "B", "C"])
    uncert_layout.addWidget(self.uncertainty_combo)
    refresh_uncert_btn = QPushButton("刷新")
    refresh_uncert_btn.setToolTip(self._tr("重新扫描数据以列出可选的不确定度参考列。", "Rescan data to list available uncertainty columns."))
    self._register_text(refresh_uncert_btn, "刷新", "Refresh")
    refresh_uncert_btn.clicked.connect(self._refresh_uncertainty_from_source)
    uncert_layout.addWidget(refresh_uncert_btn)
    extrap_layout.addLayout(uncert_layout)
    self.left_layout.addWidget(self.extrap_box)

    # Error propagation settings
    self.error_box = QGroupBox("误差传递设置")
    self._register_title(self.error_box, "误差传递设置", "Error propagation")
    error_layout = QVBoxLayout(self.error_box)
    self.formula_edit = QPlainTextEdit()
    self.formula_edit.setPlaceholderText(
        self._tr("公式（使用列名或 x1, x2 …）", "Formula (use column names or x1, x2 …)")
    )
    error_layout.addWidget(self.formula_edit)
    # Error formula preview
    self.error_formula_preview = QLabel()
    self.error_formula_preview.setWordWrap(True)
    self.error_formula_preview.setStyleSheet("color: var(--muted, #8b949e); font-family: serif; font-size: 16px; padding: 4px 8px;")
    error_layout.addWidget(self.error_formula_preview)
    self.formula_edit.textChanged.connect(lambda: _update_formula_preview(self, self.formula_edit, self.error_formula_preview))

    func_btn_row = QHBoxLayout()
    self.constants_checkbox = QCheckBox("启用常数设置")
    self.constants_checkbox.setChecked(False)
    self.constants_checkbox.toggled.connect(self._toggle_constants_options)
    self._register_text(self.constants_checkbox, "启用常数设置", "Enable constants")
    error_layout.setSpacing(4)
    func_btn_row.addWidget(self.constants_checkbox)
    func_btn_row.addStretch()
    func_help_btn = QPushButton("函数支持")
    func_help_btn.setFlat(True)
    func_help_btn.setFocusPolicy(Qt.NoFocus)
    func_help_btn.setToolTip("")  # will be set in _update_placeholders_language
    func_help_btn.clicked.connect(self._show_error_functions)
    self._register_text(func_help_btn, "函数支持", "Functions")
    self.func_help_btn = func_help_btn
    func_btn_row.addWidget(func_help_btn)
    error_layout.addLayout(func_btn_row)

    self.constants_widget = QWidget()
    const_wrapper_layout = QVBoxLayout(self.constants_widget)
    const_wrapper_layout.setSpacing(6)
    self.use_constants_file_checkbox = QCheckBox("使用常数文件")
    self.use_constants_file_checkbox.setChecked(False)
    self._register_text(self.use_constants_file_checkbox, "使用常数文件", "Use constants file")
    self.use_constants_file_checkbox.toggled.connect(self._on_constants_source_toggle)
    const_wrapper_layout.addWidget(self.use_constants_file_checkbox)

    const_row = QHBoxLayout()
    const_row.setContentsMargins(0, 0, 0, 0)
    const_row.setSpacing(2)
    self.constants_file_edit = QLineEdit()
    const_row.addWidget(self.constants_file_edit)
    const_btn = QPushButton("常数文件…")
    const_btn.clicked.connect(self.browse_constants_file)
    self._register_text(const_btn, "常数文件…", "Constants file…")
    const_row.addWidget(const_btn)
    self.constants_hint_btn = QPushButton("?")
    self.constants_hint_btn.setFlat(True)
    self.constants_hint_btn.setFixedWidth(22)
    self.constants_hint_btn.setFocusPolicy(Qt.NoFocus)
    self.constants_hint_btn.setToolTip("")
    self.constants_hint_btn.clicked.connect(self._show_constants_file_hint)
    self.constants_hint_btn.hide()
    const_row.addWidget(self.constants_hint_btn)
    self.constants_file_row = QWidget()
    self.constants_file_row.setLayout(const_row)
    self.constants_file_row.setVisible(False)
    const_wrapper_layout.addWidget(self.constants_file_row)

    # Constants table (Name | Value) — same style as data table.
    # Also supports a text-view toggle so users can paste a whole
    # block of "NAME VALUE" lines at once (matches the data area's
    # existing "文本视图" button).
    const_table_toolbar = QHBoxLayout()
    const_add_row_btn = QPushButton(self._tr("+ 行", "+ Row"))
    self._register_text(const_add_row_btn, "+ 行", "+ Row")
    const_add_row_btn.clicked.connect(lambda: self.constants_table.setRowCount(self.constants_table.rowCount() + 1))
    const_clear_btn = QPushButton(self._tr("清除", "Clear"))
    self._register_text(const_clear_btn, "清除", "Clear")
    const_clear_btn.clicked.connect(lambda: _clear_constants_table(self))
    self._constants_view_toggle = QPushButton(self._tr("文本视图", "Text View"))
    self._register_text(self._constants_view_toggle, "文本视图", "Text View")
    self._constants_view_toggle.clicked.connect(
        lambda: _toggle_constants_view(self)
    )
    const_table_toolbar.addWidget(const_add_row_btn)
    const_table_toolbar.addWidget(const_clear_btn)
    const_table_toolbar.addWidget(self._constants_view_toggle)
    const_table_toolbar.addStretch()
    const_toolbar_w = QWidget()
    const_toolbar_w.setLayout(const_table_toolbar)
    const_wrapper_layout.addWidget(const_toolbar_w)

    # Stacked widget: table view (0) / text view (1) — mirrors
    # self._data_stack for the main data-input area. The text view
    # accepts the free-form format parsed by ``_process_constants_lines``:
    # one ``name value`` entry per line; ``#`` comments and blank lines
    # are preserved in the edit buffer but stripped by the downstream parser.
    self._constants_stack = QStackedWidget()

    self.constants_table = QTableWidget(4, 2)
    self.constants_table.setHorizontalHeaderLabels(["Name", "Value"])
    _apply_equal_column_stretch(self.constants_table)
    self.constants_table.setMinimumHeight(160)
    self.constants_table.setStyleSheet(_get_table_style())
    self._constants_stack.addWidget(self.constants_table)

    # Plain-text editor for bulk paste. Previously set to ``None`` in
    # baseline; now a real QPlainTextEdit so paste workflows like
    # "paste 20 constants from a spreadsheet" work without having to
    # click through each row individually.
    self.manual_constants_edit = QPlainTextEdit()
    self.manual_constants_edit.setMinimumHeight(160)
    self.manual_constants_edit.setPlaceholderText(
        self._tr(
            "# 每行一个常数：名称 值\n# 允许空行与以 # 开头的注释\nALPHA 7.2973525693(11)[-3]",
            "# One constant per line: name value\n# Blank lines and lines starting with # are allowed\nALPHA 7.2973525693(11)[-3]",
        )
    )
    self._constants_stack.addWidget(self.manual_constants_edit)

    self._constants_stack.setCurrentIndex(_STACK_PAGE_TABLE)  # table view by default
    const_wrapper_layout.addWidget(self._constants_stack)
    error_layout.addWidget(self.constants_widget)

    # Error propagation method (Taylor vs Monte Carlo)
    method_row = QHBoxLayout()
    lbl_err_method = QLabel("方法：")
    self._register_text(lbl_err_method, "方法：", "Method:")
    self.error_method_combo = QComboBox()
    error_method_items = [
        ("Taylor（偏导）", "Taylor (derivative)", "taylor"),
        ("Monte Carlo", "Monte Carlo", "monte_carlo"),
    ]
    for zh, _en, data in error_method_items:
        self.error_method_combo.addItem(zh, data)
    self._register_combo(self.error_method_combo, error_method_items)
    self.error_method_combo.currentIndexChanged.connect(self._update_error_propagation_controls)
    method_row.addWidget(lbl_err_method)
    method_row.addWidget(self.error_method_combo)
    method_row.addStretch()
    error_layout.addLayout(method_row)

    self.error_taylor_widget = QWidget()
    taylor_layout = QHBoxLayout(self.error_taylor_widget)
    taylor_layout.setContentsMargins(0, 0, 0, 0)
    taylor_layout.setSpacing(6)
    lbl_err_order = QLabel("阶数：")
    self._register_text(lbl_err_order, "阶数：", "Order:")
    self.error_order_spin = QSpinBox()
    self.error_order_spin.setRange(1, 2)
    self.error_order_spin.setValue(1)
    self.error_order_spin.setToolTip(
        self._tr(
            "1 阶：线性误差估计；2 阶：包含 Hessian（二阶偏导）贡献。",
            "Order 1: linear propagation; order 2: includes Hessian (second-derivative) contributions.",
        )
    )
    taylor_layout.addWidget(lbl_err_order)
    taylor_layout.addWidget(self.error_order_spin)
    taylor_layout.addStretch()
    error_layout.addWidget(self.error_taylor_widget)

    self.error_mc_widget = QWidget()
    mc_layout = QFormLayout(self.error_mc_widget)
    mc_layout.setContentsMargins(0, 0, 0, 0)
    mc_layout.setSpacing(6)
    lbl_mc_samples = QLabel("MC 样本数：")
    self._register_text(lbl_mc_samples, "MC 样本数：", "MC samples:")
    self.error_mc_samples_spin = QSpinBox()
    self.error_mc_samples_spin.setRange(100, 200000)
    self.error_mc_samples_spin.setSingleStep(100)
    self.error_mc_samples_spin.setValue(5000)
    self.error_mc_samples_spin.setToolTip(
        self._tr(
            "Monte Carlo 样本数（越大越稳定，但耗时更长），至少 100。",
            "Monte Carlo sample count (larger is more stable but slower), minimum 100.",
        )
    )
    mc_layout.addRow(lbl_mc_samples, self.error_mc_samples_spin)
    lbl_mc_seed = QLabel("随机种子（可选）：")
    self._register_text(lbl_mc_seed, "随机种子（可选）：", "Seed (optional):")
    self.error_mc_seed_edit = QLineEdit()
    self.error_mc_seed_edit.setPlaceholderText(self._tr("留空=随机", "blank=random"))
    self.error_mc_seed_edit.setToolTip(
        self._tr(
            "留空表示每次随机；填写整数可复现实验结果。",
            "Leave blank for random each run; set an integer for reproducibility.",
        )
    )
    mc_layout.addRow(lbl_mc_seed, self.error_mc_seed_edit)
    error_layout.addWidget(self.error_mc_widget)
    self.error_mc_widget.hide()

    self.left_layout.addWidget(self.error_box)
    self._toggle_constants_options(self.constants_checkbox.isChecked())
    self._on_constants_source_toggle(self.use_constants_file_checkbox.isChecked())
    self._update_error_propagation_controls()

    # Fitting module
    # --- Statistics box (new) ---
    self.stats_box = QGroupBox("统计平均设置")
    self._register_title(self.stats_box, "统计平均设置", "Statistics")
    stats_layout = QFormLayout(self.stats_box)
    self.stats_value_column_edit = QLineEdit("A")
    lbl_stats_value = QLabel("数值列：")
    self._register_text(lbl_stats_value, "数值列：", "Value column:")
    stats_layout.addRow(lbl_stats_value, self.stats_value_column_edit)
    self.stats_sigma_column_edit = QLineEdit("")
    lbl_stats_sigma = QLabel("不确定度列（可选）：")
    self._register_text(lbl_stats_sigma, "不确定度列（可选）：", "Sigma column (optional):")
    stats_layout.addRow(lbl_stats_sigma, self.stats_sigma_column_edit)
    self.stats_mode_combo = QComboBox()
    stats_items = [
        ("算术平均", "Arithmetic mean", "mean"),
        ("加权平均（σ 加权）", "Weighted mean (σ)", "weighted_sigma"),
    ]
    for zh, en, data in stats_items:
        self.stats_mode_combo.addItem(zh, data)
    self._register_combo(self.stats_mode_combo, stats_items)
    lbl_stats_type = QLabel("统计类型：")
    self._register_text(lbl_stats_type, "统计类型：", "Statistics type:")
    stats_layout.addRow(lbl_stats_type, self.stats_mode_combo)
    self.stats_weight_variance_checkbox = QCheckBox("对方差/标准误差使用权重")
    self.stats_weight_variance_checkbox.setChecked(False)
    self._register_text(self.stats_weight_variance_checkbox, "对方差/标准误差使用权重", "Use weights for variance/SE")
    lbl_weight_var = QLabel("方差/标准误差：")
    self._register_text(lbl_weight_var, "方差/标准误差：", "Variance/SE:")
    self.stats_weight_variance_label = lbl_weight_var
    stats_layout.addRow(lbl_weight_var, self.stats_weight_variance_checkbox)
    self.stats_sample_checkbox = QCheckBox("样本模式 (n-1)")
    self.stats_sample_checkbox.setChecked(False)
    self._register_text(self.stats_sample_checkbox, "样本模式 (n-1)", "Sample mode (n-1)")
    lbl_stats_sample = QLabel("样本/总体：")
    self._register_text(lbl_stats_sample, "样本/总体：", "Sample/Population:")
    stats_layout.addRow(lbl_stats_sample, self.stats_sample_checkbox)
    self.left_layout.addWidget(self.stats_box)
    self.stats_box.hide()
    self.stats_mode_combo.currentIndexChanged.connect(self._on_stats_mode_change)
    self._on_stats_mode_change()

    # Fitting module
    self.fit_box = QGroupBox("拟合模块")
    self._register_title(self.fit_box, "拟合模块", "Fitting")
    fit_layout = QVBoxLayout(self.fit_box)
    model_row = QHBoxLayout()
    lbl_model = QLabel("拟合模型：")
    self._register_text(lbl_model, "拟合模型：", "Model:")
    model_row.addWidget(lbl_model)
    self.fit_model_combo = QComboBox()
    self.fit_model_combo.addItem("自定义模型（非线性）", "custom")
    self.fit_model_combo.addItem("自动模型选择", "auto")
    self.fit_model_combo.addItem("多项式拟合", "poly")
    self.fit_model_combo.addItem("1/x^p 展开", "inverse")
    self.fit_model_combo.addItem("Padé 拟合", "pade")
    self.fit_model_combo.addItem("幂律极限拟合", "power_limit")
    self.fit_model_combo.addItem("对数多项式", "log_poly")
    self.fit_model_combo.addItem("通用指数基", "exp_combo")
    fit_items = [
        ("自定义模型（非线性）", "Custom (nonlinear)", "custom"),
        ("自动模型选择", "Auto select", "auto"),
        ("多项式拟合", "Polynomial", "poly"),
        ("1/x^p 展开", "1/x^p series", "inverse"),
        ("Padé 拟合", "Padé", "pade"),
        ("幂律极限拟合", "Power limit", "power_limit"),
        ("对数多项式", "Log polynomial", "log_poly"),
        ("通用指数基", "Exponential basis", "exp_combo"),
    ]
    self._register_combo(self.fit_model_combo, fit_items)
    self.fit_model_combo.currentIndexChanged.connect(self._on_model_type_changed)
    model_row.addWidget(self.fit_model_combo)
    fit_layout.addLayout(model_row)

    # MCMC refinement opt-in (Phase 3 #12). Placed in the fit panel
    # so users discover it when selecting a model — not buried in
    # a menu. Disabled with an explanatory tooltip when emcee is
    # missing, so the feature is discoverable but un-breakable.
    self.fit_mcmc_refine = QCheckBox(self._tr(
        "MCMC 精炼（拟合后运行）",
        "Refine with MCMC (after fit)",
    ))
    self._register_text(
        self.fit_mcmc_refine,
        "MCMC 精炼（拟合后运行）",
        "Refine with MCMC (after fit)",
    )
    self.fit_mcmc_refine.setChecked(False)
    try:
        from fitting.mcmc_fitter import HAS_EMCEE as _mcmc_has_emcee
    except ImportError:
        # Only ImportError is caught — any other error (SyntaxError,
        # NameError from a bad refactor, etc.) should propagate so
        # the maintainer sees the real bug instead of a mysteriously
        # disabled checkbox.
        self.fit_mcmc_refine.setEnabled(False)
        self.fit_mcmc_refine.setToolTip(self._tr(
            "MCMC 精炼不可用（fitting.mcmc_fitter 未安装）。"
            "pip install emcee numpy corner",
            "MCMC refinement unavailable — fitting.mcmc_fitter "
            "is not importable. pip install emcee numpy corner",
        ))
    else:
        if not _mcmc_has_emcee:
            self.fit_mcmc_refine.setEnabled(False)
            self.fit_mcmc_refine.setToolTip(self._tr(
                "需要安装 emcee 包才能启用 MCMC 精炼。"
                "pip install emcee numpy corner",
                "Install the 'emcee' package to enable MCMC "
                "refinement. pip install emcee numpy corner",
            ))
        else:
            self.fit_mcmc_refine.setToolTip(self._tr(
                "对最佳 AIC 模型的参数后验分布做 MCMC 采样，"
                "给出更可靠的置信区间（可能耗时 10–60 秒）。",
                "Run emcee MCMC on the best-AIC model to produce "
                "robust credible intervals (may take 10–60 s).",
            ))
    fit_layout.addWidget(self.fit_mcmc_refine)

    self.fit_model_hint = QLabel("")
    self.fit_model_hint.setStyleSheet("color:#aa5500;")
    self.fit_model_hint.setWordWrap(True)
    self.fit_model_hint.hide()
    fit_layout.addWidget(self.fit_model_hint)

    self.inverse_power_widget = QWidget()
    inverse_layout = QHBoxLayout(self.inverse_power_widget)
    inverse_layout.setContentsMargins(0, 0, 0, 0)
    lbl_inv_min = QLabel("min p：")
    self._register_text(lbl_inv_min, "min p：", "min p:")
    inverse_layout.addWidget(lbl_inv_min)
    self.inverse_min_spin = QSpinBox()
    self.inverse_min_spin.setRange(0, 12)
    self.inverse_min_spin.setValue(1)
    inverse_layout.addWidget(self.inverse_min_spin)
    lbl_inv_max = QLabel("max p：")
    self._register_text(lbl_inv_max, "max p：", "max p:")
    inverse_layout.addWidget(lbl_inv_max)
    self.inverse_max_spin = QSpinBox()
    self.inverse_max_spin.setRange(0, 18)
    self.inverse_max_spin.setValue(3)
    inverse_layout.addWidget(self.inverse_max_spin)
    inverse_layout.addStretch()
    fit_layout.addWidget(self.inverse_power_widget)
    self.inverse_power_widget.hide()

    self.pade_widget = QWidget()
    pade_layout = QHBoxLayout(self.pade_widget)
    pade_layout.setContentsMargins(0, 0, 0, 0)
    lbl_pade_m = QLabel("Padé m：")
    self._register_text(lbl_pade_m, "Padé m：", "Padé m:")
    pade_layout.addWidget(lbl_pade_m)
    self.pade_m_spin = QSpinBox()
    self.pade_m_spin.setRange(0, 6)
    self.pade_m_spin.setValue(1)
    pade_layout.addWidget(self.pade_m_spin)
    lbl_pade_n = QLabel("n：")
    self._register_text(lbl_pade_n, "n：", "n:")
    pade_layout.addWidget(lbl_pade_n)
    self.pade_n_spin = QSpinBox()
    self.pade_n_spin.setRange(0, 6)
    self.pade_n_spin.setValue(1)
    pade_layout.addWidget(self.pade_n_spin)
    pade_layout.addStretch()
    fit_layout.addWidget(self.pade_widget)
    self.pade_widget.hide()

    self.poly_degree_widget = QWidget()
    poly_layout = QHBoxLayout(self.poly_degree_widget)
    poly_layout.setContentsMargins(0, 0, 0, 0)
    lbl_poly_deg = QLabel("多项式最高阶：")
    self._register_text(lbl_poly_deg, "多项式最高阶：", "Polynomial degree:")
    poly_layout.addWidget(lbl_poly_deg)
    self.poly_degree_spin = QSpinBox()
    self.poly_degree_spin.setRange(1, 18)
    self.poly_degree_spin.setValue(max(3, self._baseline_poly_degree))
    poly_layout.addWidget(self.poly_degree_spin)
    poly_layout.addStretch()
    fit_layout.addWidget(self.poly_degree_widget)
    self.poly_degree_widget.hide()

    self.fit_expr_edit = QPlainTextEdit("A*x**(-p) + C")
    self.fit_expr_edit.setPlaceholderText("自定义模型表达式，例如 A*x**(-p) + C / Custom model expression")
    fit_layout.addWidget(self.fit_expr_edit)
    # Fit formula preview
    self.fit_formula_preview = QLabel()
    self.fit_formula_preview.setWordWrap(True)
    self.fit_formula_preview.setStyleSheet("color: var(--muted, #8b949e); font-family: serif; font-size: 16px; padding: 4px 8px;")
    fit_layout.addWidget(self.fit_formula_preview)
    self.fit_expr_edit.textChanged.connect(lambda: _update_formula_preview(self, self.fit_expr_edit, self.fit_formula_preview))
    fit_expr_hint_row = QHBoxLayout()
    fit_expr_hint_row.setContentsMargins(0, 0, 0, 0)
    fit_expr_hint_row.setSpacing(6)
    self.fit_func_help_btn = QPushButton("函数支持")
    self.fit_func_help_btn.setFlat(True)
    self.fit_func_help_btn.setFocusPolicy(Qt.NoFocus)
    self.fit_func_help_btn.setToolTip("")  # will be set in _update_placeholders_language
    self.fit_func_help_btn.clicked.connect(self._show_error_functions)
    self._register_text(self.fit_func_help_btn, "函数支持", "Functions")
    fit_expr_hint_row.addWidget(self.fit_func_help_btn)
    fit_expr_hint_row.addStretch()
    fit_layout.addLayout(fit_expr_hint_row)
    # Hidden legacy JSON param edit retained only to satisfy references; no GUI display.
    self.fit_param_edit = QPlainTextEdit()
    self.fit_param_edit.hide()

    constraint_header = QHBoxLayout()
    self.enable_constraints_checkbox = QCheckBox("启用参数约束")
    self.enable_constraints_checkbox.setChecked(False)
    self._register_text(self.enable_constraints_checkbox, "启用参数约束", "Enable parameter constraints")
    self.enable_constraints_checkbox.toggled.connect(self._on_constraints_toggle)
    constraint_header.addWidget(self.enable_constraints_checkbox)
    constraint_header.addStretch()
    fit_layout.addLayout(constraint_header)

    param_header = QHBoxLayout()
    lbl_param_rows = QLabel("参数列表：")
    self._register_text(lbl_param_rows, "参数列表：", "Parameter list:")
    param_header.addWidget(lbl_param_rows)
    param_header.addStretch()
    self.add_param_btn = QPushButton("+")
    self.add_param_btn.setFixedWidth(28)
    self.add_param_btn.setToolTip(self._tr("添加参数行", "Add parameter row"))
    self.add_param_btn.clicked.connect(self._add_param_row)
    param_header.addWidget(self.add_param_btn)
    self.remove_param_btn = QPushButton("-")
    self.remove_param_btn.setFixedWidth(28)
    self.remove_param_btn.setToolTip(self._tr("删除最后一行参数", "Remove last parameter row"))
    self.remove_param_btn.clicked.connect(self._remove_param_row)
    param_header.addWidget(self.remove_param_btn)
    param_header_widget = QWidget()
    param_header_widget.setLayout(param_header)
    param_header_widget.setVisible(True)
    self.param_header_widget = param_header_widget
    fit_layout.addWidget(param_header_widget)

    self.param_rows_layout = QVBoxLayout()
    self.param_rows: list[tuple[QLineEdit, QLineEdit, QLineEdit, QLineEdit, QWidget]] = []
    param_rows_container = QWidget()
    param_rows_container.setLayout(self.param_rows_layout)
    param_rows_container.setVisible(True)
    self.param_rows_container = param_rows_container
    fit_layout.addWidget(param_rows_container)
    self._reset_param_rows()

    var_header = QHBoxLayout()
    lbl_varmap = QLabel("变量映射：")
    self._register_text(lbl_varmap, "变量映射：", "Variable mapping:")
    var_header.addWidget(lbl_varmap)
    var_header.addStretch()
    self.add_variable_btn = QPushButton("+")
    self.add_variable_btn.setFixedWidth(28)
    self.add_variable_btn.setToolTip(self._tr("添加变量映射", "Add variable mapping"))
    self.add_variable_btn.clicked.connect(self._add_variable_row)
    var_header.addWidget(self.add_variable_btn)
    self.remove_variable_btn = QPushButton("-")
    self.remove_variable_btn.setFixedWidth(28)
    self.remove_variable_btn.setToolTip(self._tr("删除最后一个变量映射", "Remove last variable mapping"))
    self.remove_variable_btn.clicked.connect(self._remove_variable_row)
    var_header.addWidget(self.remove_variable_btn)
    fit_layout.addLayout(var_header)

    self.variable_rows: list[tuple[QLineEdit, QLineEdit, QWidget]] = []
    self.variable_name_pool = ["x", "y", "z", "u", "v", "w"]
    self.variable_rows_layout = QVBoxLayout()
    fit_layout.addLayout(self.variable_rows_layout)
    self._reset_variable_rows(default_var="x", default_column="A")

    target_row = QHBoxLayout()
    lbl_target = QLabel("目标列：")
    self._register_text(lbl_target, "目标列：", "Target column:")
    target_row.addWidget(lbl_target)
    self.fit_target_edit = QLineEdit("B")
    target_row.addWidget(self.fit_target_edit)
    fit_layout.addLayout(target_row)

    weight_row = QHBoxLayout()
    lbl_weight_mode = QLabel("统计/系统：")
    self._register_text(lbl_weight_mode, "统计/系统：", "Stat./System:")
    weight_row.addWidget(lbl_weight_mode)
    self.fit_weighted_checkbox = QCheckBox("统计误差加权")
    self._register_text(self.fit_weighted_checkbox, "统计误差加权", "Statistical weighting (sigma)")
    weight_row.addWidget(self.fit_weighted_checkbox)
    fit_layout.addLayout(weight_row)

    self.left_layout.addWidget(self.fit_box)
    self.fit_box.hide()
    self.inverse_min_spin.valueChanged.connect(self._on_model_settings_changed)
    self.inverse_max_spin.valueChanged.connect(self._on_model_settings_changed)
    self.pade_m_spin.valueChanged.connect(self._on_model_settings_changed)
    self.pade_n_spin.valueChanged.connect(self._on_model_settings_changed)
    self.poly_degree_spin.valueChanged.connect(self._on_model_settings_changed)

    # Options
    options_box = QGroupBox("选项")
    self._register_title(options_box, "选项", "Options")
    options_layout = QVBoxLayout(options_box)
    precision_layout = QHBoxLayout()
    label_precision = QLabel("多精度位数 (mpmath)：")
    self._register_text(label_precision, "多精度位数 (mpmath)：", "mpmath digits:")
    self.mpmath_precision_spin = QSpinBox()
    self.mpmath_precision_spin.setRange(MIN_MPMATH_DPS, MAX_MPMATH_DPS)
    self.mpmath_precision_spin.setValue(16)
    self.mpmath_precision_spin.setSingleStep(1)
    width_chars = len(str(MAX_MPMATH_DPS))
    try:
        fm = self.mpmath_precision_spin.fontMetrics()
        self.mpmath_precision_spin.setFixedWidth(fm.horizontalAdvance("0" * width_chars) + 32)
    except Exception:
        pass

    # Uncertainty digits option (always visible, not tied to LaTeX toggle)
    self.uncertainty_digits_spin = QSpinBox()
    self.uncertainty_digits_spin.setRange(1, 12)
    self.uncertainty_digits_spin.setValue(1)
    unc_label = QLabel("不确定度位数：")
    self._register_text(unc_label, "不确定度位数：", "Uncertainty digits:")

    precision_layout.addWidget(label_precision)
    precision_layout.addWidget(self.mpmath_precision_spin)
    precision_layout.addSpacing(16)
    precision_layout.addWidget(unc_label)
    precision_layout.addWidget(self.uncertainty_digits_spin)
    precision_layout.addStretch()
    options_layout.addLayout(precision_layout)

    self.generate_latex_checkbox = QCheckBox("生成 LaTeX 文件")
    self.generate_latex_checkbox.setChecked(False)
    self.generate_latex_checkbox.toggled.connect(self._toggle_latex_options)
    self._register_text(self.generate_latex_checkbox, "生成 LaTeX 文件", "Generate LaTeX")
    options_layout.addWidget(self.generate_latex_checkbox)

    self.latex_options_widget = QWidget()
    latex_layout = QFormLayout(self.latex_options_widget)
    self.output_file_edit = QLineEdit()
    out_btn = QPushButton("选择…")
    out_btn.clicked.connect(self.browse_output_file)
    self._register_text(out_btn, "选择…", "Browse…")
    output_row = QHBoxLayout()
    output_row.addWidget(self.output_file_edit)
    output_row.addWidget(out_btn)
    lbl_output = QLabel("LaTeX 输出路径：")
    self._register_text(lbl_output, "LaTeX 输出路径：", "LaTeX output path:")
    latex_layout.addRow(lbl_output, output_row)
    self.latex_input_precision_spin = QSpinBox()
    self.latex_input_precision_spin.setRange(6, 200)
    self.latex_input_precision_spin.setValue(20)
    prec_label = QLabel("输入列位数：")
    self._register_text(prec_label, "输入列位数：", "Input digits:")
    self.dcolumn_checkbox = QCheckBox("使用 dcolumn 排版")
    self.dcolumn_checkbox.setChecked(False)
    self._register_text(self.dcolumn_checkbox, "使用 dcolumn 排版", "Use dcolumn")
    self.latex_group_size_spin = QSpinBox()
    self.latex_group_size_spin.setRange(0, 12)
    self.latex_group_size_spin.setValue(3)
    group_size_label = QLabel("分组位数：")
    self._register_text(group_size_label, "分组位数：", "Group size:")
    self.caption_checkbox = QCheckBox("使用标题")
    self._register_text(self.caption_checkbox, "使用标题", "Use caption")
    self.caption_checkbox.setChecked(False)
    self.caption_checkbox.toggled.connect(self._toggle_caption_input)
    latex_digits_row = QHBoxLayout()
    latex_digits_row.addWidget(prec_label)
    latex_digits_row.addWidget(self.latex_input_precision_spin)
    latex_digits_row.addSpacing(12)
    latex_digits_row.addWidget(self.dcolumn_checkbox)
    latex_digits_row.addSpacing(12)
    latex_digits_row.addWidget(group_size_label)
    latex_digits_row.addWidget(self.latex_group_size_spin)
    latex_digits_row.addStretch()
    latex_layout.addRow(latex_digits_row)

    # Caption (hidden unless checkbox checked): same row as checkbox
    self.caption_edit = QLineEdit()
    self.caption_edit.setMinimumWidth(0)
    self.caption_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    self.caption_edit.setVisible(False)
    caption_row = QHBoxLayout()
    caption_row.addWidget(self.caption_checkbox)
    caption_row.addWidget(self.caption_edit)
    latex_layout.addRow(caption_row)
    options_layout.addWidget(self.latex_options_widget)

    self.generate_plots_checkbox = QCheckBox("生成图片")
    self.generate_plots_checkbox.setChecked(False)
    self._register_text(self.generate_plots_checkbox, "生成图片", "Generate plots")
    self.generate_plots_checkbox.toggled.connect(lambda _: self._update_log_scale_visibility())
    options_layout.addWidget(self.generate_plots_checkbox)

    self.verbose_checkbox = QCheckBox("显示详细日志")
    self._register_text(self.verbose_checkbox, "显示详细日志", "Verbose log")
    options_layout.addWidget(self.verbose_checkbox)

    # NOTE: ``latex_engine_combo`` + the engine-path picker were moved
    # into the LaTeX output tab (next to the font-size row) because
    # they're compile-time, not compute-time, controls. The widgets
    # are still created on ``self`` so other code paths
    # (window_latex_pdf_mixin.compile_latex_to_pdf) keep working
    # unchanged — they reference ``self.latex_engine_combo``.

    self.left_layout.addWidget(options_box)

    self.run_button = QPushButton("开始执行")
    self._register_text(self.run_button, "开始执行", "Run")
    self.run_button.clicked.connect(self.run_calculation)
    self.left_layout.addWidget(self.run_button)
    self._update_model_controls()

def build_right_panel(self, layout: QVBoxLayout):
    self.tabs = QTabWidget()
    layout.addWidget(self.tabs)

    # Result tab
    result_widget = QWidget()
    result_layout = QVBoxLayout(result_widget)
    self.result_tabs = QTabWidget()
    result_layout.addWidget(self.result_tabs)
    self.result_tab_titles = {"numeric": "数值结果", "image": "图片"}

    numeric_tab = QWidget()
    numeric_layout = QVBoxLayout(numeric_tab)
    self.result_edit = QTextBrowser()
    self.fit_result_edit = self.result_edit
    self.result_edit.setReadOnly(True)
    self.result_edit.setOpenExternalLinks(False)
    self.result_edit.setStyleSheet(_get_result_style())
    self._add_font_control_row(numeric_layout, self.result_edit, "字体大小：")

    # Display formatting controls shared by all result types (number only; LaTeX unaffected)
    fmt_row = QHBoxLayout()
    self.scientific_checkbox = QCheckBox("使用科学计数法显示结果")
    self._register_text(self.scientific_checkbox, "使用科学计数法显示结果", "Display results in scientific notation")
    self.scientific_checkbox.setChecked(False)
    self.scientific_checkbox.stateChanged.connect(self._on_display_format_changed)
    fmt_row.addWidget(self.scientific_checkbox)
    fmt_row.addSpacing(8)
    lbl_digits = QLabel(self._tr("小数位数：", "Decimal places:"))
    self.display_digits_label = lbl_digits
    fmt_row.addWidget(lbl_digits)
    self.display_digits_spin = QSpinBox()
    self.display_digits_spin.setRange(0, 50)
    self.display_digits_spin.setValue(10)
    self.display_digits_spin.valueChanged.connect(self._on_display_format_changed)
    fmt_row.addWidget(self.display_digits_spin)
    fmt_row.addStretch()
    numeric_layout.addLayout(fmt_row)

    export_row = QHBoxLayout()
    self.export_csv_btn = QPushButton("导出 CSV")
    self._register_text(self.export_csv_btn, "导出 CSV", "Export CSV")
    self.export_csv_btn.setEnabled(False)
    self.export_csv_btn.clicked.connect(self._export_csv_data)
    export_row.addWidget(self.export_csv_btn)
    export_row.addStretch()
    numeric_layout.addLayout(export_row)
    numeric_layout.addWidget(self.result_edit)
    self.result_tabs.addTab(numeric_tab, "数值结果")
    self._reset_csv_data()

    image_tab = QWidget()
    image_layout = QVBoxLayout(image_tab)
    controls_layout = QHBoxLayout()
    self.result_zoom_in_btn = QPushButton()
    self._register_text(self.result_zoom_in_btn, "放大", "Zoom in", "setToolTip")
    self._set_zoom_icon(self.result_zoom_in_btn, "in")
    self._style_round_icon_button(self.result_zoom_in_btn)
    self.result_zoom_in_btn.clicked.connect(lambda: self._adjust_result_plot_zoom(1.25))
    self.result_zoom_out_btn = QPushButton()
    self._register_text(self.result_zoom_out_btn, "缩小", "Zoom out", "setToolTip")
    self._set_zoom_icon(self.result_zoom_out_btn, "out")
    self._style_round_icon_button(self.result_zoom_out_btn)
    self.result_zoom_out_btn.clicked.connect(lambda: self._adjust_result_plot_zoom(0.75))
    self.result_zoom_reset_btn = QPushButton("重置")
    self._register_text(self.result_zoom_reset_btn, "重置", "Reset")
    self.result_zoom_reset_btn.clicked.connect(lambda: self._reset_result_plot_zoom())
    self.result_export_btn = QPushButton("导出图片")
    self._register_text(self.result_export_btn, "导出图片", "Export image")
    self.result_export_btn.clicked.connect(self._export_result_plot)
    # Log-scale controls (visible only when fitting mode + generate plots)
    self.log_scale_label = QLabel(self._tr("对数坐标：", "Log axes:"))
    self.log_x_checkbox = QCheckBox("x 轴")
    self._register_text(self.log_x_checkbox, "x 轴", "log x")
    self.log_y_checkbox = QCheckBox("y 轴")
    self._register_text(self.log_y_checkbox, "y 轴", "log y")
    for cb in (self.log_x_checkbox, self.log_y_checkbox):
        cb.setVisible(False)
        cb.stateChanged.connect(self._on_log_scale_changed)
    self.log_scale_label.setVisible(False)
    # Zoom percent input
    self.zoom_percent_spin = QSpinBox()
    self.zoom_percent_spin.setRange(25, 400)
    self.zoom_percent_spin.setSingleStep(5)
    self.zoom_percent_spin.setValue(100)
    self._register_text(self.zoom_percent_spin, "", "", "setToolTip")
    self.zoom_percent_spin.setSuffix("%")
    self.zoom_percent_spin.valueChanged.connect(self._on_zoom_percent_changed)
    controls_layout.addWidget(self.result_zoom_in_btn)
    controls_layout.addWidget(self.result_zoom_out_btn)
    controls_layout.addWidget(self.zoom_percent_spin)
    controls_layout.addWidget(self.result_zoom_reset_btn)
    controls_layout.addWidget(self.result_export_btn)
    controls_layout.addWidget(self.log_scale_label)
    controls_layout.addWidget(self.log_x_checkbox)
    controls_layout.addWidget(self.log_y_checkbox)
    controls_layout.addStretch()
    # Navigation controls aligned to the right on the same row
    self.image_prev_btn = QPushButton()
    self.image_prev_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowLeft))
    self._register_text(self.image_prev_btn, "", "", "setText")
    self._register_text(self.image_prev_btn, "上一张", "Previous", "setToolTip")
    self.image_prev_btn.clicked.connect(self._on_image_prev)
    self.image_page_spin = QSpinBox()
    self.image_page_spin.setRange(1, 1)
    self.image_page_spin.setValue(1)
    self.image_page_spin.setFixedWidth(70)
    self._register_text(self.image_page_spin, "", "", "setToolTip")
    self.image_page_spin.valueChanged.connect(self._on_image_page_changed)
    self.image_next_btn = QPushButton()
    self.image_next_btn.setIcon(self.style().standardIcon(QStyle.SP_ArrowRight))
    self._register_text(self.image_next_btn, "", "", "setText")
    self._register_text(self.image_next_btn, "下一张", "Next", "setToolTip")
    self.image_next_btn.clicked.connect(self._on_image_next)
    self.image_status_label = QLabel(self._tr("暂无图片", "No image"))
    controls_layout.addWidget(self.image_status_label)
    controls_layout.addWidget(self.image_page_spin)
    # Hide arrow buttons (navigation via page spin)
    self.image_prev_btn.setVisible(False)
    self.image_next_btn.setVisible(False)
    image_layout.addLayout(controls_layout)

    self.result_plot_scroll = QScrollArea()
    self.result_plot_scroll.setWidgetResizable(False)
    self.result_plot_scroll.setAlignment(Qt.AlignCenter)
    self.result_plot_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    self.result_plot_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    self.result_plot_label = QLabel(self._tr("尚无图片", "No image yet"))
    self.result_plot_label.setAlignment(Qt.AlignCenter)
    self.result_plot_label.setMinimumHeight(320)
    self.result_plot_scroll.setWidget(self.result_plot_label)
    image_layout.addWidget(self.result_plot_scroll)
    self.result_tabs.addTab(image_tab, "图片")

    self.result_tab_index = self.tabs.addTab(result_widget, "结果")
    self.main_tab_titles = {
        "result": "结果",
        "log": "日志",
        "latex": "LaTeX",
        "pdf": "PDF 预览",
    }
    # Tab texts handled via QTabWidget defaults
    self._update_log_scale_visibility()

    # Log tab
    log_widget = QWidget()
    log_layout = QVBoxLayout(log_widget)
    self.log_edit = QPlainTextEdit()
    self.log_edit.setReadOnly(True)
    self._add_font_control_row(log_layout, self.log_edit, "字体大小：")
    log_layout.addWidget(self.log_edit)
    self.log_tab_index = self.tabs.addTab(log_widget, "日志")

    # LaTeX tab
    latex_widget = QWidget()
    latex_layout = QVBoxLayout(latex_widget)
    toolbar = QHBoxLayout()
    open_btn = QPushButton("打开…")
    open_btn.clicked.connect(self.open_latex_file)
    self._register_text(open_btn, "打开…", "Open…")
    toolbar.addWidget(open_btn)
    save_btn = QPushButton("保存")
    save_btn.clicked.connect(self.save_latex_editor)
    self._register_text(save_btn, "保存", "Save")
    toolbar.addWidget(save_btn)
    reload_btn = QPushButton("重新载入")
    reload_btn.clicked.connect(lambda: self.reload_latex_editor(show_message=True))
    self._register_text(reload_btn, "重新载入", "Reload")
    toolbar.addWidget(reload_btn)
    compile_btn = QPushButton("编译 PDF")
    compile_btn.clicked.connect(self.compile_latex_to_pdf)
    self._register_text(compile_btn, "编译 PDF", "Compile PDF")
    toolbar.addWidget(compile_btn)
    view_btn = QPushButton("查看 PDF")
    view_btn.clicked.connect(self.open_compiled_pdf)
    self._register_text(view_btn, "查看 PDF", "View PDF")
    toolbar.addWidget(view_btn)
    toolbar.addStretch()
    self.latex_status_label = QLabel("未加载 LaTeX 文件")
    self._register_text(self.latex_status_label, "未加载 LaTeX 文件", "No LaTeX loaded")
    toolbar.addWidget(self.latex_status_label)
    latex_layout.addLayout(toolbar)
    from app_desktop.numbered_text_edit import NumberedTextEdit

    # ``NumberedTextEdit`` is a ``QPlainTextEdit`` with a left-margin
    # line-number gutter — needed because Tectonic / pdflatex error
    # messages reference line numbers (``error: 1.tex:57: ...``) and
    # users have to find the offending line by scrolling without that.
    self.latex_edit = NumberedTextEdit()
    self.latex_edit.setPlaceholderText("% LaTeX 内容将在此显示…")
    # Attach syntax highlighter
    from app_desktop.latex_highlighter import LatexHighlighter
    self._latex_highlighter = LatexHighlighter(self.latex_edit.document())

    # Compose font-size row + LaTeX-engine controls into one toolbar.
    # The engine selector lives here (rather than the compute panel
    # on the left) because it's a compile-time setting — it has no
    # effect on the numerical results, only on how the .tex is
    # rendered to PDF.
    latex_controls_row = QHBoxLayout()
    lbl_font = QLabel("字体大小：")
    self._register_text(lbl_font, "字体大小：", "Font size:")
    latex_controls_row.addWidget(lbl_font)
    latex_font_spin = QSpinBox()
    latex_font_spin.setRange(8, 32)
    _default_size = self.latex_edit.font().pointSize()
    latex_font_spin.setValue(max(8, _default_size if _default_size > 0 else 12))
    latex_font_spin.valueChanged.connect(
        lambda value, target=self.latex_edit: self._apply_editor_font_size(target, value)
    )
    latex_controls_row.addWidget(latex_font_spin)

    lbl_engine = QLabel("LaTeX 引擎：")
    self._register_text(lbl_engine, "LaTeX 引擎：", "LaTeX engine:")
    latex_controls_row.addSpacing(16)
    latex_controls_row.addWidget(lbl_engine)
    self.latex_engine_combo = QComboBox()
    # ``tectonic`` is offered alongside the traditional engines because
    # it auto-downloads (~30 MB single binary) and resolves missing
    # LaTeX packages over the net, so users without a local TeX Live
    # install can still produce PDFs out of the box. See
    # ``shared.latex_engine`` for the resolution + install pipeline.
    self.latex_engine_combo.addItems(["pdflatex", "xelatex", "tectonic"])
    # Tectonic is the default: it auto-installs (~30 MB single binary)
    # if missing and resolves LaTeX packages over the net per-document,
    # so users without a local TeX Live install still get a working
    # PDF on first run. ``pdflatex`` / ``xelatex`` remain available
    # for power users with a tuned local TeX install.
    self.latex_engine_combo.setCurrentText("tectonic")
    latex_controls_row.addWidget(self.latex_engine_combo)
    engine_btn = QPushButton("选择引擎路径…")
    engine_btn.clicked.connect(self._prompt_engine_selection)
    self._register_text(engine_btn, "选择引擎路径…", "Select engine path…")
    latex_controls_row.addWidget(engine_btn)
    latex_controls_row.addStretch()
    latex_layout.addLayout(latex_controls_row)

    latex_layout.addWidget(self.latex_edit)
    self.tabs.addTab(latex_widget, "LaTeX")

    # PDF tab
    pdf_widget = QWidget()
    pdf_layout = QVBoxLayout(pdf_widget)
    pdf_toolbar = QHBoxLayout()
    self.pdf_status_label = QLabel("暂无 PDF 预览")
    self._register_text(self.pdf_status_label, "暂无 PDF 预览", "No PDF preview")
    pdf_toolbar.addWidget(self.pdf_status_label)
    pdf_toolbar.addStretch()
    zoom_out_btn = QPushButton()
    self._register_text(zoom_out_btn, "缩小", "Zoom out", "setToolTip")
    self._set_zoom_icon(zoom_out_btn, "out")
    self._style_round_icon_button(zoom_out_btn)
    zoom_out_btn.clicked.connect(lambda: self._apply_pdf_zoom(self.pdf_zoom * 0.75))
    pdf_toolbar.addWidget(zoom_out_btn)
    zoom_in_btn = QPushButton()
    self._register_text(zoom_in_btn, "放大", "Zoom in", "setToolTip")
    self._set_zoom_icon(zoom_in_btn, "in")
    self._style_round_icon_button(zoom_in_btn)
    zoom_in_btn.clicked.connect(lambda: self._apply_pdf_zoom(self.pdf_zoom * 1.25))
    pdf_toolbar.addWidget(zoom_in_btn)
    lbl_zoom = QLabel("缩放%：")
    self._register_text(lbl_zoom, "缩放%：", "Zoom %:")
    pdf_toolbar.addWidget(lbl_zoom)
    self.pdf_zoom_spin = QDoubleSpinBox()
    self.pdf_zoom_spin.setRange(35.0, 400.0)
    self.pdf_zoom_spin.setDecimals(0)
    self.pdf_zoom_spin.setSingleStep(5.0)
    self.pdf_zoom_spin.setValue(100.0)
    self.pdf_zoom_spin.valueChanged.connect(lambda v: self._apply_pdf_zoom(v / 100.0))
    pdf_toolbar.addWidget(self.pdf_zoom_spin)
    reset_zoom_btn = QPushButton("重置")
    self._register_text(reset_zoom_btn, "重置", "Reset")
    reset_zoom_btn.clicked.connect(self._reset_pdf_zoom)
    pdf_toolbar.addWidget(reset_zoom_btn)
    pdf_layout.addLayout(pdf_toolbar)

    self.pdf_scroll = QScrollArea()
    self.pdf_scroll.setWidgetResizable(True)
    self.pdf_container = QWidget()
    self.pdf_container_layout = QVBoxLayout(self.pdf_container)
    self.pdf_container_layout.setAlignment(Qt.AlignTop)
    self.pdf_scroll.setWidget(self.pdf_container)
    pdf_layout.addWidget(self.pdf_scroll)
    self.tabs.addTab(pdf_widget, "PDF 预览")
    # record tab indexes for translation
    self.result_tabs_indices = {
        "numeric": 0,
        "image": 1,
    }
    self.main_tabs_indices = {
        "result": self.tabs.indexOf(result_widget),
        "log": self.tabs.indexOf(log_widget),
        "latex": self.tabs.indexOf(latex_widget),
        "pdf": self.tabs.indexOf(pdf_widget),
    }
    self._update_image_status()


# -- Table editor helpers ---------------------------------------------------

def _add_table_column(self):
    """Append a new column to the manual data table."""
    table = self.manual_table
    col = table.columnCount()
    table.setColumnCount(col + 1)
    letter = chr(65 + col % 26)
    if col >= 26:
        letter = chr(64 + col // 26) + letter
    table.setHorizontalHeaderItem(col, QTableWidgetItem(letter))
    # Re-apply equal-stretch resize: ``setColumnCount`` resets the
    # new column's resize mode to Interactive (header default), so
    # without this the new column shows up at narrow default width
    # and the visible columns become uneven.
    _apply_equal_column_stretch(table)


def _add_table_row(self):
    """Append a new row to the manual data table."""
    table = self.manual_table
    table.setRowCount(table.rowCount() + 1)


def _remove_table_row(self):
    """Drop the last row from the manual data table.

    Keeps a minimum of one row so the user always has somewhere to
    type. ``setRowCount(N-1)`` discards the last row's QTableWidgetItem
    instances along with any data they held.
    """
    table = self.manual_table
    current = table.rowCount()
    if current > 1:
        table.setRowCount(current - 1)


def _remove_table_column(self):
    """Drop the last column from the manual data table.

    Keeps a minimum of one column for the same reason as
    ``_remove_table_row``. The header label is dropped automatically
    by ``setColumnCount`` along with the column's items.
    """
    table = self.manual_table
    current = table.columnCount()
    if current > 1:
        table.setColumnCount(current - 1)
        # Stretch mode survives a column drop on Qt 6.x but the
        # remaining columns share the freed width unevenly without
        # an explicit re-apply. Cheap to call regardless.
        _apply_equal_column_stretch(table)


def _view_toggle_label(self, current_index: int) -> str:
    """Label shown on a view-toggle button based on which page is *now* visible.

    When the stack is showing the table, the button offers the text view (and
    vice versa). Centralising this here keeps both the data and constants
    toggles in sync — and keeps the ``_STACK_PAGE_*`` convention in one place.
    """
    if current_index == _STACK_PAGE_TABLE:
        return self._tr("文本视图", "Text View")
    return self._tr("表格视图", "Table View")


def _toggle_data_view(self):
    """Switch between table view and plain-text view."""
    stack = self._data_stack
    if stack.currentIndex() == _STACK_PAGE_TABLE:
        # Table → Text: serialize table into text edit
        self.manual_data_edit.setPlainText(_serialize_table(self))
        stack.setCurrentIndex(_STACK_PAGE_TEXT)
    else:
        # Text → Table: load text into table
        _load_text_into_table(self, self.manual_data_edit.toPlainText())
        stack.setCurrentIndex(_STACK_PAGE_TABLE)
    self._data_view_toggle.setText(_view_toggle_label(self, stack.currentIndex()))


def _serialize_table(self) -> str:
    """Read all cells from manual_table and return whitespace-separated text."""
    table = self.manual_table
    cols = table.columnCount()
    rows_count = table.rowCount()

    # Headers from horizontal header
    headers = []
    for c in range(cols):
        item = table.horizontalHeaderItem(c)
        headers.append(item.text() if item else chr(65 + c))

    lines = ["\t".join(headers)]
    for r in range(rows_count):
        cells = []
        has_data = False
        for c in range(cols):
            item = table.item(r, c)
            val = item.text().strip() if item else ""
            cells.append(val)
            if val:
                has_data = True
        if has_data:
            lines.append("\t".join(cells))
    return "\n".join(lines)


def _load_text_into_table(self, text: str):
    """Parse whitespace/CSV text and populate manual_table.

    Delegates to ``shared.parsing.parse_clipboard_tabular`` which
    handles US/EU locale sniffing, thousand separators, scientific
    notation, quoted CSV cells, unicode whitespace, DOS line endings,
    and ragged rows. The resulting rows contain either floats or
    ``None`` for non-numeric / empty cells — the table renders the
    float via ``str(v)`` and shows empty string for ``None``.
    """
    from shared.parsing import _synthetic_headers, parse_clipboard_tabular

    table = self.manual_table
    result = parse_clipboard_tabular(text or "")
    if not result.rows and not result.headers:
        return

    max_cols = max(
        len(result.headers),
        max((len(row) for row in result.rows), default=0),
    )
    if max_cols == 0:
        return

    table.setColumnCount(max_cols)
    # Pad / synthesize headers so every column has a label. Reuse
    # ``_synthetic_headers`` (Excel-style A/B/.../Z/AA/AB) so > 26
    # columns don't get ASCII-punctuation labels like ``[`` from a
    # naive ``chr(65 + i)`` rollover bug.
    synth = _synthetic_headers(max_cols)
    headers = [
        result.headers[i] if i < len(result.headers) else synth[i]
        for i in range(max_cols)
    ]
    table.setHorizontalHeaderLabels(headers)
    _apply_equal_column_stretch(table)

    table.setRowCount(max(len(result.rows), 5))
    for r, row in enumerate(result.rows):
        for c, val in enumerate(row):
            if val is None:
                cell_text = ""
            elif val.is_integer() and abs(val) <= 1e15:
                # Prefer "1" over "1.0" for Excel-style integers;
                # preserves the user's input fidelity for whole numbers
                # without eating scientific notation for genuinely
                # float-typed values. Boundary is inclusive so 1e15
                # renders as "1000000000000000" (not "1e+15" or
                # "1000000000000000.0").
                cell_text = str(int(val))
            else:
                cell_text = repr(val)  # round-trip safe float repr
            table.setItem(r, c, QTableWidgetItem(cell_text))


def _toggle_data_collapse(self):
    """Toggle the data table between collapsed (summary) and expanded."""
    self._data_expanded = not self._data_expanded
    self._data_content.setVisible(self._data_expanded)
    if self._data_expanded:
        self._data_expand_btn.setText(self._tr("▼ 收起", "▼ Collapse"))
    else:
        self._data_expand_btn.setText(self._tr("▶ 展开编辑", "▶ Expand"))
    _update_data_summary(self)


def _update_data_summary(self):
    """Update the data summary label with row × col count."""
    table = self.manual_table
    data_rows = 0
    for r in range(table.rowCount()):
        has = False
        for c in range(table.columnCount()):
            item = table.item(r, c)
            if item and item.text().strip():
                has = True
                break
        if has:
            data_rows += 1
    cols = table.columnCount()
    self._data_summary_label.setText(f"{data_rows} × {cols}")


def _formula_to_display(expr: str) -> str:
    """Convert Mathematica-style formula to a more readable display string."""
    import re as _re
    if not expr or not expr.strip():
        return ""
    t = expr.strip()
    # Basic conversions for display
    t = _re.sub(r'\bSin\[([^\]]+)\]', r'sin(\1)', t, flags=_re.IGNORECASE)
    t = _re.sub(r'\bCos\[([^\]]+)\]', r'cos(\1)', t, flags=_re.IGNORECASE)
    t = _re.sub(r'\bTan\[([^\]]+)\]', r'tan(\1)', t, flags=_re.IGNORECASE)
    t = _re.sub(r'\bLog\[([^\]]+)\]', r'ln(\1)', t, flags=_re.IGNORECASE)
    t = _re.sub(r'\bExp\[([^\]]+)\]', r'e^(\1)', t, flags=_re.IGNORECASE)
    t = _re.sub(r'\bSqrt\[([^\]]+)\]', r'√(\1)', t, flags=_re.IGNORECASE)
    t = _re.sub(r'\bAbs\[([^\]]+)\]', r'|\1|', t, flags=_re.IGNORECASE)
    t = _re.sub(r'\bPi\b', 'π', t, flags=_re.IGNORECASE)
    t = t.replace('**', '^').replace('*', '·')
    return t


def _update_formula_preview(self, edit_widget, label_widget):
    """Update the formula preview label with converted display text."""
    text = edit_widget.toPlainText().strip()
    display = _formula_to_display(text)
    label_widget.setText(display if display else "")


def _clear_table(self):
    """Clear all data in the manual table."""
    table = self.manual_table
    table.setRowCount(6)
    table.setColumnCount(3)
    table.setHorizontalHeaderLabels(["A", "B", "C"])
    table.clearContents()
    _apply_equal_column_stretch(table)


def _clear_constants_table(self):
    """Clear the constants table."""
    self.constants_table.setRowCount(4)
    self.constants_table.clearContents()


def _serialize_constants_table(self) -> str:
    """Return the constants input as text digestible by ``_process_constants_lines``.

    If the text-view page is active, the edit buffer is returned verbatim so
    that comments and blank lines the user typed survive into the downstream
    parser (which ignores them). Otherwise, the QTableWidget is serialized
    into one ``Name\\tValue`` line per populated row.
    """
    stack = getattr(self, "_constants_stack", None)
    edit = getattr(self, "manual_constants_edit", None)
    if stack is not None and edit is not None and stack.currentIndex() == _STACK_PAGE_TEXT:
        return edit.toPlainText()

    table = self.constants_table
    lines = []
    for r in range(table.rowCount()):
        name_item = table.item(r, 0)
        val_item = table.item(r, 1)
        name = (name_item.text().strip() if name_item else "")
        val = (val_item.text().strip() if val_item else "")
        if name or val:
            lines.append(f"{name}\t{val}")
    return "\n".join(lines)


def _serialize_constants_table_as_text(self) -> str:
    """Render the constants table as the free-form text format.

    Produces ``name value`` pairs separated by a single space, one per line.
    Used when switching from table view to text view to seed the edit buffer
    from whatever the user has entered in the table.
    """
    table = self.constants_table
    lines = []
    for r in range(table.rowCount()):
        name_item = table.item(r, 0)
        val_item = table.item(r, 1)
        name = (name_item.text().strip() if name_item else "")
        val = (val_item.text().strip() if val_item else "")
        if name or val:
            lines.append(f"{name} {val}".strip())
    return "\n".join(lines)


def _load_text_into_constants_table(self, text: str) -> None:
    """Parse the free-form text buffer and populate the constants QTableWidget.

    Shares the line-tokenizer with ``_process_constants_lines`` in
    ``datalab_latex/latex_tables_error_propagation.py`` via
    ``shared.parsing.parse_name_value_pairs``. Lines that don't split into
    exactly two tokens are dropped here; the downstream parser still warns
    when ``verbose=True``.
    """
    from shared.parsing import parse_name_value_pairs

    pairs = parse_name_value_pairs(text or "")
    table = self.constants_table
    table.setRowCount(max(len(pairs), 4))
    table.clearContents()
    for r, (name, val) in enumerate(pairs):
        table.setItem(r, 0, QTableWidgetItem(name))
        table.setItem(r, 1, QTableWidgetItem(val))


def _toggle_constants_view(self) -> None:
    """Switch the constants input between table view and text view.

    Mirrors ``_toggle_data_view`` for the main data-input area so users
    get a consistent interaction model. Table → Text seeds the edit
    buffer from the table only when the buffer is empty (preserves any
    comments / freeform text the user has typed). Text → Table parses
    the buffer through ``_load_text_into_constants_table``.
    """
    stack = self._constants_stack
    if stack.currentIndex() == _STACK_PAGE_TABLE:
        # Table → Text: seed the edit buffer with the current table contents
        # only when the buffer is empty. Guarding BEFORE serialization avoids
        # the unnecessary table walk when the user has already typed into
        # the text view — and guarantees their comments are never clobbered.
        if not self.manual_constants_edit.toPlainText().strip():
            self.manual_constants_edit.setPlainText(
                _serialize_constants_table_as_text(self)
            )
        stack.setCurrentIndex(_STACK_PAGE_TEXT)
    else:
        # Text → Table: parse the buffer into table rows.
        _load_text_into_constants_table(self, self.manual_constants_edit.toPlainText())
        stack.setCurrentIndex(_STACK_PAGE_TABLE)
    self._constants_view_toggle.setText(_view_toggle_label(self, stack.currentIndex()))


class _TablePasteFilter(QObject):
    """Event filter that intercepts Ctrl/Cmd+V on a QTableWidget to handle CSV paste."""

    def __init__(self, table_widget, window):
        super().__init__(table_widget)
        self._table = table_widget
        self._window = window

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            from PySide6.QtGui import QKeySequence
            if event.matches(QKeySequence.StandardKey.Paste):
                clipboard = QApplication.clipboard()
                text = clipboard.text()
                if text and text.strip():
                    lines = [l for l in text.strip().split("\n") if l.strip()]
                    if len(lines) >= 2:
                        _load_text_into_table(self._window, text)
                        return True
        return super().eventFilter(obj, event)
