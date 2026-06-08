"""UI construction helpers for `ExtrapolationWindow`.

This module intentionally provides top-level `build_*` functions that accept the
window instance as the first argument (named `self`) and populate widgets on it.
It acts like a function-based mixin extracted from `window.py` to reduce file
size while keeping behavior unchanged.
"""
# ruff: noqa: F401, E741

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
from app_desktop.constants_editor import ConstantsEditor
from app_desktop.current_page_stack import CurrentPageStack
from app_desktop.detected_rows_table import DetectedRowsTable
from app_desktop.formula_preview import open_formula_preview_dialog
from app_desktop.formula_preview import update_formula_preview as _render_formula_preview
from app_desktop.parameter_table import ParameterTable
from app_desktop.parallel_preferences import (
    ParallelPreferencesStore,
    apply_parallel_config_to_widgets,
    save_current_parallel_config,
)
from app_desktop.schema_widgets import make_editor_header
from app_desktop.shell_layout import build_workbench_bar, update_workbench_status
from app_desktop.theme import (
    CONTROL_SPACING,
    SECTION_SPACING,
    is_dark_theme,
    result_style,
    table_style,
)
from app_desktop.workbench_layout import (
    build_workbench_main_splitter,
    make_status_strip,
    reparent_widget,
    scroll_viewport_overhead,
)
from app_desktop.workbench_visual_contract import CONFIG_RAIL_MIN_WIDTH
from app_desktop.ui_schema_binder import bind_choices, bind_field
from app_desktop.ui_schema_runtime import (
    bind_schema_command_button,
    register_schema_text_refresh,
)
from shared.parallel_config import NestedParallelPolicy, ParallelMode
from shared.ui_schema import ChoiceSpec, FormFieldSpec, LocalizedText
from shared.ui_specs import (
    CUSTOM_FORMULA_PARAMS,
    DESKTOP_RESULT_VIEWS,
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
_RESULT_VIEW_ORDER = (
    "result.numeric",
    "result.image",
    "result.log",
    "result.latex",
    "result.pdf",
)


def _result_view_schema_key(view_key: str) -> str:
    return view_key.replace("result.", "results.", 1)


def _result_view_alias(view_key: str) -> str:
    return view_key.split(".", 1)[1]


def _result_control_field(view_key: str, control_key: str) -> FormFieldSpec:
    for field in DESKTOP_RESULT_VIEWS[view_key].controls:
        if field.key == control_key:
            return field
    raise KeyError(f"Missing result control spec {control_key!r} for {view_key!r}")

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

def _is_dark_theme() -> bool:
    """Detect whether the current system appearance is dark."""
    return is_dark_theme()


def _get_table_style() -> str:
    return table_style()


def _get_result_style() -> str:
    return result_style()

def build_menu(self):
    menubar = self.menuBar()

    file_menu = menubar.addMenu("文件")
    self._register_text(file_menu, "文件", "File", "setTitle")

    new_workspace_action = QAction("新建工作区", self)
    new_workspace_action.setMenuRole(QAction.NoRole)
    new_workspace_action.triggered.connect(self.new_workspace)
    file_menu.addAction(new_workspace_action)
    self._register_text(new_workspace_action, "新建工作区", "New Workspace", "setText")

    open_workspace_action = QAction("打开工作区…", self)
    open_workspace_action.setMenuRole(QAction.NoRole)
    open_workspace_action.triggered.connect(self.open_workspace)
    file_menu.addAction(open_workspace_action)
    self._register_text(open_workspace_action, "打开工作区…", "Open Workspace…", "setText")

    open_example_workspace_action = QAction("打开示例工作区…", self)
    open_example_workspace_action.setMenuRole(QAction.NoRole)
    open_example_workspace_action.triggered.connect(self.open_example_workspace)
    file_menu.addAction(open_example_workspace_action)
    self._register_text(open_example_workspace_action, "打开示例工作区…", "Open Example Workspace…", "setText")

    file_menu.addSeparator()

    save_workspace_action = QAction("保存工作区", self)
    save_workspace_action.setMenuRole(QAction.NoRole)
    save_workspace_action.triggered.connect(self.save_workspace)
    file_menu.addAction(save_workspace_action)
    self._register_text(save_workspace_action, "保存工作区", "Save Workspace", "setText")

    save_workspace_as_action = QAction("工作区另存为…", self)
    save_workspace_as_action.setMenuRole(QAction.NoRole)
    save_workspace_as_action.triggered.connect(self.save_workspace_as)
    file_menu.addAction(save_workspace_as_action)
    self._register_text(save_workspace_as_action, "工作区另存为…", "Save Workspace As…", "setText")

    examples_menu = menubar.addMenu("示例")
    self._register_text(examples_menu, "示例", "Examples", "setTitle")
    examples_menu.addAction(open_example_workspace_action)

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

    auto_update_action = QAction("自动更新", self)
    auto_update_action.setMenuRole(QAction.NoRole)
    auto_update_action.setCheckable(True)
    auto_update_action.setChecked(self._update_controller.auto_update_enabled())
    auto_update_action.toggled.connect(self._set_auto_update_enabled)
    help_menu.addAction(auto_update_action)
    self._register_text(auto_update_action, "自动更新", "Automatic Updates", "setText")

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
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    self.workbench_root = QWidget()
    self.workbench_root.setObjectName("workbench_root")
    root_layout = QVBoxLayout(self.workbench_root)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(0)

    self.workbench_bar = build_workbench_bar(self)
    root_layout.addWidget(self.workbench_bar)
    self._main_splitter = build_workbench_main_splitter(self)
    root_layout.addWidget(self._main_splitter, 1)
    self.workbench_status_strip, self.workbench_status_layout = make_status_strip(self)
    update_workbench_status(self)
    root_layout.addWidget(self.workbench_status_strip)
    layout.addWidget(self.workbench_root)

    self.left_layout = self.workbench_config_layout
    self.left_container = self.workbench_config_content
    self._left_scroll = self.workbench_config_rail

    self._build_left_panel()
    reparent_widget(self.workbench_workspace_layout, self.mode_stack, stretch=1)
    reparent_widget(self.workbench_workspace_layout, self.manual_box, stretch=2)
    self._build_right_panel(self.workbench_result_layout)
    # 初始化手动输入占位示例
    self._update_manual_placeholder(self.mode_combo.currentData())
    # 根据当前模式刷新可见性
    self._on_mode_change()
    self._refresh_main_splitter_left_min_width()

    # Restore persisted splitter geometry so the user's last-chosen
    # left/right proportions survive a restart. See
    # ``shared.settings_store`` for the key naming and on-failure
    # fallback policy (defaults to the three-zone splitter sizes above).
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
            # older app version whose layout had a different pane count,
            # which Qt may accept and silently truncate.
            splitter = self._main_splitter
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
                # Accept the restore if the pane count and total-width
                # invariants still hold. The left-pane minimum is
                # dynamic and can change with language/mode/content or
                # before the window reaches its final shown size, so a
                # syntactically valid state may need to be clamped
                # rather than discarded.
                if (
                    restored_ok
                    and len(sizes_after) == splitter.count()
                    and all(s >= 0 for s in sizes_after)
                    and sum(sizes_after) > 0
                ):
                    self._refresh_main_splitter_left_min_width()
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

def _refresh_main_splitter_left_min_width(self) -> None:
    config_content = getattr(self, "workbench_config_content", None)
    config_scroll = getattr(self, "workbench_config_rail", None)
    if config_content is not None and config_scroll is not None:
        _activate_widget_layouts(config_content)
        _refresh_visible_table_min_widths(config_content)
        workspace_content = getattr(self, "workbench_workspace_content", None)
        if workspace_content is not None:
            _activate_widget_layouts(workspace_content)
            _refresh_visible_table_min_widths(workspace_content)
        _activate_widget_layouts(config_content)

        content_min_width = max(
            CONFIG_RAIL_MIN_WIDTH,
            config_content.minimumSizeHint().width(),
        )
        config_content.setMinimumWidth(content_min_width)
        left_min_width = content_min_width + scroll_viewport_overhead(config_scroll)
        self._main_splitter_left_min_width = left_min_width
        config_scroll.setMinimumWidth(left_min_width)

        splitter = getattr(self, "_main_splitter", None)
        workspace_scroll = getattr(self, "workbench_workspace_canvas", None)
        result_rail = getattr(self, "workbench_result_rail", None)
        if splitter is None or splitter.count() < 3 or workspace_scroll is None or result_rail is None:
            return

        center_min_width = max(1, workspace_scroll.minimumWidth())
        right_min_width = max(1, result_rail.minimumWidth())
        sizes = splitter.sizes()
        if not sizes or len(sizes) < 3:
            splitter.setSizes([left_min_width, center_min_width, right_min_width])
            return
        if (
            sizes[0] >= left_min_width
            and sizes[1] >= center_min_width
            and sizes[2] >= right_min_width
        ):
            return

        total = max(sum(sizes), splitter.width())
        minimum_total = left_min_width + center_min_width + right_min_width
        if total >= minimum_total:
            center_width = max(center_min_width, total - left_min_width - right_min_width)
            splitter.setSizes([left_min_width, center_width, right_min_width])
        else:
            splitter.setSizes([left_min_width, center_min_width, right_min_width])
        return

    left_container = getattr(self, "left_container", None)
    left_scroll = getattr(self, "_left_scroll", None)
    if left_container is None or left_scroll is None:
        return
    _activate_widget_layouts(left_container)
    _refresh_visible_table_min_widths(left_container)
    _activate_widget_layouts(left_container)
    viewport_overhead = (
        left_scroll.frameWidth() * 2
        + left_scroll.verticalScrollBar().sizeHint().width()
    )
    content_min_width = max(
        left_container.minimumSizeHint().width(),
        _visible_left_content_min_width(left_container),
    )
    left_min_width = max(CONFIG_RAIL_MIN_WIDTH, content_min_width) + viewport_overhead
    self._main_splitter_left_min_width = left_min_width
    left_scroll.setMinimumWidth(left_min_width)
    splitter = getattr(self, "_main_splitter", None)
    if splitter is None or splitter.count() < 2:
        return
    sizes = splitter.sizes()
    if not sizes or sizes[0] >= left_min_width:
        return
    total = max(sum(sizes), left_min_width + 1)
    right_width = max(1, total - left_min_width)
    splitter.setSizes([left_min_width, right_width])


def _activate_widget_layouts(widget: QWidget) -> None:
    layout = widget.layout()
    if layout is not None:
        layout.activate()
    for child in widget.findChildren(QWidget):
        child_layout = child.layout()
        if child_layout is not None:
            child_layout.activate()


def _visible_left_content_min_width(left_container: QWidget) -> int:
    layout = left_container.layout()
    if layout is None:
        return left_container.minimumSizeHint().width()
    margins = layout.contentsMargins()
    max_child_width = 0
    for index in range(layout.count()):
        item = layout.itemAt(index)
        widget = item.widget()
        if widget is not None and widget.isVisibleTo(left_container):
            max_child_width = max(max_child_width, widget.minimumSizeHint().width())
            continue
        nested = item.layout()
        if nested is not None:
            max_child_width = max(max_child_width, nested.minimumSize().width(), nested.sizeHint().width())
    return margins.left() + max_child_width + margins.right()


def _refresh_visible_table_min_widths(left_container: QWidget) -> None:
    for table in left_container.findChildren(QTableWidget):
        if not table.isVisibleTo(left_container):
            continue
        table.setMinimumWidth(_table_required_min_width(table))


def _table_required_min_width(table: QTableWidget) -> int:
    header = table.horizontalHeader()
    column_width = sum(max(header.sectionSizeHint(index), 72) for index in range(table.columnCount()))
    vertical_header = table.verticalHeader().sizeHint().width() if table.verticalHeader().isVisible() else 0
    scrollbar = table.verticalScrollBar().sizeHint().width()
    frame = table.frameWidth() * 2
    return column_width + vertical_header + scrollbar + frame + 8


def build_left_panel(self):
    self.input_section = QWidget()
    self.input_section.setObjectName("input_section")
    self.input_section_layout = QVBoxLayout(self.input_section)
    self.input_section_layout.setContentsMargins(0, 0, 0, 0)
    self.input_section_layout.setSpacing(CONTROL_SPACING)

    self.mode_section = QWidget()
    self.mode_section.setObjectName("mode_section")
    self.mode_section_layout = QVBoxLayout(self.mode_section)
    self.mode_section_layout.setContentsMargins(0, 0, 0, 0)
    self.mode_section_layout.setSpacing(SECTION_SPACING)

    self.output_setup_section = QWidget()
    self.output_setup_section.setObjectName("output_setup_section")
    self.output_setup_section_layout = QVBoxLayout(self.output_setup_section)
    self.output_setup_section_layout.setContentsMargins(0, 0, 0, 0)
    self.output_setup_section_layout.setSpacing(SECTION_SPACING)

    self.run_section = QWidget()
    self.run_section.setObjectName("run_section")
    self.run_section_layout = QVBoxLayout(self.run_section)
    self.run_section_layout.setContentsMargins(0, 0, 0, 0)
    self.run_section_layout.setSpacing(CONTROL_SPACING)

    self.left_layout.addWidget(self.input_section)
    self.left_layout.addWidget(self.mode_section)
    self.left_layout.addWidget(self.output_setup_section)
    self.left_layout.addWidget(self.run_section)

    # Mode selection
    self.mode_box = QGroupBox("计算模式")
    self._register_title(self.mode_box, "计算模式", "Mode")
    mode_layout = QHBoxLayout(self.mode_box)
    self.mode_combo = QComboBox()
    mode_items = [
        ("外推", "Extrapolation", "extrapolation"),
        ("误差传递", "Error propagation", "error"),
        ("拟合", "Fitting", "fitting"),
        ("求根", "Root solving", "root_solving"),
        ("统计平均", "Statistics", "statistics"),
    ]
    for zh, en, data in mode_items:
        self.mode_combo.addItem(zh, data)
    self._register_combo(self.mode_combo, mode_items)
    self._register_text(
        self.mode_combo,
        "选择当前要执行的计算模块。",
        "Choose the computation module to use.",
        "setToolTip",
    )
    self.mode_combo.currentIndexChanged.connect(self._on_mode_change)
    mode_layout.addWidget(self.mode_combo)
    self.mode_section_layout.addWidget(self.mode_box)

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
    self._register_text(
        self.use_file_checkbox,
        "启用后从文件读取数据；关闭后使用下方手动输入数据。",
        "Read data from a file when enabled; otherwise use the manual data input below.",
        "setToolTip",
    )
    self.use_file_checkbox.toggled.connect(self._on_data_source_toggle)
    source_row = QHBoxLayout()
    source_row.setSpacing(6)
    source_row.addWidget(self.use_file_checkbox)
    source_row.addStretch()
    self.input_section_layout.addLayout(source_row)
    self.input_section_layout.addWidget(self.file_box)
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
    self._register_text(
        remove_col_btn,
        "删除最后一列（含数据）",
        "Remove the last column (and its data)",
        "setToolTip",
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
    self._register_text(
        remove_row_btn,
        "删除最后一行（含数据）",
        "Remove the last row (and its data)",
        "setToolTip",
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
    self.input_section_layout.addWidget(self.manual_box)

    self.mode_stack = CurrentPageStack()
    self.mode_stack.setObjectName("mode_stack")

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

    self.extrap_method_stack = CurrentPageStack()
    self.extrap_method_stack.setObjectName("extrap_method_stack")

    self.custom_formula_widget = QWidget()
    custom_layout = QVBoxLayout(self.custom_formula_widget)
    self.custom_formula_preview_button = _make_formula_preview_button(
        self,
        self.custom_formula_edit if hasattr(self, "custom_formula_edit") else None,
        title="Preview formula",
    )
    custom_header_field = FormFieldSpec(
        key="extrapolation.custom.formula",
        widget_kind="textarea",
        label=LocalizedText("自定义公式：", "Custom formula:"),
        tooltip=LocalizedText(
            "输入自定义三点外推公式。可使用 A/B/C、列名或 x1/x2/x3，并支持数学函数。",
            "Enter a custom three-point extrapolation formula. Use A/B/C, column names, or x1/x2/x3; math functions are supported.",
        ),
        required=True,
    )
    custom_title_header = make_editor_header(
        self,
        custom_header_field,
        preview_button=self.custom_formula_preview_button,
    )
    lbl_custom = custom_title_header.schema_label
    custom_layout.addWidget(custom_title_header)
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
    self.custom_formula_preview_button.clicked.connect(
        lambda: _open_formula_preview(self, self.custom_formula_edit, lhs=None)
    )
    custom_hint_row = QHBoxLayout()
    custom_hint_row.setContentsMargins(0, 0, 0, 0)
    custom_hint_row.setSpacing(6)
    func_btn = QPushButton("函数支持")
    func_btn.setFlat(True)
    func_btn.setFocusPolicy(Qt.NoFocus)
    func_btn.clicked.connect(self._show_error_functions)
    self._register_text(func_btn, "函数支持", "Functions")
    self.custom_formula_function_button = func_btn
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

    # Power law parameters
    self.power_box = QGroupBox("幂律参数")
    self._register_title(self.power_box, "幂律参数", "Power-law parameters")
    power_layout = QFormLayout(self.power_box)
    self.power_x_edits: list[QLineEdit] = []
    power_x_labels: list[QLabel] = []
    for idx, default in enumerate((10, 20, 40), start=1):
        edit = QLineEdit(str(default))
        self.power_x_edits.append(edit)
        lbl_x = QLabel(f"x{idx}：")
        self._register_text(lbl_x, f"x{idx}：", f"x{idx}:")
        power_x_labels.append(lbl_x)
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

    self.extrap_method_stack.addWidget(self.power_box)
    self.extrap_method_stack.addWidget(self.levin_box)
    self.extrap_method_stack.addWidget(self.richardson_box)
    self.extrap_method_stack.addWidget(self.custom_formula_widget)
    extrap_layout.addWidget(self.extrap_method_stack)

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
    self.uncertainty_refresh_btn = refresh_uncert_btn
    uncert_layout.addWidget(refresh_uncert_btn)
    extrap_layout.addLayout(uncert_layout)
    _bind_extrapolation_schema_fields(
        self,
        method_label=method_label,
        lbl_custom=lbl_custom,
        power_x_labels=power_x_labels,
        lbl_p=lbl_p,
        lbl_seed=lbl_seed,
        lbl_variant=lbl_variant,
        lbl_order=lbl_order,
        lbl_weight=lbl_weight,
        lbl_beta=lbl_beta,
        lbl_richardson_p=lbl_richardson_p,
        lbl_uncert=lbl_uncert,
        combo_items=combo_items,
    )
    self.mode_stack.addWidget(self.extrap_box)

    # Error propagation settings
    self.error_box = QGroupBox("误差传递设置")
    self._register_title(self.error_box, "误差传递设置", "Error propagation")
    error_layout = QVBoxLayout(self.error_box)
    self.error_formula_preview_button = _make_formula_preview_button(
        self,
        None,
        title="Preview formula",
    )
    error_header_field = FormFieldSpec(
        key="error.formula",
        widget_kind="textarea",
        label=LocalizedText("公式：", "Formula:"),
        tooltip=LocalizedText(
            "输入误差传递公式。留空不会使用占位示例。",
            "Enter the error propagation formula. Leaving it blank does not use placeholder examples.",
        ),
        required=True,
    )
    error_formula_header = make_editor_header(
        self,
        error_header_field,
        preview_button=self.error_formula_preview_button,
    )
    lbl_error_formula = error_formula_header.schema_label
    error_layout.addWidget(error_formula_header)
    self.formula_edit = QPlainTextEdit()
    self.formula_edit.setPlaceholderText(
        self._tr("公式（使用列名或 x1, x2 …）", "Formula (use column names or x1, x2 …)")
    )
    error_layout.addWidget(self.formula_edit)
    self.error_formula_preview_button.clicked.connect(
        lambda: _open_formula_preview(self, self.formula_edit, lhs=None)
    )

    func_btn_row = QHBoxLayout()
    error_layout.setSpacing(4)
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

    self.error_constants_editor = ConstantsEditor(min_rows=4, checked=False)
    self._register_text(self.error_constants_editor.checkbox, "启用常数设置", "Enable constants")
    _register_constant_headers(self, self.error_constants_editor.set_table_headers)
    _apply_equal_column_stretch(self.error_constants_editor.table_view)
    self.error_constants_editor.table_view.setStyleSheet(_get_table_style())
    self.error_constants_editor.table_view.setMinimumHeight(160)
    self.error_constants_editor.text_view.setMinimumHeight(160)
    const_wrapper_layout.addWidget(self.error_constants_editor)
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
    _bind_error_schema_fields(
        self,
        lbl_error_formula=lbl_error_formula,
        lbl_error_method=lbl_err_method,
        error_method_items=error_method_items,
        lbl_error_order=lbl_err_order,
        lbl_mc_samples=lbl_mc_samples,
        lbl_mc_seed=lbl_mc_seed,
    )

    self.mode_stack.addWidget(self.error_box)
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
    _bind_statistics_schema_fields(
        self,
        lbl_stats_value=lbl_stats_value,
        lbl_stats_sigma=lbl_stats_sigma,
        lbl_stats_type=lbl_stats_type,
        lbl_weight_var=lbl_weight_var,
        lbl_stats_sample=lbl_stats_sample,
        stats_items=stats_items,
    )
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
    self.fit_model_combo.addItem("自洽隐式模型", "self_consistent")
    self.fit_model_combo.addItem("多项式拟合", "polynomial")
    self.fit_model_combo.addItem("1/x^p 展开", "inverse_power")
    self.fit_model_combo.addItem("Padé 拟合", "pade")
    self.fit_model_combo.addItem("幂律极限拟合", "power_limit")
    fit_items = [
        ("自定义模型（非线性）", "Custom (nonlinear)", "custom"),
        ("自洽隐式模型", "Self-consistent / implicit", "self_consistent"),
        ("多项式拟合", "Polynomial", "polynomial"),
        ("1/x^p 展开", "1/x^p series", "inverse_power"),
        ("Padé 拟合", "Padé", "pade"),
        ("幂律极限拟合", "Power limit", "power_limit"),
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
        self._register_text(
            self.fit_mcmc_refine,
            "MCMC 精炼不可用（fitting.mcmc_fitter 未安装）。pip install emcee numpy corner",
            "MCMC refinement unavailable — fitting.mcmc_fitter is not importable. pip install emcee numpy corner",
            "setToolTip",
        )
    else:
        if not _mcmc_has_emcee:
            self.fit_mcmc_refine.setEnabled(False)
            self.fit_mcmc_refine.setToolTip(self._tr(
                "需要安装 emcee 包才能启用 MCMC 精炼。"
                "pip install emcee numpy corner",
                "Install the 'emcee' package to enable MCMC "
                "refinement. pip install emcee numpy corner",
            ))
            self._register_text(
                self.fit_mcmc_refine,
                "需要安装 emcee 包才能启用 MCMC 精炼。pip install emcee numpy corner",
                "Install the 'emcee' package to enable MCMC refinement. pip install emcee numpy corner",
                "setToolTip",
            )
        else:
            self.fit_mcmc_refine.setToolTip(self._tr(
                "对最佳 AIC 模型的参数后验分布做 MCMC 采样，"
                "给出更可靠的置信区间（可能耗时 10–60 秒）。",
                "Run emcee MCMC on the best-AIC model to produce "
                "robust credible intervals (may take 10–60 s).",
            ))
            self._register_text(
                self.fit_mcmc_refine,
                "对最佳 AIC 模型的参数后验分布做 MCMC 采样，给出更可靠的置信区间（可能耗时 10–60 秒）。",
                "Run emcee MCMC on the best-AIC model to produce robust credible intervals (may take 10–60 s).",
                "setToolTip",
            )
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

    self.fit_formula_preview_button = _make_formula_preview_button(self, None, lhs="y", title="Preview formula")
    fit_expr_header_field = FormFieldSpec(
        key="fitting.custom.expression",
        widget_kind="textarea",
        label=LocalizedText("模型表达式：", "Model expression:"),
        tooltip=LocalizedText(
            "输入自定义拟合表达式。留空不会使用示例。",
            "Enter the custom fitting expression. Leaving it blank does not use the example.",
        ),
        required=True,
    )
    fit_expr_header = make_editor_header(
        self,
        fit_expr_header_field,
        preview_button=self.fit_formula_preview_button,
    )
    lbl_fit_expr = fit_expr_header.schema_label
    fit_layout.addWidget(fit_expr_header)
    self.fit_expr_edit = QPlainTextEdit("")
    self.fit_expr_edit.setPlaceholderText("自定义模型表达式，例如 A*x**(-p) + C / Custom model expression")
    fit_layout.addWidget(self.fit_expr_edit)
    self.fit_formula_preview_button.clicked.connect(
        lambda: _open_formula_preview(self, self.fit_expr_edit, lhs="y")
    )
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
    self.custom_constants_editor = ConstantsEditor(min_rows=3, checked=False, numeric_mode="mpmath")
    self._register_text(self.custom_constants_editor.checkbox, "启用常数设置", "Enable constants")
    self._register_text(
        self.custom_constants_editor.checkbox,
        "启用后在自定义拟合表达式中代入常数，并从参数识别中排除这些名称。",
        "Enable constants for the custom fit expression and exclude those names from parameter detection.",
        "setToolTip",
    )
    _register_constant_headers(self, self.custom_constants_editor.set_table_headers)
    _apply_equal_column_stretch(self.custom_constants_editor.table_view)
    self.custom_constants_editor.table_view.setStyleSheet(_get_table_style())
    self.custom_constants_editor.table_view.setMinimumHeight(120)
    custom_param_header = QHBoxLayout()
    lbl_custom_params = QLabel("参数列表：")
    self._register_text(lbl_custom_params, "参数列表：", "Parameters:")
    custom_param_header.addWidget(lbl_custom_params)
    custom_param_header.addStretch()
    self.custom_param_refresh_btn = QPushButton("识别参数")
    self._register_text(self.custom_param_refresh_btn, "识别参数", "Detect")
    self.custom_param_refresh_btn.clicked.connect(self._refresh_custom_parameter_rows)
    custom_param_header.addWidget(self.custom_param_refresh_btn)
    self.custom_param_add_btn = QPushButton("+ 行")
    self._register_text(self.custom_param_add_btn, "+ 行", "+ Row")
    self.custom_param_add_btn.clicked.connect(lambda: _add_parameter_table_row(self, "custom_params_table"))
    custom_param_header.addWidget(self.custom_param_add_btn)
    self.custom_param_remove_btn = QPushButton("- 行")
    self._register_text(self.custom_param_remove_btn, "- 行", "- Row")
    self.custom_param_remove_btn.clicked.connect(lambda: _remove_parameter_table_rows(self, "custom_params_table"))
    custom_param_header.addWidget(self.custom_param_remove_btn)
    custom_param_header_widget = QWidget()
    custom_param_header_widget.setLayout(custom_param_header)
    self.custom_param_header_widget = custom_param_header_widget
    fit_layout.addWidget(custom_param_header_widget)
    self.custom_constraints_checkbox = QCheckBox("启用参数约束")
    self.custom_constraints_checkbox.setChecked(False)
    self._register_text(self.custom_constraints_checkbox, "启用参数约束", "Enable parameter constraints")
    self._register_text(
        self.custom_constraints_checkbox,
        "启用后参数表显示固定、下界和上界列。",
        "Show fixed, lower-bound, and upper-bound columns in the parameter table.",
        "setToolTip",
    )
    fit_layout.addWidget(self.custom_constraints_checkbox)
    self.custom_params_table = ParameterTable()
    _register_table_headers(
        self,
        self.custom_params_table.set_headers,
        ("名称", "初值", "固定", "下界", "上界"),
        ("Name", "Init", "Fixed", "Min", "Max"),
    )
    self.custom_params_table.table_view.setMinimumHeight(150)
    self.custom_params_table.table_view.setStyleSheet(_get_table_style())
    _apply_equal_column_stretch(self.custom_params_table.table_view)
    self.custom_constraints_checkbox.toggled.connect(self.custom_params_table.set_constraints_enabled)
    fit_layout.addWidget(self.custom_params_table)
    fit_layout.addWidget(self.custom_constants_editor)

    self.implicit_model_widget = QGroupBox("自洽隐式模型")
    self._register_title(self.implicit_model_widget, "自洽隐式模型", "Self-consistent / implicit")
    implicit_layout = QVBoxLayout(self.implicit_model_widget)

    self.implicit_equation_edit = QPlainTextEdit("")
    self.implicit_equation_edit.setMinimumHeight(84)
    self.implicit_equation_edit.setPlaceholderText("示例：a + b*Cos[u] + c*x / Example: a + b*Cos[u] + c*x")
    self.implicit_equation_preview_button = _make_formula_preview_button(
        self,
        self.implicit_equation_edit,
        lhs=lambda: self.implicit_variable_edit.text(),
        title="Preview equation",
        object_name="implicit_equation_preview_button",
        tooltip_zh="预览方程",
    )
    implicit_equation_header_field = FormFieldSpec(
        key="fitting.implicit.equation",
        widget_kind="textarea",
        label=LocalizedText("自洽方程：", "Self-consistent equation:"),
        tooltip=LocalizedText(
            "输入自洽方程。留空不会使用示例。",
            "Enter the self-consistent equation. Leaving it blank does not use the example.",
        ),
        required=True,
    )
    implicit_equation_header = make_editor_header(
        self,
        implicit_equation_header_field,
        preview_button=self.implicit_equation_preview_button,
    )
    lbl_implicit_eq = implicit_equation_header.schema_label
    implicit_layout.addWidget(implicit_equation_header)
    implicit_layout.addWidget(self.implicit_equation_edit)

    self.implicit_output_edit = QPlainTextEdit("")
    self.implicit_output_edit.setMinimumHeight(84)
    self.implicit_output_edit.setPlaceholderText("示例：u / Example: u")
    self.implicit_output_preview_button = _make_formula_preview_button(
        self,
        self.implicit_output_edit,
        lhs="y",
        title="Preview output",
        object_name="implicit_output_preview_button",
        tooltip_zh="预览输出",
    )
    implicit_output_header_field = FormFieldSpec(
        key="fitting.implicit.output_expression",
        widget_kind="textarea",
        label=LocalizedText("输出表达式：", "Output expression:"),
        tooltip=LocalizedText(
            "输入由隐式变量和输入变量计算目标列的输出表达式。",
            "Enter the output expression that maps the implicit and input variables to the target column.",
        ),
        required=True,
    )
    implicit_output_header = make_editor_header(
        self,
        implicit_output_header_field,
        preview_button=self.implicit_output_preview_button,
    )
    lbl_implicit_output = implicit_output_header.schema_label
    implicit_layout.addWidget(implicit_output_header)
    implicit_layout.addWidget(self.implicit_output_edit)

    implicit_param_header = QHBoxLayout()
    lbl_implicit_params = QLabel("参数列表：")
    self._register_text(lbl_implicit_params, "参数列表：", "Parameters:")
    implicit_param_header.addWidget(lbl_implicit_params)
    implicit_param_header.addStretch()
    self.implicit_param_refresh_btn = QPushButton("识别参数")
    self._register_text(self.implicit_param_refresh_btn, "识别参数", "Detect")
    self.implicit_param_refresh_btn.clicked.connect(self._refresh_implicit_parameter_rows)
    implicit_param_header.addWidget(self.implicit_param_refresh_btn)
    self.implicit_param_add_btn = QPushButton("+ 行")
    self._register_text(self.implicit_param_add_btn, "+ 行", "+ Row")
    self.implicit_param_add_btn.clicked.connect(lambda: _add_parameter_table_row(self, "implicit_params_table"))
    implicit_param_header.addWidget(self.implicit_param_add_btn)
    self.implicit_param_remove_btn = QPushButton("- 行")
    self._register_text(self.implicit_param_remove_btn, "- 行", "- Row")
    self.implicit_param_remove_btn.clicked.connect(lambda: _remove_parameter_table_rows(self, "implicit_params_table"))
    implicit_param_header.addWidget(self.implicit_param_remove_btn)
    implicit_layout.addLayout(implicit_param_header)

    self.implicit_params_table = ParameterTable()
    _register_table_headers(
        self,
        self.implicit_params_table.set_headers,
        ("名称", "初值", "固定", "下界", "上界"),
        ("Name", "Init", "Fixed", "Min", "Max"),
    )
    self.implicit_params_table.table_view.setMinimumHeight(150)
    self.implicit_params_table.table_view.setStyleSheet(_get_table_style())
    _apply_equal_column_stretch(self.implicit_params_table.table_view)
    implicit_layout.addWidget(self.implicit_params_table)

    self.implicit_constraints_checkbox = QCheckBox("启用参数约束")
    self.implicit_constraints_checkbox.setChecked(False)
    self._register_text(self.implicit_constraints_checkbox, "启用参数约束", "Enable parameter constraints")
    self._register_text(
        self.implicit_constraints_checkbox,
        "启用后参数表显示固定、下界和上界列。",
        "Show fixed, lower-bound, and upper-bound columns in the parameter table.",
        "setToolTip",
    )
    self.implicit_constraints_checkbox.toggled.connect(self.implicit_params_table.set_constraints_enabled)
    implicit_layout.addWidget(self.implicit_constraints_checkbox)

    self.implicit_constants_editor = ConstantsEditor(min_rows=3, checked=True, numeric_mode="mpmath")
    self._register_text(self.implicit_constants_editor.checkbox, "启用常数设置", "Enable constants")
    self._register_text(
        self.implicit_constants_editor.checkbox,
        "启用后在自洽隐式模型中代入常数，并从参数识别中排除这些名称。",
        "Enable constants for the implicit model and exclude those names from parameter detection.",
        "setToolTip",
    )
    _register_constant_headers(self, self.implicit_constants_editor.set_table_headers)
    _apply_equal_column_stretch(self.implicit_constants_editor.table_view)
    self.implicit_constants_editor.table_view.setStyleSheet(_get_table_style())
    self.implicit_constants_editor.table_view.setMinimumHeight(120)
    implicit_layout.addWidget(self.implicit_constants_editor)

    implicit_basic_layout = QFormLayout()
    self.implicit_variable_edit = QLineEdit("u")
    lbl_implicit_var = QLabel("隐式变量：")
    self._register_text(lbl_implicit_var, "隐式变量：", "Implicit variable:")
    implicit_basic_layout.addRow(lbl_implicit_var, self.implicit_variable_edit)
    implicit_layout.addLayout(implicit_basic_layout)

    implicit_solver_layout = QFormLayout()
    self.implicit_initial_edit = QLineEdit("0.3")
    lbl_implicit_initial = QLabel("初始值：")
    self._register_text(lbl_implicit_initial, "初始值：", "Initial:")
    implicit_solver_layout.addRow(lbl_implicit_initial, self.implicit_initial_edit)
    self.implicit_tolerance_edit = QLineEdit("1e-30")
    lbl_implicit_tol = QLabel("求解容差：")
    self._register_text(lbl_implicit_tol, "求解容差：", "Tolerance:")
    implicit_solver_layout.addRow(lbl_implicit_tol, self.implicit_tolerance_edit)
    self.implicit_max_iterations_spin = QSpinBox()
    self.implicit_max_iterations_spin.setRange(1, 10000)
    self.implicit_max_iterations_spin.setValue(80)
    lbl_implicit_iter = QLabel("最大迭代：")
    self._register_text(lbl_implicit_iter, "最大迭代：", "Max iterations:")
    implicit_solver_layout.addRow(lbl_implicit_iter, self.implicit_max_iterations_spin)
    self.implicit_method_combo = QComboBox()
    implicit_method_items = [
        ("固定点", "Fixed point", "fixed_point"),
        ("求根", "Root", "root"),
    ]
    for zh, en, data in implicit_method_items:
        self.implicit_method_combo.addItem(zh, data)
    self._register_combo(self.implicit_method_combo, implicit_method_items)
    lbl_implicit_method = QLabel("求解方法：")
    self._register_text(lbl_implicit_method, "求解方法：", "Method:")
    implicit_solver_layout.addRow(lbl_implicit_method, self.implicit_method_combo)
    self.implicit_timeout_spin = QSpinBox()
    self.implicit_timeout_spin.setRange(0, 86400)
    self.implicit_timeout_spin.setValue(300)
    self.implicit_timeout_spin.setToolTip(self._tr("0 表示不自动超时，只能手动停止。", "0 disables automatic timeout; use Stop to cancel."))
    lbl_implicit_timeout = QLabel("最长运行秒数：")
    self._register_text(lbl_implicit_timeout, "最长运行秒数：", "Max runtime (s):")
    implicit_solver_layout.addRow(lbl_implicit_timeout, self.implicit_timeout_spin)
    implicit_layout.addLayout(implicit_solver_layout)
    fit_layout.addWidget(self.implicit_model_widget)
    self.implicit_model_widget.hide()
    _bind_fitting_schema_fields(
        self,
        lbl_model=lbl_model,
        fit_items=fit_items,
        lbl_fit_expr=lbl_fit_expr,
        lbl_implicit_eq=lbl_implicit_eq,
        lbl_implicit_output=lbl_implicit_output,
        lbl_implicit_var=lbl_implicit_var,
        lbl_implicit_initial=lbl_implicit_initial,
        lbl_implicit_tol=lbl_implicit_tol,
        lbl_implicit_iter=lbl_implicit_iter,
        lbl_implicit_method=lbl_implicit_method,
        implicit_method_items=implicit_method_items,
        lbl_implicit_timeout=lbl_implicit_timeout,
        lbl_custom_params=lbl_custom_params,
        lbl_implicit_params=lbl_implicit_params,
    )

    var_header = QHBoxLayout()
    lbl_varmap = QLabel("变量映射：")
    self._register_text(lbl_varmap, "变量映射：", "Variable mapping:")
    var_header.addWidget(lbl_varmap)
    var_header.addStretch()
    self.add_variable_btn = QPushButton("+")
    self.add_variable_btn.setFixedWidth(28)
    self.add_variable_btn.setToolTip(self._tr("添加变量映射", "Add variable mapping"))
    self._register_text(self.add_variable_btn, "添加变量映射", "Add variable mapping", "setToolTip")
    self.add_variable_btn.clicked.connect(self._add_variable_row)
    var_header.addWidget(self.add_variable_btn)
    self.remove_variable_btn = QPushButton("-")
    self.remove_variable_btn.setFixedWidth(28)
    self.remove_variable_btn.setToolTip(self._tr("删除最后一个变量映射", "Remove last variable mapping"))
    self._register_text(
        self.remove_variable_btn,
        "删除最后一个变量映射",
        "Remove last variable mapping",
        "setToolTip",
    )
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
    self._register_text(
        self.fit_target_edit,
        "目标列是拟合时要匹配的观测数据列。",
        "Target column is the observed data column matched by the fit.",
        "setToolTip",
    )
    target_row.addWidget(self.fit_target_edit)
    fit_layout.addLayout(target_row)

    weight_row = QHBoxLayout()
    lbl_weight_mode = QLabel("统计/系统：")
    self._register_text(lbl_weight_mode, "统计/系统：", "Stat./System:")
    weight_row.addWidget(lbl_weight_mode)
    self.fit_weighted_checkbox = QCheckBox("统计误差加权")
    self._register_text(self.fit_weighted_checkbox, "统计误差加权", "Statistical weighting (sigma)")
    self._register_text(
        self.fit_weighted_checkbox,
        "启用后使用目标列中的统计不确定度作为拟合权重。",
        "Use statistical uncertainties in the target column as fit weights when enabled.",
        "setToolTip",
    )
    weight_row.addWidget(self.fit_weighted_checkbox)
    fit_layout.addLayout(weight_row)

    self.mode_stack.addWidget(self.fit_box)
    self.inverse_min_spin.valueChanged.connect(self._on_model_settings_changed)
    self.inverse_max_spin.valueChanged.connect(self._on_model_settings_changed)
    self.pade_m_spin.valueChanged.connect(self._on_model_settings_changed)
    self.pade_n_spin.valueChanged.connect(self._on_model_settings_changed)
    self.poly_degree_spin.valueChanged.connect(self._on_model_settings_changed)

    # Root-solving module
    self.root_box = QGroupBox("求根")
    self._register_title(self.root_box, "求根", "Root solving")
    root_layout = QVBoxLayout(self.root_box)

    self.root_equations_help_button = _make_small_help_button()
    self.root_formula_preview_button = _make_formula_preview_button(
        self,
        None,
        title="Preview equations",
        object_name="root_formula_preview_button",
        tooltip_zh="预览方程",
    )
    self.root_formula_preview_button.clicked.connect(lambda: _open_root_formula_preview(self))
    root_equation_header_field = FormFieldSpec(
        key="root.equations",
        widget_kind="textarea",
        label=LocalizedText("方程：", "Equations:"),
        tooltip=LocalizedText(
            "输入要求解的方程。留空不会使用示例；示例只显示在背景提示中。",
            "Enter equations to solve. Leaving it blank does not use the example; the example is only placeholder text.",
        ),
        required=True,
    )
    root_equation_header = make_editor_header(
        self,
        root_equation_header_field,
        preview_button=self.root_formula_preview_button,
        help_button=self.root_equations_help_button,
    )
    lbl_root_equations = root_equation_header.schema_label
    root_layout.addWidget(root_equation_header)

    self.root_equations_edit = QPlainTextEdit()
    self.root_equations_edit.setMinimumHeight(96)
    self.root_equations_edit.setPlaceholderText(
        "每行一个方程，按 F_i(...)=0 求解；示例：x^2 - A / One equation per line as F_i(...)=0; example: x^2 - A"
    )
    root_layout.addWidget(self.root_equations_edit)

    root_mode_layout = QFormLayout()
    self.root_mode_combo = QComboBox()
    root_mode_items = [
        ("标量", "Scalar", "scalar"),
        ("扫描多根", "Scan multiple roots", "scan_multiple"),
        ("多项式", "Polynomial", "polynomial"),
        ("方程组", "System", "system"),
    ]
    for zh, _en, data in root_mode_items:
        self.root_mode_combo.addItem(zh, data)
    self._register_combo(self.root_mode_combo, root_mode_items)
    lbl_root_mode = QLabel("求解模式：")
    self._register_text(lbl_root_mode, "求解模式：", "Solve mode:")
    root_mode_row = QHBoxLayout()
    root_mode_row.addWidget(self.root_mode_combo)
    self.root_mode_help_button = _make_small_help_button()
    root_mode_row.addWidget(self.root_mode_help_button)
    root_mode_row.addStretch()
    root_mode_layout.addRow(lbl_root_mode, root_mode_row)
    root_layout.addLayout(root_mode_layout)

    root_unknown_header = QHBoxLayout()
    lbl_root_unknowns = QLabel("未知量：")
    self._register_text(lbl_root_unknowns, "未知量：", "Unknowns:")
    root_unknown_header.addWidget(lbl_root_unknowns)
    self.root_unknowns_help_button = _make_small_help_button()
    root_unknown_header.addWidget(self.root_unknowns_help_button)
    root_unknown_header.addStretch()
    self.root_detect_unknowns_button = QPushButton("识别未知量")
    self._register_text(self.root_detect_unknowns_button, "识别未知量", "Detect")
    self.root_detect_unknowns_button.setToolTip(self._tr("从方程中识别未知量", "Detect unknowns from equations"))
    self.root_detect_unknowns_button.clicked.connect(self._refresh_root_unknown_rows)
    root_unknown_header.addWidget(self.root_detect_unknowns_button)
    self.root_add_unknown_button = QPushButton("+ 行")
    self._register_text(self.root_add_unknown_button, "+ 行", "+ Row")
    self.root_add_unknown_button.setToolTip(self._tr("手动添加未知量行", "Add an unknown row"))
    self.root_add_unknown_button.clicked.connect(lambda: _add_detected_rows_table_row(self, "root_unknowns_table"))
    root_unknown_header.addWidget(self.root_add_unknown_button)
    self.root_remove_unknown_button = QPushButton("- 行")
    self._register_text(self.root_remove_unknown_button, "- 行", "- Row")
    self.root_remove_unknown_button.setToolTip(self._tr("删除选中的未知量行", "Remove selected unknown rows"))
    self.root_remove_unknown_button.clicked.connect(lambda: _remove_detected_rows_table_rows(self, "root_unknowns_table"))
    root_unknown_header.addWidget(self.root_remove_unknown_button)
    root_layout.addLayout(root_unknown_header)

    self.root_unknowns_table = DetectedRowsTable(
        columns=("name", "initial", "lower", "upper"),
        headers=("名称", "初始值", "下界", "上界"),
        min_rows=2,
    )
    _register_table_headers(
        self,
        self.root_unknowns_table.set_headers,
        ("名称", "初始值", "下界", "上界"),
        ("Name", "Initial", "Lower", "Upper"),
    )
    self.root_unknowns_table.table_view.setMinimumHeight(140)
    self.root_unknowns_table.table_view.setStyleSheet(_get_table_style())
    _apply_equal_column_stretch(self.root_unknowns_table.table_view)
    root_layout.addWidget(self.root_unknowns_table)

    self.root_constants_editor = ConstantsEditor(min_rows=3, checked=False, numeric_mode="uncertainty")
    self._register_text(self.root_constants_editor.checkbox, "启用常数设置", "Enable constants")
    _register_constant_headers(self, self.root_constants_editor.set_table_headers)
    _apply_equal_column_stretch(self.root_constants_editor.table_view)
    self.root_constants_editor.table_view.setStyleSheet(_get_table_style())
    self.root_constants_editor.table_view.setMinimumHeight(120)
    root_layout.addWidget(self.root_constants_editor)
    _bind_root_schema_fields(self, lbl_root_equations, lbl_root_mode, lbl_root_unknowns, root_mode_items)
    _refresh_root_field_help(self)

    self.root_uncertainty_group = QGroupBox("根的不确定度传播")
    self._register_title(self.root_uncertainty_group, "根的不确定度传播", "Root uncertainty propagation")
    root_uncertainty_layout = QFormLayout(self.root_uncertainty_group)
    self.root_uncertainty_method_combo = QComboBox()
    root_uncertainty_method_items = [
        ("Taylor（偏导）", "Taylor (derivative)", "taylor"),
        ("Monte Carlo", "Monte Carlo", "monte_carlo"),
        ("关闭", "Off", "off"),
    ]
    for zh, _en, data in root_uncertainty_method_items:
        self.root_uncertainty_method_combo.addItem(zh, data)
    self._register_combo(self.root_uncertainty_method_combo, root_uncertainty_method_items)
    self._register_text(
        self.root_uncertainty_method_combo,
        "选择根的不确定度传播方式；关闭时只求数值根。",
        "Choose how root uncertainties are propagated; Off solves numeric roots only.",
        "setToolTip",
    )
    lbl_root_uncertainty_method = QLabel("方法：")
    self._register_text(lbl_root_uncertainty_method, "方法：", "Method:")
    root_uncertainty_layout.addRow(lbl_root_uncertainty_method, self.root_uncertainty_method_combo)

    self.root_uncertainty_taylor_widget = QWidget()
    root_taylor_layout = QHBoxLayout(self.root_uncertainty_taylor_widget)
    root_taylor_layout.setContentsMargins(0, 0, 0, 0)
    root_taylor_layout.setSpacing(6)
    self.root_uncertainty_order_label = QLabel("阶数：")
    self._register_text(self.root_uncertainty_order_label, "阶数：", "Order:")
    self.root_uncertainty_order_spin = QSpinBox()
    self.root_uncertainty_order_spin.setRange(1, 2)
    self.root_uncertainty_order_spin.setValue(1)
    self.root_uncertainty_order_spin.setToolTip(
        self._tr(
            "1 阶：隐函数线性传播；2 阶：对标量实根使用二阶有限差分传播。",
            "Order 1: linear implicit propagation; order 2: scalar second-order finite-difference propagation.",
        )
    )
    self._register_text(
        self.root_uncertainty_order_spin,
        "1 阶：隐函数线性传播；2 阶：对标量实根使用二阶有限差分传播。",
        "Order 1: linear implicit propagation; order 2: scalar second-order finite-difference propagation.",
        "setToolTip",
    )
    root_taylor_layout.addWidget(self.root_uncertainty_order_label)
    root_taylor_layout.addWidget(self.root_uncertainty_order_spin)
    root_taylor_layout.addStretch()
    root_uncertainty_layout.addRow("", self.root_uncertainty_taylor_widget)

    self.root_monte_carlo_samples_label = QLabel("样本数：")
    self._register_text(self.root_monte_carlo_samples_label, "样本数：", "Samples:")
    self.root_monte_carlo_samples_spin = QSpinBox()
    self.root_monte_carlo_samples_spin.setRange(100, 50000)
    self.root_monte_carlo_samples_spin.setValue(2000)
    self._register_text(
        self.root_monte_carlo_samples_spin,
        "Monte Carlo 抽样次数；数值越大越稳定但越慢。",
        "Monte Carlo sample count; larger values are more stable but slower.",
        "setToolTip",
    )
    root_uncertainty_layout.addRow(self.root_monte_carlo_samples_label, self.root_monte_carlo_samples_spin)

    self.root_monte_carlo_seed_label = QLabel("随机种子：")
    self._register_text(self.root_monte_carlo_seed_label, "随机种子：", "Seed:")
    self.root_monte_carlo_seed_edit = QLineEdit()
    root_uncertainty_layout.addRow(self.root_monte_carlo_seed_label, self.root_monte_carlo_seed_edit)

    self.root_uncertainty_method_help_label = QLabel()
    self.root_uncertainty_method_help_label.setWordWrap(True)
    root_uncertainty_layout.addRow(self.root_uncertainty_method_help_label)
    self.root_uncertainty_method_combo.currentIndexChanged.connect(
        lambda _index: _on_root_uncertainty_method_changed(self)
    )
    root_layout.addWidget(self.root_uncertainty_group)
    _on_root_uncertainty_method_changed(self)

    self.mode_stack.addWidget(self.root_box)
    self.mode_stack.addWidget(self.stats_box)

    # Options
    options_box = QGroupBox("选项")
    self.options_box = options_box
    self._register_title(options_box, "选项", "Options")
    options_layout = QVBoxLayout(options_box)
    precision_layout = QHBoxLayout()
    label_precision = QLabel("数值精度位数：")
    self._register_text(label_precision, "数值精度位数：", "Precision digits:")
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

    parallel_layout = QFormLayout()
    self.parallel_mode_combo = QComboBox()
    parallel_mode_items = [
        ("自动", "Auto", ParallelMode.AUTO.value),
        ("串行优先", "Prefer serial", ParallelMode.SERIAL.value),
        ("线程优先", "Prefer threads", ParallelMode.THREAD.value),
        ("进程优先", "Prefer processes", ParallelMode.PROCESS.value),
    ]
    for zh, _en, data in parallel_mode_items:
        self.parallel_mode_combo.addItem(zh, data)
    self._register_combo(self.parallel_mode_combo, parallel_mode_items)
    self.parallel_mode_combo.setToolTip("资源调度偏好；需要快速取消和隔离的任务仍会使用独立进程。")
    lbl_parallel_mode = QLabel("资源策略：")
    self._register_text(lbl_parallel_mode, "资源策略：", "Resource policy:")
    parallel_layout.addRow(lbl_parallel_mode, self.parallel_mode_combo)

    worker_row = QHBoxLayout()
    self.parallel_max_workers_spin = QSpinBox()
    self.parallel_max_workers_spin.setRange(0, 1024)
    self.parallel_max_workers_spin.setValue(0)
    self.parallel_max_workers_spin.setToolTip("0 = auto")
    self.parallel_reserve_cores_spin = QSpinBox()
    self.parallel_reserve_cores_spin.setRange(0, 1024)
    self.parallel_reserve_cores_spin.setValue(1)
    lbl_parallel_workers = QLabel("最大 workers：")
    self._register_text(lbl_parallel_workers, "最大 workers：", "Max workers:")
    lbl_parallel_reserve = QLabel("保留核心：")
    self._register_text(lbl_parallel_reserve, "保留核心：", "Reserve cores:")
    worker_row.addWidget(lbl_parallel_workers)
    worker_row.addWidget(self.parallel_max_workers_spin)
    worker_row.addSpacing(12)
    worker_row.addWidget(lbl_parallel_reserve)
    worker_row.addWidget(self.parallel_reserve_cores_spin)
    worker_row.addStretch()
    parallel_layout.addRow(worker_row)

    self.parallel_nested_policy_combo = QComboBox()
    nested_policy_items = [
        (
            "嵌套时串行",
            "Serial when nested",
            NestedParallelPolicy.SERIAL_WHEN_NESTED.value,
        ),
        ("允许嵌套", "Allow nested", NestedParallelPolicy.ALLOW.value),
    ]
    for zh, _en, data in nested_policy_items:
        self.parallel_nested_policy_combo.addItem(zh, data)
    self._register_combo(self.parallel_nested_policy_combo, nested_policy_items)
    lbl_nested_policy = QLabel("嵌套策略：")
    self._register_text(lbl_nested_policy, "嵌套策略：", "Nested policy:")
    parallel_layout.addRow(lbl_nested_policy, self.parallel_nested_policy_combo)

    options_layout.addLayout(parallel_layout)

    try:
        from shared.settings_store import SettingsStore

        settings = getattr(self, "_settings_store", None)
        if settings is None:
            settings = SettingsStore()
            self._settings_store = settings
        apply_parallel_config_to_widgets(
            self,
            ParallelPreferencesStore(settings).load(),
        )
    except Exception:
        import logging

        logging.getLogger(__name__).debug(
            "Parallel preferences restore skipped", exc_info=True
        )

    self.parallel_mode_combo.currentIndexChanged.connect(
        lambda _index: save_current_parallel_config(self)
    )
    self.parallel_max_workers_spin.valueChanged.connect(
        lambda _value: save_current_parallel_config(self)
    )
    self.parallel_reserve_cores_spin.valueChanged.connect(
        lambda _value: save_current_parallel_config(self)
    )
    self.parallel_nested_policy_combo.currentIndexChanged.connect(
        lambda _index: save_current_parallel_config(self)
    )
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
    self.output_browse_button = out_btn
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
    _bind_global_options_schema_fields(
        self,
        label_precision=label_precision,
        unc_label=unc_label,
        lbl_parallel_mode=lbl_parallel_mode,
        lbl_parallel_workers=lbl_parallel_workers,
        lbl_parallel_reserve=lbl_parallel_reserve,
        lbl_nested_policy=lbl_nested_policy,
        parallel_mode_items=parallel_mode_items,
        nested_policy_items=nested_policy_items,
        lbl_output=lbl_output,
        prec_label=prec_label,
        group_size_label=group_size_label,
    )

    # NOTE: ``latex_engine_combo`` + the engine-path picker were moved
    # into the LaTeX output tab (next to the font-size row) because
    # they're compile-time, not compute-time, controls. The widgets
    # are still created on ``self`` so other code paths
    # (window_latex_pdf_mixin.compile_latex_to_pdf) keep working
    # unchanged — they reference ``self.latex_engine_combo``.

    self.output_setup_section_layout.addWidget(options_box)

    self.run_button = QPushButton("开始执行")
    self._register_text(self.run_button, "开始执行", "Run")
    self.run_button.clicked.connect(lambda _checked=False: self.run_calculation())
    self.run_section_layout.addWidget(self.run_button)
    self._update_model_controls()

def build_right_panel(self, layout: QVBoxLayout):
    self.tabs = QTabWidget()
    self.tabs.setProperty("datalab_schema_key", "main.result_tabs")
    layout.addWidget(self.tabs)

    # Result tab
    result_widget = QWidget()
    result_layout = QVBoxLayout(result_widget)
    self.result_tabs = QTabWidget()
    result_layout.addWidget(self.result_tabs)
    self.result_tabs.setProperty("datalab_schema_key", "results.tabs")
    result_view_specs = {
        _result_view_alias(view_key): {
            "schema_key": _result_view_schema_key(spec.key),
            "attachment_key": spec.attachment_key,
            "raw_columns": tuple(spec.raw_columns),
            "display_columns": tuple(spec.display_columns),
            "controls": tuple(field.key for field in spec.controls),
        }
        for view_key, spec in DESKTOP_RESULT_VIEWS.items()
        if view_key in _RESULT_VIEW_ORDER
    }
    self.result_tabs.setProperty(
        "datalab_schema_tabs",
        {
            _result_view_alias(view_key): _result_view_schema_key(DESKTOP_RESULT_VIEWS[view_key].key)
            for view_key in _RESULT_VIEW_ORDER
        },
    )
    self.result_tabs.setProperty("datalab_result_view_specs", result_view_specs)
    self.result_tab_titles = {
        _result_view_alias(view_key): DESKTOP_RESULT_VIEWS[view_key].title.zh
        for view_key in _RESULT_VIEW_ORDER
    }

    numeric_tab = QWidget()
    numeric_layout = QVBoxLayout(numeric_tab)
    self.result_edit = QTextBrowser()
    self.result_edit.setProperty("datalab_schema_key", "results.numeric.markdown")
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
    numeric_spec = DESKTOP_RESULT_VIEWS["result.numeric"]
    numeric_index = self.result_tabs.addTab(numeric_tab, numeric_spec.title.zh)
    self.result_tabs.setTabToolTip(numeric_index, numeric_spec.title.zh)
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
    self.result_plot_zoom_spin = self.zoom_percent_spin
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
    self.result_plot_page_spin = self.image_page_spin
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
    self.result_plot_scroll.setProperty("datalab_schema_key", "results.image.preview")
    self.result_plot_scroll.setWidgetResizable(False)
    self.result_plot_scroll.setAlignment(Qt.AlignCenter)
    self.result_plot_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    self.result_plot_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    self.result_plot_label = QLabel(self._tr("尚无图片", "No image yet"))
    self.result_plot_label.setProperty("datalab_schema_key", "results.image.preview")
    self.result_plot_label.setAlignment(Qt.AlignCenter)
    self.result_plot_label.setMinimumHeight(320)
    self.result_plot_scroll.setWidget(self.result_plot_label)
    image_layout.addWidget(self.result_plot_scroll)
    image_spec = DESKTOP_RESULT_VIEWS["result.image"]
    image_index = self.result_tabs.addTab(image_tab, image_spec.title.zh)
    self.result_tabs.setTabToolTip(image_index, image_spec.title.zh)

    self.result_tab_index = self.tabs.addTab(result_widget, "结果")
    self.main_tab_titles = {
        "result": "结果",
    }
    # Tab texts handled via QTabWidget defaults
    self._update_log_scale_visibility()

    # Log result view
    log_widget = QWidget()
    log_layout = QVBoxLayout(log_widget)
    self.log_edit = QPlainTextEdit()
    self.log_edit.setProperty("datalab_schema_key", "results.log")
    self.log_edit.setReadOnly(True)
    self._add_font_control_row(log_layout, self.log_edit, "字体大小：")
    log_layout.addWidget(self.log_edit)
    log_spec = DESKTOP_RESULT_VIEWS["result.log"]
    self.log_tab_index = self.result_tabs.addTab(log_widget, log_spec.title.zh)
    self.result_tabs.setTabToolTip(self.log_tab_index, log_spec.title.zh)

    # LaTeX result view
    latex_widget = QWidget()
    latex_layout = QVBoxLayout(latex_widget)
    toolbar = QHBoxLayout()
    open_btn = QPushButton("打开…")
    open_btn.clicked.connect(self.open_latex_file)
    self._register_text(open_btn, "打开…", "Open…")
    self.latex_open_button = open_btn
    toolbar.addWidget(open_btn)
    save_btn = QPushButton("保存")
    save_btn.clicked.connect(self.save_latex_editor)
    self._register_text(save_btn, "保存", "Save")
    self.latex_save_button = save_btn
    toolbar.addWidget(save_btn)
    reload_btn = QPushButton("重新载入")
    reload_btn.clicked.connect(lambda: self.reload_latex_editor(show_message=True))
    self._register_text(reload_btn, "重新载入", "Reload")
    self.latex_reload_button = reload_btn
    toolbar.addWidget(reload_btn)
    compile_btn = QPushButton("编译 PDF")
    compile_btn.clicked.connect(self.compile_latex_to_pdf)
    self._register_text(compile_btn, "编译 PDF", "Compile PDF")
    self.latex_compile_button = compile_btn
    toolbar.addWidget(compile_btn)
    view_btn = QPushButton("查看 PDF")
    view_btn.clicked.connect(self.open_compiled_pdf)
    self._register_text(view_btn, "查看 PDF", "View PDF")
    self.latex_view_pdf_button = view_btn
    toolbar.addWidget(view_btn)
    toolbar.addStretch()
    self.latex_status_label = QLabel("未加载 LaTeX 文件")
    self.latex_status_label.setProperty("datalab_schema_key", "results.latex.status")
    self._register_text(self.latex_status_label, "未加载 LaTeX 文件", "No LaTeX loaded")
    toolbar.addWidget(self.latex_status_label)
    latex_layout.addLayout(toolbar)
    from app_desktop.numbered_text_edit import NumberedTextEdit

    # ``NumberedTextEdit`` is a ``QPlainTextEdit`` with a left-margin
    # line-number gutter — needed because Tectonic / pdflatex error
    # messages reference line numbers (``error: 1.tex:57: ...``) and
    # users have to find the offending line by scrolling without that.
    self.latex_edit = NumberedTextEdit()
    self.latex_edit.setProperty("datalab_schema_key", "results.latex.source")
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
    self._register_text(
        lbl_font,
        "调整 LaTeX 源码视图的显示字体大小。",
        "Adjust the display font size for the LaTeX source view.",
        "setToolTip",
    )
    latex_controls_row.addWidget(lbl_font)
    latex_font_spin = QSpinBox()
    latex_font_spin.setRange(8, 32)
    _default_size = self.latex_edit.font().pointSize()
    latex_font_spin.setValue(max(8, _default_size if _default_size > 0 else 12))
    latex_font_spin.setToolTip(
        self._tr(
            "调整 LaTeX 源码视图的显示字体大小。",
            "Adjust the display font size for the LaTeX source view.",
        )
    )
    self._register_text(
        latex_font_spin,
        "调整 LaTeX 源码视图的显示字体大小。",
        "Adjust the display font size for the LaTeX source view.",
        "setToolTip",
    )
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
    self.latex_engine_path_button = engine_btn
    latex_controls_row.addWidget(engine_btn)
    latex_controls_row.addStretch()
    latex_layout.addLayout(latex_controls_row)

    latex_layout.addWidget(self.latex_edit)
    latex_spec = DESKTOP_RESULT_VIEWS["result.latex"]
    latex_index = self.result_tabs.addTab(latex_widget, latex_spec.title.zh)
    self.result_tabs.setTabToolTip(latex_index, latex_spec.title.zh)

    # PDF result view
    pdf_widget = QWidget()
    pdf_layout = QVBoxLayout(pdf_widget)
    pdf_toolbar = QHBoxLayout()
    self.pdf_status_label = QLabel("暂无 PDF 预览")
    self.pdf_status_label.setProperty("datalab_schema_key", "results.pdf.status")
    self._register_text(self.pdf_status_label, "暂无 PDF 预览", "No PDF preview")
    pdf_toolbar.addWidget(self.pdf_status_label)
    pdf_toolbar.addStretch()
    zoom_out_btn = QPushButton()
    self._register_text(zoom_out_btn, "缩小", "Zoom out", "setToolTip")
    self._set_zoom_icon(zoom_out_btn, "out")
    self._style_round_icon_button(zoom_out_btn)
    zoom_out_btn.clicked.connect(lambda: self._apply_pdf_zoom(self.pdf_zoom * 0.75))
    self.pdf_zoom_out_button = zoom_out_btn
    pdf_toolbar.addWidget(zoom_out_btn)
    zoom_in_btn = QPushButton()
    self._register_text(zoom_in_btn, "放大", "Zoom in", "setToolTip")
    self._set_zoom_icon(zoom_in_btn, "in")
    self._style_round_icon_button(zoom_in_btn)
    zoom_in_btn.clicked.connect(lambda: self._apply_pdf_zoom(self.pdf_zoom * 1.25))
    self.pdf_zoom_in_button = zoom_in_btn
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
    self.pdf_zoom_reset_button = reset_zoom_btn
    pdf_toolbar.addWidget(reset_zoom_btn)
    pdf_layout.addLayout(pdf_toolbar)

    self.pdf_scroll = QScrollArea()
    self.pdf_scroll.setWidgetResizable(True)
    self.pdf_container = QWidget()
    self.pdf_container_layout = QVBoxLayout(self.pdf_container)
    self.pdf_container_layout.setAlignment(Qt.AlignTop)
    self.pdf_scroll.setWidget(self.pdf_container)
    pdf_layout.addWidget(self.pdf_scroll)
    pdf_spec = DESKTOP_RESULT_VIEWS["result.pdf"]
    pdf_index = self.result_tabs.addTab(pdf_widget, pdf_spec.title.zh)
    self.result_tabs.setTabToolTip(pdf_index, pdf_spec.title.zh)
    _bind_result_latex_pdf_schema_fields(
        self,
        lbl_digits=lbl_digits,
        lbl_engine=lbl_engine,
        lbl_zoom=lbl_zoom,
    )
    # record tab indexes for translation
    self.result_tabs_indices = {
        _result_view_alias(view_key): index
        for index, view_key in enumerate(_RESULT_VIEW_ORDER)
    }
    _bind_result_area_schema_fields(self)
    self.main_tabs_indices = {
        "result": self.tabs.indexOf(result_widget),
    }
    self.tabs.setProperty(
        "datalab_schema_tabs",
        {
            "result": "results.overview",
        },
    )
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
    raw_rows = result.raw_rows or [["" for _ in row] for row in result.rows]
    for r, row in enumerate(result.rows):
        raw_row = raw_rows[r] if r < len(raw_rows) else []
        for c, val in enumerate(row):
            raw_cell = raw_row[c].strip() if c < len(raw_row) else ""
            if val is None:
                cell_text = raw_cell
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


def _update_formula_preview(self, edit_widget, label_widget, lhs=None):
    """Update the formula preview label through the shared renderer."""
    if hasattr(edit_widget, "toPlainText"):
        text = edit_widget.toPlainText().strip()
    else:
        text = edit_widget.text().strip()
    left_hand_side = lhs() if callable(lhs) else lhs
    _render_formula_preview(label_widget, text, lhs=left_hand_side)


def _make_formula_preview_button(
    self,
    edit_widget=None,
    lhs=None,
    title: str = "Preview formula",
    *,
    object_name: str = "",
    tooltip_zh: str = "预览公式",
):
    button = QPushButton("Preview")
    if object_name:
        button.setObjectName(object_name)
    button.setFocusPolicy(Qt.NoFocus)
    button.setProperty("datalab_preserve_tooltip", True)
    button.setToolTip(title)
    button.setAccessibleName(button.text())
    button.setAccessibleDescription(title)
    self._register_text(button, "预览", "Preview")
    self._register_text(button, tooltip_zh, title, "setToolTip")
    self._register_text(button, "预览", "Preview", "setAccessibleName")
    self._register_text(button, tooltip_zh, title, "setAccessibleDescription")
    if edit_widget is not None:
        button.clicked.connect(lambda: _open_formula_preview(self, edit_widget, lhs=lhs))
    return button


class _HeaderRegistration:
    def __init__(self, setter):
        self._setter = setter

    def set_headers(self, headers) -> None:
        self._setter(headers)

    def set_table_headers(self, headers) -> None:
        self._setter(*headers)


def _register_table_headers(self, setter, zh_headers: tuple[str, ...], en_headers: tuple[str, ...]) -> None:
    registration = _HeaderRegistration(setter)
    registration.set_headers(zh_headers if not bool(getattr(self, "_is_en", lambda: False)()) else en_headers)
    self._register_text(registration, zh_headers, en_headers, "set_headers")


def _register_constant_headers(
    self,
    setter,
    zh_headers: tuple[str, str] = ("名称", "值"),
    en_headers: tuple[str, str] = ("Name", "Value"),
) -> None:
    registration = _HeaderRegistration(setter)
    registration.set_table_headers(zh_headers if not bool(getattr(self, "_is_en", lambda: False)()) else en_headers)
    self._register_text(registration, zh_headers, en_headers, "set_table_headers")


def _make_small_help_button() -> QPushButton:
    button = QPushButton("?")
    button.setFlat(True)
    button.setFocusPolicy(Qt.NoFocus)
    button.setFixedWidth(24)
    return button


def _register_schema_label_refresh(self, label: QLabel, field: FormFieldSpec) -> None:
    self._register_text(label, field.label.zh, field.label.en, "setText")
    if field.tooltip.zh or field.tooltip.en:
        self._register_text(label, field.tooltip.zh, field.tooltip.en, "setToolTip")


def _bind_extrapolation_schema_fields(
    self,
    *,
    method_label: QLabel,
    lbl_custom: QLabel,
    power_x_labels: list[QLabel],
    lbl_p: QLabel,
    lbl_seed: QLabel,
    lbl_variant: QLabel,
    lbl_order: QLabel,
    lbl_weight: QLabel,
    lbl_beta: QLabel,
    lbl_richardson_p: QLabel,
    lbl_uncert: QLabel,
    combo_items: list[tuple[str, str, str]],
) -> None:
    lang = "en" if bool(getattr(self, "_is_en", lambda: False)()) else "zh"
    method_field = FormFieldSpec(
        key="extrapolation.method",
        widget_kind="select",
        label=LocalizedText("外推方法：", "Method:"),
        tooltip=LocalizedText(
            "选择外推算法。不同方法会显示对应的参数设置。",
            "Choose the extrapolation algorithm. Different methods show their relevant parameter settings.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in combo_items
        ],
    )
    method_help_field = FormFieldSpec(
        key="extrapolation.method",
        widget_kind="button",
        label=LocalizedText("外推方法帮助", "Extrapolation method help"),
        tooltip=LocalizedText(
            "点击查看当前外推方法的详细说明、适用场景和参数解释。",
            "Click to view detailed description, applicable scenarios, and parameter explanations for the current method.",
        ),
        required=False,
    )
    custom_formula_field = FormFieldSpec(
        key="extrapolation.custom.formula",
        widget_kind="textarea",
        label=LocalizedText("自定义公式：", "Custom formula:"),
        placeholder=LocalizedText(
            "示例: (C - B)^2/(B - A) + C 或 Exp[-x1]*Sin[x2]",
            "Example: (C - B)^2/(B - A) + C or Exp[-x1]*Sin[x2]",
        ),
        tooltip=LocalizedText(
            "输入自定义三点外推公式。可使用 A/B/C、列名或 x1/x2/x3，并支持数学函数。",
            "Enter a custom three-point extrapolation formula. Use A/B/C, column names, or x1/x2/x3; math functions are supported.",
        ),
        required=True,
    )
    custom_formula_preview_field = FormFieldSpec(
        key="extrapolation.custom.formula",
        widget_kind="button",
        label=LocalizedText("预览公式", "Preview formula"),
        tooltip=LocalizedText(
            "打开渲染后的自定义外推公式预览。",
            "Open a rendered preview of the custom extrapolation formula.",
        ),
        required=False,
    )
    custom_functions_field = FormFieldSpec(
        key="extrapolation.custom.functions",
        widget_kind="button",
        label=LocalizedText("函数支持", "Functions"),
        tooltip=LocalizedText(
            "查看自定义外推公式支持的函数和表达式语法。",
            "View supported functions and expression syntax for custom extrapolation formulas.",
        ),
        required=False,
    )
    power_x_fields = [
        FormFieldSpec(
            key=f"extrapolation.power_law.x{idx}",
            widget_kind="text",
            label=LocalizedText(f"x{idx}：", f"x{idx}:"),
            tooltip=LocalizedText(
                f"幂律三点外推的第 {idx} 个自变量值。",
                f"Input x value {idx} for three-point power-law extrapolation.",
            ),
            required=True,
        )
        for idx in range(1, 4)
    ]
    power_p_field = FormFieldSpec(
        key="extrapolation.power_law.p",
        widget_kind="text",
        label=LocalizedText("自定义 p（可选）：", "Custom p (optional):"),
        placeholder=LocalizedText("留空则自动求解 p", "Leave blank to solve p automatically"),
        tooltip=LocalizedText(
            "可选幂指数。留空时由程序根据数据自动求解。",
            "Optional power exponent. Leave blank for automatic solving from the data.",
        ),
        required=False,
    )
    power_seed_field = FormFieldSpec(
        key="extrapolation.power_law.seed_guesses",
        widget_kind="text",
        label=LocalizedText("p 种子列表（可选）：", "p seed list (optional):"),
        placeholder=LocalizedText("如 0.5, 1, 2, -1", "e.g. 0.5, 1, 2, -1"),
        tooltip=LocalizedText(
            "用于自动求解 p 的候选初值，多个值用逗号分隔。",
            "Candidate initial guesses for solving p automatically, separated by commas.",
        ),
        required=False,
    )
    levin_variant_field = FormFieldSpec(
        key="extrapolation.levin.variant",
        widget_kind="select",
        label=LocalizedText("变换类型：", "Variant:"),
        tooltip=LocalizedText(
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[0].tooltip_zh,
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[0].tooltip_en,
        ),
        required=True,
        choices=[
            ChoiceSpec(value="u", label=LocalizedText("u (最常用)", "u (most common)")),
            ChoiceSpec(value="t", label=LocalizedText("t (级数)", "t (series)")),
            ChoiceSpec(value="v", label=LocalizedText("v (积分)", "v (integrals)")),
        ],
    )
    levin_order_field = FormFieldSpec(
        key="extrapolation.levin.order",
        widget_kind="number",
        label=LocalizedText("变换阶数：", "Transform order:"),
        tooltip=LocalizedText(
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[1].tooltip_zh,
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[1].tooltip_en,
        ),
        required=True,
    )
    levin_weight_field = FormFieldSpec(
        key="extrapolation.levin.weight",
        widget_kind="select",
        label=LocalizedText("权重函数：", "Weight function:"),
        tooltip=LocalizedText(
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[2].tooltip_zh,
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[2].tooltip_en,
        ),
        required=True,
        choices=[
            ChoiceSpec(value="default", label=LocalizedText("默认 (1)", "Default (1)")),
            ChoiceSpec(value="reciprocal", label=LocalizedText("1/(n+1)", "1/(n+1)")),
            ChoiceSpec(value="reciprocal_beta", label=LocalizedText("1/(n+β)", "1/(n+β)")),
        ],
    )
    levin_beta_field = FormFieldSpec(
        key="extrapolation.levin.beta",
        widget_kind="number",
        label=LocalizedText("β 参数：", "β parameter:"),
        tooltip=LocalizedText(
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[3].tooltip_zh,
            EXTRAPOLATION_METHOD_SPECS["levin_u"].parameter_groups[0].parameters[3].tooltip_en,
        ),
        required=False,
    )
    richardson_p_field = FormFieldSpec(
        key="extrapolation.richardson.p",
        widget_kind="number",
        label=LocalizedText("收敛幂指数 p：", "Convergence power p:"),
        tooltip=LocalizedText(
            EXTRAPOLATION_METHOD_SPECS["richardson"].parameter_groups[0].parameters[0].tooltip_zh,
            EXTRAPOLATION_METHOD_SPECS["richardson"].parameter_groups[0].parameters[0].tooltip_en,
        ),
        required=True,
    )
    uncertainty_field = FormFieldSpec(
        key="extrapolation.uncertainty.reference_column",
        widget_kind="select",
        label=LocalizedText("不确定度参考列：", "Uncertainty ref column:"),
        tooltip=LocalizedText(
            "重新扫描数据以列出可选的不确定度参考列。",
            "Rescan data to list available uncertainty columns.",
        ),
        required=False,
    )
    uncertainty_refresh_field = FormFieldSpec(
        key="extrapolation.uncertainty.reference_column",
        widget_kind="button",
        label=LocalizedText("刷新不确定度列", "Refresh uncertainty columns"),
        tooltip=LocalizedText(
            "重新扫描数据以列出可选的不确定度参考列。",
            "Rescan data to list available uncertainty columns.",
        ),
        required=False,
    )

    bind_field(field=method_field, label=method_label, widget=self.method_combo, lang=lang)
    bind_choices(self.method_combo, method_field.choices, lang=lang)
    register_schema_text_refresh(self, method_field, widget=self.method_combo)
    bind_field(field=method_help_field, help_button=self.method_help_btn, lang=lang)
    register_schema_text_refresh(self, method_help_field, help_button=self.method_help_btn)
    bind_field(
        field=custom_formula_field,
        label=lbl_custom,
        widget=self.custom_formula_edit,
        lang=lang,
    )
    register_schema_text_refresh(
        self,
        custom_formula_field,
        widget=self.custom_formula_edit,
    )
    _register_schema_label_refresh(self, lbl_custom, custom_formula_field)
    bind_schema_command_button(
        self,
        self.custom_formula_preview_button,
        field=custom_formula_preview_field,
        accessible_name=LocalizedText("预览公式", "Preview formula"),
        lang=lang,
    )
    bind_field(field=custom_functions_field, widget=self.custom_formula_function_button, lang=lang)
    register_schema_text_refresh(self, custom_functions_field, widget=self.custom_formula_function_button)
    for field, label, edit in zip(power_x_fields, power_x_labels, self.power_x_edits, strict=True):
        bind_field(field=field, label=label, widget=edit, lang=lang)
        register_schema_text_refresh(self, field, widget=edit)
    bind_field(field=power_p_field, label=lbl_p, widget=self.power_p_edit, lang=lang)
    register_schema_text_refresh(self, power_p_field, widget=self.power_p_edit)
    bind_field(field=power_seed_field, label=lbl_seed, widget=self.power_seed_guesses_edit, lang=lang)
    register_schema_text_refresh(self, power_seed_field, widget=self.power_seed_guesses_edit)
    bind_field(field=levin_variant_field, label=lbl_variant, widget=self.levin_variant_combo, lang=lang)
    bind_choices(self.levin_variant_combo, levin_variant_field.choices, lang=lang)
    register_schema_text_refresh(self, levin_variant_field, widget=self.levin_variant_combo)
    bind_field(field=levin_order_field, label=lbl_order, widget=self.levin_order_spin, lang=lang)
    register_schema_text_refresh(self, levin_order_field, widget=self.levin_order_spin)
    bind_field(field=levin_weight_field, label=lbl_weight, widget=self.levin_weight_combo, lang=lang)
    bind_choices(self.levin_weight_combo, levin_weight_field.choices, lang=lang)
    register_schema_text_refresh(self, levin_weight_field, widget=self.levin_weight_combo)
    bind_field(field=levin_beta_field, label=lbl_beta, widget=self.levin_beta_spin, lang=lang)
    register_schema_text_refresh(self, levin_beta_field, widget=self.levin_beta_spin)
    bind_field(field=richardson_p_field, label=lbl_richardson_p, widget=self.richardson_p_spin, lang=lang)
    register_schema_text_refresh(self, richardson_p_field, widget=self.richardson_p_spin)
    bind_field(
        field=uncertainty_field,
        label=lbl_uncert,
        widget=self.uncertainty_combo,
        lang=lang,
    )
    register_schema_text_refresh(self, uncertainty_field, widget=self.uncertainty_combo)
    bind_schema_command_button(
        self,
        self.uncertainty_refresh_btn,
        field=uncertainty_refresh_field,
        accessible_name=LocalizedText("刷新不确定度列", "Refresh uncertainty columns"),
        lang=lang,
    )


def _bind_statistics_schema_fields(
    self,
    *,
    lbl_stats_value: QLabel,
    lbl_stats_sigma: QLabel,
    lbl_stats_type: QLabel,
    lbl_weight_var: QLabel,
    lbl_stats_sample: QLabel,
    stats_items: list[tuple[str, str, str]],
) -> None:
    lang = "en" if bool(getattr(self, "_is_en", lambda: False)()) else "zh"
    value_field = FormFieldSpec(
        key="statistics.value_column",
        widget_kind="text",
        label=LocalizedText("数值列：", "Value column:"),
        tooltip=LocalizedText(
            "数值数据所在列，例如 A 或列名。",
            "Column containing measured values, for example A or a header name.",
        ),
        required=True,
    )
    sigma_field = FormFieldSpec(
        key="statistics.sigma_column",
        widget_kind="text",
        label=LocalizedText("不确定度列（可选）：", "Sigma column (optional):"),
        placeholder=LocalizedText("留空则不使用不确定度列", "Leave blank to ignore sigma values"),
        tooltip=LocalizedText(
            "可选的不确定度列。加权平均模式会使用该列作为 σ。",
            "Optional uncertainty column. Weighted mean mode uses this column as sigma.",
        ),
        required=False,
    )
    mode_field = FormFieldSpec(
        key="statistics.mode",
        widget_kind="select",
        label=LocalizedText("统计类型：", "Statistics type:"),
        tooltip=LocalizedText(
            "选择算术平均或使用 σ 值作为权重的加权平均。",
            "Choose arithmetic mean or weighted mean. Use sigma values as weights for weighted statistics.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in stats_items
        ],
    )
    weight_variance_field = FormFieldSpec(
        key="statistics.weight_variance",
        widget_kind="checkbox",
        label=LocalizedText("方差/标准误差：", "Variance/SE:"),
        tooltip=LocalizedText(
            "启用后，方差和标准误差也按权重计算。",
            "When enabled, variance and standard error are also computed with weights.",
        ),
        required=False,
    )
    sample_field = FormFieldSpec(
        key="statistics.sample_mode",
        widget_kind="checkbox",
        label=LocalizedText("样本/总体：", "Sample/Population:"),
        tooltip=LocalizedText(
            "启用样本模式时使用 n-1 自由度；关闭时使用总体模式。",
            "Sample mode uses n-1 degrees of freedom; otherwise population mode is used.",
        ),
        required=False,
    )

    bind_field(field=value_field, label=lbl_stats_value, widget=self.stats_value_column_edit, lang=lang)
    register_schema_text_refresh(self, value_field, widget=self.stats_value_column_edit)
    bind_field(field=sigma_field, label=lbl_stats_sigma, widget=self.stats_sigma_column_edit, lang=lang)
    register_schema_text_refresh(self, sigma_field, widget=self.stats_sigma_column_edit)
    bind_field(field=mode_field, label=lbl_stats_type, widget=self.stats_mode_combo, lang=lang)
    bind_choices(self.stats_mode_combo, mode_field.choices, lang=lang)
    register_schema_text_refresh(self, mode_field, widget=self.stats_mode_combo)
    bind_field(
        field=weight_variance_field,
        label=lbl_weight_var,
        widget=self.stats_weight_variance_checkbox,
        lang=lang,
    )
    register_schema_text_refresh(self, weight_variance_field, widget=self.stats_weight_variance_checkbox)
    bind_field(field=sample_field, label=lbl_stats_sample, widget=self.stats_sample_checkbox, lang=lang)
    register_schema_text_refresh(self, sample_field, widget=self.stats_sample_checkbox)


def _bind_fitting_schema_fields(
    self,
    *,
    lbl_model: QLabel,
    fit_items: list[tuple[str, str, str]],
    lbl_fit_expr: QLabel,
    lbl_implicit_eq: QLabel,
    lbl_implicit_output: QLabel,
    lbl_implicit_var: QLabel,
    lbl_implicit_initial: QLabel,
    lbl_implicit_tol: QLabel,
    lbl_implicit_iter: QLabel,
    lbl_implicit_method: QLabel,
    implicit_method_items: list[tuple[str, str, str]],
    lbl_implicit_timeout: QLabel,
    lbl_custom_params: QLabel,
    lbl_implicit_params: QLabel,
) -> None:
    lang = "en" if bool(getattr(self, "_is_en", lambda: False)()) else "zh"
    fit_model_field = FormFieldSpec(
        key="fitting.model",
        widget_kind="select",
        label=LocalizedText("拟合模型：", "Model:"),
        tooltip=LocalizedText(
            "选择拟合模型。自定义模型允许编辑表达式；其他模型会显示只读预览。",
            "Choose the fitting model. Custom models allow expression editing; other models show read-only previews.",
        ),
        required=True,
        choices=[ChoiceSpec(value=data, label=LocalizedText(zh, en)) for zh, en, data in fit_items],
    )
    custom_expression_field = FormFieldSpec(
        key="fitting.custom.expression",
        widget_kind="textarea",
        label=LocalizedText("模型表达式：", "Model expression:"),
        placeholder=LocalizedText("示例：A*x**(-p) + C", "Example: A*x**(-p) + C"),
        tooltip=LocalizedText(
            "输入自定义拟合表达式。留空不会使用示例；示例只显示在背景提示中。",
            "Enter the custom fitting expression. Leaving it blank does not use the example; the example is only placeholder text.",
        ),
        required=True,
    )
    custom_constants_field = FormFieldSpec(
        key="fitting.custom.constants",
        widget_kind="table",
        label=LocalizedText("常数设置", "Constants"),
        tooltip=LocalizedText(
            "可选常数表。启用后，常数名会从参数识别和拟合参数中排除。",
            "Optional constants table. When enabled, constant names are excluded from parameter detection and fit parameters.",
        ),
        required=False,
    )
    custom_params_field = FormFieldSpec(
        key="fitting.custom.parameters",
        widget_kind="table",
        label=LocalizedText("参数列表：", "Parameters:"),
        tooltip=LocalizedText(
            "自定义模型参数及初值、固定值和约束。",
            "Custom model parameters with initial values, fixed values, and constraints.",
        ),
        required=False,
    )
    implicit_equation_field = FormFieldSpec(
        key="fitting.implicit.equation",
        widget_kind="textarea",
        label=LocalizedText("自洽方程：", "Self-consistent equation:"),
        placeholder=LocalizedText("示例：a + b*Cos[u] + c*x", "Example: a + b*Cos[u] + c*x"),
        tooltip=LocalizedText(
            "输入自洽方程。留空不会使用示例；示例只显示在背景提示中。",
            "Enter the self-consistent equation. Leaving it blank does not use the example; the example is only placeholder text.",
        ),
        required=True,
    )
    implicit_output_field = FormFieldSpec(
        key="fitting.implicit.output_expression",
        widget_kind="textarea",
        label=LocalizedText("输出表达式：", "Output expression:"),
        placeholder=LocalizedText("示例：u", "Example: u"),
        tooltip=LocalizedText(
            "输入由隐式变量和输入变量计算目标列的输出表达式。",
            "Enter the output expression that maps the implicit and input variables to the target column.",
        ),
        required=True,
    )
    implicit_variable_field = FormFieldSpec(
        key="fitting.implicit.variable",
        widget_kind="text",
        label=LocalizedText("隐式变量：", "Implicit variable:"),
        tooltip=LocalizedText("自洽方程中要求解的变量名。", "Variable solved by the self-consistent equation."),
        required=True,
    )
    implicit_initial_field = FormFieldSpec(
        key="fitting.implicit.initial",
        widget_kind="text",
        label=LocalizedText("初始值：", "Initial:"),
        tooltip=LocalizedText("隐式变量求解初值。", "Initial value for solving the implicit variable."),
        required=True,
    )
    implicit_tolerance_field = FormFieldSpec(
        key="fitting.implicit.tolerance",
        widget_kind="text",
        label=LocalizedText("求解容差：", "Tolerance:"),
        tooltip=LocalizedText("隐式变量求解容差。", "Tolerance for solving the implicit variable."),
        required=True,
    )
    implicit_iterations_field = FormFieldSpec(
        key="fitting.implicit.max_iterations",
        widget_kind="number",
        label=LocalizedText("最大迭代：", "Max iterations:"),
        tooltip=LocalizedText("每次隐式变量求解允许的最大迭代次数。", "Maximum iterations allowed for each implicit solve."),
        required=True,
    )
    implicit_method_field = FormFieldSpec(
        key="fitting.implicit.method",
        widget_kind="select",
        label=LocalizedText("求解方法：", "Method:"),
        tooltip=LocalizedText(
            "固定点用于 u=g(...) 形式；求根用于 F(...)=0 形式。",
            "Fixed point is for u=g(...) forms; Root is for F(...)=0 forms.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in implicit_method_items
        ],
    )
    implicit_timeout_field = FormFieldSpec(
        key="fitting.implicit.timeout_seconds",
        widget_kind="number",
        label=LocalizedText("最长运行秒数：", "Max runtime (s):"),
        tooltip=LocalizedText(
            "0 表示不自动超时，只能手动停止。",
            "0 disables automatic timeout; use Stop to cancel.",
        ),
        required=True,
    )
    implicit_constants_field = FormFieldSpec(
        key="fitting.implicit.constants",
        widget_kind="table",
        label=LocalizedText("常数设置", "Constants"),
        tooltip=LocalizedText(
            "可选常数表。启用后，常数名会从隐式参数识别和拟合参数中排除。",
            "Optional constants table. When enabled, constant names are excluded from implicit parameter detection and fit parameters.",
        ),
        required=False,
    )
    implicit_params_field = FormFieldSpec(
        key="fitting.implicit.parameters",
        widget_kind="table",
        label=LocalizedText("参数列表：", "Parameters:"),
        tooltip=LocalizedText(
            "自洽隐式模型参数及初值、固定值和约束。",
            "Self-consistent implicit model parameters with initial values, fixed values, and constraints.",
        ),
        required=False,
    )

    bind_field(field=fit_model_field, label=lbl_model, widget=self.fit_model_combo, lang=lang)
    bind_choices(self.fit_model_combo, fit_model_field.choices, lang=lang)
    bind_field(
        field=custom_expression_field,
        label=lbl_fit_expr,
        widget=self.fit_expr_edit,
        help_button=self.fit_formula_preview_button,
        lang=lang,
    )
    register_schema_text_refresh(
        self,
        custom_expression_field,
        widget=self.fit_expr_edit,
        help_button=self.fit_formula_preview_button,
    )
    _register_schema_label_refresh(self, lbl_fit_expr, custom_expression_field)
    bind_field(field=custom_constants_field, widget=self.custom_constants_editor, lang=lang)
    bind_field(field=custom_params_field, label=lbl_custom_params, widget=self.custom_params_table, lang=lang)
    bind_field(
        field=implicit_equation_field,
        label=lbl_implicit_eq,
        widget=self.implicit_equation_edit,
        help_button=self.implicit_equation_preview_button,
        lang=lang,
    )
    register_schema_text_refresh(
        self,
        implicit_equation_field,
        widget=self.implicit_equation_edit,
        help_button=self.implicit_equation_preview_button,
    )
    _register_schema_label_refresh(self, lbl_implicit_eq, implicit_equation_field)
    bind_field(
        field=implicit_output_field,
        label=lbl_implicit_output,
        widget=self.implicit_output_edit,
        help_button=self.implicit_output_preview_button,
        lang=lang,
    )
    register_schema_text_refresh(
        self,
        implicit_output_field,
        widget=self.implicit_output_edit,
        help_button=self.implicit_output_preview_button,
    )
    _register_schema_label_refresh(self, lbl_implicit_output, implicit_output_field)
    bind_field(field=implicit_variable_field, label=lbl_implicit_var, widget=self.implicit_variable_edit, lang=lang)
    bind_field(field=implicit_initial_field, label=lbl_implicit_initial, widget=self.implicit_initial_edit, lang=lang)
    bind_field(field=implicit_tolerance_field, label=lbl_implicit_tol, widget=self.implicit_tolerance_edit, lang=lang)
    bind_field(field=implicit_iterations_field, label=lbl_implicit_iter, widget=self.implicit_max_iterations_spin, lang=lang)
    bind_field(field=implicit_method_field, label=lbl_implicit_method, widget=self.implicit_method_combo, lang=lang)
    bind_choices(self.implicit_method_combo, implicit_method_field.choices, lang=lang)
    bind_field(field=implicit_timeout_field, label=lbl_implicit_timeout, widget=self.implicit_timeout_spin, lang=lang)
    bind_field(field=implicit_constants_field, widget=self.implicit_constants_editor, lang=lang)
    bind_field(field=implicit_params_field, label=lbl_implicit_params, widget=self.implicit_params_table, lang=lang)

def _mark_schema_choices(combo: QComboBox) -> None:
    combo.setProperty("datalab_schema_choices", True)


def _bind_global_options_schema_fields(
    self,
    *,
    label_precision: QLabel,
    unc_label: QLabel,
    lbl_parallel_mode: QLabel,
    lbl_parallel_workers: QLabel,
    lbl_parallel_reserve: QLabel,
    lbl_nested_policy: QLabel,
    parallel_mode_items: list[tuple[str, str, str]],
    nested_policy_items: list[tuple[str, str, str]],
    lbl_output: QLabel,
    prec_label: QLabel,
    group_size_label: QLabel,
) -> None:
    lang = "en" if bool(getattr(self, "_is_en", lambda: False)()) else "zh"
    precision_field = FormFieldSpec(
        key="options.precision_digits",
        widget_kind="number",
        label=LocalizedText("数值精度位数：", "Precision digits:"),
        tooltip=LocalizedText(
            "数值计算精度位数。16 位及以下通常使用双精度快速路径；更高位数使用多精度计算。",
            "Numerical precision digits. Values up to 16 usually use the double-precision fast path; higher values use multiprecision calculation.",
        ),
        required=True,
    )
    uncertainty_digits_field = FormFieldSpec(
        key="options.uncertainty_digits",
        widget_kind="number",
        label=LocalizedText("不确定度位数：", "Uncertainty digits:"),
        tooltip=LocalizedText(
            "控制结果中括号不确定度的有效位数。",
            "Controls the significant digits shown for parenthesized uncertainties.",
        ),
        required=True,
    )
    parallel_mode_field = FormFieldSpec(
        key="parallel.mode",
        widget_kind="select",
        label=LocalizedText("资源策略：", "Resource policy:"),
        tooltip=LocalizedText(
            "资源调度偏好；需要快速取消和进程隔离的任务仍会使用独立进程。",
            "Resource scheduling preference; tasks that need fast cancellation or process isolation may still use separate processes.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in parallel_mode_items
        ],
    )
    max_workers_field = FormFieldSpec(
        key="parallel.max_workers",
        widget_kind="number",
        label=LocalizedText("最大 workers：", "Max workers:"),
        tooltip=LocalizedText(
            "最大并行 worker 数。0 表示自动根据任务和机器资源决定。",
            "Maximum parallel worker count. 0 means automatic selection based on workload and machine resources.",
        ),
        required=False,
    )
    reserve_cores_field = FormFieldSpec(
        key="parallel.reserve_cores",
        widget_kind="number",
        label=LocalizedText("保留核心：", "Reserve cores:"),
        tooltip=LocalizedText(
            "为系统和界面响应保留的 CPU 核心数。",
            "CPU cores reserved for the system and UI responsiveness.",
        ),
        required=False,
    )
    nested_policy_field = FormFieldSpec(
        key="parallel.nested_policy",
        widget_kind="select",
        label=LocalizedText("嵌套策略：", "Nested policy:"),
        tooltip=LocalizedText(
            "当一个并行任务内部再次请求并行时如何处理。",
            "How to handle a parallel request made from inside another parallel task.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in nested_policy_items
        ],
    )
    generate_latex_field = FormFieldSpec(
        key="output.latex.enabled",
        widget_kind="checkbox",
        label=LocalizedText("生成 LaTeX 文件", "Generate LaTeX"),
        tooltip=LocalizedText("启用后将计算结果写入 LaTeX 文件。", "When enabled, write calculation results to a LaTeX file."),
        required=False,
    )
    output_path_field = FormFieldSpec(
        key="output.latex.path",
        widget_kind="file",
        label=LocalizedText("LaTeX 输出路径：", "LaTeX output path:"),
        placeholder=LocalizedText("选择 .tex 输出文件", "Choose a .tex output file"),
        tooltip=LocalizedText("LaTeX 结果文件的保存路径。", "Save path for the LaTeX result file."),
        required=False,
    )
    output_browse_field = FormFieldSpec(
        key="output.latex.path",
        widget_kind="button",
        label=LocalizedText("选择 LaTeX 输出路径", "Choose LaTeX output path"),
        tooltip=LocalizedText("选择 LaTeX 输出文件路径。", "Choose the LaTeX output file path."),
        required=False,
    )
    input_digits_field = FormFieldSpec(
        key="output.latex.input_digits",
        widget_kind="number",
        label=LocalizedText("输入列位数：", "Input digits:"),
        tooltip=LocalizedText("LaTeX 表格中输入列保留的数字位数。", "Digit count retained for input columns in LaTeX tables."),
        required=False,
    )
    dcolumn_field = FormFieldSpec(
        key="output.latex.dcolumn",
        widget_kind="checkbox",
        label=LocalizedText("使用 dcolumn 排版", "Use dcolumn"),
        tooltip=LocalizedText("使用 dcolumn 对齐数字列。", "Use dcolumn to align numeric columns."),
        required=False,
    )
    group_size_field = FormFieldSpec(
        key="output.latex.group_size",
        widget_kind="number",
        label=LocalizedText("分组位数：", "Group size:"),
        tooltip=LocalizedText("LaTeX 数字分组的位数；0 表示不分组。", "Digit group size in LaTeX numbers; 0 disables grouping."),
        required=False,
    )
    caption_enabled_field = FormFieldSpec(
        key="output.latex.caption.enabled",
        widget_kind="checkbox",
        label=LocalizedText("使用标题", "Use caption"),
        tooltip=LocalizedText("启用 LaTeX 表格标题。", "Enable a LaTeX table caption."),
        required=False,
    )
    caption_field = FormFieldSpec(
        key="output.latex.caption",
        widget_kind="text",
        label=LocalizedText("标题内容", "Caption text"),
        placeholder=LocalizedText("表格标题", "Table caption"),
        tooltip=LocalizedText("LaTeX 表格标题文本。", "LaTeX table caption text."),
        required=False,
    )
    plots_field = FormFieldSpec(
        key="output.plots.enabled",
        widget_kind="checkbox",
        label=LocalizedText("生成图片", "Generate plots"),
        tooltip=LocalizedText("启用后生成当前计算模块支持的图片。", "When enabled, generate plots supported by the current calculation module."),
        required=False,
    )
    verbose_field = FormFieldSpec(
        key="options.verbose_log",
        widget_kind="checkbox",
        label=LocalizedText("显示详细日志", "Verbose log"),
        tooltip=LocalizedText("显示更详细的计算日志。", "Show more detailed calculation logs."),
        required=False,
    )

    field_bindings = [
        (precision_field, label_precision, self.mpmath_precision_spin),
        (uncertainty_digits_field, unc_label, self.uncertainty_digits_spin),
        (parallel_mode_field, lbl_parallel_mode, self.parallel_mode_combo),
        (max_workers_field, lbl_parallel_workers, self.parallel_max_workers_spin),
        (reserve_cores_field, lbl_parallel_reserve, self.parallel_reserve_cores_spin),
        (nested_policy_field, lbl_nested_policy, self.parallel_nested_policy_combo),
        (output_path_field, lbl_output, self.output_file_edit),
        (input_digits_field, prec_label, self.latex_input_precision_spin),
        (group_size_field, group_size_label, self.latex_group_size_spin),
    ]
    for field, label, widget in field_bindings:
        bind_field(field=field, label=label, widget=widget, lang=lang)
        register_schema_text_refresh(self, field, widget=widget)

    for combo in (self.parallel_mode_combo, self.parallel_nested_policy_combo):
        _mark_schema_choices(combo)

    for field, widget in [
        (generate_latex_field, self.generate_latex_checkbox),
        (dcolumn_field, self.dcolumn_checkbox),
        (caption_enabled_field, self.caption_checkbox),
        (caption_field, self.caption_edit),
        (plots_field, self.generate_plots_checkbox),
        (verbose_field, self.verbose_checkbox),
    ]:
        bind_field(field=field, widget=widget, lang=lang)
        register_schema_text_refresh(self, field, widget=widget)

    bind_schema_command_button(
        self,
        self.output_browse_button,
        field=output_browse_field,
        accessible_name=LocalizedText("选择 LaTeX 输出路径", "Choose LaTeX output path"),
        lang=lang,
    )


def _bind_result_latex_pdf_schema_fields(
    self,
    *,
    lbl_digits: QLabel,
    lbl_engine: QLabel,
    lbl_zoom: QLabel,
) -> None:
    lang = "en" if bool(getattr(self, "_is_en", lambda: False)()) else "zh"
    display_scientific_field = _result_control_field("result.numeric", "results.display.scientific")
    display_digits_field = _result_control_field("result.numeric", "results.display.decimal_places")
    image_zoom_field = _result_control_field("result.image", "results.image.zoom_percent")
    log_x_field = _result_control_field("result.image", "results.image.log_x")
    log_y_field = _result_control_field("result.image", "results.image.log_y")
    latex_compile_field = _result_control_field("result.latex", "latex.compile")
    latex_view_field = _result_control_field("result.latex", "latex.view_pdf")
    latex_engine_field = _result_control_field("result.latex", "latex.engine")
    latex_engine_path_field = _result_control_field("result.latex", "latex.engine_path")
    pdf_zoom_field = _result_control_field("result.pdf", "pdf.zoom_percent")
    pdf_zoom_in_field = _result_control_field("result.pdf", "pdf.zoom_in")
    pdf_zoom_out_field = _result_control_field("result.pdf", "pdf.zoom_out")
    pdf_zoom_reset_field = _result_control_field("result.pdf", "pdf.zoom_reset")

    for field, label, widget in [
        (display_digits_field, lbl_digits, self.display_digits_spin),
        (latex_engine_field, lbl_engine, self.latex_engine_combo),
        (pdf_zoom_field, lbl_zoom, self.pdf_zoom_spin),
    ]:
        bind_field(field=field, label=label, widget=widget, lang=lang)
        register_schema_text_refresh(self, field, widget=widget)
    _mark_schema_choices(self.latex_engine_combo)

    for field, widget in [
        (display_scientific_field, self.scientific_checkbox),
        (image_zoom_field, self.zoom_percent_spin),
        (log_x_field, self.log_x_checkbox),
        (log_y_field, self.log_y_checkbox),
    ]:
        bind_field(field=field, widget=widget, lang=lang)
        register_schema_text_refresh(self, field, widget=widget)

    for field, button, accessible_name in [
        (latex_compile_field, self.latex_compile_button, latex_compile_field.label),
        (latex_view_field, self.latex_view_pdf_button, latex_view_field.label),
        (latex_engine_path_field, self.latex_engine_path_button, latex_engine_path_field.label),
        (pdf_zoom_in_field, self.pdf_zoom_in_button, pdf_zoom_in_field.label),
        (pdf_zoom_out_field, self.pdf_zoom_out_button, pdf_zoom_out_field.label),
        (pdf_zoom_reset_field, self.pdf_zoom_reset_button, pdf_zoom_reset_field.label),
    ]:
        bind_schema_command_button(
            self,
            button,
            field=field,
            accessible_name=accessible_name,
            lang=lang,
        )


def _bind_result_area_schema_fields(self) -> None:
    lang = "en" if bool(getattr(self, "_is_en", lambda: False)()) else "zh"
    numeric_result_field = FormFieldSpec(
        key="results.numeric.markdown",
        widget_kind="textarea",
        label=LocalizedText("数值结果", "Numeric results"),
        tooltip=LocalizedText("显示当前计算的数值结果和摘要。", "Shows numeric results and summaries for the current calculation."),
        required=False,
    )
    csv_export_field = _result_control_field("result.numeric", "results.export.csv")
    image_zoom_in_field = _result_control_field("result.image", "results.image.zoom_in")
    image_zoom_out_field = _result_control_field("result.image", "results.image.zoom_out")
    image_zoom_reset_field = _result_control_field("result.image", "results.image.zoom_reset")
    image_export_field = _result_control_field("result.image", "results.image.export")
    image_page_field = _result_control_field("result.image", "results.image.page")
    image_prev_field = _result_control_field("result.image", "results.image.previous")
    image_next_field = _result_control_field("result.image", "results.image.next")
    image_preview_field = FormFieldSpec(
        key="results.image.preview",
        widget_kind="image",
        label=LocalizedText("图片", "Image"),
        tooltip=LocalizedText("显示当前计算生成的图片。", "Displays plots generated by the current calculation."),
        required=False,
    )
    image_status_field = FormFieldSpec(
        key="results.image.status",
        widget_kind="text",
        label=LocalizedText("图片状态", "Image status"),
        tooltip=LocalizedText("当前图片页和加载状态。", "Current image page and loading status."),
        required=False,
    )
    log_field = FormFieldSpec(
        key="results.log",
        widget_kind="textarea",
        label=LocalizedText("日志", "Log"),
        tooltip=LocalizedText("显示计算日志和警告。", "Shows calculation logs and warnings."),
        required=False,
    )
    latex_source_field = FormFieldSpec(
        key="results.latex.source",
        widget_kind="textarea",
        label=LocalizedText("LaTeX 源码", "LaTeX source"),
        tooltip=LocalizedText("显示或编辑当前 LaTeX 输出内容。", "Shows or edits the current LaTeX output content."),
        required=False,
    )
    latex_status_field = FormFieldSpec(
        key="results.latex.status",
        widget_kind="text",
        label=LocalizedText("LaTeX 状态", "LaTeX status"),
        tooltip=LocalizedText("当前 LaTeX 文件加载和保存状态。", "Current LaTeX file load/save status."),
        required=False,
    )
    latex_open_field = _result_control_field("result.latex", "results.latex.open")
    latex_save_field = _result_control_field("result.latex", "results.latex.save")
    latex_reload_field = _result_control_field("result.latex", "results.latex.reload")
    pdf_status_field = FormFieldSpec(
        key="results.pdf.status",
        widget_kind="text",
        label=LocalizedText("PDF 状态", "PDF status"),
        tooltip=LocalizedText("当前 PDF 预览状态。", "Current PDF preview status."),
        required=False,
    )

    for field, widget in [
        (numeric_result_field, self.result_edit),
        (image_preview_field, self.result_plot_scroll),
        (image_preview_field, self.result_plot_label),
        (image_status_field, self.image_status_label),
        (log_field, self.log_edit),
        (latex_source_field, self.latex_edit),
        (latex_status_field, self.latex_status_label),
        (pdf_status_field, self.pdf_status_label),
        (image_page_field, self.image_page_spin),
    ]:
        bind_field(field=field, widget=widget, lang=lang)
        register_schema_text_refresh(self, field, widget=widget)

    for field, button, accessible_name in [
        (csv_export_field, self.export_csv_btn, LocalizedText("导出 CSV", "Export CSV")),
        (image_zoom_in_field, self.result_zoom_in_btn, LocalizedText("放大图片", "Zoom image in")),
        (image_zoom_out_field, self.result_zoom_out_btn, LocalizedText("缩小图片", "Zoom image out")),
        (image_zoom_reset_field, self.result_zoom_reset_btn, LocalizedText("重置图片缩放", "Reset image zoom")),
        (image_export_field, self.result_export_btn, LocalizedText("导出图片", "Export image")),
        (image_prev_field, self.image_prev_btn, LocalizedText("上一张图片", "Previous image")),
        (image_next_field, self.image_next_btn, LocalizedText("下一张图片", "Next image")),
        (latex_open_field, self.latex_open_button, LocalizedText("打开 LaTeX 文件", "Open LaTeX file")),
        (latex_save_field, self.latex_save_button, LocalizedText("保存 LaTeX 文件", "Save LaTeX file")),
        (latex_reload_field, self.latex_reload_button, LocalizedText("重新载入 LaTeX 文件", "Reload LaTeX file")),
    ]:
        bind_schema_command_button(
            self,
            button,
            field=field,
            accessible_name=accessible_name,
            lang=lang,
        )


def _bind_error_schema_fields(
    self,
    *,
    lbl_error_formula: QLabel,
    lbl_error_method: QLabel,
    error_method_items: list[tuple[str, str, str]],
    lbl_error_order: QLabel,
    lbl_mc_samples: QLabel,
    lbl_mc_seed: QLabel,
) -> None:
    lang = "en" if bool(getattr(self, "_is_en", lambda: False)()) else "zh"
    formula_field = FormFieldSpec(
        key="error.formula",
        widget_kind="textarea",
        label=LocalizedText("公式：", "Formula:"),
        placeholder=LocalizedText(
            "公式（使用列名或 x1, x2 …）",
            "Formula (use column names or x1, x2 …)",
        ),
        tooltip=LocalizedText(
            "输入要传播不确定度的公式，可使用数据列名或 x1、x2 等变量。",
            "Enter the formula whose uncertainty should be propagated; use column names or variables such as x1 and x2.",
        ),
        required=True,
    )
    function_help_field = FormFieldSpec(
        key="error.functions",
        widget_kind="button",
        label=LocalizedText("函数支持", "Functions"),
        tooltip=LocalizedText(
            "查看公式中支持的函数和表达式语法。",
            "View supported functions and expression syntax for formulas.",
        ),
        required=False,
    )
    constants_use_file_field = FormFieldSpec(
        key="error.constants.use_file",
        widget_kind="checkbox",
        label=LocalizedText("使用常数文件", "Use constants file"),
        tooltip=LocalizedText(
            "启用后从外部常数文件读取固定量；关闭时使用下方常数表。",
            "When enabled, fixed values are read from an external constants file; otherwise the constants table below is used.",
        ),
        required=False,
    )
    constants_file_field = FormFieldSpec(
        key="error.constants.file_path",
        widget_kind="file",
        label=LocalizedText("常数文件…", "Constants file…"),
        placeholder=LocalizedText("选择常数文件", "Choose a constants file"),
        tooltip=LocalizedText(
            "常数文件每行填写名称和值，例如 ALPHA 7.2973525693(11)[-3]。",
            "Constants files use one name and value per line, for example ALPHA 7.2973525693(11)[-3].",
        ),
        required=False,
    )
    constants_field = FormFieldSpec(
        key="error.constants",
        widget_kind="table",
        label=LocalizedText("常数设置", "Constants"),
        tooltip=LocalizedText(
            "可选常数设置，支持表格和文本视图；关闭时不会向误差传递公式代入这些常数。",
            "Optional constants for table or text entry; when disabled they are not substituted into the error propagation formula.",
        ),
        required=False,
    )
    method_field = FormFieldSpec(
        key="error.method",
        widget_kind="select",
        label=LocalizedText("方法：", "Method:"),
        tooltip=LocalizedText(
            "Taylor 使用偏导传播不确定度；Monte Carlo 通过随机采样估计不确定度。",
            "Taylor propagates uncertainty with derivatives; Monte Carlo estimates uncertainty by random sampling.",
        ),
        required=True,
        choices=[ChoiceSpec(value=data, label=LocalizedText(zh, en)) for zh, en, data in error_method_items],
    )
    order_field = FormFieldSpec(
        key="error.taylor.order",
        widget_kind="number",
        label=LocalizedText("阶数：", "Order:"),
        tooltip=LocalizedText(
            "1 阶：线性误差估计；2 阶：包含 Hessian（二阶偏导）贡献。",
            "Order 1: linear propagation; order 2: includes Hessian (second-derivative) contributions.",
        ),
        required=False,
    )
    mc_samples_field = FormFieldSpec(
        key="error.monte_carlo.samples",
        widget_kind="number",
        label=LocalizedText("MC 样本数：", "MC samples:"),
        tooltip=LocalizedText(
            "Monte Carlo 样本数（越大越稳定，但耗时更长），至少 100。",
            "Monte Carlo sample count (larger is more stable but slower), minimum 100.",
        ),
        required=False,
    )
    mc_seed_field = FormFieldSpec(
        key="error.monte_carlo.seed",
        widget_kind="text",
        label=LocalizedText("随机种子（可选）：", "Seed (optional):"),
        placeholder=LocalizedText("留空=随机", "blank=random"),
        tooltip=LocalizedText(
            "留空表示每次随机；填写整数可复现实验结果。",
            "Leave blank for random each run; set an integer for reproducibility.",
        ),
        required=False,
    )

    bind_field(
        field=formula_field,
        label=lbl_error_formula,
        widget=self.formula_edit,
        help_button=self.error_formula_preview_button,
        lang=lang,
    )
    register_schema_text_refresh(
        self,
        formula_field,
        widget=self.formula_edit,
        help_button=self.error_formula_preview_button,
    )
    _register_schema_label_refresh(self, lbl_error_formula, formula_field)
    bind_field(field=function_help_field, widget=self.func_help_btn, lang=lang)
    register_schema_text_refresh(self, function_help_field, widget=self.func_help_btn)
    bind_field(field=constants_use_file_field, widget=self.use_constants_file_checkbox, lang=lang)
    register_schema_text_refresh(self, constants_use_file_field, widget=self.use_constants_file_checkbox)
    bind_field(
        field=constants_file_field,
        widget=self.constants_file_edit,
        help_button=self.constants_hint_btn,
        lang=lang,
    )
    register_schema_text_refresh(self, constants_file_field, widget=self.constants_file_edit)
    bind_field(
        field=constants_field,
        widget=self.error_constants_editor,
        help_button=self.error_constants_editor.help_button,
        lang=lang,
    )
    register_schema_text_refresh(self, constants_field, widget=self.error_constants_editor, help_button=self.error_constants_editor.help_button)
    register_schema_text_refresh(self, constants_field, widget=self.error_constants_editor.checkbox)
    bind_field(field=method_field, label=lbl_error_method, widget=self.error_method_combo, lang=lang)
    bind_choices(self.error_method_combo, method_field.choices, lang=lang)
    register_schema_text_refresh(self, method_field, widget=self.error_method_combo)
    bind_field(field=order_field, label=lbl_error_order, widget=self.error_order_spin, lang=lang)
    register_schema_text_refresh(self, order_field, widget=self.error_order_spin)
    bind_field(field=mc_samples_field, label=lbl_mc_samples, widget=self.error_mc_samples_spin, lang=lang)
    register_schema_text_refresh(self, mc_samples_field, widget=self.error_mc_samples_spin)
    bind_field(field=mc_seed_field, label=lbl_mc_seed, widget=self.error_mc_seed_edit, lang=lang)
    register_schema_text_refresh(self, mc_seed_field, widget=self.error_mc_seed_edit)


def _bind_root_schema_fields(
    self,
    lbl_root_equations: QLabel,
    lbl_root_mode: QLabel,
    lbl_root_unknowns: QLabel,
    root_mode_items: list[tuple[str, str, object]],
) -> None:
    lang = "en" if bool(getattr(self, "_is_en", lambda: False)()) else "zh"
    root_equations_field = FormFieldSpec(
        key="root.equations",
        widget_kind="textarea",
        label=LocalizedText("方程：", "Equations:"),
        placeholder=LocalizedText(
            "每行一个方程，按 F_i(...)=0 求解；示例：x^2 - A",
            "One equation per line as F_i(...)=0; example: x^2 - A",
        ),
        tooltip=LocalizedText(
            "输入要求解的方程。留空不会使用示例；示例只显示在背景提示中。",
            "Enter equations to solve. Leaving it blank does not use the example; the example is only placeholder text.",
        ),
        required=True,
    )
    root_mode_field = FormFieldSpec(
        key="root.mode",
        widget_kind="select",
        label=LocalizedText("求解模式：", "Solve mode:"),
        tooltip=LocalizedText(
            "标量：单未知量单根；扫描多根：从区间/采样查找多个根；多项式：一元多项式根；方程组：多个未知量联立求解。",
            "Scalar: one unknown and one root; Scan multiple: search multiple roots by interval/sampling; Polynomial: univariate polynomial roots; System: solve coupled equations.",
        ),
        required=True,
        choices=[
            ChoiceSpec(value=data, label=LocalizedText(zh, en))
            for zh, en, data in root_mode_items
        ],
    )
    root_unknowns_field = FormFieldSpec(
        key="root.unknowns",
        widget_kind="table",
        label=LocalizedText("未知量：", "Unknowns:"),
        tooltip=LocalizedText(
            "不同模式需要的列不同：标量通常填名称和初始值；扫描多根还可填下界/上界；多项式可只填名称；方程组每个未知量一行。",
            "Columns depend on mode: scalar usually needs name and initial; scan can use lower/upper; polynomial can use only name; system uses one row per unknown.",
        ),
        required=True,
    )
    root_constants_field = FormFieldSpec(
        key="root.constants",
        widget_kind="table",
        label=LocalizedText("常数设置", "Constants"),
        tooltip=LocalizedText(
            "常数设置：填写方程中的固定量，支持 1.23(4) 和 1.23(4)[-5] 这类不确定度写法。关闭时不会代入常数表。",
            "Constants: fixed quantities used by equations; accepts uncertainty notation such as 1.23(4) and 1.23(4)[-5]. When disabled, constants are not substituted.",
        ),
        required=False,
    )

    bind_field(
        field=root_equations_field,
        label=lbl_root_equations,
        widget=self.root_equations_edit,
        help_button=self.root_equations_help_button,
        lang=lang,
    )
    register_schema_text_refresh(
        self,
        root_equations_field,
        widget=self.root_equations_edit,
        help_button=self.root_equations_help_button,
    )
    _register_schema_label_refresh(self, lbl_root_equations, root_equations_field)
    bind_field(
        field=root_mode_field,
        label=lbl_root_mode,
        widget=self.root_mode_combo,
        help_button=self.root_mode_help_button,
        lang=lang,
    )
    bind_choices(self.root_mode_combo, root_mode_field.choices, lang=lang)
    bind_field(
        field=root_unknowns_field,
        label=lbl_root_unknowns,
        widget=self.root_unknowns_table,
        help_button=self.root_unknowns_help_button,
        lang=lang,
    )
    bind_field(field=root_constants_field, widget=self.root_constants_editor, lang=lang)


def _refresh_root_field_help(self) -> None:
    is_en = bool(getattr(self, "_is_en", lambda: False)())
    unknown_headers = (
        ("Name", "Initial", "Lower", "Upper")
        if is_en
        else ("名称", "初始值", "下界", "上界")
    )
    constants_headers = ("Name", "Value") if is_en else ("名称", "值")
    unknowns_table = getattr(self, "root_unknowns_table", None)
    if unknowns_table is not None:
        unknowns_table.set_headers(unknown_headers)
        unknowns_table.setToolTip(
            self._tr(
                "未知量表：名称为要求解的变量；初始值用于数值迭代；下界/上界可选，仅部分求解器使用。不同模式可只填写需要的列。",
                "Unknowns table: Name is the variable to solve; Initial seeds numeric iteration; Lower/Upper are optional and used only by supported solvers. Fill only the columns needed by the selected mode.",
            )
        )
    constants_editor = getattr(self, "root_constants_editor", None)
    if constants_editor is not None:
        constants_editor.set_table_headers(*constants_headers)
        constants_tooltip = self._tr(
            "常数设置：填写方程中的固定量，支持 1.23(4) 和 1.23(4)[-5] 这类不确定度写法。关闭时不会代入常数表。",
            "Constants: fixed quantities used by equations; accepts uncertainty notation such as 1.23(4) and 1.23(4)[-5]. When disabled, constants are not substituted.",
        )
        constants_editor.setToolTip(constants_tooltip)
        if hasattr(constants_editor, "help_button"):
            constants_editor.help_button.setToolTip(constants_tooltip)
        if hasattr(constants_editor, "checkbox"):
            constants_editor.checkbox.setToolTip(constants_tooltip)
    tooltip_pairs = (
        (
            "root_equations_help_button",
            "方程按 F(...)=0 求解；可写多行方程组。示例：x^2 - A。",
            "Equations are solved as F(...)=0; use multiple lines for a system. Example: x^2 - A.",
        ),
        (
            "root_mode_help_button",
            "标量：单未知量单根；扫描多根：从区间/采样查找多个根；多项式：一元多项式根；方程组：多个未知量联立求解。",
            "Scalar: one unknown and one root; Scan multiple: search multiple roots by interval/sampling; Polynomial: univariate polynomial roots; System: solve coupled equations.",
        ),
        (
            "root_unknowns_help_button",
            "不同模式需要的列不同：标量通常填名称和初始值；扫描多根还可填下界/上界；多项式可只填名称；方程组每个未知量一行。",
            "Columns depend on mode: scalar usually needs name and initial; scan can use lower/upper; polynomial can use only name; system uses one row per unknown.",
        ),
    )
    for attr, zh, en in tooltip_pairs:
        widget = getattr(self, attr, None)
        if widget is not None:
            widget.setToolTip(self._tr(zh, en))
    if hasattr(self, "root_equations_edit"):
        self.root_equations_edit.setToolTip(
            self._tr(
                "输入要求解的方程。留空不会使用示例；示例只显示在背景提示中。",
                "Enter equations to solve. Leaving it blank does not use the example; the example is only placeholder text.",
            )
        )
    if hasattr(self, "root_mode_combo"):
        self.root_mode_combo.setToolTip(getattr(self, "root_mode_help_button", self.root_mode_combo).toolTip())
    button_tooltips = {
        "root_detect_unknowns_button": (
            "按当前方程、数据列和常数重新识别未知量；已删除的已识别行会被移除。",
            "Detect unknowns from the current equations, data columns, and constants; removed detected symbols are removed from the table.",
        ),
        "root_add_unknown_button": (
            "手动添加未知量行，用于补充或覆盖自动识别。",
            "Add an unknown row manually to supplement or override detection.",
        ),
        "root_remove_unknown_button": (
            "删除选中的未知量行。",
            "Remove selected unknown rows.",
        ),
    }
    for attr, (zh, en) in button_tooltips.items():
        widget = getattr(self, attr, None)
        if widget is not None:
            widget.setToolTip(self._tr(zh, en))


def _open_formula_preview(self, edit_widget, lhs=None) -> None:
    if hasattr(edit_widget, "toPlainText"):
        text = edit_widget.toPlainText().strip()
    else:
        text = edit_widget.text().strip()
    left_hand_side = lhs() if callable(lhs) else lhs
    open_formula_preview_dialog(self, text, left_hand_side)


def _open_root_formula_preview(self) -> None:
    lines = [
        line.strip()
        for line in self.root_equations_edit.toPlainText().splitlines()
        if line.strip()
    ]
    if not lines:
        expression = ""
        lhs = "F"
    elif len(lines) == 1:
        expression = lines[0]
        lhs = "F"
    else:
        expression = "\n".join(lines)
        lhs = "F_i"
    open_formula_preview_dialog(self, expression, lhs)


def _on_root_uncertainty_method_changed(self) -> None:
    method = str(self.root_uncertainty_method_combo.currentData() or "taylor")
    show_monte_carlo = method == "monte_carlo"
    show_taylor = method == "taylor"
    taylor_widget = getattr(self, "root_uncertainty_taylor_widget", None)
    if taylor_widget is not None:
        taylor_widget.setVisible(show_taylor)
    for widget_name in (
        "root_monte_carlo_samples_label",
        "root_monte_carlo_samples_spin",
        "root_monte_carlo_seed_label",
        "root_monte_carlo_seed_edit",
    ):
        widget = getattr(self, widget_name, None)
        if widget is not None:
            widget.setVisible(show_monte_carlo)

    help_text = {
        "off": self._tr("不传播输入不确定度。", "Input uncertainty is not propagated."),
        "taylor": self._tr("使用 Taylor 传播；阶数由阶数控件设置。", "Uses Taylor propagation; order is set by the order control."),
        "monte_carlo": self._tr("对输入不确定度抽样后重新求根。", "Resolves roots from sampled uncertain inputs."),
    }.get(method, "")
    self.root_uncertainty_method_help_label.setText(help_text)


def _add_detected_rows_table_row(self, table_name: str) -> None:
    table = getattr(self, table_name, None)
    if table is None:
        return
    table.add_row()


def _remove_detected_rows_table_rows(self, table_name: str) -> None:
    table = getattr(self, table_name, None)
    if table is None:
        return
    selected_rows = {index.row() for index in table.table_view.selectedIndexes()}
    if not selected_rows and table.table_view.rowCount() > 0:
        last_row = table.table_view.rowCount() - 1
        if not table.is_row_empty(last_row):
            return
        selected_rows = {last_row}
    table.delete_rows(selected_rows)


def _add_parameter_table_row(self, table_name: str) -> None:
    table = getattr(self, table_name, None)
    if table is None:
        return
    table.add_parameter_row()


def _remove_parameter_table_rows(self, table_name: str) -> None:
    table = getattr(self, table_name, None)
    if table is None:
        return
    selected_rows = {index.row() for index in table.table_view.selectedIndexes()}
    if not selected_rows and table.table_view.rowCount() > 0:
        last_row = table.table_view.rowCount() - 1
        if not table.is_row_empty(last_row):
            return
        selected_rows = {last_row}
    table.delete_rows(selected_rows)


def _clear_table(self):
    """Clear all data in the manual table."""
    table = self.manual_table
    mode = self.mode_combo.currentData() if hasattr(self, "mode_combo") else None
    column_count = 1 if mode == "root_solving" else 3
    table.setRowCount(6)
    table.setColumnCount(column_count)
    table.setHorizontalHeaderLabels([chr(65 + index) for index in range(column_count)])
    table.clearContents()
    _apply_equal_column_stretch(table)


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
