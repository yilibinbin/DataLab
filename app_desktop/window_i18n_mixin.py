from __future__ import annotations

import os
import sys

from PySide6.QtCore import QLocale, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton, QStyle

from formula_help import get_function_tooltip

from .resources import _apply_system_theme, _detect_windows_light_mode, _locate_icon_file

_LANG_ZH = "zh"
_LANG_EN = "en"
_LANG_AUTO = "auto"


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
        button.setStyleSheet(
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
        )

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
            "Richardson 序列加速(三点外推)": "Richardson (3-point)",
            "Shanks 变换": "Shanks transform",
            "Levin u-transform": "Levin u-transform",
            "自定义公式(三点外推) (A,B,C)": "Custom (A,B,C)",
            "自定义模型": "Custom model",
            "自动模型选择": "Auto model selection",
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
        if hasattr(self, "manual_constants_edit") and self.manual_constants_edit is not None:
            self.manual_constants_edit.setPlaceholderText(
                self._tr("手动常数示例：\nALPHA 7.2973525693(11)[-3]", "Manual constant example:\nALPHA 7.2973525693(11)[-3]")
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
        if hasattr(self, "fit_param_edit"):
            placeholder_zh = (
                "{\n  \"A\": {\"initial\": 1.0},\n  \"p\": {\"initial\": 1.0, \"min\": 0.1},\n"
                "  \"C\": {\"initial\": 0.0}\n}\n# 参数配置（JSON）"
            )
            placeholder_en = (
                "{\n  \"A\": {\"initial\": 1.0},\n  \"p\": {\"initial\": 1.0, \"min\": 0.1},\n"
                "  \"C\": {\"initial\": 0.0}\n}\n# Parameter config (JSON)"
            )
            self.fit_param_edit.setPlaceholderText(self._tr(placeholder_zh, placeholder_en))
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
            hint_text = (
                self._tr(
                    "常数文件示例：ALPHA 7.2973525693(11)[-3]",
                    "Constants file example: ALPHA 7.2973525693(11)[-3]",
                )
                if checked
                else (self.manual_constants_edit.placeholderText() if hasattr(self, "manual_constants_edit") and self.manual_constants_edit is not None else "ALPHA 7.2973525693(11)[-3]")
            )
            self.constants_hint_btn.setToolTip(hint_text)

    # ------------------------------------------------------------------ UI --
    def _maybe_refresh_system_theme(self):
        if os.name != "nt":
            return
        app = QApplication.instance()
        if not app:
            return
        current = _detect_windows_light_mode()
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
        # 更新占位文本
        if hasattr(self, "mode_combo"):
            self._update_manual_placeholder(self.mode_combo.currentData())
        self._update_placeholders_language()
        # 更新标签页文字
        try:
            if self.result_tabs and self.result_tabs.count() >= 2:
                self.result_tabs.setTabText(0, "数值结果" if effective_lang == _LANG_ZH else "Values")
                self.result_tabs.setTabText(1, "图片" if effective_lang == _LANG_ZH else "Image")
            if hasattr(self, "main_tabs_indices"):
                self.tabs.setTabText(self.main_tabs_indices["result"], "结果" if effective_lang == _LANG_ZH else "Result")
                self.tabs.setTabText(self.main_tabs_indices["log"], "日志" if effective_lang == _LANG_ZH else "Log")
                self.tabs.setTabText(self.main_tabs_indices["latex"], "LaTeX" if effective_lang == _LANG_ZH else "LaTeX")
                self.tabs.setTabText(
                    self.main_tabs_indices["pdf"], "PDF 预览" if effective_lang == _LANG_ZH else "PDF Preview"
                )
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
        if app:
            app.setWindowIcon(icon)
        self._window_icon = icon

