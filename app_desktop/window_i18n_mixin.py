from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import QObject, QLocale, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton, QStyle

from formula_help import get_function_tooltip
from app_desktop.result_view_titles import result_view_tab_title, result_view_tooltip
from app_desktop.theme import round_icon_button_style

from .resources import (
    _apply_system_theme,
    _detect_system_light_mode,
    _locate_icon_file,
    should_set_runtime_app_icon,
)

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
_LOGGER = logging.getLogger(__name__)


class WindowI18nMixin:
    # ------------------------------ Language helpers -------------------- #
    def _is_en(self) -> bool:
        system_lang = getattr(self, "_system_lang", _LANG_EN)
        if self._lang_mode == _LANG_EN:
            return True
        if self._lang_mode == _LANG_ZH:
            return False
        return system_lang == _LANG_EN

    def _tr(self, zh: str, en: str) -> str:
        return en if self._is_en() else zh

    def _localize_text(self, text: str) -> str:
        """Pick the appropriate language from a dual-language 'zh / en' string."""
        if not text:
            return text
        marker = " / "
        if marker in text:
            left, right = text.split(marker, 1)
            candidate = right if self._is_en() else left
            if candidate.strip():
                return candidate.strip()
        return text

    def _set_zoom_icon(self, button: QPushButton, kind: str):
        """Attach a zoom in/out icon with a magnifier +/− if available."""
        theme_name = "zoom-in" if kind == "in" else "zoom-out"
        icon = QIcon.fromTheme(theme_name)
        if icon.isNull():
            fallback = QStyle.SP_ArrowUp if kind == "in" else QStyle.SP_ArrowDown
            icon = self.style().standardIcon(fallback)
        if not icon.isNull():
            button.setIcon(icon)
            button.setIconSize(QSize(18, 18))

    def _style_round_icon_button(self, button: QPushButton):
        """Apply a rounded style with subtle hover/pressed feedback."""
        button.setFixedSize(32, 32)
        button.setStyleSheet(round_icon_button_style())

    def _localize_label(self, label: str) -> str:
        mapping = {
            "幂律极限模型": "Power-limit model",
            "Padé 拟合": "Padé fit",
            "多项式拟合": "Polynomial fit",
            "1/x^p 展开": "1/x^p series",
            "通用指数基": "Exponential basis",
            "对数多项式": "Log polynomial",
            "高次衰减 / High-order decay": "High-order decay",
            "x 级数 / 1/x series": "1/x series",
            "1/x^3~1/x^5 / 1/x^3~1/x^5": "1/x^3~1/x^5",
            "幂律外推(三点外推)": "Power-law (3-point)",
            "Richardson 序列加速": "Richardson",
            "Shanks 变换": "Shanks transform",
            "Levin u-transform": "Levin u-transform",
            "自定义公式(三点外推) (A,B,C)": "Custom (A,B,C)",
            "自定义模型": "Custom model",
            "显式模型拟合": "Explicit model fitting",
        }
        if self._is_en() and label in mapping:
            return mapping[label]
        if not self._is_en() and label in mapping:
            return label
        if "/" in label:
            parts = [part.strip() for part in label.split("/", 1)]
            if len(parts) == 2:
                return parts[1] if self._is_en() else parts[0]
        return label

    def _update_placeholders_language(self):
        if hasattr(self, "formula_edit"):
            self.formula_edit.setPlaceholderText(self._tr("公式（使用列名或 x1, x2 …）", "Formula (use column names or x1, x2 …)"))
        if hasattr(self, "error_constants_editor") and self.error_constants_editor is not None:
            self.error_constants_editor.text_view.setPlaceholderText(
                self._tr(
                    "# 每行一个常数：名称 值\n# 允许空行与以 # 开头的注释\nALPHA 7.2973525693(11)[-3]",
                    "# One constant per line: name value\n# Blank lines and lines starting with # are allowed\nALPHA 7.2973525693(11)[-3]",
                )
            )
        if hasattr(self, "custom_formula_edit"):
            self.custom_formula_edit.setPlaceholderText(
                self._tr(
                    "示例: (C - B)^2/(B - A) + C 或 Exp[-x1]*Sin[x2]",
                    "Example: (C - B)^2/(B - A) + C or Exp[-x1]*Sin[x2]",
                )
            )
        if hasattr(self, "power_p_edit"):
            self.power_p_edit.setPlaceholderText(self._tr("留空则自动求解 p", "Leave blank to solve p automatically"))
        if hasattr(self, "power_seed_guesses_edit"):
            self.power_seed_guesses_edit.setPlaceholderText(self._tr("如 0.5, 1, 2, -1", "e.g. 0.5, 1, 2, -1"))
        if hasattr(self, "fit_expr_edit"):
            self.fit_expr_edit.setPlaceholderText(
                self._tr("自定义模型表达式，例如 A*x**(-p) + C", "Custom model expression, e.g., A*x**(-p) + C")
            )
        if hasattr(self, "root_equations_edit"):
            self.root_equations_edit.setPlaceholderText(
                self._tr(
                    "每行一个方程，按 F(...)=0 求解；示例：x^2 - A",
                    "One equation per line, solved as F(...)=0; example: x^2 - A",
                )
            )
        if hasattr(self, "func_help_btn"):
            lang = "en" if self._is_en() else "zh"
            self.func_help_btn.setToolTip(get_function_tooltip(lang))
        if hasattr(self, "fit_func_help_btn"):
            lang = "en" if self._is_en() else "zh"
            self.fit_func_help_btn.setToolTip(get_function_tooltip(lang))
        if hasattr(self, "error_order_spin"):
            self.error_order_spin.setToolTip(
                self._tr(
                    "1 阶：线性误差估计；2 阶：包含 Hessian（二阶偏导）贡献。",
                    "Order 1: linear propagation; order 2: includes Hessian (second-derivative) contributions.",
                )
            )
        if hasattr(self, "error_mc_samples_spin"):
            self.error_mc_samples_spin.setToolTip(
                self._tr(
                    "Monte Carlo 样本数（越大越稳定，但耗时更长），至少 100。",
                    "Monte Carlo sample count (larger is more stable but slower), minimum 100.",
                )
            )
        if hasattr(self, "error_mc_seed_edit"):
            self.error_mc_seed_edit.setPlaceholderText(self._tr("留空=随机", "blank=random"))
            self.error_mc_seed_edit.setToolTip(
                self._tr(
                    "留空表示每次随机；填写整数可复现实验结果。",
                    "Leave blank for random each run; set an integer for reproducibility.",
                )
            )
        if hasattr(self, "method_help_btn"):
            self.method_help_btn.setToolTip(
                self._tr(
                    "点击查看当前外推方法的详细说明、适用场景和参数解释",
                    "Click to view detailed description, applicable scenarios, and parameter explanations for the current method",
                )
            )
        if hasattr(self, "constants_hint_btn") and hasattr(self, "use_constants_file_checkbox"):
            checked = self.use_constants_file_checkbox.isChecked()
            constants_placeholder = "ALPHA 7.2973525693(11)[-3]"
            if hasattr(self, "error_constants_editor") and self.error_constants_editor is not None:
                constants_placeholder = self.error_constants_editor.text_view.placeholderText()
            hint_text = (
                self._tr(
                    "常数文件示例：ALPHA 7.2973525693(11)[-3]",
                    "Constants file example: ALPHA 7.2973525693(11)[-3]",
                )
                if checked
                else constants_placeholder
            )
            self.constants_hint_btn.setToolTip(hint_text)

    # ------------------------------------------------------------------ UI --
    def set_theme_mode(self, mode: str) -> None:
        """Apply an explicit theme mode: 'auto' (follow OS), 'light', or 'dark'.

        'auto' re-reads the OS preference; 'light'/'dark' pin the palette and
        make _maybe_refresh_system_theme ignore later OS changes."""
        if mode not in ("auto", "light", "dark"):
            mode = "auto"
        self._theme_mode = mode
        app = QApplication.instance()
        if not app:
            return
        if mode == "auto":
            prefer_light = _detect_system_light_mode()
        else:
            prefer_light = mode == "light"
        self._windows_light_pref = prefer_light
        _apply_system_theme(app, prefer_light=prefer_light)
        self._update_theme_from_palette()

    def _maybe_refresh_system_theme(self, *args):
        # Cross-platform: fired by QStyleHints.colorSchemeChanged (macOS/Linux/
        # Windows) or, as a fallback, the Windows registry poll timer. In manual
        # Light/Dark mode the user's choice wins, so system changes are ignored.
        if getattr(self, "_theme_mode", "auto") != "auto":
            return
        app = QApplication.instance()
        if not app:
            return
        current = _detect_system_light_mode()
        if current is None or current == self._windows_light_pref:
            return
        self._windows_light_pref = current
        _apply_system_theme(app, prefer_light=current)
        self._update_theme_from_palette()

    # ------------------------------ Language helpers -------------------- #
    def _detect_system_language(self, refresh: bool = False) -> str:
        if not refresh:
            cached = getattr(self, "_system_lang", None)
            if cached in (_LANG_ZH, _LANG_EN):
                return cached

        def _cache(lang: str) -> str:
            self._system_lang = lang
            return lang

        try:
            # QLocale primary check
            sys_locale = QLocale.system()
            # uiLanguages for macOS/Qt-aware locale
            ui_langs = []
            try:
                ui_langs.extend([s.lower() for s in sys_locale.uiLanguages()])
            except Exception:
                pass
            try:
                ui_langs.extend([s.lower() for s in QLocale().uiLanguages()])
            except Exception:
                pass
            seen = set()
            ui_langs = [u for u in ui_langs if not (u in seen or seen.add(u))]
            for entry in ui_langs:
                if "zh" in entry:
                    return _cache(_LANG_ZH)
                if entry.startswith("en"):
                    return _cache(_LANG_EN)
            lang_enum = sys_locale.language()
            if lang_enum in (
                QLocale.Language.Chinese,
                QLocale.Language.SimplifiedChinese,
                QLocale.Language.TraditionalChinese,
            ):
                return _cache(_LANG_ZH)
            if lang_enum == QLocale.Language.English:
                return _cache(_LANG_EN)
            locale_name = sys_locale.name().lower()
            if "zh" in locale_name:
                return _cache(_LANG_ZH)
            if "en" in locale_name:
                return _cache(_LANG_EN)
            import locale

            lang = None
            loc = locale.getlocale()
            if loc and loc[0]:
                lang = loc[0]
            if not lang:
                lang, _ = locale.getdefaultlocale()
            if not lang:
                # macOS locale hints
                apple_langs = os.environ.get("AppleLanguages", "")
                if apple_langs:
                    apple_langs = apple_langs.lower()
                    if "zh" in apple_langs:
                        return _cache(_LANG_ZH)
                    if "en" in apple_langs:
                        return _cache(_LANG_EN)
                apple_locale = os.environ.get("AppleLocale", "")
                if apple_locale:
                    apple_locale = apple_locale.lower()
                    if apple_locale.startswith("zh") or "zh" in apple_locale:
                        return _cache(_LANG_ZH)
                    if apple_locale.startswith("en") or "en" in apple_locale:
                        return _cache(_LANG_EN)
                if lang is None and sys.platform.startswith("darwin"):
                    try:
                        import subprocess

                        output = subprocess.check_output(["defaults", "read", "-g", "AppleLanguages"], text=True)
                        lower = output.lower()
                        if "zh" in lower:
                            return _cache(_LANG_ZH)
                        if "en" in lower:
                            return _cache(_LANG_EN)
                    except Exception:
                        pass
                lang = os.environ.get("LANG", "") or os.environ.get("LC_ALL", "") or os.environ.get("LC_CTYPE", "")
            lang_lower = str(lang).lower() if lang else ""
            if lang_lower.startswith("zh") or "zh" in lang_lower:
                return _cache(_LANG_ZH)
            if lang_lower.startswith("en") or "en" in lang_lower:
                return _cache(_LANG_EN)
        except Exception:
            pass
        return _cache(_LANG_EN)

    def _register_text(self, widget, zh: str, en: str, attr: str = "setText"):
        self._translations.append((widget, attr, zh, en))

    def _register_title(self, widget, zh: str, en: str):
        self._register_text(widget, zh, en, "setTitle")

    def _register_combo(self, combo: QComboBox, items: list[tuple[str, str, object]]):
        self._combo_translations.append((combo, items))

    def _apply_language(self, lang: str):
        effective_lang = lang if lang in (_LANG_ZH, _LANG_EN) else self._detect_system_language()
        if self._lang_mode == _LANG_AUTO:
            self._system_lang = effective_lang
        # Window title
        self.setWindowTitle("DataLab")
        for widget, attr, zh, en in self._translations:
            try:
                getattr(widget, attr)(zh if effective_lang == _LANG_ZH else en)
            except Exception:
                continue
        for widget in [self, *self.findChildren(QObject)]:
            try:
                zh_tooltip = widget.property("datalab_tooltip_zh")
                en_tooltip = widget.property("datalab_tooltip_en")
                if zh_tooltip or en_tooltip:
                    widget.setToolTip(zh_tooltip if effective_lang == _LANG_ZH else en_tooltip)
            except Exception:
                continue
        for combo, items in self._combo_translations:
            current_data = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for zh, en, data in items:
                combo.addItem(zh if effective_lang == _LANG_ZH else en, data)
            if current_data is not None:
                idx = combo.findData(current_data)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            combo.blockSignals(False)
        # The engine combo is dynamically populated (自动 + detected engines), so it is NOT
        # in _combo_translations; re-run its populate to retranslate the 自动/Auto label while
        # preserving the detected engine rows + current selection.
        if hasattr(self, "latex_engine_combo"):
            from app_desktop.panels import populate_latex_engine_combo

            populate_latex_engine_combo(self)
        # 更新占位文本
        if hasattr(self, "mode_combo"):
            self._update_manual_placeholder(self.mode_combo.currentData())
        self._update_placeholders_language()
        # 更新标签页文字
        try:
            if self.result_tabs:
                result_indices = getattr(self, "result_tabs_indices", {})
                for view_key in _RESULT_VIEW_ORDER:
                    alias = view_key.split(".", 1)[1]
                    index = result_indices.get(alias)
                    if index is None or index >= self.result_tabs.count():
                        continue
                    self.result_tabs.setTabText(index, result_view_tab_title(view_key, effective_lang))
                    self.result_tabs.setTabToolTip(index, result_view_tooltip(view_key, effective_lang))
            if hasattr(self, "main_tabs_indices"):
                self.tabs.setTabText(self.main_tabs_indices["result"], "结果" if effective_lang == _LANG_ZH else "Result")
            # Input-data sheet tabs (输入数据 / 常数) — retranslate by matching the hosted widget,
            # since the 常数 tab is added/removed by mode so its index is not fixed.
            input_tabs = getattr(self, "input_data_tabs", None)
            if input_tabs is not None:
                for index in range(input_tabs.count()):
                    widget = input_tabs.widget(index)
                    if widget is getattr(self, "_data_tab", None):
                        input_tabs.setTabText(index, "输入数据" if effective_lang == _LANG_ZH else "Data input")
                    elif widget is getattr(self, "_constants_tab", None):
                        input_tabs.setTabText(index, "常数" if effective_lang == _LANG_ZH else "Constants")
            if hasattr(self, "latex_edit"):
                self.latex_edit.setPlaceholderText(
                    "% LaTeX 内容将在此显示…" if effective_lang == _LANG_ZH else "% LaTeX content will appear here…"
                )
            if hasattr(self, "result_plot_label") and not self.result_plot_label.pixmap():
                self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
        except Exception:
            pass
        self._update_display_digits_label()
        self._update_model_hint()
        self._refresh_reference_auto_label()
        if hasattr(self, "root_uncertainty_method_combo"):
            try:
                from app_desktop.panels import _on_root_uncertainty_method_changed, _refresh_root_field_help

                _refresh_root_field_help(self)
                _on_root_uncertainty_method_changed(self)
            except Exception:
                _LOGGER.exception("Failed to refresh root uncertainty i18n")
        if hasattr(self, "refresh_workbench_result_rail"):
            self.refresh_workbench_result_rail()
        if hasattr(self, "refresh_workbench_formula_panel"):
            self.refresh_workbench_formula_panel()
        if hasattr(self, "refresh_workbench_variable_panel"):
            self.refresh_workbench_variable_panel()
        if hasattr(self, "refresh_workbench_data_card"):
            self.refresh_workbench_data_card()
        if hasattr(self, "refresh_workbench_data_summary"):
            self.refresh_workbench_data_summary()
        if hasattr(self, "_refresh_main_splitter_left_min_width"):
            self._refresh_main_splitter_left_min_width()

    def _on_language_change(self, index: int):
        if index == 0:
            lang = self._detect_system_language(refresh=True)
            self._lang_mode = _LANG_AUTO
        elif index == 1:
            lang = _LANG_ZH
            self._lang_mode = _LANG_ZH
        else:
            lang = _LANG_EN
            self._lang_mode = _LANG_EN
        self._apply_language(lang)

    def _apply_window_icon(self):
        icon_path = _locate_icon_file()
        if not icon_path:
            return
        icon = QIcon(str(icon_path))
        self.setWindowIcon(icon)
        app = QApplication.instance()
        if app and should_set_runtime_app_icon():
            app.setWindowIcon(icon)
        self._window_icon = icon
