#!/usr/bin/env python3
"""
Modern PySide6 GUI for the extrapolation & error propagation utilities.

The interface mirrors the previous Tk layout but adopts Qt widgets, GPU-backed
rendering, and higher-DPI PDF previews.
"""
# ruff: noqa: F401, E402

from __future__ import annotations

import csv
import io
import json
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout, redirect_stderr, nullcontext, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence, Any
from types import SimpleNamespace
import re

import mpmath as mp
from desktop_doc_loader import load_desktop_doc, load_desktop_manifest
from app_desktop.update_controller import UpdateController
from shared.update_checker import REPOSITORY_URL

from PySide6.QtCore import Qt, QSize, QTimer, QLocale, Signal, QObject, QThread, QUrl
from PySide6.QtGui import (
    QPixmap,
    QImage,
    QAction,
    QTextCursor,
    QPalette,
    QIcon,
    QColor,
    QDesktopServices,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QFileDialog,
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QSpinBox,
    QSizePolicy,
    QStyle,
    QTextBrowser,
    QListWidget,
    QListWidgetItem,
    QTableWidgetItem,
)

try:
    from PIL import Image, ImageOps

    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from data_extrapolation_latex_latest import (
    _dual_msg,
    apply_formula_to_data,
    calculate_dcolumn_format_for_column,
    detect_used_error_propagation_inputs,
    generate_error_propagation_table,
    generate_latex_table,
    format_value_for_latex_file,
    format_result_with_uncertainty_latex,
    format_uncertainty_display_latex,
    format_uncertainty_notation_for_dcolumn,
    add_spacing_to_number,
    siunitx_column_spec,
    DEFAULT_THREE_POINT_FORMULA,
    process_constants_file,
    process_constants_string,
    process_data_file,
    process_data_string,
    process_uncertainty_data_file,
    process_uncertainty_string,
    ExtrapolationOptions,
    ExtrapolationResult,
    UncertainValue,
    parse_uncertainty_format,
)
from fitting import (
    build_model_specification,
    build_parameter_state,
    fit_custom_model,
    auto_fit_dataset,
    infer_parameter_names,
    ModelSpecification,
    ParameterState,
    render_fitting_overview,
    summarize_auto_results,
    sample_mp_function,
)
from fitting.auto_models import (
    AUTO_MODELS,
    AutoModelDefinition,
    build_inverse_series_definition,
    build_polynomial_definition,
    fit_linear_model,
)
from fitting.hp_fitter import FitResult
from extrapolation_methods import PowerLawConfig
from statistics_utils import compute_statistics, generate_statistics_latex, generate_statistics_latex_batches
from formula_help import (
    get_function_help,
    get_function_tooltip,
    get_method_description,
    get_method_name,
    get_method_parameters,
    EXTRAPOLATION_METHODS,
)
from shared.ui_specs import (
    EXTRAPOLATION_METHOD_SPECS,
    get_method_options,
    POWER_LAW_PARAMS,
    RICHARDSON_PARAMS,
    LEVIN_U_PARAMS,
    CUSTOM_FORMULA_PARAMS,
    METHOD_HELP_BUTTON,
    get_parameter_visibility_rules,
)
from shared.ui_keyguards import ArrowKeyGuard

_LANG_ZH = "zh"
_LANG_EN = "en"
_LANG_AUTO = "auto"

_REFCOL_AUTO_MAX_DIFF_KEY = "auto_max_diff"
_REFCOL_AUTO_MAX_DIFF_ZH = "最大差异列"
_REFCOL_AUTO_MAX_DIFF_EN = "Max-diff column"


from .about_dialog import show_about_dialog
from .docs_dialog import DocsDialog
from .resources import (
    _apply_system_theme,
    _compute_default_pdf_dpi,
    _detect_windows_light_mode,
    _ensure_default_path_augmented,
    _locate_icon_file,
    _pil_to_qpixmap,
    resolve_resource_path,
)
from .workers_core import (
    AutoFitJob,
    AutoFitRenderResult,
    CalcJob,
    CalcResult,
    FitBatchResultEntry,
    FitBatchTask,
    FitJob,
    FitResultPayload,
    _mp_precision_guard,
    _render_extrapolation_plot_bytes,
    _safe_read_text,
    _safe_resolve_path,
    split_extrapolation_result,
)
from .workers_qt import AutoFitWorker, CalcWorker, FitBatchWorker, FitWorker

from .window_latex_pdf_mixin import WindowLatexPdfMixin
from .window_i18n_mixin import WindowI18nMixin
from .window_images_mixin import WindowImagesMixin
from .window_statistics_mixin import WindowStatisticsMixin
from .window_data_mixin import WindowDataMixin
from .window_fitting_mixin import WindowFittingMixin
from .window_extrapolation_mixin import WindowExtrapolationMixin


# Per-mode example placeholder text. Maps the mode key from
# ``self.mode_combo.currentData()`` to a ``(zh, en)`` example pair.
# Adding a new mode requires editing only this table — pre-fix the
# zh and en branches drifted (extrapolation had different newline
# counts in the two languages, etc.) because they were two parallel
# if/elif ladders. The fallback key ``"extrapolation"`` is the
# default for any unknown mode value.
_MANUAL_EXAMPLES: dict[str, tuple[str, str]] = {
    "error": (
        "误差示例：\nx1 x2\n1.23(4)[-5] 9.9(1)",
        "Error example:\nx1 x2\n1.23(4)[-5] 9.9(1)",
    ),
    "fitting": (
        "拟合示例：\nx y\n1.0 2.34(5)\n2.0 1.98(3)\n3.0 1.56(4)",
        "Fitting example:\nx y\n1.0 2.34(5)\n2.0 1.98(3)\n3.0 1.56(4)",
    ),
    "statistics": (
        "统计平均示例：\nValue\n1.234(5)\n1.111(8)\n0.998(6)",
        "Statistics example:\nValue\n1.234(5)\n1.111(8)\n0.998(6)",
    ),
    "extrapolation": (
        "外推示例：\nA B C\n1.0 1.1 1.2",
        "Extrapolation example:\nA B C\n1.0 1.1 1.2",
    ),
}


def _qt_object_alive(obj) -> bool:
    """Return False when the Qt C++ object behind ``obj`` has been
    deleted out from under its Python wrapper.

    Qt deletes child widgets when their parent is destroyed; the
    Python wrapper outlives the C++ object briefly, and any method
    call on it segfaults. ``shiboken6.isValid`` is the documented
    health check; a try/except on a cheap call is the
    portable fallback when the shiboken module isn't importable
    (e.g. a future Qt binding swap).
    """
    try:
        from shiboken6 import isValid  # type: ignore[import-not-found]
        return bool(isValid(obj))
    except Exception:
        try:
            obj.objectName()  # cheap, raises if dead
            return True
        except Exception:
            return False


class _CornerExampleClickFilter(QObject):
    """Event filter that fires a callback on a mouse press.

    Used to attach the "click the (1,1) corner cell to see the
    example" handler to QTableWidget's corner button without
    touching its internal ``clicked(QModelIndex)`` signal —
    that signal's argument shape mismatches our zero-arg slot
    and produces ``Failed to disconnect`` warnings on every
    mode switch.
    """

    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def eventFilter(self, obj, event) -> bool:
        # Click semantics: fire only when the user *releases* a left
        # click that *began* on this widget. Without the button +
        # in-rect checks, a right-click context menu (release fires
        # on any button) or a press-elsewhere-and-drag-into-corner
        # gesture would also trigger the example dialog — neither is
        # what "click the corner" means to a user. ``rect().contains``
        # uses local coordinates, so a press that started inside the
        # widget but the user dragged out before release also no
        # longer triggers — matching the behaviour of a real
        # ``QAbstractButton.clicked`` signal.
        if event.type() == event.Type.MouseButtonRelease:
            from PySide6.QtCore import Qt
            try:
                inside = obj.rect().contains(event.position().toPoint())
            except Exception:
                inside = True
            if event.button() == Qt.LeftButton and inside:
                try:
                    self._callback()
                except Exception:
                    # Surface but don't propagate — a Qt event filter
                    # that raises corrupts the event-loop dispatch on
                    # some platforms.
                    import logging
                    logging.getLogger(__name__).warning(
                        "corner-click handler failed", exc_info=True
                    )
        return False  # don't consume; let Qt do its own processing


class ExtrapolationWindow(
    QMainWindow,
    WindowLatexPdfMixin,
    WindowI18nMixin,
    WindowImagesMixin,
    WindowStatisticsMixin,
    WindowDataMixin,
    WindowFittingMixin,
    WindowExtrapolationMixin,
):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DataLab")
        self.resize(1280, 760)
        self._window_icon = None
        self._apply_window_icon()
        self._windows_light_pref = _detect_windows_light_mode()
        self._theme_timer: QTimer | None = None
        if os.name == "nt":
            self._theme_timer = QTimer(self)
            self._theme_timer.setInterval(5000)
            self._theme_timer.timeout.connect(self._maybe_refresh_system_theme)
            self._theme_timer.start()

        self.current_latex_path: Path | None = None
        self.last_pdf_path: Path | None = None
        self.pdf_preview_tool: tuple[str, str] | None = None
        self.pdf_base_images: list[Image.Image] = []
        self.pdf_zoom = 1.0
        self._pdf_default_zoom = 1.0
        self.pdf_dark_mode = False

        self._latex_engine_paths: dict[str, str] = {}
        self._pdf_base_dpi = _compute_default_pdf_dpi()
        self.sequence_accelerators = {"richardson", "shanks", "levin_u"}
        # Use shared specs to determine mpmath methods
        from shared.ui_specs import METHOD_DISPLAY_ORDER
        self.mpmath_methods = {key for key in METHOD_DISPLAY_ORDER if key not in {"custom"}}
        self._fit_output_digits = 12
        self._auto_model_map = {definition.identifier: definition for definition in AUTO_MODELS}
        self._baseline_poly_degree = 0
        for definition in AUTO_MODELS:
            if "多项式" in definition.label or definition.label == "线性":
                self._baseline_poly_degree = max(self._baseline_poly_degree, len(definition.parameter_names) - 1)
        if self._baseline_poly_degree <= 0:
            self._baseline_poly_degree = 3
        self._result_plot_base_pixmap: QPixmap | None = None
        self.result_plot_bytes: bytes | None = None
        self.result_plot_zoom = 1.0
        self._result_plot_default_zoom = 1.0
        self._zoom_spin_syncing = False
        self._user_zoom_override = False
        self._workspace_path: Path | None = None
        self._workspace_dirty = False
        self._workspace_degraded = False
        self._workspace_snapshot_only = False
        self._workspace_snapshot_stale = False
        self._workspace_restoring = False

        self.current_fit_figures: list[Path] = []
        self.current_stats_figures: list[Path] = []
        self.current_error_figures: list[Path] = []
        self.current_fit_index = 0
        self.current_stats_index = 0
        self.current_error_index = 0
        self._image_mode: str | None = None
        self._fit_batch_context: dict[str, object] | None = None
        self._temp_batch_images: list[Path] = []
        self.current_extrap_figures: list[Path] = []
        self.current_extrap_index: int = 0

        self._current_precision = mp.mp.dps
        self._auto_fit_worker: AutoFitWorker | None = None
        self._fit_worker: FitWorker | None = None
        self._calc_worker: CalcWorker | None = None
        self._translations: list[tuple[object, str, str, str]] = []  # (widget, attr, zh, en)
        self._combo_translations: list[tuple[QComboBox, list[tuple[str, str, object]]]] = []
        self._lang_mode = _LANG_AUTO
        self._system_lang = self._detect_system_language()
        self._update_controller = UpdateController(self)
        self._build_menu()
        self._build_ui()
        self._initialize_workspace_tracking()
        self._init_theme_tracking()
        self._update_method_state()
        self._toggle_latex_options(self.generate_latex_checkbox.isChecked())
        self._apply_language(self._system_lang if self._lang_mode == _LANG_AUTO else self._lang_mode)
        self._update_workspace_window_title()
        QTimer.singleShot(500, self._update_controller.maybe_show_startup_update_notice)
        QTimer.singleShot(1500, self._update_controller.maybe_auto_check)
        app = QApplication.instance()
        if app:
            app.aboutToQuit.connect(self._cleanup_workers)

    def _build_menu(self):
        from . import panels as _panels
        _panels.build_menu(self)

    def _build_ui(self):
        from . import panels as _panels
        _panels.build_ui(self)

    def _build_left_panel(self):
        from . import panels as _panels
        _panels.build_left_panel(self)

    def _workspace_title(self) -> str:
        if self._workspace_path is None:
            return "Untitled"
        return self._workspace_path.name

    def _update_workspace_window_title(self) -> None:
        suffix = " *" if self._workspace_dirty else ""
        self.setWindowTitle(f"DataLab - {self._workspace_title()}{suffix}")

    def _mark_workspace_dirty(self, *_args) -> None:
        if getattr(self, "_workspace_restoring", False):
            return
        self._workspace_dirty = True
        if self._workspace_snapshot_only and not self._workspace_snapshot_stale:
            self._workspace_snapshot_stale = True
            warning = self._tr(
                "结果为保存的快照，当前输入或配置已更改，请重新计算。",
                "This is a saved result snapshot. Inputs or settings have changed; rerun to update.",
            )
            if hasattr(self, "result_edit") and warning not in self.result_edit.toPlainText():
                current = self.result_edit.toPlainText()
                self.result_edit.setPlainText(f"{warning}\n\n{current}" if current else warning)
        self._update_workspace_window_title()

    def _set_snapshot_controls_enabled(self, enabled: bool) -> None:
        for widget_name in ("scientific_checkbox", "display_digits_spin"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setEnabled(enabled)

    def _initialize_workspace_tracking(self) -> None:
        widgets = [
            getattr(self, "data_file_edit", None),
            getattr(self, "manual_data_edit", None),
            getattr(self, "constants_file_edit", None),
            getattr(self, "manual_constants_edit", None),
            getattr(self, "custom_formula_edit", None),
            getattr(self, "formula_edit", None),
            getattr(self, "fit_expr_edit", None),
            getattr(self, "fit_target_edit", None),
            getattr(self, "stats_value_column_edit", None),
            getattr(self, "stats_sigma_column_edit", None),
            getattr(self, "output_file_edit", None),
            getattr(self, "caption_edit", None),
            getattr(self, "latex_edit", None),
        ]
        for widget in widgets:
            if widget is None:
                continue
            signal = getattr(widget, "textChanged", None)
            if signal is not None:
                signal.connect(self._mark_workspace_dirty)
        for table_name in ("manual_table", "constants_table", "implicit_params_table", "implicit_constants_table"):
            table = getattr(self, table_name, None)
            if table is not None:
                table.itemChanged.connect(self._mark_workspace_dirty)
        for combo_name in (
            "mode_combo",
            "method_combo",
            "levin_variant_combo",
            "levin_weight_combo",
            "error_method_combo",
            "stats_mode_combo",
            "fit_model_combo",
            "latex_engine_combo",
        ):
            combo = getattr(self, combo_name, None)
            if combo is not None:
                combo.currentIndexChanged.connect(self._mark_workspace_dirty)
        for check_name in (
            "use_file_checkbox",
            "constants_checkbox",
            "use_constants_file_checkbox",
            "generate_latex_checkbox",
            "generate_plots_checkbox",
            "verbose_checkbox",
            "scientific_checkbox",
            "dcolumn_checkbox",
            "caption_checkbox",
            "fit_weighted_checkbox",
            "fit_mcmc_refine",
            "enable_constraints_checkbox",
            "stats_sample_checkbox",
            "stats_weight_variance_checkbox",
            "log_x_checkbox",
            "log_y_checkbox",
        ):
            checkbox = getattr(self, check_name, None)
            if checkbox is not None:
                checkbox.toggled.connect(self._mark_workspace_dirty)
        for spin_name in (
            "mpmath_precision_spin",
            "uncertainty_digits_spin",
            "display_digits_spin",
            "latex_input_precision_spin",
            "latex_group_size_spin",
            "levin_order_spin",
            "levin_beta_spin",
            "richardson_p_spin",
            "error_order_spin",
            "error_mc_samples_spin",
            "inverse_min_spin",
            "inverse_max_spin",
            "pade_m_spin",
            "pade_n_spin",
            "poly_degree_spin",
        ):
            spin = getattr(self, spin_name, None)
            if spin is not None:
                spin.valueChanged.connect(self._mark_workspace_dirty)

    def _workspace_guard_running(self) -> bool:
        if self._has_running_worker():
            QMessageBox.information(
                self,
                self._tr("任务正在运行", "Task running"),
                self._tr(
                    "请等待或停止当前计算后再保存或打开工作区。",
                    "Wait for or stop the current task before saving or opening a workspace.",
                ),
            )
            return False
        return True

    def _confirm_workspace_discard_or_save(self) -> bool:
        if not self._workspace_dirty:
            return True
        reply = QMessageBox.question(
            self,
            self._tr("保存工作区？", "Save workspace?"),
            self._tr(
                "当前工作区有未保存更改。是否先保存？",
                "The current workspace has unsaved changes. Save before continuing?",
            ),
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return False
        if reply == QMessageBox.StandardButton.Save:
            return self.save_workspace()
        return True

    def new_workspace(self, _checked: bool = False) -> bool:
        if not self._workspace_guard_running() or not self._confirm_workspace_discard_or_save():
            return False
        self._workspace_restoring = True
        try:
            self._workspace_path = None
            self._workspace_dirty = False
            self._workspace_degraded = False
            self._workspace_snapshot_only = False
            self._workspace_snapshot_stale = False
            self.result_edit.clear()
            self.log_edit.clear()
            self.latex_edit.clear()
            self._reset_csv_data()
            self.result_plot_bytes = None
            self._result_plot_base_pixmap = None
            if hasattr(self, "result_plot_label"):
                self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self._last_result_kind = None
            self._last_result_payloads = {}
        finally:
            self._workspace_restoring = False
        self._update_workspace_window_title()
        return True

    def save_workspace(self, _checked: bool = False) -> bool:
        if self._workspace_path is None:
            return self.save_workspace_as()
        return self._save_workspace_to_path(self._workspace_path)

    def save_workspace_as(self, _checked: bool = False) -> bool:
        if not self._workspace_guard_running():
            return False
        filename, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("保存工作区", "Save Workspace"),
            str(self._workspace_path or Path("analysis.datalab")),
            "DataLab Workspace (*.datalab);;All Files (*)",
        )
        if not filename:
            return False
        path = Path(filename)
        if path.suffix.lower() != ".datalab":
            path = path.with_suffix(".datalab")
        return self._save_workspace_to_path(path)

    def _save_workspace_to_path(self, path: Path) -> bool:
        if not self._workspace_guard_running():
            return False
        if self._workspace_degraded and self._workspace_path == path:
            reply = QMessageBox.warning(
                self,
                self._tr("降级工作区", "Degraded workspace"),
                self._tr(
                    "此工作区曾以降级模式打开。建议使用“另存为”修复副本。仍要覆盖原文件吗？",
                    "This workspace was opened in degraded mode. Save As is recommended. Overwrite anyway?",
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False
        try:
            from app_desktop.workspace_controller import capture_workspace
            from shared.workspace_io import write_workspace

            bundle = capture_workspace(self, title=path.stem)
            write_workspace(path, bundle.manifest, bundle.attachments)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self._tr("保存失败", "Save failed"), str(exc))
            return False
        self._workspace_path = path
        self._workspace_dirty = False
        self._workspace_degraded = False
        self._update_workspace_window_title()
        return True

    def open_workspace_path(self, path: Path, *, confirm_discard: bool = True) -> bool:
        if not self._workspace_guard_running():
            return False
        if confirm_discard and not self._confirm_workspace_discard_or_save():
            return False
        return self._open_workspace_from_path(Path(path))

    def open_workspace(self, _checked: bool = False) -> bool:
        if not self._workspace_guard_running() or not self._confirm_workspace_discard_or_save():
            return False
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self._tr("打开工作区", "Open Workspace"),
            "",
            "DataLab Workspace (*.datalab);;All Files (*)",
        )
        if not filename:
            return False
        return self._open_workspace_from_path(Path(filename))

    def _open_workspace_from_path(self, path: Path) -> bool:
        if not self._workspace_guard_running():
            return False
        try:
            from app_desktop.workspace_controller import restore_workspace
            from shared.workspace_io import read_workspace

            loaded = read_workspace(path)
            self._workspace_restoring = True
            try:
                restore_workspace(self, loaded.manifest, loaded.attachments)
            finally:
                self._workspace_restoring = False
        except Exception as exc:  # noqa: BLE001
            self._workspace_restoring = False
            QMessageBox.critical(self, self._tr("打开失败", "Open failed"), str(exc))
            return False
        self._workspace_path = path
        self._workspace_dirty = False
        self._workspace_degraded = False
        self._workspace_snapshot_stale = False
        self._update_workspace_window_title()
        return True

    def _next_variable_name(self) -> str:
        existing = {
            edit.text().strip()
            for edit, _, _ in getattr(self, "variable_rows", [])
            if edit.text().strip()
        }
        for name in self.variable_name_pool:
            if name not in existing:
                return name
        idx = 1
        while True:
            candidate = f"x{idx}"
            if candidate not in existing:
                return candidate
            idx += 1

    def _add_variable_row(self, default_var: str | None = None, default_column: str = ""):
        if not hasattr(self, "variable_rows_layout"):
            return
        var_name = default_var or self._next_variable_name()
        row_layout = QHBoxLayout()
        var_edit = QLineEdit(var_name)
        col_edit = QLineEdit(default_column)
        lbl_var = QLabel(self._tr("变量", "Var"))
        lbl_col = QLabel(self._tr("列名", "Column"))
        row_layout.addWidget(lbl_var)
        row_layout.addWidget(var_edit)
        row_layout.addWidget(lbl_col)
        row_layout.addWidget(col_edit)
        container = QWidget()
        container.setLayout(row_layout)
        self.variable_rows_layout.addWidget(container)
        self.variable_rows.append((var_edit, col_edit, container))

    def _remove_variable_row(self):
        if not hasattr(self, "variable_rows") or not self.variable_rows:
            return
        if len(self.variable_rows) <= 1:
            return
        _, _, container = self.variable_rows.pop()
        try:
            container.setParent(None)
            container.deleteLater()
        except Exception:
            pass

    def _reset_variable_rows(self, default_var: str = "x", default_column: str = "A"):
        if not hasattr(self, "variable_rows_layout"):
            return
        for _, _, container in getattr(self, "variable_rows", []):
            try:
                container.setParent(None)
                container.deleteLater()
            except Exception:
                pass
        self.variable_rows = []
        self._add_variable_row(default_var=default_var, default_column=default_column)

    def _build_right_panel(self, layout: QVBoxLayout):
        from . import panels as _panels
        _panels.build_right_panel(self, layout)

    def _init_theme_tracking(self):
        app = QApplication.instance()
        if app and hasattr(app, "paletteChanged"):
            app.paletteChanged.connect(self._update_theme_from_palette)
        self._update_theme_from_palette()

    # ------------------------------------------------------------- Handlers --
    def browse_data_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self._tr("选择数据文件", "Select Data File"),
            "",
            "Data (*.txt *.dat *.csv);;All Files (*)",
        )
        if filename:
            self.data_file_edit.setText(filename)

    def browse_output_file(self):
        filename, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("保存 LaTeX", "Save LaTeX"),
            "",
            "LaTeX (*.tex);;All Files (*)",
        )
        if filename:
            self.output_file_edit.setText(filename)

    def browse_constants_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self._tr("选择常数文件", "Select Constants File"),
            "",
            "Data (*.txt *.dat);;All Files (*)",
        )
        if filename:
            self.constants_file_edit.setText(filename)

    def _show_help(self):
        if self._is_en():
            title = "Help"
            message = (
                "1. Choose a data file or paste data in the manual input area (first row = headers).\n"
                "2. Select extrapolation, error propagation, fitting, or statistics on the left; set power/constant options as needed.\n"
                "3. In fitting mode, choose polynomial, Padé, 1/x^p, power-limit, custom, or auto; related controls appear below for expression/JSON.\n"
                "4. In fitting, the Stat./System row controls statistical weighting: when enabled, data sigmas are used as weights (stat only); when disabled but sigmas exist, they are treated as systematic only (no double counting). Uncertainties are auto-parsed (1.23(4)[-5] or sigma-like headers), no extra sigma field needed.\n"
                "5. Enable “Generate LaTeX” to export tables/images; you can edit/compile in the LaTeX tab; right tabs show results, logs, LaTeX, and PDF preview."
            )
        else:
            title = "帮助"
            message = (
                "1. 选择数据文件或在手动输入区域粘贴数据（首行为表头）。\n"
                "2. 在左侧选择外推、误差传递、拟合或统计模式，并根据需要设置幂律/常数等参数。\n"
                "3. 拟合模式使用下拉框选择多项式、Padé、1/x^p、power-limit、自定义或自动模型，相关参数控件会在下方即时显示，可写入表达式/JSON。\n"
                "4. 拟合模块的“统计/系统”一行控制统计加权：勾选“统计误差加权”则数据 σ 作为统计权重；不勾选时若检测到 σ，则只作为系统误差来源（避免双计）。不再需要单独输入 σ 列，程序会自动解析 1.23(4)[-5] 或包含 sigma/err 的列，日志会提示 χ²、边界警告等。\n"
                "5. 勾选“生成 LaTeX 文件”即可导出表格/图像，并可在 LaTeX 标签页编辑或编译；右侧标签页展示数值结果、日志、LaTeX 内容和 PDF 预览。"
            )
        QMessageBox.information(self, title, message)

    def _show_docs(self, _checked: bool = False):
        lang = "en" if self._is_en() else "zh"
        dlg = DocsDialog(lang=lang, parent=self)
        dlg.setAttribute(Qt.WA_DeleteOnClose, True)
        dlg.show()
        if not hasattr(self, "_open_docs_dialogs"):
            self._open_docs_dialogs = []
        self._open_docs_dialogs.append(dlg)
        dlg.destroyed.connect(lambda: self._open_docs_dialogs.remove(dlg) if dlg in self._open_docs_dialogs else None)

    def _open_project_homepage(self, _checked: bool = False):
        QDesktopServices.openUrl(QUrl(REPOSITORY_URL))

    def _check_for_updates(self, _checked: bool = False):
        self._update_controller.check_now()

    def _set_auto_update_enabled(self, checked: bool) -> None:
        self._update_controller.set_auto_update_enabled(bool(checked))

    def is_english(self) -> bool:
        return self._is_en()

    def ask_update(self, title: str, message: str, *, was_skipped: bool = False) -> str:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(title)
        box.setText(message)
        update_button = box.addButton("Update Now", QMessageBox.ButtonRole.AcceptRole)
        later_button = box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        skip_button = box.addButton("Skip This Version", QMessageBox.ButtonRole.DestructiveRole)
        box.setDefaultButton(update_button)
        box.exec()
        clicked = box.clickedButton()
        if clicked == update_button:
            return "update"
        if clicked == skip_button:
            return "skip"
        if clicked == later_button:
            return "later"
        return "later"

    def warning(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    def information(self, title: str, message: str) -> None:
        QMessageBox.information(self, title, message)

    def open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def exit_for_update(self) -> None:
        QApplication.quit()

    def _show_about(self):
        lang = "en" if self._is_en() else "zh"
        show_about_dialog(parent=self, lang=lang)

    def _toggle_latex_options(self, checked: bool):
        self.latex_options_widget.setVisible(checked)
        # Sync caption row visibility when LaTeX toggle changes
        self._toggle_caption_input(self.caption_checkbox.isChecked() if hasattr(self, "caption_checkbox") else False)

    def _toggle_caption_input(self, checked: bool):
        if hasattr(self, "caption_edit"):
            self.caption_edit.setVisible(bool(checked))

    def _toggle_constants_options(self, checked: bool):
        self.constants_widget.setVisible(checked)

    def _on_constants_source_toggle(self, checked: bool):
        if hasattr(self, "constants_file_row"):
            self.constants_file_row.setVisible(checked)
        # Hide the whole stack (table + text-view pages) when the file
        # source is selected, and the per-view toggle button with it.
        if hasattr(self, "_constants_stack"):
            self._constants_stack.setVisible(not checked)
        elif hasattr(self, "constants_table"):
            self.constants_table.setVisible(not checked)
        if hasattr(self, "_constants_view_toggle"):
            self._constants_view_toggle.setVisible(not checked)
        if hasattr(self, "constants_hint_btn"):
            hint_text = self._tr(
                "常数文件示例：ALPHA 7.2973525693(11)[-3]",
                "Constants file example: ALPHA 7.2973525693(11)[-3]",
            ) if checked else "ALPHA 7.2973525693(11)[-3]"
            self.constants_hint_btn.setToolTip(hint_text)
            self.constants_hint_btn.setVisible(checked)

    def _update_error_propagation_controls(self):
        if not hasattr(self, "error_method_combo"):
            return
        method = (self.error_method_combo.currentData() or "taylor").strip().lower()
        is_mc = method in {"monte_carlo", "mc", "montecarlo", "monte-carlo"}
        if hasattr(self, "error_taylor_widget"):
            self.error_taylor_widget.setVisible(not is_mc)
        if hasattr(self, "error_mc_widget"):
            self.error_mc_widget.setVisible(is_mc)
        if hasattr(self, "error_order_spin"):
            self.error_order_spin.setEnabled(not is_mc)
        if hasattr(self, "error_mc_samples_spin"):
            self.error_mc_samples_spin.setEnabled(is_mc)
        if hasattr(self, "error_mc_seed_edit"):
            self.error_mc_seed_edit.setEnabled(is_mc)

    def _on_data_source_toggle(self, checked: bool):
        if hasattr(self, "file_box"):
            self.file_box.setVisible(checked)
        if hasattr(self, "manual_box"):
            self.manual_box.setVisible(not checked)
        if hasattr(self, "use_file_hint_btn"):
            hint_text = getattr(self, "_current_example_text", "") or self.manual_data_edit.placeholderText()
            self.use_file_hint_btn.setToolTip(hint_text)
            self.use_file_hint_btn.setVisible(checked)

    def _on_stats_mode_change(self):
        mode = self.stats_mode_combo.currentData() if hasattr(self, "stats_mode_combo") else None
        if hasattr(self, "stats_weight_variance_checkbox"):
            visible = mode == "weighted_sigma"
            self.stats_weight_variance_checkbox.setVisible(visible)
            if hasattr(self, "stats_weight_variance_label"):
                self.stats_weight_variance_label.setVisible(visible)

    def _update_model_controls(self):
        if not hasattr(self, "fit_model_combo"):
            return
        mode = self.fit_model_combo.currentData()
        if hasattr(self, "poly_degree_widget"):
            self.poly_degree_widget.setVisible(mode == "poly")
        if hasattr(self, "inverse_power_widget"):
            self.inverse_power_widget.setVisible(mode == "inverse")
        if hasattr(self, "pade_widget"):
            self.pade_widget.setVisible(mode == "pade")
        if hasattr(self, "implicit_model_widget"):
            self.implicit_model_widget.setVisible(mode == "self_consistent")
        show_expr = mode not in {"auto", "self_consistent"}
        self.fit_expr_edit.setVisible(show_expr)
        if show_expr:
            self.fit_expr_edit.setEnabled(True)
            self.fit_expr_edit.setReadOnly(mode != "custom")
            if mode != "custom":
                self.fit_expr_edit.setPlainText(self._mode_expression_preview(mode))
        if hasattr(self, "fit_param_edit"):
            self.fit_param_edit.setVisible(False)
            self.fit_param_edit.setReadOnly(True)
        if hasattr(self, "fit_func_help_btn"):
            self.fit_func_help_btn.setVisible(mode == "custom")
        if hasattr(self, "add_variable_btn"):
            self.add_variable_btn.setVisible(mode in {"custom", "self_consistent"})
        if hasattr(self, "remove_variable_btn"):
            self.remove_variable_btn.setVisible(mode in {"custom", "self_consistent"})
            if mode not in {"custom", "self_consistent"}:
                self._reset_variable_rows(default_var="x", default_column="A")
        # 参数约束仅对自由参数模型生效，其它模型隐藏以避免误导
        show_params = mode in {"custom", "self_consistent"}
        if not show_params and hasattr(self, "enable_constraints_checkbox"):
            self.enable_constraints_checkbox.setChecked(False)
        if hasattr(self, "enable_constraints_checkbox"):
            self.enable_constraints_checkbox.setVisible(show_params)
        if hasattr(self, "add_param_btn"):
            self.add_param_btn.setVisible(show_params and self.enable_constraints_checkbox.isChecked())
        if hasattr(self, "remove_param_btn"):
            self.remove_param_btn.setVisible(show_params and self.enable_constraints_checkbox.isChecked())
        if hasattr(self, "param_header_widget"):
            self.param_header_widget.setVisible(show_params and self.enable_constraints_checkbox.isChecked())
        if hasattr(self, "param_rows_container"):
            self.param_rows_container.setVisible(show_params and self.enable_constraints_checkbox.isChecked())

    def _refresh_mode_expression(self, mode: str | None = None):
        mode = mode or (self.fit_model_combo.currentData() if hasattr(self, "fit_model_combo") else None)
        if mode and mode != "custom" and hasattr(self, "fit_expr_edit"):
            preview = self._mode_expression_preview(mode)
            if preview:
                self.fit_expr_edit.setPlainText(preview)

    def _on_model_type_changed(self):
        self._update_model_controls()
        mode = self.fit_model_combo.currentData()
        if mode in {"power_limit", "pade"}:
            self._apply_model_template(mode)
        self._update_model_hint()

    def _on_model_settings_changed(self):
        if not hasattr(self, "fit_model_combo"):
            return
        mode = self.fit_model_combo.currentData()
        if mode in {"power_limit", "pade"}:
            self._apply_model_template(mode)
        elif mode in {"poly", "inverse"}:
            self._refresh_mode_expression(mode)
        self._update_model_hint()

    def _update_model_hint(self):
        if not hasattr(self, "fit_model_combo") or not hasattr(self, "fit_model_hint"):
            return
        mode = self.fit_model_combo.currentData()
        hint = ""
        if mode in {"log_poly", "exp_combo"}:
            hint = self._tr("该模型要求 x>0。", "This model requires x>0.")
        elif mode == "self_consistent":
            hint = self._tr(
                "通用自洽模型中的符号默认都是变量或参数；常量请在表达式中显式处理。",
                "Symbols in generic self-consistent models are variables or parameters by default; handle constants explicitly in the expression.",
            )
        self.fit_model_hint.setVisible(bool(hint))
        if hint:
            self.fit_model_hint.setText(hint)

    def _mode_expression_preview(self, mode: str) -> str:
        if mode == "power_limit":
            expr, _ = self._power_limit_template()
            return expr
        if mode == "pade":
            payload = self._pade_template(self.pade_m_spin.value(), self.pade_n_spin.value())
            if payload:
                return payload[0]
        if mode == "poly":
            degree = self.poly_degree_spin.value()
            terms = [f"b{i}*x^{i}" if i > 0 else "b0" for i in range(degree + 1)]
            return " + ".join(terms)
        if mode == "inverse":
            p_min, p_max = self._inverse_power_range()
            parts = [f"A{p}/x^{p}" for p in range(p_min, p_max + 1)]
            return " + ".join(parts) if parts else "A0"
        if mode in {"log_poly", "exp_combo"}:
            definition = self._auto_model_map.get("M4B" if mode == "log_poly" else "M7B")
            if definition:
                return " + ".join([f"{name}*({text})" for name, text in zip(definition.parameter_names, definition.basis_texts)])
        if mode == "self_consistent" and hasattr(self, "implicit_output_edit"):
            return self.implicit_output_edit.toPlainText().strip()
        if mode == "custom":
            return self.fit_expr_edit.toPlainText()

    def _apply_quantum_defect_preset(self):
        if hasattr(self, "implicit_variable_edit"):
            self.implicit_variable_edit.setText("delta")
        if hasattr(self, "implicit_equation_edit"):
            self.implicit_equation_edit.setPlainText("d0 + d2/(n-delta)^2 + d4/(n-delta)^4")
        if hasattr(self, "implicit_output_edit"):
            self.implicit_output_edit.setPlainText("En - R*c/(n-delta)^2")
        if hasattr(self, "implicit_initial_edit"):
            self.implicit_initial_edit.setText("0")
        if hasattr(self, "implicit_tolerance_edit"):
            self.implicit_tolerance_edit.setText("1e-30")
        if hasattr(self, "implicit_max_iterations_spin"):
            self.implicit_max_iterations_spin.setValue(80)
        if hasattr(self, "implicit_method_combo"):
            index = self.implicit_method_combo.findData("fixed_point")
            if index >= 0:
                self.implicit_method_combo.setCurrentIndex(index)
        if hasattr(self, "_reset_variable_rows"):
            self._reset_variable_rows(default_var="n", default_column="A")
        if hasattr(self, "_reset_implicit_constants_rows"):
            self._reset_implicit_constants_rows({"R": "10973731.568160", "c": "299792458"})
        if hasattr(self, "fit_target_edit"):
            self.fit_target_edit.setText("B")

    def _implicit_builtin_constants(self, equation: str, output_expression: str) -> dict[str, str]:
        quantum_equation = "d0 + d2/(n-delta)^2 + d4/(n-delta)^4"
        if equation != quantum_equation:
            return {}
        if output_expression == "En - R*c/(n-delta)^2":
            return {"R": "10973731.568160", "c": "299792458"}
        if output_expression == "En - K/(n-delta)^2":
            return {"K": "1.0"}
        return {}

    def _reset_implicit_param_rows(self, config: dict[str, object] | None = None):
        table = getattr(self, "implicit_params_table", None)
        if table is None:
            return
        config = config or {}
        table.blockSignals(True)
        try:
            table.setRowCount(0)
            for row, name in enumerate(config):
                entry = config.get(name)
                if not isinstance(entry, dict):
                    entry = {"initial": entry}
                table.insertRow(row)
                values = [
                    str(name),
                    "" if entry.get("initial") is None else str(entry.get("initial")),
                    "" if entry.get("fixed") is None else str(entry.get("fixed")),
                    "" if entry.get("min") is None else str(entry.get("min")),
                    "" if entry.get("max") is None else str(entry.get("max")),
                ]
                for col, value in enumerate(values):
                    table.setItem(row, col, QTableWidgetItem(value))
        finally:
            table.blockSignals(False)

    def _collect_implicit_parameter_config(self, parameter_names: Sequence[str]) -> dict[str, dict[str, str]]:
        table = getattr(self, "implicit_params_table", None)
        allowed = set(parameter_names)
        collected: dict[str, dict[str, str]] = {}
        if table is not None:
            for row in range(table.rowCount()):
                name_item = table.item(row, 0)
                name = name_item.text().strip() if name_item else ""
                if not name or name not in allowed:
                    continue
                init_text = table.item(row, 1).text().strip() if table.item(row, 1) else ""
                fixed_text = table.item(row, 2).text().strip() if table.item(row, 2) else ""
                min_text = table.item(row, 3).text().strip() if table.item(row, 3) else ""
                max_text = table.item(row, 4).text().strip() if table.item(row, 4) else ""
                entry: dict[str, str] = {}
                for key, text in (
                    ("initial", init_text),
                    ("fixed", fixed_text),
                    ("min", min_text),
                    ("max", max_text),
                ):
                    if not text:
                        continue
                    try:
                        mp.mpf(text)
                    except ValueError as exc:
                        raise ValueError(self._tr(f"参数 {name} 的 {key} 无效。", f"Invalid {key} for parameter {name}.")) from exc
                    entry[key] = text
                if "initial" not in entry and "fixed" not in entry:
                    raise ValueError(self._tr(f"参数 {name} 需要初值或固定值。", f"Parameter {name} needs an initial or fixed value."))
                collected[name] = entry
        missing = [name for name in parameter_names if name not in collected]
        if missing:
            joined = ", ".join(missing)
            raise ValueError(self._tr(f"隐式参数缺少初值或固定值：{joined}", f"Implicit parameters need initial or fixed values: {joined}"))
        return collected

    def _refresh_implicit_parameter_rows(self):
        config = self._collect_implicit_config(validate_parameters=False)
        parameter_names = tuple(config["parameter_names"])
        table = getattr(self, "implicit_params_table", None)
        before: list[tuple[str, str, str, str, str]] = []
        preserved: dict[str, dict[str, str]] = {}
        if table is not None:
            for row in range(table.rowCount()):
                name_item = table.item(row, 0)
                name = name_item.text().strip() if name_item else ""
                before.append(tuple(
                    table.item(row, col).text().strip() if table.item(row, col) else ""
                    for col in range(table.columnCount())
                ))
                if not name:
                    continue
                preserved[name] = {
                    "initial": table.item(row, 1).text().strip() if table.item(row, 1) else "",
                    "fixed": table.item(row, 2).text().strip() if table.item(row, 2) else "",
                    "min": table.item(row, 3).text().strip() if table.item(row, 3) else "",
                    "max": table.item(row, 4).text().strip() if table.item(row, 4) else "",
                }
        self._reset_implicit_param_rows({
            name: preserved.get(name, {"initial": "", "fixed": "", "min": "", "max": ""})
            for name in parameter_names
        })
        if table is not None:
            after = [
                tuple(
                    table.item(row, col).text().strip() if table.item(row, col) else ""
                    for col in range(table.columnCount())
                )
                for row in range(table.rowCount())
            ]
            if after != before and hasattr(self, "_mark_workspace_dirty") and not getattr(self, "_workspace_restoring", False):
                self._mark_workspace_dirty()

    def _reset_implicit_constants_rows(self, config: dict[str, object] | None = None):
        table = getattr(self, "implicit_constants_table", None)
        if table is None:
            return
        constants = config or {}
        table.blockSignals(True)
        try:
            table.clearContents()
            table.setRowCount(max(3, len(constants)))
            for row, (name, value) in enumerate(constants.items()):
                table.setItem(row, 0, QTableWidgetItem(str(name)))
                table.setItem(row, 1, QTableWidgetItem(str(value)))
        finally:
            table.blockSignals(False)

    def _collect_implicit_constants(self) -> dict[str, str]:
        table = getattr(self, "implicit_constants_table", None)
        if table is None:
            return {}
        constants: dict[str, str] = {}
        for row in range(table.rowCount()):
            name_item = table.item(row, 0)
            value_item = table.item(row, 1)
            name = name_item.text().strip() if name_item else ""
            value = value_item.text().strip() if value_item else ""
            if not name and not value:
                continue
            if not name:
                raise ValueError(self._tr("常数名称不能为空。", "Constant name cannot be empty."))
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
                raise ValueError(self._tr(f"常数名称无效：{name}", f"Invalid constant name: {name}"))
            if not value:
                raise ValueError(self._tr(f"常数 {name} 缺少取值。", f"Constant {name} needs a value."))
            if name in constants:
                raise ValueError(self._tr(f"常数名称重复：{name}", f"Duplicate constant name: {name}"))
            try:
                mp.mpf(value)
            except (ValueError, TypeError) as exc:
                raise ValueError(self._tr(f"常数 {name} 的取值无效。", f"Invalid value for constant {name}.")) from exc
            constants[name] = value
        return constants

    def _collect_implicit_config(self, validate_parameters: bool = True) -> dict[str, object]:
        x_variables = [
            var_edit.text().strip()
            for var_edit, _col_edit, *_ in getattr(self, "variable_rows", [])
            if var_edit.text().strip()
        ] or ["n"]
        implicit_variable = self.implicit_variable_edit.text().strip()
        equation = self.implicit_equation_edit.toPlainText().strip()
        output_expression = self.implicit_output_edit.toPlainText().strip()
        if not equation:
            raise ValueError(self._tr("隐式方程不能为空。", "Implicit equation cannot be empty."))
        if not output_expression:
            raise ValueError(self._tr("输出表达式不能为空。", "Output expression cannot be empty."))
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", implicit_variable):
            raise ValueError(self._tr("隐式变量必须是有效标识符。", "Implicit variable must be a valid identifier."))
        method = self.implicit_method_combo.currentData() or "fixed_point"
        initial = self.implicit_initial_edit.text().strip() or "0"
        tolerance = self.implicit_tolerance_edit.text().strip() or "1e-30"
        max_iterations = self.implicit_max_iterations_spin.value()
        timeout_seconds = self.implicit_timeout_spin.value()
        expressions = f"{equation}\n{output_expression}"
        constants = self._collect_implicit_constants()
        constant_names = set(constants)
        reserved = set(x_variables)
        reserved.add(implicit_variable)
        reserved.update(constant_names)
        parameter_names = self._infer_parameter_names(
            expressions,
            x_variables + [implicit_variable, *sorted(constant_names)],
            [],
        )
        parameter_names = [name for name in parameter_names if name not in reserved]
        if validate_parameters:
            self._collect_implicit_parameter_config(parameter_names)
        return {
            "x_variables": tuple(x_variables),
            "implicit_variable": implicit_variable,
            "equation": equation,
            "output_expression": output_expression,
            "method": str(method),
            "initial": initial,
            "tolerance": tolerance,
            "max_iterations": max_iterations,
            "timeout_seconds": timeout_seconds,
            "parameter_names": tuple(parameter_names),
            "constants": constants,
        }

    def _apply_model_template(self, template: str):
        payload = None
        if template == "power_limit":
            payload = self._power_limit_template()
        elif template == "pade":
            payload = self._pade_template(self.pade_m_spin.value(), self.pade_n_spin.value())
        if not payload:
            return
        expr, params = payload
        self.fit_expr_edit.setPlainText(expr)
        self.fit_param_edit.setPlainText(json.dumps(params, ensure_ascii=False, indent=2))

    def _power_limit_template(self) -> tuple[str, dict[str, object]]:
        return (
            "A*x**(-p) + C",
            {
                "A": {"initial": 1.0},
                "p": {"initial": 1.0, "min": 0.1},
                "C": {"initial": 0.0},
            },
        )

    def _pade_template(self, m: int, n: int) -> tuple[str, dict[str, object]] | None:
        if m < 0 or n < 0:
            return None
        num_terms = []
        params: dict[str, dict[str, float]] = {}
        for power in range(m + 1):
            name = f"a{power}"
            params[name] = {"initial": 1.0 if power == 0 else 0.0}
            if power == 0:
                num_terms.append(name)
            else:
                num_terms.append(f"{name}*x**{power}")
        den_terms = ["1"]
        for power in range(1, n + 1):
            name = f"b{power}"
            params[name] = {"initial": 0.0}
            den_terms.append(f"{name}*x**{power}")
        numerator = " + ".join(num_terms) if num_terms else "a0"
        denominator = " + ".join(den_terms)
        expression = f"({numerator})/({denominator})"
        return expression, params

    def _build_spec_state(
        self, expression: str, params: dict[str, dict[str, object]]
    ) -> tuple[ModelSpecification, ParameterState]:
        parameter_names = list(params.keys())
        spec = build_model_specification(expression, ["x"], parameter_names)
        state = build_parameter_state(params, parameter_names)
        return spec, state

    def _default_auto_linear_definitions(self) -> list[AutoModelDefinition]:
        definitions: list[AutoModelDefinition] = []
        max_degree = max(1, min(6, self.poly_degree_spin.value()))
        for degree in range(1, max_degree + 1):
            definitions.append(build_polynomial_definition(degree))
        for min_power, max_power in [(1, 3), (2, 4)]:
            try:
                definitions.append(build_inverse_series_definition(min_power, max_power))
            except ValueError:
                continue
        return definitions

    def _default_auto_custom_entries(self) -> list[tuple[str, ModelSpecification, ParameterState]]:
        entries: list[tuple[str, ModelSpecification, ParameterState]] = []
        power_payload = self._power_limit_template()
        if power_payload:
            expr, params = power_payload
            spec, state = self._build_spec_state(expr, params)
            entries.append(("幂律极限模型", spec, state))
        for m, n in [(1, 1), (2, 2)]:
            payload = self._pade_template(m, n)
            if not payload:
                continue
            expr, params = payload
            spec, state = self._build_spec_state(expr, params)
            entries.append((f"Padé({m}|{n})", spec, state))
        return entries

    def _update_theme_from_palette(self, *args):
        from app_desktop.panels import _is_dark_theme, _get_table_style, _get_result_style
        new_dark = _is_dark_theme()
        if new_dark != self.pdf_dark_mode:
            self.pdf_dark_mode = new_dark
            self._display_pdf_images()
        # Update table and result browser styles to match new theme
        if hasattr(self, "manual_table"):
            self.manual_table.setStyleSheet(_get_table_style())
        if hasattr(self, "result_edit"):
            self.result_edit.setStyleSheet(_get_result_style())

    def _on_mode_change(self):
        mode = self.mode_combo.currentData()
        if mode == "extrapolation":
            self.extrap_box.show()
            self.error_box.hide()
            self.fit_box.hide()
            self.stats_box.hide()
        elif mode == "error":
            self.extrap_box.hide()
            self.error_box.show()
            self.fit_box.hide()
            self.stats_box.hide()
        elif mode == "statistics":
            self.extrap_box.hide()
            self.error_box.hide()
            self.fit_box.hide()
            self.stats_box.show()
            self._on_stats_mode_change()
        else:
            self.extrap_box.hide()
            self.error_box.hide()
            self.fit_box.show()
            self.stats_box.hide()
        self._update_manual_placeholder(mode)
        self._update_log_scale_visibility()

    def _update_method_state(self):
        method = self.method_combo.currentData()
        show_power = method == "power_law"
        show_levin = method == "levin_u"
        show_richardson = method == "richardson"
        show_custom = method == "custom"

        self.power_box.setVisible(show_power)
        if hasattr(self, "levin_box"):
            self.levin_box.setVisible(show_levin)
        if hasattr(self, "richardson_box"):
            self.richardson_box.setVisible(show_richardson)
        self.custom_formula_widget.setVisible(show_custom)

        if hasattr(self, "mpmath_precision_spin"):
            self.mpmath_precision_spin.setEnabled(True)

    def _update_levin_weight_state(self):
        """Show/hide Levin beta parameter based on weight function selection."""
        if not hasattr(self, "levin_weight_combo") or not hasattr(self, "levin_beta_spin"):
            return
        weight_type = self.levin_weight_combo.currentData()
        show_beta = weight_type == "reciprocal_beta"
        if hasattr(self, "levin_beta_label"):
            self.levin_beta_label.setVisible(show_beta)
        self.levin_beta_spin.setVisible(show_beta)

    def _set_corner_example_hint(self, example: str) -> None:
        """Show the per-mode example as a tooltip on the table's
        corner button (row-header × column-header intersection —
        the visual "(1,1)" cell users see).

        First call walks the table's child tree to locate the corner
        button (QTableWidget doesn't expose it as a named property);
        subsequent calls reuse the cached reference and only update
        the tooltip text. The event filter is installed once and
        carries the click → ``_show_data_file_hint`` wiring; we don't
        use ``.clicked`` because QTableWidget's corner button emits
        ``clicked(QModelIndex)`` whose argument shape doesn't match a
        no-arg slot, producing PySide6 ``Failed to disconnect``
        warnings on every mode switch.
        """
        from PySide6.QtWidgets import QAbstractButton

        table = self.manual_table
        tooltip = self._tr(
            f"示例（点击此处查看）：\n{example}",
            f"Example (click here to view):\n{example}",
        )
        table.setToolTip(tooltip)

        corner_button = getattr(self, "_corner_button", None)
        # Validate the cached reference: a Qt C++ object can be
        # destroyed underneath a Python wrapper (e.g. if some future
        # code path rebuilds the table), in which case calling
        # ``setToolTip`` would segfault. ``shiboken6.isValid`` is the
        # canonical health check; falling back to a try/except on a
        # cheap method call covers shiboken6 import failures.
        if corner_button is not None and not _qt_object_alive(corner_button):
            corner_button = None
            self._corner_button = None
        if corner_button is None:
            # The corner button is the lone QAbstractButton child
            # whose parent is the table itself (header buttons live
            # under QHeaderView, not the table directly).
            corner_button = next(
                (
                    child
                    for child in table.findChildren(QAbstractButton)
                    if child.parent() is table
                ),
                None,
            )
            self._corner_button = corner_button
            if corner_button is not None:
                self._corner_filter = _CornerExampleClickFilter(
                    self._show_data_file_hint
                )
                corner_button.installEventFilter(self._corner_filter)
        if corner_button is not None:
            corner_button.setToolTip(tooltip)

    def _update_manual_placeholder(self, mode: str | None):
        system_lang = getattr(self, "_system_lang", _LANG_EN)
        is_en = self._lang_mode == _LANG_EN or (self._lang_mode == _LANG_AUTO and system_lang == _LANG_EN)
        base = (
            "Paste data here (first row as headers).\n\n"
            if is_en
            else "在此粘贴与数据文件完全一致的内容（首行为表头）。\n\n"
        )
        zh_example, en_example = _MANUAL_EXAMPLES.get(
            mode or "extrapolation", _MANUAL_EXAMPLES["extrapolation"]
        )
        example = en_example if is_en else zh_example
        self._current_example_text = example
        placeholder = base + example
        self.manual_data_edit.setPlaceholderText(placeholder)
        if hasattr(self, "use_file_hint_btn"):
            self.use_file_hint_btn.setToolTip(example)
        # 根据行数动态调整高度，保证示例完整可见
        line_count = placeholder.count("\n") + 1
        target_height = max(120, int(line_count * 18 + 40))
        self.manual_data_edit.setMinimumHeight(target_height)

        # Auto-loading the example INTO the data table was confusing
        # users — pre-populated cells got mistaken for real data and
        # the example also leaked across mode switches because the
        # "table is empty" check fired only on the first switch. The
        # placeholder text + the "示例" tooltip on the corner header
        # button (set up below) are the right places for the example;
        # the data table stays clean until the user types.
        if hasattr(self, "manual_table"):
            self._set_corner_example_hint(example)

    def _show_data_file_hint(self):
        """Show the current data example (same content as the '?' tooltip)."""
        example = getattr(self, "_current_example_text", "") or (
            self.manual_data_edit.placeholderText() if hasattr(self, "manual_data_edit") else ""
        )
        example = (example or "").strip()
        if not example:
            return
        QMessageBox.information(self, self._tr("示例", "Example"), example)

    def _show_constants_file_hint(self):
        """Show the constants file example (same content as the '?' tooltip)."""
        hint = ""
        if hasattr(self, "constants_hint_btn"):
            hint = self.constants_hint_btn.toolTip() or ""
        hint = hint.strip()
        if not hint:
            hint = self._tr(
                "常数文件示例：ALPHA 7.2973525693(11)[-3]",
                "Constants file example: ALPHA 7.2973525693(11)[-3]",
            )
        QMessageBox.information(self, self._tr("常数文件示例", "Constants file example"), hint)

    def _show_error_functions(self):
        """Show function support help dialog - shared for both error propagation and custom extrapolation."""
        lang = "en" if self._is_en() else "zh"
        title = "Functions" if self._is_en() else "函数说明"
        message = get_function_help(lang)
        QMessageBox.information(self, title, message)

    def _show_method_help(self):
        """Show help dialog for the currently selected extrapolation method."""
        if not hasattr(self, "method_combo"):
            return
        method_key = self.method_combo.currentData()
        if not method_key:
            return

        lang = "en" if self._is_en() else "zh"
        msg = ""
        try:
            specs_path = resolve_resource_path(Path("shared") / "help_specs.json")
            if not specs_path:
                raise FileNotFoundError("help_specs.json not found in bundled resources")
            with open(specs_path, "r", encoding="utf-8") as fh:
                help_specs = json.load(fh)
            method_map = help_specs.get("extrapolation_methods", {}).get(method_key, {})
            block = method_map.get(lang) if isinstance(method_map, dict) else None
            if isinstance(block, dict):
                msg = str(block.get("description") or "")
            if msg:
                msg = msg.replace("{{DEFAULT_THREE_POINT_FORMULA}}", DEFAULT_THREE_POINT_FORMULA)
        except Exception:
            msg = ""
        if not msg:
            try:
                msg = str(get_method_description(str(method_key), lang) or "")
                if msg:
                    msg = msg.replace("{{DEFAULT_THREE_POINT_FORMULA}}", DEFAULT_THREE_POINT_FORMULA)
            except Exception:
                msg = ""
        if not msg:
            msg = self._tr("暂无详细说明。", "No detailed description available.")

        title = self._tr("外推方法说明", "Extrapolation Method Help")
        QMessageBox.information(self, title, msg)

    # ------------------------------------------------------------- Logging --
    def _set_result_text(self, text: str):
        """Display result text.  Uses Markdown rendering when available."""
        if hasattr(self.result_edit, 'setMarkdown'):
            self.result_edit.setMarkdown(text)
        else:
            self.result_edit.setPlainText(text)

    def _add_font_control_row(self, parent_layout: QVBoxLayout, editor, label: str):
        control_layout = QHBoxLayout()
        lbl = QLabel(label)
        self._register_text(lbl, "字体大小：", "Font size:")
        control_layout.addWidget(lbl)
        spin = QSpinBox()
        spin.setRange(8, 32)
        default_size = editor.font().pointSize()
        spin.setValue(max(8, default_size if default_size > 0 else 12))
        spin.valueChanged.connect(lambda value, target=editor: self._apply_editor_font_size(target, value))
        control_layout.addWidget(spin)
        control_layout.addStretch()
        parent_layout.addLayout(control_layout)

    def _apply_editor_font_size(self, editor, size: int):
        font = editor.font()
        font.setPointSize(size)
        editor.setFont(font)

    # Display formatting helpers (only affect presentation; core calculations remain at mpmath precision)
    def _display_digits_limit(self) -> int:
        """Return the display digits/places selected by user (0-50 in UI)."""
        return int(self.display_digits_spin.value() if hasattr(self, "display_digits_spin") else 10)

    def _update_display_digits_label(self):
        """Update the digits label to reflect current mode (decimal places vs significant digits)."""
        label = getattr(self, "display_digits_label", None)
        if not label:
            return
        sci = bool(getattr(self, "scientific_checkbox", None) and self.scientific_checkbox.isChecked())
        label.setText(self._tr("有效位数：", "Significant digits:") if sci else self._tr("小数位数：", "Decimal places:"))
        spin = getattr(self, "display_digits_spin", None)
        if not spin:
            return
        spin.blockSignals(True)
        try:
            spin.setMinimum(1 if sci else 0)
            if sci and spin.value() < 1:
                spin.setValue(1)
        finally:
            spin.blockSignals(False)

    def _format_display_value(self, value) -> str:
        """Format a numeric value according to the UI display controls (sci toggle + digits/places)."""
        if value is None or value == "":
            return "--"
        try:
            mp_val = value if isinstance(value, mp.mpf) else mp.mpf(value)
        except Exception:
            return str(value)
        if mp.isnan(mp_val):
            return "--"
        if mp.isinf(mp_val):
            return "inf" if mp_val > 0 else "-inf"
        digits_or_places = self._display_digits_limit()
        sci = bool(getattr(self, "scientific_checkbox", None) and self.scientific_checkbox.isChecked())

        try:
            # Convert to Decimal through a high-precision string snapshot (display-only).
            # NOTE: Decimal operations (quantize/rounding) must run under the same high-precision
            # context; otherwise the default Decimal precision (28) causes formatting to stop
            # working beyond ~28-30 digits.
            snapshot_digits = max(80, int(digits_or_places) + 60)
            raw = mp.nstr(mp_val, snapshot_digits, strip_zeros=False)
            with localcontext() as ctx:
                ctx.prec = max(100, snapshot_digits + 20)
                dec_val = Decimal(raw)

                if sci:
                    sig = max(1, int(digits_or_places))
                    if dec_val == 0:
                        return "0"
                    sign = "-" if dec_val.is_signed() else ""
                    abs_val = -dec_val if dec_val.is_signed() else dec_val
                    exp = abs_val.adjusted()
                    quant = Decimal(1).scaleb(exp - sig + 1)
                    rounded = abs_val.quantize(quant, rounding=ROUND_HALF_UP)
                    exp2 = rounded.adjusted()
                    mant = rounded.scaleb(-exp2)
                    mant_str = f"{mant:.{sig - 1}f}"
                    return f"{sign}{mant_str}e{exp2:+d}"

                places = max(0, int(digits_or_places))
                quant = Decimal(1).scaleb(-places)
                rounded = dec_val.quantize(quant, rounding=ROUND_HALF_UP)
                if rounded == 0:
                    return "0" if places == 0 else f"0.{('0' * places)}"
                return format(rounded, "f")
        except (InvalidOperation, ValueError):
            return str(mp_val)
        except Exception:
            return str(mp_val)

    def _format_display_uncertainty(self, sigma) -> str:
        """Format an uncertainty value without silently rounding non-zero values to 0."""
        text = self._format_display_value(sigma)
        try:
            sigma_val = sigma if isinstance(sigma, mp.mpf) else mp.mpf(sigma)
        except Exception:
            return text
        if sigma_val == 0:
            return text
        if re.fullmatch(r"-?0(?:\\.0+)?", str(text).strip()):
            sig = max(1, int(self._display_digits_limit()))
            try:
                return mp.nstr(sigma_val, sig)
            except Exception:
                return str(sigma_val)
        return text

    def _on_display_format_changed(self, *args):
        """Re-render current results using the presentation-only formatting layer."""
        self._update_display_digits_label()
        self._refresh_display_format()

    def _is_fit_mode_active(self) -> bool:
        return hasattr(self, "mode_combo") and self.mode_combo.currentData() == "fitting"

    def _current_log_scale(self) -> str | None:
        if not hasattr(self, "log_x_checkbox") or not hasattr(self, "log_y_checkbox"):
            return None
        if not self.log_x_checkbox.isVisible() and not self.log_y_checkbox.isVisible():
            return None
        flags = []
        if self.log_x_checkbox.isChecked():
            flags.append("x")
        if self.log_y_checkbox.isChecked():
            flags.append("y")
        return "".join(flags) if flags else None

    def _set_log_checkbox_checked(self, checkbox: QCheckBox | None, checked: bool):
        if not checkbox:
            return
        checkbox.blockSignals(True)
        checkbox.setChecked(checked)
        checkbox.blockSignals(False)

    def _sanitize_log_scale(self, log_scale: str | None, x_values: Sequence, y_values: Sequence) -> str | None:
        """Ensure selected log axes are valid for current data; auto-uncheck invalid axes."""
        scale = (log_scale or "").lower()
        if not scale:
            return None
        active = set(scale)

        def _has_non_positive(seq) -> bool:
            try:
                return any(mp.mpf(v) <= 0 for v in seq)
            except Exception:
                return True

        warning_parts: list[str] = []
        if "x" in active and _has_non_positive(x_values):
            active.discard("x")
            self._set_log_checkbox_checked(getattr(self, "log_x_checkbox", None), False)
            warning_parts.append(self._tr("存在非正 x 数据，无法使用 log-x。已回退为线性坐标。", "Non-positive x detected; log-x disabled."))
        if "y" in active and _has_non_positive(y_values):
            active.discard("y")
            self._set_log_checkbox_checked(getattr(self, "log_y_checkbox", None), False)
            warning_parts.append(self._tr("存在非正 y 数据，无法使用 log-y。已回退为线性坐标。", "Non-positive y detected; log-y disabled."))
        if warning_parts:
            self._append_log("\n".join(warning_parts))
        return "".join(sorted(active)) or None

    def _update_log_scale_visibility(self):
        """Show/hide log-scale controls based on mode and plot toggle."""
        enabled = self._is_fit_mode_active() and getattr(self, "generate_plots_checkbox", None) and self.generate_plots_checkbox.isChecked()
        for cb in (getattr(self, "log_x_checkbox", None), getattr(self, "log_y_checkbox", None)):
            if cb is None:
                continue
            cb.setVisible(enabled)
            cb.setEnabled(enabled)
            if not enabled and cb.isChecked():
                self._set_log_checkbox_checked(cb, False)
        if hasattr(self, "log_scale_label") and self.log_scale_label:
            self.log_scale_label.setVisible(enabled)

    def _on_log_scale_changed(self, *args):
        """Re-render the latest fit plot using the selected log-scale (display-only)."""
        self._refresh_fit_plot_log_scale()

    def _reset_csv_data(self):
        """Clear cached CSV rows and disable export control."""
        self._csv_rows: list[dict[str, object]] = []
        self._csv_headers: list[str] = []
        self._csv_suggest_name = "results.csv"
        if hasattr(self, "export_csv_btn"):
            self.export_csv_btn.setEnabled(False)

    def _set_csv_data(self, rows: list[dict[str, object]] | None, headers: list[str] | None = None, suggestion: str | None = None):
        """Cache the latest tabular results for CSV export."""
        self._csv_rows = rows or []
        if headers:
            self._csv_headers = headers
        elif self._csv_rows:
            self._csv_headers = list(self._csv_rows[0].keys())
        else:
            self._csv_headers = []
        if suggestion:
            self._csv_suggest_name = suggestion
        if hasattr(self, "export_csv_btn"):
            self.export_csv_btn.setEnabled(bool(self._csv_rows))
        if hasattr(self, "_workspace_dirty") and not getattr(self, "_workspace_restoring", False):
            self._mark_workspace_dirty()

    def _export_csv_data(self):
        if not getattr(self, "_csv_rows", None):
            QMessageBox.information(
                self,
                self._tr("无可导出的数据", "No data to export"),
                self._tr("请先运行计算以生成结果。", "Please run a calculation first."),
            )
            return
        default_name = getattr(self, "_csv_suggest_name", "results.csv") or "results.csv"
        initial_dir = getattr(self, "_last_export_dir", "")
        if initial_dir and Path(initial_dir).is_dir():
            initial_path = str(Path(initial_dir) / default_name)
        else:
            initial_path = default_name
        filename, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("导出 CSV", "Export CSV"),
            initial_path,
            "CSV (*.csv);;All Files (*)",
        )
        if not filename:
            return
        try:
            with open(filename, "w", encoding="utf-8", newline="") as fh:
                writer = csv.DictWriter(fh, fieldnames=self._csv_headers)
                writer.writeheader()
                writer.writerows(self._csv_rows)
            try:
                self._last_export_dir = str(Path(filename).parent)
            except Exception:
                pass
            QMessageBox.information(
                self,
                self._tr("已导出", "Exported"),
                self._tr(f"CSV 已保存到: {filename}", f"CSV saved to: {filename}"),
            )
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self._tr("导出失败", "Export failed"), str(exc))

    def _remember_last_result(self, kind: str, payload: dict[str, object]):
        """Cache the most recent result payload so we can reformat without recomputation."""
        self._last_result_kind = kind
        if not hasattr(self, "_last_result_payloads"):
            self._last_result_payloads = {}
        self._last_result_payloads[kind] = payload
        self._workspace_snapshot_only = False
        self._workspace_snapshot_stale = False
        self._set_snapshot_controls_enabled(True)
        if hasattr(self, "_workspace_dirty") and not getattr(self, "_workspace_restoring", False):
            self._mark_workspace_dirty()

    def _refresh_display_format(self):
        """Reformat the last shown results using the current display format controls."""
        kind = getattr(self, "_last_result_kind", None)
        payloads = getattr(self, "_last_result_payloads", {}) or {}
        if not kind or kind not in payloads:
            return
        payload = payloads[kind]
        try:
            if kind == "extrapolation":
                text, csv_rows = self._format_extrapolation_display(**payload)
                self._set_result_text(text)
                if csv_rows:
                    self._set_csv_data(csv_rows, ["index", "value", "uncertainty", "latex"], suggestion="extrapolation_results.csv")
                else:
                    self._reset_csv_data()
            elif kind == "error":
                text, csv_rows = self._format_error_display(**payload)
                self._set_result_text(text)
                if csv_rows:
                    self._set_csv_data(csv_rows, ["index", "value", "uncertainty", "latex"], suggestion="error_propagation_results.csv")
                else:
                    self._reset_csv_data()
            elif kind == "statistics_single":
                text, csv_rows = self._format_statistics_display(**payload)
                self._set_result_text(text)
                if csv_rows:
                    self._set_csv_data(csv_rows, ["batch", "metric", "value", "uncertainty"], suggestion="statistics_results.csv")
                else:
                    self._reset_csv_data()
            elif kind == "statistics_batches":
                text, csv_rows = self._format_statistics_batches_display(**payload)
                self._set_result_text(text)
                if csv_rows:
                    self._set_csv_data(csv_rows, ["batch", "metric", "value", "uncertainty"], suggestion="statistics_results.csv")
                else:
                    self._reset_csv_data()
            elif kind == "fit_single":
                text, csv_rows = self._format_fit_display(**payload)
                self._set_result_text(text)
                if csv_rows:
                    self._set_csv_data(
                        csv_rows,
                        ["batch", "section", "name", "value", "uncertainty", "stat_error", "sys_error", "note"],
                        suggestion="fitting_results.csv",
                    )
                else:
                    self._reset_csv_data()
            elif kind == "fit_auto":
                auto_kwargs = {k: payload.get(k) for k in [
                    "summary",
                    "headers",
                    "data_rows",
                    "sigma_rows",
                    "x_series",
                    "y_series",
                    "sigma_series",
                    "weights",
                    "generate_latex",
                    "output_path",
                    "extra_models",
                    "verbose_mode",
                ] if k in payload}
                render = self._render_auto_fit_summary(return_payload=True, render_plots=False, job_obj=payload.get("job"), **auto_kwargs)
                self._set_result_text(render.text)
                csv_rows = []
                if render.fit_result:
                    csv_rows = self._build_fit_csv_rows(render.fit_result, render.expression or "", batch_idx=1)
                if csv_rows:
                    self._set_csv_data(
                        csv_rows,
                        ["batch", "section", "name", "value", "uncertainty", "stat_error", "sys_error", "note"],
                        suggestion="fitting_results.csv",
                    )
                else:
                    self._reset_csv_data()
            elif kind == "fit_batches":
                self._reformat_fit_batches(**payload)
            else:
                return
        except Exception:
            # Avoid breaking UI on formatting errors
            return

    def _append_log(self, text: str):
        localized = "\n".join(self._localize_text(line) for line in text.splitlines())
        cursor = self.log_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(localized)
        cursor.insertText("\n" if not localized.endswith("\n") else "")
        self.log_edit.setTextCursor(cursor)
        self.log_edit.ensureCursorVisible()

    def _mp_to_float(self, value) -> float:
        try:
            mp_value = mp.mpf(value)
        except Exception:
            return float("nan")
        if mp.isnan(mp_value):
            return float("nan")
        if mp.isinf(mp_value):
            return float("inf") if mp_value > 0 else float("-inf")
        return float(mp_value)

    def _convert_mp_sequence(self, values: Sequence[mp.mpf]) -> list[float]:
        return [self._mp_to_float(value) for value in values]

    def _build_linear_plot_series(
        self,
        definition: AutoModelDefinition,
        fit_result: FitResult,
        x_series: list[mp.mpf],
        y_series: list[mp.mpf],
    ) -> tuple[list[float], list[float]]:
        evaluator = fit_result.details.get("evaluator")
        if callable(evaluator):
            samples = sample_mp_function(
                evaluator, x_series, precision=self._fit_output_digits
            )
        else:
            samples = [mp.mpf(value) for value in fit_result.fitted_curve]
        mp_targets = [mp.mpf(value) for value in y_series]
        residuals = [sample - target for sample, target in zip(samples, mp_targets)]
        return self._convert_mp_sequence(samples), self._convert_mp_sequence(residuals)

    def _build_standard_plot_series(self, fit_result: FitResult) -> tuple[list[float], list[float]]:
        return (
            self._convert_mp_sequence(fit_result.fitted_curve),
            self._convert_mp_sequence(fit_result.residuals),
        )

    def _set_fit_output_precision(self, digits: int):
        try:
            value = int(digits)
        except (TypeError, ValueError):
            value = 12
        self._fit_output_digits = max(6, value)

    def _format_precision_value(self, value: mp.mpf) -> str:
        return self._format_display_value(value)

    def _uncertainty_digits_value(self) -> int:
        if hasattr(self, "uncertainty_digits_spin"):
            return int(self.uncertainty_digits_spin.value())
        return 3

    def _latex_to_plain_uncertainty(self, latex_str: str) -> str:
        text = latex_str.replace(r"\\,", "")
        text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)
        return text.replace("\\", "")

    def _format_uncertainty_value(self, value: mp.mpf, error: mp.mpf, latex: bool = False) -> str:
        precision_hint = getattr(self, "_current_precision", None)
        with _mp_precision_guard(precision_hint):
            try:
                err = error if isinstance(error, mp.mpf) else mp.mpf(error)
            except Exception:
                err = mp.mpf("0")
            if mp.almosteq(err, mp.mpf("0")):
                return self._format_precision_value(value)
            latex_value = format_result_with_uncertainty_latex(value, err, self._uncertainty_digits_value())
        if latex:
            return latex_value
        return self._latex_to_plain_uncertainty(latex_value)

    def _format_table_value(self, value: mp.mpf, sigma: mp.mpf | None, digits: int) -> str:
        precision_hint = getattr(self, "_current_precision", None)
        with _mp_precision_guard(precision_hint):
            if sigma is not None:
                try:
                    sigma_val = sigma if isinstance(sigma, mp.mpf) else mp.mpf(sigma)
                except Exception:
                    sigma_val = mp.mpf("0")
                if not mp.almosteq(sigma_val, mp.mpf("0")):
                    return format_result_with_uncertainty_latex(value, sigma_val, self._uncertainty_digits_value())
            mp_val = value if isinstance(value, mp.mpf) else mp.mpf(value)
            return self._latex_escape(mp.nstr(mp_val, digits))

    def closeEvent(self, event):
        """Handle window close event - stop any running workers before closing."""
        # Persist UI state unconditionally here. If the user later
        # clicks "No" on the running-worker dialog, the save is still
        # valid — the user's last splitter position should be
        # remembered whether or not the exit completes. On the next
        # real close, the then-current sizes overwrite this save.
        try:
            from shared.settings_store import (
                KEY_MAIN_SPLITTER_STATE,
                SettingsStore,
            )

            splitter = getattr(self, "_main_splitter", None)
            if splitter is not None:
                # Reuse the instance cached by build_ui so the load
                # path and the save path hit the same QSettings object.
                settings = getattr(self, "_settings_store", None)
                if settings is None:
                    settings = SettingsStore()
                    self._settings_store = settings
                settings.save_bytes(
                    KEY_MAIN_SPLITTER_STATE, splitter.saveState()
                )
        except Exception:
            # Never block exit on a settings write failure. Log at
            # debug level so an unexpected failure (including ImportError
            # from a broken settings_store install) is discoverable in
            # DATALAB_DEBUG=1 runs without noise in production logs.
            import logging

            logging.getLogger(__name__).debug(
                "Splitter state save skipped during close",
                exc_info=True,
            )

        if event.spontaneous() and not self._confirm_workspace_discard_or_save():
            event.ignore()
            return

        if self._has_running_worker():
            reply = QMessageBox.question(
                self,
                self._tr("确认退出", "Confirm Exit"),
                self._tr(
                    "有任务正在运行。确定要退出吗？\n正在运行的任务将被停止。",
                    "A task is currently running. Are you sure you want to exit?\nThe running task will be stopped."
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Stop all running workers
                self._stop_current_worker()

                # Wait a short time for workers to stop gracefully
                max_wait_ms = 2000
                while self._has_running_worker() and max_wait_ms > 0:
                    QApplication.processEvents()
                    if self._calc_worker:
                        self._calc_worker.wait(100)
                    if self._fit_worker:
                        self._fit_worker.wait(100)
                    if self._auto_fit_worker:
                        self._auto_fit_worker.wait(100)
                    max_wait_ms -= 100

                # Force terminate if still running
                if self._calc_worker and self._calc_worker.isRunning():
                    self._calc_worker.terminate()
                    self._calc_worker.wait()
                if self._fit_worker and self._fit_worker.isRunning():
                    self._fit_worker.terminate()
                    self._fit_worker.wait()
                if self._auto_fit_worker and self._auto_fit_worker.isRunning():
                    self._auto_fit_worker.terminate()
                    self._auto_fit_worker.wait()

                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
