from __future__ import annotations

import csv
import json
import math
import os
import random
import re
import tempfile
from pathlib import Path
from types import SimpleNamespace

import mpmath as mp

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMessageBox, QWidget

from data_extrapolation_latex_latest import _dual_msg
from fitting import (
    auto_fit_dataset,
    build_model_specification,
    build_parameter_state,
    fit_custom_model,
    infer_parameter_names,
    render_fitting_overview,
    sample_mp_function,
    summarize_auto_results,
)
from fitting.auto_models import (
    AUTO_MODELS,
    AutoModelDefinition,
    build_inverse_series_definition,
    build_polynomial_definition,
    fit_linear_model,
)
from fitting.hp_fitter import FitResult

from .workers_core import (
    AutoFitJob,
    AutoFitRenderResult,
    FitBatchResultEntry,
    FitBatchTask,
    FitJob,
    FitResultPayload,
    _mp_precision_guard,
)
from .workers_qt import AutoFitWorker, FitBatchWorker, FitWorker
from . import fitting_latex_writer as _fit_latex_writer


class WindowFittingMixin:
    # ------------------------------ Param helpers --------------------------- #
    def _next_param_name(self) -> str:
        existing = {row[0].text().strip() for row in getattr(self, "param_rows", []) if row[0].text().strip()}
        for candidate in ["A", "B", "C", "p", "k", "C0"]:
            if candidate not in existing:
                return candidate
        idx = 1
        while True:
            name = f"P{idx}"
            if name not in existing:
                return name
            idx += 1

    def _add_param_row(self, default_name: str | None = None, init: str = "", min_val: str = "", max_val: str = ""):
        if not hasattr(self, "param_rows_layout"):
            return
        name = default_name or self._next_param_name()
        row_layout = QHBoxLayout()
        name_edit = QLineEdit(name)
        init_edit = QLineEdit(init)
        min_edit = QLineEdit(min_val)
        max_edit = QLineEdit(max_val)
        lbl_name = QLabel(self._tr("名称", "Name"))
        lbl_init = QLabel(self._tr("初值", "Init"))
        lbl_min = QLabel(self._tr("下界", "Min"))
        lbl_max = QLabel(self._tr("上界", "Max"))
        for widget in (lbl_name, name_edit, lbl_init, init_edit, lbl_min, min_edit, lbl_max, max_edit):
            row_layout.addWidget(widget)
        container = QWidget()
        container.setLayout(row_layout)
        self.param_rows_layout.addWidget(container)
        if not hasattr(self, "param_rows"):
            self.param_rows = []
        self.param_rows.append((name_edit, init_edit, min_edit, max_edit, container))

    def _remove_param_row(self):
        if not hasattr(self, "param_rows") or not self.param_rows:
            return
        if hasattr(self, "enable_constraints_checkbox") and self.enable_constraints_checkbox.isChecked():
            if len(self.param_rows) <= 1:
                return
        _, _, _, _, container = self.param_rows.pop()
        try:
            container.setParent(None)
            container.deleteLater()
        except Exception:
            pass

    def _on_constraints_toggle(self, checked: bool):
        mode = self.fit_model_combo.currentData() if hasattr(self, "fit_model_combo") else None
        show_params = checked and mode != "auto"
        if show_params and (not getattr(self, "param_rows", None)):
            self._add_param_row()
        if hasattr(self, "param_header_widget"):
            self.param_header_widget.setVisible(show_params)
        if hasattr(self, "param_rows_container"):
            self.param_rows_container.setVisible(show_params)
        if hasattr(self, "add_param_btn"):
            self.add_param_btn.setVisible(show_params)
        if hasattr(self, "remove_param_btn"):
            self.remove_param_btn.setVisible(show_params)

    def _reset_param_rows(self):
        if not hasattr(self, "param_rows_layout"):
            return
        for _, _, _, _, container in getattr(self, "param_rows", []):
            try:
                container.setParent(None)
                container.deleteLater()
            except Exception:
                pass
        self.param_rows = []
        # start empty; user can add constraints as needed

    def _extract_param_rows(self) -> dict:
        config: dict[str, dict[str, float]] = {}
        for name_edit, init_edit, min_edit, max_edit, _ in getattr(self, "param_rows", []):
            name = name_edit.text().strip()
            init_text = init_edit.text().strip()
            if not name and not init_text:
                continue
            if not name:
                raise ValueError(self._tr("参数名称不能为空。", "Parameter name cannot be empty."))
            if not init_text:
                raise ValueError(self._tr(f"参数 {name} 需要初值。", f"Parameter {name} needs an initial value."))
            try:
                init_val = float(init_text)
            except ValueError as exc:
                raise ValueError(self._tr(f"参数 {name} 的初值无效。", f"Invalid initial value for parameter {name}.")) from exc
            entry: dict[str, float] = {"initial": init_val}
            for key, edit in (("min", min_edit), ("max", max_edit)):
                text = edit.text().strip()
                if text:
                    try:
                        entry[key] = float(text)
                    except ValueError as exc:
                        raise ValueError(self._tr(f"参数 {name} 的 {key} 无效。", f"Invalid {key} for parameter {name}."))
                config[name] = entry
        return config

    def _collect_parameter_config(self, allow_empty: bool = True) -> dict:
        if hasattr(self, "enable_constraints_checkbox") and not self.enable_constraints_checkbox.isChecked():
            return {}
        from_rows = self._extract_param_rows()
        if from_rows:
            return from_rows
        if allow_empty:
            return {}
        raise ValueError(self._tr("请在参数列表中添加参数。", "Please add at least one parameter."))

    def _build_substituted_expression(self, expression: str, params: dict[str, mp.mpf], digits: int | None = None) -> str:
        if not expression:
            return ""

        parameter_names = set(params.keys())
        # Use specified digits for LaTeX output, or fall back to fit output digits
        precision = digits if digits is not None else getattr(self, "_fit_output_digits", 12)

        def repl(match: re.Match[str]) -> str:
            name = match.group(0)
            if name in parameter_names:
                mp_value = mp.mpf(params[name])
                if mp.isnan(mp_value) or mp.isinf(mp_value):
                    return str(mp_value)
                return mp.nstr(mp_value, precision)
            return name

        return re.sub(r"[A-Za-z_][A-Za-z0-9_]*", repl, expression)

    def _infer_parameter_names(
        self, expression: str, variable_names: list[str], config_keys: list[str]
    ) -> list[str]:
        return infer_parameter_names(expression, variable_names, config_keys)

    def _format_fit_result_text(
        self, fit_result: FitResult, expression: str | None, substituted: str | None
    ) -> str:
        lines = [self._tr("=== 拟合结果 ===", "=== Fit Results ===")]
        if expression:
            lines.append(self._tr(f"模型: {expression}", f"Model: {expression}"))
        if substituted:
            lines.append(self._tr(f"代入参数: {substituted}", f"With params: {substituted}"))
        lines.append("")
        lines.append(self._tr("参数结果：", "Parameters:"))
        for name, value in fit_result.params.items():
            total_err = (fit_result.param_errors_total or fit_result.param_errors).get(name, mp.mpf("0"))
            stat_err = (fit_result.param_errors_stat or {}).get(name, total_err)
            sys_err = (fit_result.param_errors_sys or {}).get(name, mp.mpf("0"))
            line = f"{name} = {self._format_uncertainty_value(value, total_err)}"
            if sys_err and not mp.almosteq(sys_err, mp.mpf("0")):
                line += self._tr(
                    f" (统计 {self._format_precision_value(stat_err)}, 系统 {self._format_precision_value(sys_err)})",
                    f" (stat {self._format_precision_value(stat_err)}, sys {self._format_precision_value(sys_err)})",
                )
            lines.append(line)
        lines.append("")
        lines.extend(
            [
                self._tr(
                    f"χ² = {self._format_precision_value(fit_result.chi2)}",
                    f"χ² = {self._format_precision_value(fit_result.chi2)}",
                ),
                self._tr(
                    f"Reduced χ² = {self._format_precision_value(fit_result.reduced_chi2)}",
                    f"Reduced χ² = {self._format_precision_value(fit_result.reduced_chi2)}",
                ),
                f"AIC = {self._format_precision_value(fit_result.aic)}",
                f"BIC = {self._format_precision_value(fit_result.bic)}",
                f"R² = {self._format_precision_value(fit_result.r2)}",
                f"RMSE = {self._format_precision_value(fit_result.rmse)}",
            ]
        )
        if fit_result.details.get("weighted"):
            lines.append(self._tr("说明: 使用测量不确定度加权拟合。", "Note: Weighted by measurement uncertainty."))
        note = fit_result.details.get("uncertainty_note")
        if isinstance(note, dict):
            zh_note = note.get("zh", "")
            en_note = note.get("en", "")
            if zh_note or en_note:
                lines.append(self._tr(f"说明: {zh_note}", f"Note: {en_note}"))
        elif note:
            localized_note = self._localize_text(str(note))
            lines.append(self._tr(f"说明: {localized_note}", f"Note: {localized_note}"))
        sys_warning = fit_result.details.get("systematic_warning")
        if sys_warning:
            localized = self._localize_text(str(sys_warning))
            lines.append(self._tr(f"警告: {localized}", f"Warning: {localized}"))
        warning = fit_result.details.get("boundary_warning")
        if warning:
            localized = self._localize_text(str(warning))
            lines.append(self._tr(f"警告: {localized}", f"Warning: {localized}"))
        return "\n".join(lines)

    def _format_fit_display(self, fit_result: FitResult, expression: str | None, substituted: str | None, batch_idx: int = 1, **_ignored) -> tuple[str, list[dict[str, object]]]:
        """Return formatted fit summary text/CSV rows (numbers only; LaTeX unaffected)."""
        text = self._format_fit_result_text(fit_result, expression, substituted)
        csv_rows = self._build_fit_csv_rows(fit_result, expression or "", batch_idx=batch_idx)
        return text, csv_rows

    def _reformat_fit_batches(self, entries: list[FitBatchResultEntry], context: dict[str, object]):
        """Reformat batch fit results without recomputation or image regeneration."""
        batch_texts: list[str] = []
        csv_rows: list[dict[str, object]] = []
        for entry in sorted(entries, key=lambda e: e.index):
            header = self._tr(f"=== 拟合结果：批次 {entry.index} ===", f"=== Fit Result: Batch {entry.index} ===")
            if entry.error:
                batch_texts.append(header + "\n" + self._tr(f"批次 {entry.index} 失败: {entry.error}", f"Batch {entry.index} failed: {entry.error}"))
                continue
            if entry.kind == "fit" and entry.fit_payload:
                payload = entry.fit_payload
                job = payload.job
                expression = payload.expression or job.model_expr
                substituted = self._build_substituted_expression(expression, payload.fit_result.params) if expression else ""
                text, rows = self._format_fit_display(payload.fit_result, expression, substituted, batch_idx=entry.index)
                batch_texts.append(header + "\n" + text)
                csv_rows.extend(rows)
            elif entry.kind == "auto" and entry.auto_payload:
                summary_obj, job = entry.auto_payload
                render = self._render_auto_fit_summary(
                    summary_obj,
                    job.headers,
                    job.data_rows,
                    job.sigma_rows,
                    job.x_series,
                    job.y_series,
                    job.sigma_series,
                    job.weights,
                    False,
                    "",
                    job.extra_models if hasattr(job, "extra_models") else [],
                    context.get("verbose", False),
                    job_obj=job,
                    return_payload=True,
                    render_plots=False,
                )
                batch_texts.append(header + "\n" + render.text)
                if render.fit_result:
                    csv_rows.extend(
                        self._build_fit_csv_rows(
                            render.fit_result,
                            render.expression or "",
                            batch_idx=entry.index,
                        )
                    )
            else:
                batch_texts.append(header + "\n" + self._tr("未获得该批次结果。", "No result for this batch."))
        combined = "\n\n".join(batch_texts)
        self._set_result_text(combined)
        if csv_rows:
            self._set_csv_data(
                csv_rows,
                ["batch", "section", "name", "value", "uncertainty", "stat_error", "sys_error", "note"],
                suggestion="fitting_results.csv",
            )
        else:
            self._reset_csv_data()

    def _build_fit_csv_rows(self, fit_result: FitResult, expression: str | None, batch_idx: int | None = None) -> list[dict[str, object]]:
        def _fmt(val) -> str:
            return self._format_display_value(val)

        batch_value = batch_idx if batch_idx is not None else 1
        rows: list[dict[str, object]] = []
        if expression:
            rows.append(
                {
                    "batch": batch_value,
                    "section": "model",
                    "name": "expression",
                    "value": expression,
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        for name, value in fit_result.params.items():
            total_err = (fit_result.param_errors_total or fit_result.param_errors).get(name, mp.mpf("0"))
            stat_err = (fit_result.param_errors_stat or {}).get(name)
            sys_err = (fit_result.param_errors_sys or {}).get(name)
            rows.append(
                {
                    "batch": batch_value,
                    "section": "parameter",
                    "name": name,
                    "value": _fmt(value),
                    "uncertainty": _fmt(total_err),
                    "stat_error": _fmt(stat_err) if stat_err is not None else "",
                    "sys_error": _fmt(sys_err) if sys_err is not None else "",
                    "note": "",
                }
            )
        metrics = [
            ("chi2", fit_result.chi2),
            ("reduced_chi2", fit_result.reduced_chi2),
            ("aic", fit_result.aic),
            ("bic", fit_result.bic),
            ("r2", fit_result.r2),
            ("rmse", fit_result.rmse),
        ]
        for name, value in metrics:
            rows.append(
                {
                    "batch": batch_value,
                    "section": "metric",
                    "name": name,
                    "value": _fmt(value),
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        cov = getattr(fit_result, "covariance", None)
        if cov:
            for i, cov_row in enumerate(cov):
                for j, cov_val in enumerate(cov_row):
                    rows.append(
                        {
                            "batch": batch_value,
                            "section": "covariance",
                            "name": f"cov[{i + 1},{j + 1}]",
                            "value": _fmt(cov_val),
                            "uncertainty": "",
                            "stat_error": "",
                            "sys_error": "",
                            "note": "",
                        }
                    )
        if fit_result.details.get("weighted"):
            rows.append(
                {
                    "batch": batch_value,
                    "section": "note",
                    "name": "weighted",
                    "value": "True",
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        note = fit_result.details.get("uncertainty_note")
        if note:
            localized = ""
            if isinstance(note, dict):
                localized = note.get("en" if self._is_en() else "zh", "") or str(note)
            else:
                localized = self._localize_text(str(note))
            rows.append(
                {
                    "batch": batch_value,
                    "section": "note",
                    "name": "uncertainty_note",
                    "value": localized,
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        sys_warning = fit_result.details.get("systematic_warning")
        if sys_warning:
            rows.append(
                {
                    "batch": batch_value,
                    "section": "note",
                    "name": "systematic_warning",
                    "value": self._localize_text(str(sys_warning)),
                    "uncertainty": "",
                    "stat_error": "",
                    "sys_error": "",
                    "note": "",
                }
            )
        return rows

    def _latex_escape(self, text: str) -> str:
        return _fit_latex_writer.latex_escape(text)

    def _fit_latex_preamble(self, use_dcolumn: bool, digits: int, latex_group_size: int) -> list[str]:
        return _fit_latex_writer.build_fit_latex_preamble(
            use_dcolumn=use_dcolumn,
            digits=digits,
            latex_group_size=latex_group_size,
        )

    def _fit_latex_block(
        self,
        headers: list[str],
        rows: list[tuple[mp.mpf, ...]],
        sigma_rows: list[tuple[mp.mpf | None, ...]],
        fit_result: FitResult,
        expression: str,
        substituted: str,
        image_path: Path | None,
        use_dcolumn: bool,
        digits: int,
        *,
        latex_group_size: int = 3,
        batch_index: int | None = None,
    ) -> list[str]:
        default_unc_digits = self._uncertainty_digits_value()
        target_column = self.fit_target_edit.text().strip()
        try:
            variable_pairs = self._ordered_variable_pairs(headers)
        except Exception:
            variable_pairs = []
        caption_base = self._caption_value() if hasattr(self, "_caption_value") else None

        if expression and fit_result.params:
            cleaned_sub = (
                self._build_substituted_expression(expression, fit_result.params, digits).strip().replace("**", "^")
            )
        else:
            cleaned_sub = (substituted or "").strip().replace("**", "^")

        return _fit_latex_writer.build_fit_latex_block(
            headers=headers,
            rows=rows,
            sigma_rows=sigma_rows,
            fit_result=fit_result,
            expression=expression,
            substituted=substituted,
            image_path=image_path,
            use_dcolumn=use_dcolumn,
            digits=digits,
            latex_group_size=latex_group_size,
            batch_index=batch_index,
            target_column=target_column,
            variable_pairs=variable_pairs,
            caption_text=caption_base,
            default_uncertainty_digits=default_unc_digits,
            cleaned_substituted=cleaned_sub,
        )

    def _write_fitting_latex(
        self,
        headers: list[str],
        rows: list[tuple[mp.mpf, ...]],
        sigma_rows: list[tuple[mp.mpf | None, ...]],
        fit_result: FitResult,
        expression: str,
        substituted: str,
        plot_bytes: bytes | None,
        output_path: str,
        use_dcolumn: bool,
    ) -> Path | None:
        digits = self.latex_input_precision_spin.value() if hasattr(self, "latex_input_precision_spin") else 16
        group_size = self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3
        tex_path = Path(output_path).expanduser()
        image_path = None  # 不再向 LaTeX 中插入图片
        lines = self._fit_latex_preamble(use_dcolumn, digits, group_size)
        lines.extend(
            self._fit_latex_block(
                headers,
                rows,
                sigma_rows,
                fit_result,
                expression,
                substituted,
                image_path,
                use_dcolumn,
                digits,
                latex_group_size=group_size,
            )
        )
        lines.append("\\end{document}")
        try:
            with open(tex_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            self._append_log(f"拟合 LaTeX 已写入: {tex_path}")
            self._load_latex_into_editor(tex_path)
            return tex_path
        except OSError as exc:
            QMessageBox.warning(
                self,
                self._tr("写入失败", "Write Failed"),
                str(exc)
            )
            return None

    def _write_fitting_latex_batches(
        self,
        batches: list[dict],
        output_path: str,
        use_dcolumn: bool,
        *,
        latex_group_size: int | None = None,
    ) -> Path | None:
        digits = self.latex_input_precision_spin.value() if hasattr(self, "latex_input_precision_spin") else 16
        if latex_group_size is not None:
            group_size = max(1, int(latex_group_size))
        else:
            group_size = self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3
        tex_path = Path(output_path).expanduser()
        lines = self._fit_latex_preamble(use_dcolumn, digits, group_size)
        for entry in batches:
            lines.extend(
                self._fit_latex_block(
                    entry.get("headers", []),
                    entry.get("rows", []),
                    entry.get("sigma_rows", []),
                    entry["fit_result"],
                    entry.get("expression", ""),
                    entry.get("substituted", ""),
                    entry.get("figure_path"),
                    use_dcolumn,
                    digits,
                    latex_group_size=group_size,
                    batch_index=entry.get("index"),
                )
            )
        lines.append("\\end{document}")
        try:
            with open(tex_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            self._append_log(f"拟合 LaTeX 已写入: {tex_path}")
            self._load_latex_into_editor(tex_path)
            return tex_path
        except OSError as exc:
            QMessageBox.warning(
                self,
                self._tr("写入失败", "Write Failed"),
                str(exc)
            )
            return None

    def _execute_custom_fit(
        self,
        dataset: tuple[list[str], list[tuple[mp.mpf, ...]], list[tuple[mp.mpf | None, ...]]],
        generate_latex: bool,
        output_path: str,
        batch_tag: str = "",
        verbose: bool = False,
    ) -> str | None:
        try:
            headers, data_rows, sigma_rows = dataset
            variable_map = self._collect_variable_mapping(headers)
            target_column = self.fit_target_edit.text().strip()
            if not target_column:
                raise ValueError(_dual_msg("请指定目标列。", "Please specify the target column."))
            target_series = self._column_series(headers, data_rows, target_column)
            sigma_series = self._resolve_uncertainties(
                headers,
                data_rows,
                sigma_rows,
                target_column,
                None,
            )
            weights = None
            if self.fit_weighted_checkbox.isChecked():
                weights = self._build_weight_vector(sigma_series)
            variable_data = {
                var: self._column_series(headers, data_rows, column)
                for var, column in variable_map.items()
            }
            model_expr = self.fit_expr_edit.toPlainText().strip()
            parameter_config = self._collect_parameter_config(allow_empty=False)
            parameter_names = self._infer_parameter_names(
                model_expr, list(variable_map.keys()), list(parameter_config.keys())
            )
            precision = self._read_precision()
            if verbose:
                print(f"[fit] custom model: expr={model_expr} target={target_column} variables={variable_map}")
                print(f"[fit] n_points={len(target_series)} precision={precision}")
                print(f"[fit] initial_params={parameter_config}")
            with _mp_precision_guard(precision):
                self._set_fit_output_precision(precision)
                model_spec = build_model_specification(
                    model_expr, list(variable_map.keys()), parameter_names
                )
                parameter_state = build_parameter_state(parameter_config, parameter_names)
                fit_result = fit_custom_model(
                    model_spec,
                    parameter_state,
                    variable_data,
                    target_series,
                    precision=precision,
                    weights=weights,
                    data_sigmas=sigma_series,
                )
            if verbose:
                print(f"[fit] params={fit_result.params}")
                print(f"[fit] chi2={fit_result.chi2} reduced_chi2={fit_result.reduced_chi2} r2={fit_result.r2}")
            substituted = self._build_substituted_expression(model_expr, fit_result.params)
            fit_result.details["expression"] = model_expr
            fit_result.details["substituted_expression"] = substituted
            summary = self._format_fit_result_text(fit_result, model_expr, substituted)
            self._set_result_text(summary)
            tag = f"{batch_tag} " if batch_tag else ""
            self._append_log(tag + "自定义拟合完成。")
            warning_detail = fit_result.details.get("boundary_warning")
            if warning_detail:
                self._append_log(warning_detail)
            is_multidim = len(variable_map) > 1
            if not variable_map:
                primary_var = "x"
                x_values = []
            else:
                primary_var = next(iter(variable_map.keys()))
                x_values = [float(val) for val in variable_data.get(primary_var, [])]
            y_values = [] if is_multidim else [float(val) for val in target_series]
            fitted, residuals = ([], []) if is_multidim else self._build_standard_plot_series(fit_result)
            comparison_data = [
                (
                    model_expr or "自定义",
                    float(fit_result.aic),
                    float(fit_result.bic),
                    float(fit_result.r2),
                )
            ]
            parameter_info = (
                model_expr or "自定义",
                fit_result.params,
                fit_result.param_errors_total or fit_result.param_errors,
            )
            uncertainties = (
                [float(s) if s is not None else 0.0 for s in sigma_series]
                if (sigma_series and not is_multidim)
                else None
            )
            log_scale = self._sanitize_log_scale(self._current_log_scale(), x_values, y_values)
            plot_data = render_fitting_overview(
                x_values,
                y_values,
                [] if is_multidim else [(model_expr or "拟合", fitted)],
                [] if is_multidim else [(model_expr or "拟合", residuals)],
                comparison=comparison_data,
                parameter_info=parameter_info,
                uncertainties=uncertainties,
                show_curves=not is_multidim,
                log_scale=log_scale,
            )
            self._image_mode = "fit"
            self.current_fit_figures = []
            self.current_fit_index = 0
            self._update_result_plot(plot_data)
            plot_job = SimpleNamespace(
                model_type="custom",
                poly_degree=0,
                inverse_min=1,
                inverse_max=1,
                auto_identifier=None,
                is_multidim=is_multidim,
                label=model_expr or "custom",
                x_series=variable_data.get(primary_var, []),
                y_series=target_series,
                sigma_series=sigma_series,
                render_plots=True,
            )
            self._remember_last_result(
                "fit_single",
                {"fit_result": fit_result, "expression": model_expr, "substituted": substituted, "job": plot_job},
            )
            if generate_latex and output_path:
                self._write_fitting_latex(
                    headers,
                    data_rows,
                    sigma_rows,
                    fit_result,
                    model_expr,
                    substituted,
                    plot_data,
                    output_path,
                    self.dcolumn_checkbox.isChecked(),
                )
            self.tabs.setCurrentIndex(self.result_tab_index)
            return summary
        except Exception as exc:
            localized = self._localize_text(str(exc))
            QMessageBox.critical(
                self,
                self._tr("自定义拟合失败", "Custom Fit Failed"),
                localized
            )
            log_msg = self._tr(f"自定义拟合失败: {localized}", f"Custom fit failed: {localized}")
            self._append_log(log_msg)
            return None

    def _run_linear_definition_fit(
        self,
        definition: AutoModelDefinition,
        headers: list[str],
        data_rows: list[tuple[mp.mpf, ...]],
        sigma_rows: list[tuple[mp.mpf | None, ...]],
        x_series: list[mp.mpf],
        y_series: list[mp.mpf],
        sigma_series: list[mp.mpf | None],
        weights: list[mp.mpf] | None,
        generate_latex: bool,
        output_path: str,
    ):
        fit_result = fit_linear_model(
            definition,
            x_series,
            y_series,
            precision=self._current_precision,
            weights=weights,
            data_sigmas=sigma_series,
        )
        expression = fit_result.details.get("expression")
        substituted = (
            self._build_substituted_expression(expression, fit_result.params)
            if expression
            else None
        )
        summary = self._format_fit_result_text(fit_result, expression, substituted)
        self._set_result_text(summary)
        self._append_log(f"{definition.label} 拟合完成。")
        warning_detail = fit_result.details.get("boundary_warning")
        if warning_detail:
            self._append_log(warning_detail)
        x_values = [float(val) for val in x_series]
        y_values = [float(val) for val in y_series]
        fitted_curve, residuals = self._build_linear_plot_series(
            definition, fit_result, x_series, y_series
        )
        comparison_data = [
            (
                definition.label,
                float(fit_result.aic),
                float(fit_result.bic),
                float(fit_result.r2),
            )
        ]
        parameter_info = (
            definition.label,
            fit_result.params,
            fit_result.param_errors_total or fit_result.param_errors,
        )
        uncertainties = (
            [float(s) if s is not None else 0.0 for s in sigma_series] if sigma_series else None
        )
        log_scale = self._sanitize_log_scale(self._current_log_scale(), x_series, y_series)
        plot_data = render_fitting_overview(
            x_values,
            y_values,
            [(definition.label, fitted_curve)],
            [(definition.label, residuals)],
            comparison=comparison_data,
            parameter_info=parameter_info,
            uncertainties=uncertainties,
            log_scale=log_scale,
        )
        self._image_mode = "fit"
        self.current_fit_figures = []
        self.current_fit_index = 0
        self._update_result_plot(plot_data)
        plot_job = SimpleNamespace(
            model_type="auto",
            poly_degree=0,
            inverse_min=1,
            inverse_max=1,
            auto_identifier=getattr(definition, "identifier", None),
            is_multidim=False,
            label=definition.label,
            x_series=x_series,
            y_series=y_series,
            sigma_series=sigma_series,
            render_plots=True,
        )
        self._remember_last_result(
            "fit_single",
            {"fit_result": fit_result, "expression": expression, "substituted": substituted, "job": plot_job},
        )
        if generate_latex and output_path:
            self._write_fitting_latex(
                headers,
                data_rows,
                sigma_rows,
                fit_result,
                expression or "",
                substituted or "",
                plot_data,
                output_path,
                self.dcolumn_checkbox.isChecked(),
            )
        self.tabs.setCurrentIndex(self.result_tab_index)

    def _execute_custom_polynomial_model(
        self,
        dataset: tuple[list[str], list[tuple[mp.mpf, ...]], list[tuple[mp.mpf | None, ...]]],
        generate_latex: bool,
        output_path: str,
        batch_tag: str = "",
    ):
        try:
            headers, data_rows, sigma_rows, x_series, y_series, sigma_series, weights = self._prepare_linear_fit_inputs(*dataset)
            precision = self._read_precision()
            with _mp_precision_guard(precision):
                self._set_fit_output_precision(precision)
                degree = self.poly_degree_spin.value()
                definition = build_polynomial_definition(degree)
                self._run_linear_definition_fit(
                    definition, headers, data_rows, sigma_rows, x_series, y_series, sigma_series, weights, generate_latex, output_path
                )
            if batch_tag:
                log_msg = self._tr(f"{batch_tag} 多项式拟合完成。", f"{batch_tag} Polynomial fit completed.")
                self._append_log(log_msg)
        except Exception as exc:
            localized = self._localize_text(str(exc))
            QMessageBox.critical(
                self,
                self._tr("多项式拟合失败", "Polynomial Fit Failed"),
                localized
            )
            log_msg = self._tr(f"多项式拟合失败: {localized}", f"Polynomial fit failed: {localized}")
            self._append_log(log_msg)

    def _execute_inverse_model(
        self,
        dataset: tuple[list[str], list[tuple[mp.mpf, ...]], list[tuple[mp.mpf | None, ...]]],
        generate_latex: bool,
        output_path: str,
        batch_tag: str = "",
    ):
        try:
            headers, data_rows, sigma_rows, x_series, y_series, sigma_series, weights = self._prepare_linear_fit_inputs(*dataset)
            precision = self._read_precision()
            with _mp_precision_guard(precision):
                self._set_fit_output_precision(precision)
                definition = build_inverse_series_definition(*self._inverse_power_range())
                self._run_linear_definition_fit(
                    definition, headers, data_rows, sigma_rows, x_series, y_series, sigma_series, weights, generate_latex, output_path
                )
            if batch_tag:
                log_msg = self._tr(f"{batch_tag} 1/x^p 拟合完成。", f"{batch_tag} 1/x^p fit completed.")
                self._append_log(log_msg)
        except Exception as exc:
            localized = self._localize_text(str(exc))
            QMessageBox.critical(
                self,
                self._tr("1/x^p 拟合失败", "1/x^p Fit Failed"),
                localized
            )
            log_msg = self._tr(f"1/x^p 拟合失败: {localized}", f"1/x^p fit failed: {localized}")
            self._append_log(log_msg)

    def _execute_linear_named_model(self, identifier: str, label: str, dataset, generate_latex: bool, output_path: str, batch_tag: str = ""):
        definition = self._auto_model_map.get(identifier)
        if not definition:
            raise ValueError(
                _dual_msg(
                    f"未找到模型 {label} ({identifier})。",
                    f"Model not found: {label} ({identifier}).",
                )
            )
        headers, data_rows, sigma_rows, x_series, y_series, sigma_series, weights = self._prepare_linear_fit_inputs(*dataset)
        precision = self._read_precision()
        with _mp_precision_guard(precision):
            self._set_fit_output_precision(precision)
            self._run_linear_definition_fit(
                definition, headers, data_rows, sigma_rows, x_series, y_series, sigma_series, weights, generate_latex, output_path
            )
        if batch_tag:
            self._append_log(f"{batch_tag} {label} 完成。")

    def _execute_template_custom_fit(self, template: str, label: str, dataset, generate_latex: bool, output_path: str, batch_tag: str = ""):
        try:
            headers, data_rows, sigma_rows, x_series, y_series, sigma_series, weights = self._prepare_linear_fit_inputs(*dataset)
            precision = self._read_precision()
            with _mp_precision_guard(precision):
                self._set_fit_output_precision(precision)
                if template == "power_limit":
                    payload = self._power_limit_template()
                elif template == "pade":
                    payload = self._pade_template(self.pade_m_spin.value(), self.pade_n_spin.value())
                else:
                    payload = None
                if not payload:
                    raise ValueError(
                        _dual_msg(
                            "无法生成预设模型。",
                            "Could not generate the preset model.",
                        )
                    )
                expr, params = payload
                spec, state = self._build_spec_state(expr, params)
                fit_result = fit_custom_model(
                    spec,
                    state,
                    {"x": x_series},
                    y_series,
                    precision=precision,
                    weights=weights,
                    data_sigmas=sigma_series,
                )
            substituted = self._build_substituted_expression(expr, fit_result.params)
            fit_result.details["expression"] = expr
            fit_result.details["substituted_expression"] = substituted
            summary = self._format_fit_result_text(fit_result, expr, substituted)
            self._set_result_text(summary)
            tag = f"{batch_tag} " if batch_tag else ""
            self._append_log(f"{tag}{label} 拟合完成。")
            warning_detail = fit_result.details.get("boundary_warning")
            if warning_detail:
                self._append_log(warning_detail)
            x_values = [float(val) for val in x_series]
            y_values = [float(val) for val in y_series]
            fitted, residuals = self._build_standard_plot_series(fit_result)
            comparison_data = [
                (
                    label,
                    float(fit_result.aic),
                    float(fit_result.bic),
                    float(fit_result.r2),
                )
            ]
            parameter_info = (
                label,
                fit_result.params,
                fit_result.param_errors_total or fit_result.param_errors,
            )
            uncertainties = [float(s) if s is not None else 0.0 for s in sigma_series] if sigma_series else None
            log_scale = self._sanitize_log_scale(self._current_log_scale(), x_series, y_series)
            plot_data = render_fitting_overview(
                x_values,
                y_values,
                [(label, fitted)],
                [(label, residuals)],
                comparison=comparison_data,
                parameter_info=parameter_info,
                uncertainties=uncertainties,
                log_scale=log_scale,
            )
            self._image_mode = "fit"
            self.current_fit_figures = []
            self.current_fit_index = 0
            self._update_result_plot(plot_data)
            plot_job = SimpleNamespace(
                model_type="custom",
                poly_degree=0,
                inverse_min=1,
                inverse_max=1,
                auto_identifier=None,
                is_multidim=False,
                label=label,
                x_series=x_series,
                y_series=y_series,
                sigma_series=sigma_series,
                render_plots=True,
            )
            self._remember_last_result(
                "fit_single",
                {"fit_result": fit_result, "expression": expr, "substituted": substituted, "job": plot_job},
            )
            if generate_latex and output_path:
                self._write_fitting_latex(
                    headers,
                    data_rows,
                    sigma_rows,
                    fit_result,
                    expr,
                    substituted,
                    plot_data,
                    output_path,
                    self.dcolumn_checkbox.isChecked(),
                )
            self.tabs.setCurrentIndex(self.result_tab_index)
        except Exception as exc:
            title_zh = f"{label} 拟合失败"
            title_en = f"{label} Fit Failed"
            localized = self._localize_text(str(exc))
            QMessageBox.critical(
                self,
                self._tr(title_zh, title_en),
                localized
            )
            log_msg = self._tr(f"{label} 拟合失败: {localized}", f"{label} fit failed: {localized}")
            self._append_log(log_msg)

    def _execute_power_limit_model(self, dataset, generate_latex: bool, output_path: str, batch_tag: str = ""):
        self._execute_template_custom_fit("power_limit", "幂律极限模型", dataset, generate_latex, output_path, batch_tag=batch_tag)

    def _execute_pade_model(self, dataset, generate_latex: bool, output_path: str, batch_tag: str = ""):
        self._execute_template_custom_fit("pade", "Padé 拟合", dataset, generate_latex, output_path, batch_tag=batch_tag)

    def _execute_auto_fit(self, dataset, generate_latex: bool, output_path: str, batch_tag: str = ""):
        try:
            verbose_mode = self.verbose_checkbox.isChecked()
            job = self._prepare_auto_fit_job(dataset, verbose_mode)
            with _mp_precision_guard(job.precision):
                summary = auto_fit_dataset(
                    job.x_series,
                    job.y_series,
                    precision=job.precision,
                    custom_entries=job.custom_entries or None,
                    extra_models=job.extra_models,
                    weights=job.weights,
                    data_sigmas=job.sigma_series,
                )
            self._render_auto_fit_summary(
                summary,
                job.headers,
                job.data_rows,
                job.sigma_rows,
                job.x_series,
                job.y_series,
                job.sigma_series,
                job.weights,
                generate_latex,
                output_path,
                job.extra_models,
                verbose_mode,
                job_obj=job,
                render_plots=job.render_plots,
            )
        except Exception as exc:
            localized = self._localize_text(str(exc))
            QMessageBox.critical(self, self._tr("自动拟合失败", "Auto fit failed"), localized)
            self._append_log(self._tr(f"自动拟合失败: {localized}", f"Auto fit failed: {localized}"))

    def _render_auto_fit_summary(
        self,
        summary,
        headers: list[str],
        data_rows: list[tuple[mp.mpf, ...]],
        sigma_rows: list[tuple[mp.mpf | None, ...]],
        x_series: list[mp.mpf],
        y_series: list[mp.mpf],
        sigma_series: list[mp.mpf | None],
        weights: list[mp.mpf] | None,
        generate_latex: bool,
        output_path: str,
        extra_models: list[AutoModelDefinition],
        verbose_mode: bool,
        job_obj=None,
        return_payload: bool = False,
        render_plots: bool = True,
    ):
        """Render the auto-fit summary and plots on the main thread."""
        cached_payload = {
            "summary": summary,
            "headers": headers,
            "data_rows": data_rows,
            "sigma_rows": sigma_rows,
            "x_series": x_series,
            "y_series": y_series,
            "sigma_series": sigma_series,
            "weights": weights,
            # Re-rendering should not regenerate LaTeX or plots
            "generate_latex": False,
            "output_path": "",
            "extra_models": extra_models,
            "verbose_mode": verbose_mode,
            "job": job_obj,
        }

        def _translate_error(err: str) -> str:
            if not err:
                return "unknown"
            return self._localize_text(err)

        comparison_rows: list[tuple[str, float, float, float]] = []
        detail_lines: list[str] = []
        used_labels: set[str] = set()
        extra_model_map = {definition.identifier: definition for definition in extra_models}
        for entry in summary.results:
            raw_label = entry.label or ""
            lbl = self._localize_label(raw_label)
            if (not lbl or len(lbl.strip()) <= 1) and getattr(entry, "identifier", None):
                lbl = entry.identifier
            if lbl in used_labels:
                lbl = f"{lbl}#{len(used_labels)+1}"
            used_labels.add(lbl)
            if entry.success and entry.fit_result:
                comparison_rows.append(
                    (
                        lbl,
                        float(entry.fit_result.aic),
                        float(entry.fit_result.bic),
                        float(entry.fit_result.r2),
                    )
                )
                detail_lines.append(
                    self._tr(
                        f"{lbl}: 成功，AIC={self._format_display_value(entry.fit_result.aic)}, BIC={self._format_display_value(entry.fit_result.bic)}, R²={self._format_display_value(entry.fit_result.r2)}",
                        f"{lbl}: success, AIC={self._format_display_value(entry.fit_result.aic)}, BIC={self._format_display_value(entry.fit_result.bic)}, R²={self._format_display_value(entry.fit_result.r2)}",
                    )
                )
            else:
                err = _translate_error(entry.error or "unknown")
                detail_lines.append(self._tr(f"{lbl}: 失败 ({err})", f"{lbl}: failed ({err})"))

        text_lines = detail_lines[:] if detail_lines else [summarize_auto_results(summary.results)]
        if comparison_rows:
            try:
                sorted_comp = sorted(comparison_rows, key=lambda t: t[1])
            except Exception:
                sorted_comp = comparison_rows
            text_lines.append(self._tr("模型比较 (AIC/BIC/R²)：", "Model comparison (AIC/BIC/R²):"))
            for idx, (name, aic, bic, r2) in enumerate(sorted_comp):
                marker = "*" if idx == 0 else " "
                text_lines.append(
                    f"{marker} {name}: AIC={self._format_display_value(aic)}, BIC={self._format_display_value(bic)}, R²={self._format_display_value(r2)}"
                )
        text = "\n".join(text_lines)
        best = summary.best()
        render = AutoFitRenderResult(text=text, plot_bytes=None, fit_result=None, expression=None, substituted=None)
        if best and best.fit_result:
            expression = best.fit_result.details.get("expression")
            substituted = (
                self._build_substituted_expression(expression, best.fit_result.params)
                if expression
                else None
            )
            with _mp_precision_guard(self._current_precision):
                best_text = self._format_fit_result_text(best.fit_result, expression, substituted)
            best_label = self._localize_label(best.label)
            if (not best_label or len(best_label.strip()) <= 1) and getattr(best, "identifier", None):
                best_label = best.identifier
            text = text + "\n\n" + self._tr(f"最佳模型: {best_label}", f"Best model: {best_label}") + "\n" + best_text
            log_scale = self._sanitize_log_scale(self._current_log_scale(), x_series, y_series)
            plot_job = SimpleNamespace(
                model_type="auto",
                poly_degree=0,
                inverse_min=1,
                inverse_max=1,
                auto_identifier=getattr(best, "identifier", None),
                is_multidim=False,
                label=best_label,
                x_series=x_series,
                y_series=y_series,
                sigma_series=sigma_series,
                render_plots=render_plots,
            )
            cached_payload["job"] = plot_job
            render = AutoFitRenderResult(
                text=text,
                plot_bytes=None,
                fit_result=best.fit_result,
                expression=expression or "",
                substituted=substituted or "",
            )
            plot_data = None
            if render_plots:
                plot_data = self._render_fit_plot_bytes(plot_job, best.fit_result, comparison=comparison_rows, log_scale=log_scale)
            cached_payload.update(
                {
                    "fit_result": best.fit_result,
                    "expression": expression or "",
                    "substituted": substituted or "",
                    "job": plot_job,
                }
            )
            if return_payload:
                return AutoFitRenderResult(
                    text=text,
                    plot_bytes=plot_data,
                    fit_result=best.fit_result,
                    expression=expression or "",
                    substituted=substituted or "",
                )
            self._set_result_text(text)
            csv_rows = self._build_fit_csv_rows(best.fit_result, expression, batch_idx=1)
            if csv_rows:
                self._set_csv_data(
                    csv_rows,
                    ["batch", "section", "name", "value", "uncertainty", "stat_error", "sys_error", "note"],
                    suggestion="fitting_results.csv",
                )
            else:
                self._reset_csv_data()
            warning_detail = best.fit_result.details.get("boundary_warning")
            if warning_detail:
                self._append_log(warning_detail)
            if plot_data:
                self._image_mode = "fit"
                self.current_fit_figures = []
                self.current_fit_index = 0
                self._update_result_plot(plot_data)
            if generate_latex and output_path:
                self._write_fitting_latex(
                    headers,
                    data_rows,
                    sigma_rows,
                    best.fit_result,
                    expression or "",
                    substituted or "",
                    plot_data if render_plots else None,
                    output_path,
                    self.dcolumn_checkbox.isChecked(),
                )
        else:
            if return_payload:
                return render
            self._set_result_text(text)
        if not return_payload:
            self._remember_last_result("fit_auto", cached_payload)
        self._set_result_text(text)
        log_message = text if verbose_mode else self._tr("自动模型选择完成。", "Auto model selection finished.")
        if not return_payload:
            self._append_log(log_message)
            self.tabs.setCurrentIndex(self.result_tab_index)
            QMessageBox.information(self, self._tr("完成", "Done"), self._tr("自动拟合完成。", "Auto fit completed."))
        return render

    def _prepare_auto_fit_job(self, dataset, verbose: bool = False) -> AutoFitJob:
        headers, data_rows, sigma_rows, x_series, y_series, sigma_series, weights = self._prepare_linear_fit_inputs(*dataset)
        precision = self._read_precision()
        self._current_precision = precision
        self._set_fit_output_precision(precision)
        custom_entries: list[tuple[str, Any, Any]] = []
        parameter_config: dict[str, object] = {}
        param_text = self.fit_param_edit.toPlainText().strip()
        if param_text:
            try:
                parameter_config = json.loads(param_text)
                if not isinstance(parameter_config, dict):
                    warning = self._tr(
                        "参数配置必须是 JSON 对象（键值对），已忽略该配置。",
                        "Parameter config must be a JSON object (key-value pairs); ignoring it.",
                    )
                    QMessageBox.warning(self, self._tr("参数错误", "Parameter error"), warning)
                    self._append_log(warning)
                    parameter_config = {}
            except json.JSONDecodeError as exc:
                warning = self._tr(
                    "参数配置格式有误，请检查 JSON 格式。",
                    "Parameter configuration JSON is invalid. Please fix the format.",
                )
                QMessageBox.warning(self, self._tr("参数错误", "Parameter error"), warning)
                self._append_log(f"{warning} ({exc})")
                parameter_config = {}
        model_expr = self.fit_expr_edit.toPlainText().strip()
        if model_expr:
            parameter_names = self._infer_parameter_names(
                model_expr, ["x"], list(parameter_config.keys())
            )
            spec = build_model_specification(model_expr, ["x"], parameter_names)
            state = build_parameter_state(parameter_config, parameter_names)
            custom_entries.append(("自定义模型", spec, state))
        custom_entries.extend(self._default_auto_custom_entries())
        extra_models = self._default_auto_linear_definitions()
        return AutoFitJob(
            headers=headers,
            data_rows=data_rows,
            sigma_rows=sigma_rows,
            x_series=x_series,
            y_series=y_series,
            sigma_series=sigma_series,
            weights=weights,
            precision=precision,
            custom_entries=custom_entries,
            extra_models=extra_models,
            verbose=verbose,
            render_plots=self.generate_plots_checkbox.isChecked() if hasattr(self, "generate_plots_checkbox") else True,
            refine_with_mcmc=(
                self.fit_mcmc_refine.isChecked()
                if hasattr(self, "fit_mcmc_refine")
                and self.fit_mcmc_refine.isEnabled()
                else False
            ),
        )

    def _prepare_fit_job(self, dataset, generate_latex: bool, output_path: str, verbose: bool, render_plots: bool = True) -> FitJob:
        headers, data_rows, sigma_rows, x_series, y_series, sigma_series, weights = self._prepare_linear_fit_inputs(*dataset)
        precision = self._read_precision()
        self._current_precision = precision
        self._set_fit_output_precision(precision)
        variable_map = self._collect_variable_mapping(headers)
        target_column = self.fit_target_edit.text().strip()
        variable_data = {var: self._column_series(headers, data_rows, col) for var, col in variable_map.items()}
        target_series = self._column_series(headers, data_rows, target_column)
        model_type = self.fit_model_combo.currentData()
        model_expr = self.fit_expr_edit.toPlainText().strip()
        parameter_config: dict = {}
        parameter_names: list[str] = []
        template_expr: str | None = None
        template_params: dict | None = None
        label = self._localize_label(self.fit_model_combo.currentText())
        is_multidim = len(variable_map) > 1
        job_kwargs: dict[str, object] = {}
        if model_type == "custom":
            parameter_config = self._collect_parameter_config(allow_empty=False)
            parameter_names = self._infer_parameter_names(model_expr, list(variable_map.keys()), list(parameter_config.keys()))
        elif model_type == "poly":
            job_kwargs["poly_degree"] = self.poly_degree_spin.value()
            model_expr = self._mode_expression_preview("poly")
        elif model_type == "inverse":
            inv_min, inv_max = self._inverse_power_range()
            job_kwargs["inverse_min"] = inv_min
            job_kwargs["inverse_max"] = inv_max
            model_expr = self._mode_expression_preview("inverse")
        elif model_type == "pade":
            job_kwargs["pade_m"] = self.pade_m_spin.value()
            job_kwargs["pade_n"] = self.pade_n_spin.value()
            payload = self._pade_template(self.pade_m_spin.value(), self.pade_n_spin.value())
            if payload:
                template_expr, template_params = payload
                model_expr = template_expr
        elif model_type == "power_limit":
            template_expr, template_params = self._power_limit_template()
            model_expr = template_expr
        elif model_type in {"log_poly", "exp_combo"}:
            job_kwargs["auto_identifier"] = "M4B" if model_type == "log_poly" else "M7B"
            model_expr = self._mode_expression_preview(model_type)
        else:
            # fallback to custom
            parameter_config = self._collect_parameter_config(allow_empty=False)
            parameter_names = self._infer_parameter_names(model_expr, list(variable_map.keys()), list(parameter_config.keys()))
        return FitJob(
            model_type=model_type,
            headers=headers,
            data_rows=data_rows,
            sigma_rows=sigma_rows,
            x_series=x_series,
            y_series=y_series,
            sigma_series=sigma_series,
            weights=weights,
            variable_map=variable_map,
            variable_data=variable_data,
            target_series=target_series,
            target_column=target_column,
            model_expr=model_expr,
            parameter_config=parameter_config,
            parameter_names=parameter_names,
            template_expr=template_expr,
            template_params=template_params,
            precision=precision,
            generate_latex=generate_latex,
            output_path=output_path,
            use_dcolumn=self.dcolumn_checkbox.isChecked(),
            caption=self._caption_value(),
            verbose=verbose,
            render_plots=render_plots,
            latex_digits=self.latex_input_precision_spin.value(),
            weighted=self.fit_weighted_checkbox.isChecked(),
            label=label,
            is_multidim=is_multidim,
            **job_kwargs,
        )

    def _execute_fit_async(self, job: FitJob):
        if self._fit_worker and self._fit_worker.isRunning():
            QMessageBox.information(self, self._tr("提示", "Notice"), self._tr("拟合正在运行中。", "Fitting already running."))
            return
        worker = FitWorker(job)
        worker.finished_ok.connect(self._on_fit_finished)
        worker.failed.connect(self._on_fit_failed)
        worker.finished.connect(self._on_fit_thread_done)
        worker.cancelled.connect(self._on_worker_cancelled)
        if getattr(job, "verbose", False):
            worker.log_ready.connect(self._append_log)
        self._fit_worker = worker
        self._set_button_to_stop_mode()
        worker.start()
        self._append_log(self._tr("拟合已在后台运行…", "Fit running in background…"))

    def _render_fit_plot_bytes(self, job: FitJob, fit_result: FitResult, comparison=None, log_scale: str | None = None) -> bytes | None:
        x_values = [float(v) for v in job.x_series]
        y_values = [float(v) for v in job.y_series]
        show_curves = not job.is_multidim
        try:
            # Validate log-scale selection against current data to avoid log(<=0) failures
            safe_log_scale = self._sanitize_log_scale(log_scale if log_scale is not None else self._current_log_scale(), job.x_series, job.y_series)
            if show_curves:
                if job.model_type in {"poly", "inverse", "log_poly", "exp_combo"}:
                    if job.model_type == "poly":
                        definition = build_polynomial_definition(job.poly_degree)
                    elif job.model_type == "inverse":
                        definition = build_inverse_series_definition(job.inverse_min, job.inverse_max)
                    else:
                        identifier = job.auto_identifier or ("M4B" if job.model_type == "log_poly" else "M7B")
                        definition = next((d for d in AUTO_MODELS if d.identifier == identifier), None)
                    if definition:
                        fitted_curve, residuals = self._build_linear_plot_series(definition, fit_result, job.x_series, job.y_series)
                    else:
                        fitted_curve, residuals = self._build_standard_plot_series(fit_result)
                else:
                    fitted_curve, residuals = self._build_standard_plot_series(fit_result)
                uncertainties = [float(s) if s is not None else 0.0 for s in job.sigma_series] if job.sigma_series else None
                parameter_info = (
                    job.label or job.model_expr or "model",
                    fit_result.params,
                    fit_result.param_errors_total or fit_result.param_errors,
                )
                return render_fitting_overview(
                    x_values,
                    y_values,
                    [(job.label or "fit", fitted_curve)],
                    [(job.label or "fit", residuals)],
                    comparison=comparison,
                    parameter_info=parameter_info,
                    uncertainties=uncertainties,
                    log_scale=safe_log_scale,
                )
            residuals = fit_result.residuals
            return render_fitting_overview(
                x_values,
                y_values,
                [],
                [(job.label or "fit", residuals)],
                comparison=comparison,
                parameter_info=(
                    job.label or "fit",
                    fit_result.params,
                    fit_result.param_errors_total or fit_result.param_errors,
                ),
                uncertainties=None,
                log_scale=safe_log_scale,
                show_curves=False,
            )
        except Exception as exc:  # noqa: BLE001
            self._append_log(self._tr(f"生成拟合图像失败: {exc}", f"Failed to render fit plot: {exc}"))
            return None

    def _refresh_fit_plot_log_scale(self):
        """Re-render existing fit plots with the current log-scale selection (display-only)."""
        if not self._is_fit_mode_active():
            return
        kind = getattr(self, "_last_result_kind", None)
        payloads = getattr(self, "_last_result_payloads", {}) or {}
        if not kind or kind not in payloads:
            return
        log_scale = self._current_log_scale()
        if kind == "fit_single":
            payload = payloads[kind]
            job = payload.get("job")
            fit_result = payload.get("fit_result")
            if job and fit_result and getattr(job, "render_plots", True):
                plot_bytes = self._render_fit_plot_bytes(job, fit_result, log_scale=log_scale)
                if plot_bytes:
                    self._image_mode = "fit"
                    self._update_result_plot(plot_bytes)
        elif kind == "fit_auto":
            payload = payloads[kind]
            job = payload.get("job")
            fit_result = payload.get("fit_result")
            if job and fit_result and getattr(job, "render_plots", True):
                plot_bytes = self._render_fit_plot_bytes(job, fit_result, log_scale=log_scale)
                if plot_bytes:
                    self._image_mode = "fit"
                    self._update_result_plot(plot_bytes)
        elif kind == "fit_batches":
            self._rebuild_fit_batch_plots(log_scale)

    def _rebuild_fit_batch_plots(self, log_scale: str | None):
        payloads = getattr(self, "_last_result_payloads", {}) or {}
        payload = payloads.get("fit_batches")
        if not payload:
            return
        entries = payload.get("entries") or []
        ctx = payload.get("context", {}) or {}
        figure_paths: list[Path] = []
        self._cleanup_temp_batch_images()
        for entry in sorted(entries, key=lambda e: e.index):
            if entry.kind == "fit" and entry.fit_payload:
                job = entry.fit_payload.job
                fit_res = entry.fit_payload.fit_result
                if job and fit_res and getattr(job, "render_plots", True):
                    plot_bytes = self._render_fit_plot_bytes(job, fit_res, log_scale=log_scale)
                    if plot_bytes:
                        path = self._save_batch_figure(plot_bytes, ctx.get("output_path", ""), entry.index, "fit")
                        if path:
                            figure_paths.append(path)
            elif entry.kind == "auto" and entry.auto_payload:
                summary_obj, job = entry.auto_payload
                render = self._render_auto_fit_summary(
                    summary_obj,
                    job.headers,
                    job.data_rows,
                    job.sigma_rows,
                    job.x_series,
                    job.y_series,
                    job.sigma_series,
                    job.weights,
                    False,
                    "",
                    job.extra_models if hasattr(job, "extra_models") else [],
                    ctx.get("verbose", False),
                    return_payload=True,
                    render_plots=False,
                    job_obj=job,
                )
                if render.fit_result and getattr(job, "render_plots", True):
                    job_for_plot = SimpleNamespace(
                        model_type="auto",
                        poly_degree=0,
                        inverse_min=1,
                        inverse_max=1,
                        auto_identifier=None,
                        is_multidim=False,
                        label=f"fit#{entry.index}",
                        x_series=job.x_series,
                        y_series=job.y_series,
                        sigma_series=job.sigma_series,
                        render_plots=job.render_plots,
                    )
                    plot_bytes = self._render_fit_plot_bytes(job_for_plot, render.fit_result, log_scale=log_scale)
                    if plot_bytes:
                        path = self._save_batch_figure(plot_bytes, ctx.get("output_path", ""), entry.index, "fit")
                        if path:
                            figure_paths.append(path)
        if figure_paths:
            self._set_image_list("fit", figure_paths)
        else:
            self.current_fit_figures = []
            self.current_fit_index = 0
            self.result_plot_bytes = None
            self._result_plot_base_pixmap = None
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self._update_image_status()

    def _on_fit_batches_finished(self, entries: list[FitBatchResultEntry]):
        ctx = self._fit_batch_context or {}
        generate_latex = bool(ctx.get("generate_latex"))
        output_path = ctx.get("output_path", "")
        use_dcolumn = bool(ctx.get("use_dcolumn", True))
        # 清理上一次生成的临时批次图像，避免累积
        self._cleanup_temp_batch_images()
        batch_texts: list[str] = []
        figure_paths: list[Path] = []
        latex_batches: list[dict] = []
        csv_rows: list[dict[str, object]] = []
        for entry in sorted(entries, key=lambda e: e.index):
            if ctx.get("verbose") and entry.captured_log:
                self._append_log(entry.captured_log)
            header = self._tr(f"=== 拟合结果：批次 {entry.index} ===", f"=== Fit Result: Batch {entry.index} ===")
            if entry.error:
                batch_texts.append(header + "\n" + self._tr(f"批次 {entry.index} 失败: {entry.error}", f"Batch {entry.index} failed: {entry.error}"))
                continue
            if entry.kind == "fit" and entry.fit_payload:
                payload = entry.fit_payload
                job = payload.job
                expression = payload.expression or job.model_expr
                substituted = self._build_substituted_expression(expression, payload.fit_result.params) if expression else ""
                summary = self._format_fit_result_text(payload.fit_result, expression, substituted)
                batch_texts.append(header + "\n" + summary)
                plot_bytes = self._render_fit_plot_bytes(job, payload.fit_result) if getattr(job, "render_plots", True) else None
                fig_path = self._save_batch_figure(plot_bytes, output_path, entry.index, "fit") if plot_bytes else None
                if fig_path:
                    figure_paths.append(fig_path)
                latex_batches.append(
                    {
                        "index": entry.index,
                        "headers": job.headers,
                        "rows": job.data_rows,
                        "sigma_rows": job.sigma_rows,
                        "fit_result": payload.fit_result,
                        "expression": expression or "",
                        "substituted": substituted or "",
                        "figure_path": fig_path,
                    }
                )
                csv_rows.extend(
                    self._build_fit_csv_rows(
                        payload.fit_result,
                        expression or "",
                        batch_idx=entry.index,
                    )
                )
            elif entry.kind == "auto" and entry.auto_payload:
                summary_obj, job = entry.auto_payload
                render = self._render_auto_fit_summary(
                    summary_obj,
                    job.headers,
                    job.data_rows,
                    job.sigma_rows,
                    job.x_series,
                    job.y_series,
                    job.sigma_series,
                    job.weights,
                    False,
                    "",
                    job.extra_models,
                    self.verbose_checkbox.isChecked(),
                    return_payload=True,
                    render_plots=job.render_plots,
                )
                batch_texts.append(header + "\n" + render.text)
                fig_path = self._save_batch_figure(render.plot_bytes, output_path, entry.index, "fit") if render.plot_bytes else None
                if fig_path:
                    figure_paths.append(fig_path)
                    if render.fit_result:
                        latex_batches.append(
                            {
                                "index": entry.index,
                                "headers": job.headers,
                            "rows": job.data_rows,
                            "sigma_rows": job.sigma_rows,
                            "fit_result": render.fit_result,
                            "expression": render.expression or "",
                            "substituted": render.substituted or "",
                                "figure_path": fig_path,
                            }
                        )
                        csv_rows.extend(
                            self._build_fit_csv_rows(
                                render.fit_result,
                                render.expression or "",
                                batch_idx=entry.index,
                            )
                        )
            else:
                batch_texts.append(header + "\n" + self._tr("未获得该批次结果。", "No result for this batch."))
        combined = "\n\n".join(batch_texts)
        self._set_result_text(combined)
        self._set_image_list("fit", figure_paths)
        if csv_rows:
            self._set_csv_data(
                csv_rows,
                ["batch", "section", "name", "value", "uncertainty", "stat_error", "sys_error", "note"],
                suggestion="fitting_results.csv",
            )
        else:
            self._reset_csv_data()
        if generate_latex and output_path and latex_batches:
            self._write_fitting_latex_batches(
                latex_batches,
                output_path,
                use_dcolumn,
                latex_group_size=int(ctx.get("latex_group_size", 3) or 3),
            )
        self.tabs.setCurrentIndex(self.result_tab_index)
        QMessageBox.information(self, self._tr("完成", "Done"), self._tr("批量拟合完成。", "Batch fitting completed."))
        self._remember_last_result("fit_batches", {"entries": entries, "context": ctx})
        self._fit_batch_context = None

    def _on_fit_finished(self, payload: FitResultPayload):
        job = payload.job
        fit_result = payload.fit_result
        expression = payload.expression or job.model_expr
        for entry in payload.logs:
            self._append_log(entry)
        for warn in payload.warnings:
            self._append_log(self._tr(f"警告: {warn}", f"Warning: {warn}"))
        substituted = self._build_substituted_expression(expression, fit_result.params) if expression else None
        summary = self._format_fit_result_text(fit_result, expression, substituted)
        self._set_result_text(summary)
        csv_rows = self._build_fit_csv_rows(fit_result, expression, batch_idx=1)
        if csv_rows:
            self._set_csv_data(
                csv_rows,
                ["batch", "section", "name", "value", "uncertainty", "stat_error", "sys_error", "note"],
                suggestion="fitting_results.csv",
            )
        else:
            self._reset_csv_data()
        warning_detail = fit_result.details.get("boundary_warning")
        if warning_detail:
            self._append_log(warning_detail)
        sys_warning = fit_result.details.get("systematic_warning")
        if sys_warning:
            self._append_log(self._tr(f"系统误差警告: {sys_warning}", f"Systematic warning: {sys_warning}"))
        plot_bytes = self._render_fit_plot_bytes(job, fit_result) if getattr(job, "render_plots", True) else None
        if plot_bytes is not None:
            self._image_mode = "fit"
            self.current_fit_figures = []
            self.current_fit_index = 0
            self._update_result_plot(plot_bytes)
        if job.generate_latex and job.output_path:
            self._write_fitting_latex(
                job.headers,
                job.data_rows,
                job.sigma_rows,
                fit_result,
                expression or "",
                substituted or "",
                plot_bytes,
                job.output_path,
                job.use_dcolumn,
            )
        self.tabs.setCurrentIndex(self.result_tab_index)
        self._remember_last_result(
            "fit_single",
            {"fit_result": fit_result, "expression": expression, "substituted": substituted, "job": job},
        )
        QMessageBox.information(self, self._tr("完成", "Done"), self._tr("拟合完成。", "Fit completed."))

    def _on_fit_failed(self, message: str):
        localized = self._localize_text(message)
        QMessageBox.critical(self, self._tr("拟合失败", "Fit failed"), localized)
        log_msg = self._tr(f"拟合失败: {localized}", f"Fit failed: {localized}")
        self._append_log(log_msg)
        self._fit_batch_context = None

    def _on_fit_thread_done(self):
        self._set_button_to_run_mode()
        if self._fit_worker:
            try:
                self._fit_worker.deleteLater()
            except Exception:
                pass
        self._fit_worker = None

    def _execute_auto_fit_async(self, dataset, generate_latex: bool, output_path: str, verbose: bool):
        if self._auto_fit_worker and self._auto_fit_worker.isRunning():
            QMessageBox.information(self, self._tr("提示", "Notice"), self._tr("自动拟合正在运行中。", "Auto fit already running."))
            return
        try:
            job = self._prepare_auto_fit_job(dataset, verbose)
        except Exception as exc:
            localized = self._localize_text(str(exc))
            QMessageBox.critical(self, self._tr("自动拟合失败", "Auto fit failed"), localized)
            log_msg = self._tr(f"自动拟合失败: {localized}", f"Auto fit failed: {localized}")
            self._append_log(log_msg)
            return

        worker = AutoFitWorker(job)
        worker.result_ready.connect(
            lambda payload, g=generate_latex, o=output_path, v=job.verbose: self._on_auto_fit_finished(payload, g, o, v)
        )
        worker.failed.connect(self._on_auto_fit_failed)
        worker.finished.connect(self._on_auto_fit_thread_done)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.progress_changed.connect(self._on_auto_fit_progress)
        if job.verbose:
            worker.log_ready.connect(self._append_log)
        self._auto_fit_worker = worker
        self._set_button_to_stop_mode()
        worker.start()
        self._append_log(self._tr("自动拟合已在后台运行…", "Auto fit running in background…"))

    def _on_auto_fit_progress(self, event):
        """Receive a ``ProgressEvent`` from the auto-fit worker and
        surface it in the log. The GUI shows e.g.
        ``"[3/19] 正在拟合 Padé(1|1)…"`` so the user can see which
        model is currently running and that the pipeline is
        progressing — not frozen — even on long fits.
        """
        # Translate status into a localised verb. Anything we don't
        # have a translation for falls through to the raw status
        # string so a future maintainer adding a new ProgressStatus
        # value still sees something rather than silently dropping
        # the event.
        verbs_zh = {
            "started": "正在拟合",
            "ok": "完成",
            "timeout": "超时跳过",
            "error": "失败",
            "cancelled": "已取消",
        }
        verbs_en = {
            "started": "Fitting",
            "ok": "Done",
            "timeout": "Timed out",
            "error": "Failed",
            "cancelled": "Cancelled",
        }
        status = getattr(event, "status", "?")
        verb = self._tr(verbs_zh.get(status, status), verbs_en.get(status, status))
        idx = getattr(event, "index", 0) + 1
        total = getattr(event, "total", 0)
        label = getattr(event, "label", "?")
        line = f"[{idx}/{total}] {verb}: {label}"
        err = getattr(event, "error", None)
        if err:
            line += f" — {err}"
        self._append_log(line)

    def _on_auto_fit_finished(self, payload, generate_latex: bool, output_path: str, verbose_mode: bool):
        captured_log = ""
        try:
            if isinstance(payload, (list, tuple)) and len(payload) == 3:
                summary, job, captured_log = payload
            else:
                summary, job = payload
        except Exception as exc:  # noqa: BLE001
            self._on_auto_fit_failed(str(exc))
            return
        if verbose_mode and captured_log:
            self._append_log(captured_log)
        self._render_auto_fit_summary(
            summary,
            job.headers,
            job.data_rows,
            job.sigma_rows,
            job.x_series,
            job.y_series,
            job.sigma_series,
            job.weights,
            generate_latex,
            output_path,
            job.extra_models,
            verbose_mode,
            render_plots=job.render_plots,
        )

    def _on_auto_fit_failed(self, message: str):
        localized = self._localize_text(message)
        QMessageBox.critical(self, self._tr("自动拟合失败", "Auto fit failed"), localized)
        log_msg = self._tr(f"自动拟合失败: {localized}", f"Auto fit failed: {localized}")
        self._append_log(log_msg)

    def _on_auto_fit_thread_done(self):
        self._set_button_to_run_mode()
        if self._auto_fit_worker:
            try:
                self._auto_fit_worker.deleteLater()
            except Exception:
                pass
        self._auto_fit_worker = None

    def _run_fitting_mode(self, generate_latex: bool, output_path: str, verbose: bool, render_plots: bool = True) -> bool:
        headers, rows, sigma_rows, segments, _ = self._collect_batched_fitting_dataset(precision_hint=self._peek_user_precision())
        batches = self._build_batches_from_segments(headers, rows, sigma_rows, segments)
        if not batches:
            raise ValueError(_dual_msg("没有可用于拟合的数据。", "No data available for fitting."))
        mode = self.fit_model_combo.currentData()
        if len(batches) == 1:
            batch = batches[0]
            dataset = (batch["headers"], batch["rows"], batch["sigma_rows"])
            if mode == "auto":
                self._execute_auto_fit_async(dataset, generate_latex, output_path, verbose)
                return True
            job = self._prepare_fit_job(dataset, generate_latex, output_path, verbose, render_plots=render_plots)
            self._execute_fit_async(job)
            return True
        tasks: list[FitBatchTask] = []
        if mode == "auto":
            for batch in batches:
                dataset = (batch["headers"], batch["rows"], batch["sigma_rows"])
                job = self._prepare_auto_fit_job(dataset, verbose)
                tasks.append(FitBatchTask(index=batch.get("index", len(tasks) + 1), auto_job=job))
        else:
            for batch in batches:
                dataset = (batch["headers"], batch["rows"], batch["sigma_rows"])
                job = self._prepare_fit_job(dataset, False, output_path, verbose, render_plots=render_plots)
                tasks.append(FitBatchTask(index=batch.get("index", len(tasks) + 1), fit_job=job))
        worker = FitBatchWorker(tasks, capture_output=verbose)
        worker.finished_ok.connect(self._on_fit_batches_finished)
        worker.failed.connect(self._on_fit_failed)
        worker.finished.connect(self._on_fit_thread_done)
        worker.cancelled.connect(self._on_worker_cancelled)
        self._fit_worker = worker
        self._fit_batch_context = {
            "generate_latex": generate_latex,
            "output_path": output_path,
            "use_dcolumn": self.dcolumn_checkbox.isChecked(),
            "latex_group_size": self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3,
            "caption": self._caption_value(),
            "mode": mode,
            "verbose": verbose,
        }
        self._set_button_to_stop_mode()
        worker.start()
        self._append_log(self._tr("批量拟合已在后台运行…", "Batch fitting running in background…"))
        return True
