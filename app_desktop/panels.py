"""UI construction helpers for `ExtrapolationWindow`.

This module intentionally provides top-level `build_*` functions that accept the
window instance as the first argument (named `self`) and populate widgets on it.
It acts like a function-based mixin extracted from `window.py` to reduce file
size while keeping behavior unchanged.
"""
# ruff: noqa: F401, E741

from __future__ import annotations

from collections.abc import Callable
import weakref

from PySide6.QtCore import Qt, QObject, QEvent
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from formula_help import (
    get_function_help,
    get_function_tooltip,
    get_method_description,
    get_method_name,
)
from app_desktop.current_page_stack import CurrentPageStack
from app_desktop.parallel_preferences import (
    ParallelPreferencesStore,
    apply_parallel_config_to_widgets,
    save_current_parallel_config,
)
from app_desktop.result_view_titles import result_view_tab_title, result_view_tooltip
from app_desktop.shell_layout import build_workbench_bar, update_workbench_status
from app_desktop.theme import (
    CONTROL_SPACING,
    SECTION_SPACING,
    config_card_style,
    data_input_card_style,
    input_data_tabs_style,
    is_dark_theme,
    result_detail_card_style,
    result_overview_card_style,
    result_style,
    result_tab_pane_style,
    table_style,
    workbench_section_card_style,
)
from app_desktop.workbench_layout import (
    build_workbench_main_splitter,
    make_status_strip,
    reparent_widget,
    scroll_viewport_overhead,
)
from app_desktop.workbench_model_bindings import (
    bind_model_path,
    model_path_for_formula_schema_key,
    model_path_for_state_role,
)
from app_desktop.workbench_formula_panel import (
    build_formula_workspace_panel,
    populate_formula_workspace_panel,
    refresh_formula_workspace_panel,
    schedule_formula_workspace_refresh,
)
from app_desktop.workbench_results import build_result_overview
from app_desktop.history_panel import build_history_panel
from app_desktop.workbench_specs import MODE_WORKBENCH_SPECS, ModeKey
from app_desktop.workbench_variable_panel import (
    build_variable_workspace_panel,
    populate_variable_workspace_panel,
    refresh_variable_workspace_panel,
)
from app_desktop.workbench_visual_contract import WORKSPACE_CANVAS_MIN_WIDTH
from app_desktop.ui_schema_binder import bind_choices, bind_field
from app_desktop.ui_schema_runtime import (
    bind_schema_command_button,
    register_schema_text_refresh,
)
from app_desktop.views.error import build_error_mode_view
from app_desktop.views.extrapolation import build_extrapolation_mode_view
from app_desktop.views.fitting import build_fitting_mode_view
from app_desktop.views.root_solving import (
    build_root_solving_mode_view,
    on_root_uncertainty_method_changed,
    refresh_root_field_help,
)
from app_desktop.views.statistics import build_statistics_mode_view
from app_desktop.views import helpers as view_helpers
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
# Visible result subtabs, in order. TeX/PDF are intentionally NOT here: the on-demand
# LaTeX preview dialog is their viewer now (opened by the result-panel 生成 TeX / 预览 PDF
# buttons). The latex/pdf widgets are still built — hosted off-screen in
# ``_offscreen_result_views`` — so the dialog, workspace round-trip, and compile paths
# keep reading them; see build_right_panel and DESKTOP_RESULT_VIEWS (which keeps all 5
# view specs for the off-screen widgets + result_view_titles).
_RESULT_VIEW_ORDER = (
    "result.numeric",
    "result.image",
    "result.log",
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


class _FilePathChecked:
    """Compatibility stand-in for the removed 使用数据文件 checkbox.

    The data source is now driven purely by whether a file path is entered (file takes precedence
    over manual input). Callers still ask ``use_file_checkbox.isChecked()`` / ``_checked(...)``; this
    reports ``True`` iff the linked path edit is non-empty. ``setChecked`` is a no-op (the path is the
    source of truth), so workspace-restore's ``setChecked(False)`` doesn't fight it.
    """

    class _NoopSignal:
        def connect(self, *_args: object, **_kwargs: object) -> None:
            return None

    def __init__(self, path_edit: QLineEdit) -> None:
        self._path_edit = path_edit
        # Callers wire the (former) checkbox's ``toggled`` signal to mark-dirty; the path edit's
        # own textChanged already covers that, so this is a no-op sink.
        self.toggled = _FilePathChecked._NoopSignal()

    def isChecked(self) -> bool:
        return bool(self._path_edit.text().strip())

    def setChecked(self, _value: bool) -> None:
        return None

_MODE_VIEW_BUILDERS: dict[ModeKey, tuple[str, Callable[[object], QGroupBox]]] = {
    "extrapolation": ("extrap_box", build_extrapolation_mode_view),
    "error": ("error_box", build_error_mode_view),
    "fitting": ("fit_box", build_fitting_mode_view),
    "root_solving": ("root_box", build_root_solving_mode_view),
    "statistics": ("stats_box", build_statistics_mode_view),
}


def _mode_stack_order() -> tuple[ModeKey, ...]:
    return tuple(
        mode
        for mode, _spec in sorted(
            MODE_WORKBENCH_SPECS.items(),
            key=lambda item: item[1].mode_stack_index,
        )
    )


def _build_mode_stack_pages(self) -> None:
    missing = set(MODE_WORKBENCH_SPECS) - set(_MODE_VIEW_BUILDERS)
    extra = set(_MODE_VIEW_BUILDERS) - set(MODE_WORKBENCH_SPECS)
    if missing or extra:
        raise RuntimeError(
            "Mode view builders do not match MODE_WORKBENCH_SPECS: "
            f"missing={sorted(missing)}, extra={sorted(extra)}"
        )
    for mode in _mode_stack_order():
        page_attr, builder = _MODE_VIEW_BUILDERS[mode]
        page = builder(self)
        setattr(self, page_attr, page)
        self.mode_stack.addWidget(page)


def _apply_equal_column_stretch(table: QTableWidget) -> None:
    view_helpers.apply_equal_column_stretch(table)


def build_menu(self):
    menubar = self.menuBar()

    file_menu = menubar.addMenu("文件")
    file_menu.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
    self._register_text(file_menu, "文件", "File", "setTitle")

    new_workspace_action = QAction("新建工作区", self)
    new_workspace_action.setMenuRole(QAction.NoRole)
    # Standard shortcuts auto-map to the platform convention (⌘ on macOS,
    # Ctrl elsewhere) and render in the menu automatically (a11y / discoverability).
    new_workspace_action.setShortcut(QKeySequence.StandardKey.New)
    new_workspace_action.triggered.connect(self.new_workspace)
    file_menu.addAction(new_workspace_action)
    self._register_text(new_workspace_action, "新建工作区", "New Workspace", "setText")

    open_workspace_action = QAction("打开工作区…", self)
    open_workspace_action.setMenuRole(QAction.NoRole)
    open_workspace_action.setShortcut(QKeySequence.StandardKey.Open)
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
    save_workspace_action.setShortcut(QKeySequence.StandardKey.Save)
    save_workspace_action.triggered.connect(self.save_workspace)
    file_menu.addAction(save_workspace_action)
    self._register_text(save_workspace_action, "保存工作区", "Save Workspace", "setText")

    save_workspace_as_action = QAction("工作区另存为…", self)
    save_workspace_as_action.setMenuRole(QAction.NoRole)
    save_workspace_as_action.setShortcut(QKeySequence.StandardKey.SaveAs)
    save_workspace_as_action.triggered.connect(self.save_workspace_as)
    file_menu.addAction(save_workspace_as_action)
    self._register_text(save_workspace_as_action, "工作区另存为…", "Save Workspace As…", "setText")

    examples_menu = menubar.addMenu("示例")
    examples_menu.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogListView))
    self._register_text(examples_menu, "示例", "Examples", "setTitle")
    examples_menu.addAction(open_example_workspace_action)

    lang_menu = menubar.addMenu("语言")
    lang_menu.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
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

    theme_menu = menubar.addMenu("主题")
    theme_menu.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon))
    self._register_text(theme_menu, "主题", "Theme", "setTitle")
    theme_group = QActionGroup(self)
    theme_group.setExclusive(True)
    for mode, zh, en in (("auto", "自动", "Auto"), ("light", "浅色", "Light"), ("dark", "深色", "Dark")):
        action = QAction(zh, self)
        action.setMenuRole(QAction.NoRole)
        action.setCheckable(True)
        action.setChecked(mode == "auto")
        action.triggered.connect(lambda _checked=False, m=mode: self.set_theme_mode(m))
        theme_group.addAction(action)
        theme_menu.addAction(action)
        self._register_text(action, zh, en, "setText")

    help_menu = menubar.addMenu("帮助")
    help_menu.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion))
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

    # Two-pane layout: the left config sections merge into the workspace pane, so the
    # "left" aliases point at the MERGED (workspace) pane — the new left-pane source of
    # truth for sizing/scroll. ``workbench_config_*`` survive only as detached
    # compatibility attributes (never a splitter pane).
    self.left_layout = self.workbench_workspace_layout
    self.left_container = self.workbench_workspace_content
    self._left_scroll = self.workbench_workspace_canvas

    # The left workspace column is exactly TWO blocks: [输入数据 tabs] (added by _build_left_panel)
    # + [one config card]. The config card wraps the per-mode config in a single QGroupBox, ordered
    # mode config FIRST (mode_stack — holds the model selector etc.), then the shared formula input,
    # then the shared variable mapping. All three are per-mode stacked widgets that switch together;
    # the formula/variable panels self-hide in modes that don't use them (no gap). This replaces the
    # old three-separate-blocks layout so users "pick the model first, then see its fields".
    self._build_left_panel()
    self.workbench_config_card = QGroupBox()
    self.workbench_config_card.setObjectName("workbench_config_card")
    self.workbench_config_card.setProperty("datalab_config_card", True)
    _config_card_layout = QVBoxLayout(self.workbench_config_card)
    _config_card_layout.setSpacing(CONTROL_SPACING)
    # NB: inner margins are set by _style_config_card (10px) below — it is the single source of
    # the card padding and also runs on theme change, so we don't set margins here.

    # mode_stack (CurrentPageStack) pins its own height to the active page's sizeHint (no gap / no
    # clip, review S3); formula/variable panels build per-mode pages and self-hide when unused.
    reparent_widget(_config_card_layout, self.mode_stack, stretch=0)
    self.workbench_formula_panel = build_formula_workspace_panel(self)
    _config_card_layout.addWidget(self.workbench_formula_panel)
    populate_formula_workspace_panel(self)
    self.workbench_variable_panel = build_variable_workspace_panel(self)
    _config_card_layout.addWidget(self.workbench_variable_panel)
    populate_variable_workspace_panel(self)

    self.workbench_workspace_layout.addWidget(self.workbench_config_card)
    self.workbench_workspace_layout.addStretch(1)
    _style_config_card(self.workbench_config_card, dark=is_dark_theme())
    # ``output_setup_section`` and ``run_section`` are no longer added to the layout — the
    # first went empty when options moved to the toolbar dialogs, the second when the
    # bottom 开始执行 button was removed (4·4c; run is on the toolbar). Both attributes are
    # kept for compatibility but never shown.
    self._build_right_panel(self.workbench_result_layout)
    # Part C/D: always-visible result status strip (footer of the result rail) +
    # click-to-open overview popover. Both read the shared result-state source and
    # create NEW widgets — they never move the existing overview/footer widgets.
    from app_desktop.result_status_strip import build_result_status_strip
    from app_desktop.result_overview_popover import install_overview_popover_trigger

    self.workbench_result_layout.addWidget(build_result_status_strip(self))
    install_overview_popover_trigger(self)
    self._bind_workbench_state_roles()
    self._bind_workbench_spec_schema_keys()
    _connect_workbench_formula_editors(self)
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


def _bind_workbench_state_roles(self) -> None:
    self.manual_box.setObjectName("manual_box")
    self.manual_table.setObjectName("manual_table")
    self.manual_data_edit.setObjectName("manual_data_edit")
    self.mode_stack.setObjectName("mode_stack")
    self.tabs.setObjectName("result_tabs")
    self.custom_params_table.setObjectName("custom_params_table")
    self.implicit_params_table.setObjectName("implicit_params_table")
    self.root_unknowns_table.setObjectName("root_unknowns_table")
    self.input_constants_editor.setObjectName("input_constants_editor")
    shared_constants_editor = self.input_constants_editor
    for editor_name in (
        "error_constants_editor",
        "custom_constants_editor",
        "implicit_constants_editor",
        "root_constants_editor",
    ):
        editor = getattr(self, editor_name)
        if editor is not shared_constants_editor:
            editor.setObjectName(editor_name)

    self.input_constants_editor.setProperty("datalab_state_role", "input_constants_owner")
    bind_model_path(self.input_constants_editor, model_path_for_state_role("input_constants_owner"))

    self.manual_box.setProperty("datalab_state_role", "manual_data_owner")
    bind_model_path(self.manual_box, model_path_for_state_role("manual_data_owner"))
    self.manual_table.setProperty("datalab_state_role", "manual_table_editor")
    bind_model_path(self.manual_table, model_path_for_state_role("manual_table_editor"))
    self.manual_data_edit.setProperty("datalab_state_role", "manual_text_editor")
    bind_model_path(self.manual_data_edit, model_path_for_state_role("manual_text_editor"))
    self.mode_stack.setProperty("datalab_state_role", "mode_stack_owner")
    bind_model_path(self.mode_stack, model_path_for_state_role("mode_stack_owner"))
    self.tabs.setProperty("datalab_state_role", "result_tabs_owner")
    bind_model_path(self.tabs, model_path_for_state_role("result_tabs_owner"))
    for spec in MODE_WORKBENCH_SPECS.values():
        for mount in spec.parameters + spec.constants + spec.tables:
            widget = getattr(self, mount.widget_attr)
            widget.setProperty("datalab_state_role", mount.state_role)
            bind_model_path(
                widget,
                model_path_for_state_role(mount.state_role, schema_key=mount.schema_key),
            )


def _bind_workbench_spec_schema_keys(self) -> None:
    for spec in MODE_WORKBENCH_SPECS.values():
        for formula in spec.formulas:
            editor = getattr(self, formula.editor_attr, None)
            if editor is not None:
                editor.setProperty("datalab_schema_key", formula.schema_key)
                bind_model_path(editor, model_path_for_formula_schema_key(formula.schema_key))
            button = getattr(self, formula.preview_button_attr, None)
            if button is not None:
                button.setProperty("datalab_schema_key", formula.schema_key)
        for mount in spec.parameters + spec.constants + spec.tables:
            widget = getattr(self, mount.widget_attr, None)
            if widget is not None:
                widget.setProperty("datalab_schema_key", mount.schema_key)


def _connect_workbench_formula_editors(self) -> None:
    callbacks = []
    owner_ref = weakref.ref(self)
    for spec in MODE_WORKBENCH_SPECS.values():
        for formula in spec.formulas:
            editor = getattr(self, formula.editor_attr, None)
            if editor is not None and hasattr(editor, "textChanged"):
                def _refresh_formula(*args, _attr=formula.editor_attr) -> None:
                    owner = owner_ref()
                    if owner is not None:
                        schedule_formula_workspace_refresh(owner, _attr)

                callbacks.append(_refresh_formula)
                editor.textChanged.connect(_refresh_formula)
    self._workbench_formula_text_changed_callbacks = callbacks


def refresh_workbench_formula_panel(self) -> None:
    refresh_formula_workspace_panel(self)


def refresh_workbench_variable_panel(self) -> None:
    refresh_variable_workspace_panel(self)


def refresh_workbench_config_cards(self) -> None:
    for section in _config_card_sections(self):
        _style_config_card(section, dark=is_dark_theme())


def refresh_workbench_section_cards(self) -> None:
    qss = workbench_section_card_style(dark=is_dark_theme())
    for section in self.findChildren(QGroupBox):
        if section.property("datalab_workbench_section_host") is True and section.styleSheet() != qss:
            section.setStyleSheet(qss)


def refresh_workbench_data_card(self) -> None:
    manual_box = getattr(self, "manual_box", None)
    if manual_box is not None:
        manual_box.setStyleSheet(data_input_card_style(dark=is_dark_theme()))


def refresh_workbench_data_summary(self) -> None:
    _update_data_summary(self)


def refresh_workbench_result_overview_card(self) -> None:
    panel = getattr(self, "workbench_result_overview_panel", None)
    if panel is not None:
        panel.setStyleSheet(result_overview_card_style(dark=is_dark_theme()))


def refresh_workbench_result_details_card(self) -> None:
    panel = getattr(self, "workbench_result_details_panel", None)
    if panel is not None:
        panel.setStyleSheet(result_detail_card_style(dark=is_dark_theme()))


def _clamp_workbench_splitter_sizes(sizes: list[int], minimums: list[int], total: int) -> list[int]:
    if total <= sum(minimums):
        return list(minimums)
    clamped = [max(size, minimum) for size, minimum in zip(sizes, minimums, strict=True)]
    overflow = sum(clamped) - total
    while overflow > 0:
        surplus = [size - minimum for size, minimum in zip(clamped, minimums, strict=True)]
        candidates = [(available, index) for index, available in enumerate(surplus) if available > 0]
        if not candidates:
            break
        total_surplus = sum(available for available, _ in candidates)
        reductions: list[tuple[int, int]] = []
        pass_overflow = overflow
        for available, index in candidates:
            proportional = int(pass_overflow * (available / total_surplus))
            reductions.append((index, min(available, proportional)))
        if not any(reduction for _, reduction in reductions):
            _, index = max(candidates)
            reductions = [(index, 1)]
        for index, reduction in reductions:
            if overflow <= 0:
                break
            reduction = min(reduction, clamped[index] - minimums[index], overflow)
            if reduction <= 0:
                continue
            clamped[index] -= reduction
            overflow -= reduction
    return clamped


def _refresh_main_splitter_left_min_width(self) -> None:
    # Two-pane layout: the merged (workspace) pane IS the left pane. Its minimum width
    # is derived from the merged content, NOT the detached config rail. Pane 0 = merged
    # workspace, pane 1 = result.
    merged_content = getattr(self, "workbench_workspace_content", None)
    merged_scroll = getattr(self, "workbench_workspace_canvas", None)
    if merged_content is not None and merged_scroll is not None:
        _activate_widget_layouts(merged_content)
        _refresh_visible_table_min_widths(merged_content)

        # The merged pane holds BOTH input and config, so its floor is the workspace
        # canvas minimum (wider than the old config-rail minimum).
        content_min_width = max(
            WORKSPACE_CANVAS_MIN_WIDTH,
            merged_content.minimumSizeHint().width(),
        )
        merged_content.setMinimumWidth(content_min_width)
        left_min_width = content_min_width + scroll_viewport_overhead(merged_scroll)
        self._main_splitter_left_min_width = left_min_width
        merged_scroll.setMinimumWidth(left_min_width)

        splitter = getattr(self, "_main_splitter", None)
        result_rail = getattr(self, "workbench_result_rail", None)
        if splitter is None or splitter.count() < 2 or result_rail is None:
            return

        right_min_width = max(1, result_rail.minimumWidth())
        sizes = splitter.sizes()
        if not sizes or len(sizes) < 2:
            splitter.setSizes([left_min_width, right_min_width])
            return
        pane_sizes = sizes[:2]
        minimums = [left_min_width, right_min_width]
        if all(size >= minimum for size, minimum in zip(pane_sizes, minimums, strict=True)):
            return

        handle_total = splitter.handleWidth() * max(0, splitter.count() - 1)
        total = sum(pane_sizes) or max(0, splitter.width() - handle_total - sum(sizes[2:]))
        clamped = _clamp_workbench_splitter_sizes(pane_sizes, minimums, total)
        if clamped != pane_sizes:
            splitter.setSizes(clamped + sizes[2:])
        return


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


def _config_card_sections(self) -> tuple[QWidget, ...]:
    # run_section is no longer a visible card (bottom 开始执行 removed in 4·4c); only the
    # input section remains a styled config card in the merged pane.
    sections: list[QWidget] = []
    for attr in ("input_section", "workbench_config_card"):
        section = getattr(self, attr, None)
        if isinstance(section, QWidget):
            sections.append(section)
    return tuple(sections)


def _style_config_card(section: QWidget, *, dark: bool | None = None) -> None:
    section.setProperty("datalab_config_card", True)
    section.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    layout = section.layout()
    if layout is not None:
        layout.setContentsMargins(10, 10, 10, 10)
    section.setStyleSheet(config_card_style(dark=dark))
    section.style().unpolish(section)
    section.style().polish(section)


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

    refresh_workbench_config_cards(self)

    # Two-pane layout: the left config sections live in the MERGED workspace pane
    # (``left_layout`` is aliased to the workspace layout in build_ui). Only the input
    # section is added here, at the TOP; the per-mode config (formula/mode_stack) is
    # added by build_ui right after, and ``output_setup_section`` + ``run_section`` are
    # appended at the BOTTOM by build_ui (see _append_left_footer_sections). This yields
    # the confirmed order: 输入 (top) → 配置 → 输出设置 → 运行.
    # ``mode_section``/``mode_box`` are kept as detached compatibility attributes but are
    # NOT added to any pane (the mode selector is on the toolbar).
    self.left_layout.addWidget(self.input_section)

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
    # The mode selector now lives on the workbench toolbar, not in the left-rail
    # ``mode_box`` card. Insert the SAME ``mode_combo`` widget into the toolbar's
    # reserved slot (``_toolbar_mode_slot``, created in build_workbench_toolbar).
    # ``mode_box``/``mode_section`` are kept as detached compatibility attributes.
    mode_slot = getattr(self, "_toolbar_mode_slot", None)
    if mode_slot is not None:
        mode_slot.addWidget(self.mode_combo)
    else:  # pragma: no cover - toolbar always builds first in build_ui
        mode_layout.addWidget(self.mode_combo)

    # Data file — label + path edit + Browse all on ONE row. No 使用数据文件 checkbox: the file
    # picker sits directly with the data, and a non-empty path takes PRECEDENCE over the manual
    # input below (see _active_input_bundle).
    # Plain container (matches the 常数 tab's constants_file_row exactly). A little L/R padding so
    # the row isn't flush against the tab edge, and the tab layout adds a gap before the card below.
    self.file_box = QWidget()
    file_layout = QHBoxLayout(self.file_box)
    file_layout.setContentsMargins(4, 2, 4, 2)
    file_layout.setSpacing(6)
    self._data_file_label = QLabel(self._tr("数据文件：", "Data file:"))
    self._register_text(self._data_file_label, "数据文件：", "Data file:")
    file_layout.addWidget(self._data_file_label)
    self.data_file_edit = QLineEdit()
    self.data_file_edit.setPlaceholderText(
        self._tr("数据文件路径（可选，填写后忽略下方手动输入）", "Data file path (optional; overrides manual input below)")
    )
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
    # Compatibility shim: many callers read `use_file_checkbox.isChecked()` / _checked(...) to
    # decide file-vs-manual. With the checkbox gone, this shim reports checked==(a file path is
    # entered), so every existing caller gets file-precedence with no per-caller change.
    self.use_file_checkbox = _FilePathChecked(self.data_file_edit)
    self.file_box.show()

    # Manual data — table editor + text fallback
    self.manual_box = QGroupBox("")
    self.manual_box.setProperty("datalab_data_card", True)
    self.manual_box.setStyleSheet(data_input_card_style(dark=is_dark_theme()))
    manual_layout = QVBoxLayout(self.manual_box)
    manual_layout.setContentsMargins(10, 8, 10, 10)
    manual_layout.setSpacing(6)

    data_header = QHBoxLayout()
    data_header.setContentsMargins(0, 0, 0, 0)
    data_header.setSpacing(6)
    self.manual_data_title = QLabel("输入数据")
    self.manual_data_title.setObjectName("manual_data_title")
    self._register_text(self.manual_data_title, "输入数据", "Data input")
    data_header.addWidget(self.manual_data_title)
    data_header.addStretch()
    self.manual_data_summary = QLabel("")
    self.manual_data_summary.setObjectName("manual_data_summary")
    data_header.addWidget(self.manual_data_summary)
    manual_layout.addLayout(data_header)

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
    self.manual_data_toolbar_buttons = (
        add_col_btn,
        remove_col_btn,
        add_row_btn,
        remove_row_btn,
        clear_btn,
        self._data_view_toggle,
    )
    for toolbar_button in self.manual_data_toolbar_buttons:
        toolbar_button.setProperty("datalab_data_toolbar_button", True)
    table_toolbar.addWidget(add_col_btn)
    table_toolbar.addWidget(remove_col_btn)
    table_toolbar.addWidget(add_row_btn)
    table_toolbar.addWidget(remove_row_btn)
    table_toolbar.addWidget(clear_btn)
    table_toolbar.addWidget(self._data_view_toggle)
    table_toolbar.addStretch()
    # ? help button on the right of the data toolbar (mirrors the constants editor's ?).
    self.manual_data_help_btn = QPushButton("?")
    self.manual_data_help_btn.setFlat(True)
    self.manual_data_help_btn.setFixedWidth(24)
    self.manual_data_help_btn.setFocusPolicy(Qt.NoFocus)
    self.manual_data_help_btn.setToolTip(
        self._tr(
            "输入数据：每列一个变量，每行一组数据；也可用上方“数据文件”从文件读取。",
            "Data input: one variable per column, one sample per row; or read from a file via 数据文件 above.",
        )
    )
    self._register_text(
        self.manual_data_help_btn,
        "输入数据：每列一个变量，每行一组数据；也可用上方“数据文件”从文件读取。",
        "Data input: one variable per column, one sample per row; or read from a file via 数据文件 above.",
        "setToolTip",
    )
    self.manual_data_help_btn.clicked.connect(self._show_data_file_hint)
    table_toolbar.addWidget(self.manual_data_help_btn)
    manual_layout.addLayout(table_toolbar)

    # Stacked widget: table view (0) / text view (1)
    self._data_stack = QStackedWidget()

    self.manual_table = QTableWidget(1, 3)
    self.manual_table.setHorizontalHeaderLabels(["A", "B", "C"])
    self.manual_table.verticalHeader().setVisible(True)
    _apply_equal_column_stretch(self.manual_table)
    self.manual_table.setAlternatingRowColors(True)
    self.manual_table.setStyleSheet(view_helpers.get_table_style())
    # Excel-like block selection + copy: select a rectangular range and Ctrl/Cmd+C copies it
    # as TSV (paste handled by the same filter).
    self.manual_table.setSelectionMode(QAbstractItemView.SelectionMode.ContiguousSelection)
    self.manual_table.installEventFilter(_TablePasteFilter(self.manual_table, self))
    self.manual_table.itemChanged.connect(lambda *_args: _update_data_summary(self))
    manual_table_model = self.manual_table.model()
    manual_table_model.rowsInserted.connect(lambda *_args: _refresh_manual_table_summary_from_model(self))
    manual_table_model.rowsRemoved.connect(lambda *_args: _refresh_manual_table_summary_from_model(self))
    manual_table_model.columnsInserted.connect(lambda *_args: _refresh_manual_table_summary_from_model(self))
    manual_table_model.columnsRemoved.connect(lambda *_args: _refresh_manual_table_summary_from_model(self))
    manual_table_model.modelReset.connect(lambda *_args: _refresh_manual_table_summary_from_model(self))
    view_helpers.fit_table_height_to_contents(self.manual_table)
    self._data_stack.addWidget(self.manual_table)

    self.manual_data_edit = QPlainTextEdit()
    self._data_stack.addWidget(self.manual_data_edit)

    self._data_stack.setCurrentIndex(_STACK_PAGE_TABLE)  # table view by default
    manual_layout.addWidget(self._data_stack)

    from app_desktop.constants_editor import ConstantsEditor
    self.input_constants_editor = ConstantsEditor(min_rows=1, checked=False, numeric_mode="uncertainty")
    self.input_constants_editor.set_embedded_in_workbench(True)

    # Merge input data + constants into sheet-like tabs (输入数据 / 常数) to reuse space instead
    # of stacking two tables. The 常数 tab is added/removed by mode (see _set_constants_tab_
    # visible) — only constant-using modes (error/custom-fit/implicit) show it.
    # Each tab is SELF-CONTAINED: the 输入数据 tab holds its own 使用数据文件 checkbox + file
    # picker + table, so the data-file toggle can never bleed into the 常数 tab.
    self._data_tab = QWidget()
    _data_tab_layout = QVBoxLayout(self._data_tab)
    _data_tab_layout.setContentsMargins(0, 6, 0, 0)
    _data_tab_layout.setSpacing(10)  # gap between the file row and the data card below
    _data_tab_layout.addWidget(self.file_box)
    _data_tab_layout.addWidget(self.manual_box)

    # 常数 tab: its OWN 使用数据文件 checkbox + file picker (independent from the data tab).
    # The backend already supports constants-from-file (workers_core reads constants_file_path);
    # only the UI was missing. Manual constants table hides when the file source is on.
    self._constants_tab = QWidget()
    _const_tab_layout = QVBoxLayout(self._constants_tab)
    _const_tab_layout.setContentsMargins(0, 6, 0, 0)
    _const_tab_layout.setSpacing(10)  # gap between the file row and the constants card below

    # Symmetric with the data tab: no checkbox — a non-empty constants-file path takes precedence
    # over the manual constants table below.
    self.constants_file_row = QWidget()
    _const_file_layout = QHBoxLayout(self.constants_file_row)
    _const_file_layout.setContentsMargins(4, 2, 4, 2)
    _const_file_layout.setSpacing(6)
    _const_file_label = QLabel(self._tr("常数文件：", "Constants file:"))
    self._register_text(_const_file_label, "常数文件：", "Constants file:")
    _const_file_layout.addWidget(_const_file_label)
    self.constants_file_edit = QLineEdit()
    self.constants_file_edit.setPlaceholderText(
        self._tr("常数文件路径（可选，填写后忽略下方手动输入）", "Constants file path (optional; overrides manual input below)")
    )
    _const_file_layout.addWidget(self.constants_file_edit)
    _const_browse = QPushButton("浏览…")
    _const_browse.clicked.connect(self.browse_constants_file)
    self._register_text(_const_browse, "浏览…", "Browse…")
    _const_file_layout.addWidget(_const_browse)
    self.constants_file_row.show()
    self.use_constants_file_checkbox = _FilePathChecked(self.constants_file_edit)
    _const_tab_layout.addWidget(self.constants_file_row)
    _const_tab_layout.addWidget(self.input_constants_editor)

    self.input_data_tabs = QTabWidget()
    self.input_data_tabs.setObjectName("input_data_tabs")
    # documentMode=False so the styled pane border (rounded, from input_data_tabs_style) renders.
    self.input_data_tabs.setDocumentMode(False)
    self.input_data_tabs.setStyleSheet(input_data_tabs_style(dark=is_dark_theme()))
    self.input_data_tabs.addTab(self._data_tab, self._tr("输入数据", "Data input"))
    self.input_data_tabs.addTab(self._constants_tab, self._tr("常数", "Constants"))

    # Expand/collapse toggle in the tab bar's top-right corner: expands the input area rightward
    # (widening the left pane) to show many data columns, then collapses back to the default width.
    # Smooth width animation lives on the window (_toggle_input_area_expanded).
    self.input_expand_button = QToolButton()
    self.input_expand_button.setObjectName("input_expand_button")
    self.input_expand_button.setText("⤢")
    self.input_expand_button.setCheckable(True)
    self.input_expand_button.setCursor(Qt.PointingHandCursor)
    self.input_expand_button.setFocusPolicy(Qt.NoFocus)
    self.input_expand_button.setAutoRaise(True)
    self.input_expand_button.setToolTip(self._tr("展开输入区（显示更多数据列）", "Expand the input area (show more data columns)"))
    self._register_text(
        self.input_expand_button,
        "展开输入区（显示更多数据列）",
        "Expand the input area (show more data columns)",
        "setToolTip",
    )
    self.input_expand_button.clicked.connect(self._toggle_input_area_expanded)
    self.input_data_tabs.setCornerWidget(self.input_expand_button, Qt.TopRightCorner)

    self.input_section_layout.addWidget(self.input_data_tabs)

    self.error_constants_editor = self.input_constants_editor
    self.custom_constants_editor = self.input_constants_editor
    self.implicit_constants_editor = self.input_constants_editor
    self.root_constants_editor = self.input_constants_editor

    self._update_data_summary = lambda: _update_data_summary(self)
    _update_data_summary(self)

    self.mode_stack = CurrentPageStack()
    self.mode_stack.setObjectName("mode_stack")
    # CurrentPageStack pins its own fixed height to the ACTIVE page's sizeHint (see
    # current_page_stack.py) — this is what prevents both the hollow gap on short modes and the
    # clip on modes whose config grows after layout (review S3). No size-policy override needed.
    _build_mode_stack_pages(self)

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

    # Uncertainty digits option (always visible, not tied to LaTeX toggle).
    # The widget itself is created here so the FormFieldSpec binding + reveal system keep
    # working, but it is PLACED in the result panel's display-format row (see build_result_*),
    # next to 小数位数/科学计数法, so it can be adjusted post-run with live re-render. Its label
    # travels with it; we keep a reference for that placement.
    self.uncertainty_digits_spin = QSpinBox()
    self.uncertainty_digits_spin.setRange(1, 12)
    self.uncertainty_digits_spin.setValue(1)
    unc_label = QLabel("不确定度位数：")
    self._register_text(unc_label, "不确定度位数：", "Uncertainty digits:")
    self.uncertainty_digits_label = unc_label

    precision_layout.addWidget(label_precision)
    precision_layout.addWidget(self.mpmath_precision_spin)
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
    # The "生成 LaTeX 文件" checkbox was removed (4·4d): the run never writes tex (tex is
    # generated on demand from the result), so it gated nothing. The LaTeX options below are
    # now always visible in the LaTeX 选项 dialog.
    self.latex_options_widget = QWidget()
    latex_layout = QFormLayout(self.latex_options_widget)
    # The LaTeX output PATH field is no longer shown in the options — the path is chosen
    # at save-time via the TeX window's Save dialog (Module 1). ``output_file_edit`` is
    # kept as a DETACHED widget on ``self`` so the save/persist code paths that reference
    # ``self.output_file_edit`` keep working; it is simply not placed in the options UI.
    self.output_file_edit = QLineEdit()
    out_btn = QPushButton("选择…")
    out_btn.clicked.connect(self.browse_output_file)
    self._register_text(out_btn, "选择…", "Browse…")
    self.output_browse_button = out_btn
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
        prec_label=prec_label,
        group_size_label=group_size_label,
    )

    # NOTE: ``latex_engine_combo`` + the engine-path picker were moved
    # into the LaTeX output tab (next to the font-size row) because
    # they're compile-time, not compute-time, controls. The widgets
    # are still created on ``self`` so other code paths
    # (window_latex_pdf_mixin.compile_latex_to_pdf) keep working
    # unchanged — they reference ``self.latex_engine_combo``.

    # Low-frequency options live in two resizable, non-modal QDialog windows (计算 /
    # LaTeX), opened from the toolbar buttons (see app_desktop.options_dialogs; user
    # chose "真独立窗口"). The REAL controls are reparented — never recreated — into each
    # dialog's content widget, so their schema keys, signal wirings, and parallel-prefs
    # persistence (all set up above) survive intact. The run pipeline keeps reading
    # ``self.<widget>`` unchanged; the controls just live in the dialog now.
    from app_desktop.options_dialogs import (
        add_separator,
        bind_options_button,
        build_options_dialog,
    )

    # Detach the already-built groups from options_layout (a layout/widget has one parent
    # layout), then re-add to each dialog's content — reparenting the SAME instances.
    options_layout.removeItem(precision_layout)
    options_layout.removeItem(parallel_layout)
    options_layout.removeWidget(self.latex_options_widget)
    options_layout.removeWidget(self.generate_plots_checkbox)
    options_layout.removeWidget(self.verbose_checkbox)

    compute_content = QWidget()
    compute_content.setObjectName("compute_options_content")
    compute_layout = QVBoxLayout(compute_content)
    compute_layout.addLayout(precision_layout)
    compute_layout.addLayout(parallel_layout)
    add_separator(compute_layout)
    compute_layout.addWidget(self.generate_plots_checkbox)
    compute_layout.addWidget(self.verbose_checkbox)

    latex_content = QWidget()
    latex_content.setObjectName("latex_options_content")
    latex_content_layout = QVBoxLayout(latex_content)
    latex_content_layout.addWidget(self.latex_options_widget)
    # The engine selector row is built later (with the off-screen latex widgets); keep a
    # handle to this layout so it can be appended into the LaTeX 选项 dialog then.
    self._latex_options_content_layout = latex_content_layout

    self.compute_options_dialog = build_options_dialog(
        self, "compute_options_dialog", "计算选项", "Compute options", compute_content
    )
    self.latex_options_dialog = build_options_dialog(
        self, "latex_options_dialog", "LaTeX 选项", "LaTeX options", latex_content
    )
    bind_options_button(self.workbench_compute_options_button, self.compute_options_dialog)
    # latex_options_dialog is opened from the result-panel 「LaTeX 选项」 button
    # (result_latex_options_button), bound in build_right_panel after that button exists.

    # The bottom 开始执行 button was removed (4·4c): it duplicated the toolbar 运行 button.
    # Run/stop is driven by the toolbar 运行 / 停止 pair (workbench_run_button /
    # workbench_stop_button); Ctrl+Return runs via the toolbar run button (shortcut set in
    # workbench_toolbar.py). run_section stays an empty compat widget, not added to the
    # layout (like output_setup_section).
    self._update_model_controls()

def build_right_panel(self, layout: QVBoxLayout):
    # The overview card is built but NOT added to the visible layout: the toolbar status chip
    # is the overview entry point now (user-approved). The widget stays alive off-layout so
    # refresh_result_overview's writes to its sub-widgets remain valid (mirrors the 4·4b
    # "remove from view, keep widget" pattern), and the popover reads the same result state.
    # Parent it to the window and hide it so it is not a leaked top-level widget (CodeRabbit).
    self.workbench_result_overview_panel = build_result_overview(self)
    self.workbench_result_overview_panel.setParent(self)
    self.workbench_result_overview_panel.hide()
    # History is opened from a toolbar 历史 button as a popup now (user request), so the panel
    # is NOT added to the result layout — it is parented to the window and hidden until the
    # popup hosts it (history_popup.toggle_history_popup reparents the real widget in/out).
    self.workbench_history_panel = build_history_panel(self)
    self.workbench_history_panel.setParent(self)
    self.workbench_history_panel.hide()

    self.workbench_result_details_panel = QWidget()
    self.workbench_result_details_panel.setObjectName("workbench_result_details_panel")
    self.workbench_result_details_panel.setProperty("datalab_result_detail_card", True)
    self.workbench_result_details_panel.setStyleSheet(result_detail_card_style(dark=is_dark_theme()))
    details_layout = QVBoxLayout(self.workbench_result_details_panel)
    details_layout.setContentsMargins(10, 8, 10, 10)
    details_layout.setSpacing(6)
    self.workbench_result_details_title = QLabel(self._tr("结果详情", "Result details"))
    self.workbench_result_details_title.setObjectName("workbench_result_details_title")
    self._register_text(self.workbench_result_details_title, "结果详情", "Result details")
    details_layout.addWidget(self.workbench_result_details_title)
    self.workbench_result_details_empty_panel = QWidget()
    self.workbench_result_details_empty_panel.setObjectName("workbench_result_details_empty_panel")
    empty_layout = QVBoxLayout(self.workbench_result_details_empty_panel)
    empty_layout.setContentsMargins(8, 8, 8, 8)
    empty_layout.setSpacing(6)
    empty_layout.addStretch(1)
    self.workbench_result_details_empty_label = QLabel(self._tr("暂无结果详情", "No result details"))
    self.workbench_result_details_empty_label.setObjectName("workbench_result_details_empty_label")
    self.workbench_result_details_empty_label.setWordWrap(True)
    self.workbench_result_details_empty_label.setAlignment(Qt.AlignCenter)
    self._register_text(self.workbench_result_details_empty_label, "暂无结果详情", "No result details")
    empty_layout.addWidget(self.workbench_result_details_empty_label)
    empty_layout.addStretch(1)
    details_layout.addWidget(self.workbench_result_details_empty_panel, 1)

    self.tabs = QTabWidget()
    self.tabs.setProperty("datalab_schema_key", "main.result_tabs")
    self.tabs.setDocumentMode(True)
    self.tabs.tabBar().hide()
    self.tabs.setStyleSheet(result_tab_pane_style())
    details_layout.addWidget(self.tabs, 1)
    layout.addWidget(self.workbench_result_details_panel, 1)

    # Result tab
    result_widget = QWidget()
    result_layout = QVBoxLayout(result_widget)
    result_layout.setContentsMargins(0, 0, 0, 0)
    result_layout.setSpacing(8)
    # On-demand LaTeX buttons: 生成 TeX rebuilds the tex from the current result and opens
    # the LaTeX preview window on the TeX tab; 预览 PDF also compiles + shows the PDF tab.
    latex_button_row = QHBoxLayout()
    latex_button_row.setContentsMargins(0, 0, 0, 0)
    self.result_generate_tex_button = QPushButton("生成 TeX")
    self.result_generate_tex_button.setObjectName("result_generate_tex_button")
    self._register_text(self.result_generate_tex_button, "生成 TeX", "Generate TeX")
    self.result_generate_tex_button.clicked.connect(
        lambda _c=False: self.open_latex_preview("tex")
    )
    self.result_preview_pdf_button = QPushButton("预览 PDF")
    self.result_preview_pdf_button.setObjectName("result_preview_pdf_button")
    self._register_text(self.result_preview_pdf_button, "预览 PDF", "Preview PDF")
    self.result_preview_pdf_button.clicked.connect(
        lambda _c=False: self.open_latex_preview("pdf")
    )
    # LaTeX 选项 opens the (existing) latex_options_dialog — the entry moved here from the
    # toolbar (user: 工具栏不需要 latex). The dialog is built later in build_left_panel;
    # the button→dialog binding happens there once the dialog exists.
    self.result_latex_options_button = QPushButton("LaTeX 选项")
    self.result_latex_options_button.setObjectName("result_latex_options_button")
    self._register_text(self.result_latex_options_button, "LaTeX 选项", "LaTeX options")
    from app_desktop.options_dialogs import bind_options_button

    bind_options_button(self.result_latex_options_button, self.latex_options_dialog)
    latex_button_row.addWidget(self.result_generate_tex_button)
    latex_button_row.addWidget(self.result_preview_pdf_button)
    latex_button_row.addWidget(self.result_latex_options_button)
    latex_button_row.addStretch(1)
    result_layout.addLayout(latex_button_row)

    self.result_tabs = QTabWidget()
    self.result_tabs.setObjectName("result_detail_tabs")
    self.result_tabs.setDocumentMode(True)
    self.result_tabs.tabBar().setUsesScrollButtons(False)
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
        _result_view_alias(view_key): result_view_tab_title(view_key, _LANG_ZH)
        for view_key in _RESULT_VIEW_ORDER
    }

    numeric_tab = QWidget()
    numeric_layout = QVBoxLayout(numeric_tab)
    self.result_edit = QTextBrowser()
    self.result_edit.setProperty("datalab_schema_key", "results.numeric.markdown")
    self.fit_result_edit = self.result_edit
    self.result_edit.setReadOnly(True)
    self.result_edit.setOpenExternalLinks(False)
    self.result_edit.setStyleSheet(result_style())
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
    # Uncertainty digits sits alongside 小数位数/科学计数法 so it can be tuned AFTER a run with a
    # live re-render (_format_error/extrapolation_display already read _uncertainty_digits_value
    # at render time — connecting valueChanged is all that's needed). The widget was created in
    # build_left_panel (keeping its FormFieldSpec binding); it is reparented into this row.
    if hasattr(self, "uncertainty_digits_spin"):
        fmt_row.addSpacing(8)
        if hasattr(self, "uncertainty_digits_label"):
            fmt_row.addWidget(self.uncertainty_digits_label)
        self.uncertainty_digits_spin.valueChanged.connect(self._on_display_format_changed)
        fmt_row.addWidget(self.uncertainty_digits_spin)
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
    numeric_index = self.result_tabs.addTab(numeric_tab, result_view_tab_title(numeric_spec.key, _LANG_ZH))
    self.result_tabs.setTabToolTip(numeric_index, result_view_tooltip(numeric_spec.key, _LANG_ZH))
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
    image_index = self.result_tabs.addTab(image_tab, result_view_tab_title(image_spec.key, _LANG_ZH))
    self.result_tabs.setTabToolTip(image_index, result_view_tooltip(image_spec.key, _LANG_ZH))

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
    self.log_tab_index = self.result_tabs.addTab(log_widget, result_view_tab_title(log_spec.key, _LANG_ZH))
    self.result_tabs.setTabToolTip(self.log_tab_index, result_view_tooltip(log_spec.key, _LANG_ZH))

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

    latex_controls_row.addStretch()
    latex_layout.addLayout(latex_controls_row)

    latex_layout.addWidget(self.latex_edit)

    # LaTeX ENGINE selector — placed in the LaTeX 选项 dialog (not this off-screen latex tab)
    # so the user can actually see + pick it. First item 自动; then the engines actually
    # detected on this machine (populate_latex_engine_combo).
    lbl_engine = QLabel("LaTeX 引擎：")
    self._register_text(lbl_engine, "LaTeX 引擎：", "LaTeX engine:")
    self.latex_engine_combo = QComboBox()
    populate_latex_engine_combo(self)
    engine_btn = QPushButton("选择引擎路径…")
    engine_btn.clicked.connect(self._prompt_engine_selection)
    self._register_text(engine_btn, "选择引擎路径…", "Select engine path…")
    self.latex_engine_path_button = engine_btn
    _engine_row_widget = QWidget()
    _engine_row = QHBoxLayout(_engine_row_widget)
    _engine_row.setContentsMargins(0, 0, 0, 0)
    _engine_row.addWidget(lbl_engine)
    _engine_row.addWidget(self.latex_engine_combo)
    _engine_row.addWidget(engine_btn)
    _engine_row.addStretch()
    if getattr(self, "_latex_options_content_layout", None) is not None:
        self._latex_options_content_layout.addWidget(_engine_row_widget)

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

    # TeX/PDF are NOT added as tabs (the preview dialog is their viewer). The widgets stay
    # alive in an off-screen holder — a hidden child of the details panel — so schema-scan
    # /findChildren still see them (schema keys + bindings intact) while nothing shows them
    # as a tab. latex_edit is read by the preview dialog + workspace + compile; pdf_* by the
    # PDF preview mixin.
    self._offscreen_result_views = QWidget(self.workbench_result_details_panel)
    self._offscreen_result_views.setObjectName("offscreen_result_views")
    _offscreen_layout = QVBoxLayout(self._offscreen_result_views)
    _offscreen_layout.setContentsMargins(0, 0, 0, 0)
    _offscreen_layout.addWidget(latex_widget)
    _offscreen_layout.addWidget(pdf_widget)
    self._offscreen_result_views.setVisible(False)

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

def _refresh_manual_table_summary_from_model(self) -> None:
    table = getattr(self, "manual_table", None)
    if table is None:
        return
    try:
        table.rowCount()
    except RuntimeError:
        return
    _update_data_summary(self)


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
        _update_data_summary(self)
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

    model = table.model()
    previous_table_blocked = table.blockSignals(True)
    previous_model_blocked = model.blockSignals(True)
    try:
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

        table.clearContents()
        table.setRowCount(max(len(result.rows) + 1, 1))
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
    finally:
        model.blockSignals(previous_model_blocked)
        table.blockSignals(previous_table_blocked)
    _update_data_summary(self)


def _update_data_summary(self):
    """Update the data summary label with row × col count."""
    summary_label = getattr(self, "manual_data_summary", None)
    if summary_label is None:
        return
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
    row_unit = "row" if data_rows == 1 else "rows"
    column_unit = "column" if cols == 1 else "columns"
    summary_label.setText(
        self._tr(
            f"{data_rows} 行 · {cols} 列",
            f"{data_rows} {row_unit} · {cols} {column_unit}",
        )
    )
    view_helpers.fit_table_height_to_contents(table)


def _mark_schema_choices(combo: QComboBox) -> None:
    combo.setProperty("datalab_schema_choices", True)


# Source labels for detected engines, shown after the engine name in the dropdown.
_ENGINE_SOURCE_LABELS = {
    "system": ("系统", "system"),
    "bundled": ("捆绑", "bundled"),
    "auto-tectonic": ("内置", "bundled"),
}


def populate_latex_engine_combo(self) -> None:
    """Fill ``latex_engine_combo`` with 自动 + the engines actually detected on this machine.

    Item data is ``"auto"`` for the auto entry, or the engine's absolute PATH for a concrete
    pick (the compile mixin uses the path directly). The 自动 label retranslates on language
    switch; engine names are proper nouns and stay as-is. Called once at build time (and
    again by a refresh if the environment changes)."""
    from shared.latex_engine import discover_all_engines

    combo = self.latex_engine_combo
    current = combo.currentData()
    combo.blockSignals(True)
    combo.clear()

    lang_en = bool(getattr(self, "_is_en", lambda: False)())
    combo.addItem("Auto" if lang_en else "自动", "auto")
    # NOT registered with _register_combo — that generic sweep would rebuild the whole combo
    # from a static list and wipe the dynamic engine rows. Instead _apply_language re-runs
    # this function (see _refresh_engine_combo_language) so 自动↔Auto retranslates while the
    # detected engine rows are preserved.

    for name, choice in discover_all_engines():
        src_zh, src_en = _ENGINE_SOURCE_LABELS.get(choice.source, (choice.source, choice.source))
        label = f"{name} ({src_en if lang_en else src_zh})"
        combo.addItem(label, choice.path)

    if current is not None:
        idx = combo.findData(current)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)


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
        (input_digits_field, prec_label, self.latex_input_precision_spin),
        (group_size_field, group_size_label, self.latex_group_size_spin),
    ]
    for field, label, widget in field_bindings:
        bind_field(field=field, label=label, widget=widget, lang=lang)
        register_schema_text_refresh(self, field, widget=widget)

    for combo in (self.parallel_mode_combo, self.parallel_nested_policy_combo):
        _mark_schema_choices(combo)

    for field, widget in [
        (dcolumn_field, self.dcolumn_checkbox),
        (caption_enabled_field, self.caption_checkbox),
        (caption_field, self.caption_edit),
        (plots_field, self.generate_plots_checkbox),
        (verbose_field, self.verbose_checkbox),
    ]:
        bind_field(field=field, widget=widget, lang=lang)
        register_schema_text_refresh(self, field, widget=widget)

    # The LaTeX output-PATH field + its browse button are no longer part of the options
    # UI (the save path is chosen at save-time in the TeX window). ``output_file_edit`` /
    # ``output_browse_button`` remain as detached widgets on ``self`` for the save/persist
    # code paths, but carry NO schema binding (so they are not enumerated as reachable
    # config inputs).


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


def _refresh_root_field_help(self) -> None:
    refresh_root_field_help(self)


def _on_root_uncertainty_method_changed(self) -> None:
    on_root_uncertainty_method_changed(self)


def _clear_table(self):
    """Clear all data in the manual table."""
    table = self.manual_table
    mode = self.mode_combo.currentData() if hasattr(self, "mode_combo") else None
    column_count = 1 if mode == "root_solving" else 3
    model = table.model()
    previous_table_blocked = table.blockSignals(True)
    previous_model_blocked = model.blockSignals(True)
    try:
        table.setRowCount(1)
        table.setColumnCount(column_count)
        table.setHorizontalHeaderLabels([chr(65 + index) for index in range(column_count)])
        table.clearContents()
        _apply_equal_column_stretch(table)
    finally:
        model.blockSignals(previous_model_blocked)
        table.blockSignals(previous_table_blocked)
    _update_data_summary(self)


class _TablePasteFilter(QObject):
    """Event filter for a QTableWidget: Ctrl/Cmd+V pastes CSV/TSV, Ctrl/Cmd+C copies the
    selected cells as TSV (Excel-compatible)."""

    def __init__(self, table_widget, window):
        super().__init__(table_widget)
        self._table = table_widget
        self._window = window

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            from PySide6.QtGui import QKeySequence
            if event.matches(QKeySequence.StandardKey.Copy):
                if self._copy_selection():
                    return True
            if event.matches(QKeySequence.StandardKey.Paste):
                clipboard = QApplication.clipboard()
                text = clipboard.text()
                if text and text.strip():
                    lines = [l for l in text.strip().split("\n") if l.strip()]
                    if len(lines) >= 2:
                        _load_text_into_table(self._window, text)
                        return True
        return super().eventFilter(obj, event)

    def _copy_selection(self) -> bool:
        """Copy the selected cell block to the clipboard as TSV so it pastes cleanly into
        Excel/Sheets (shared with the constants table via table_copy)."""
        from app_desktop.table_copy import _copy_selection_as_tsv

        return _copy_selection_as_tsv(self._table)
