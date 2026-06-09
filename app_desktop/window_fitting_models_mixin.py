"""Phase 7 #19 split — fit-mode dispatch and worker orchestration
concern.

Methods extracted VERBATIM from the original ``window_fitting_mixin.py``.
This file owns fit-mode dispatch for custom Levenberg-Marquardt fits,
polynomial / inverse / Padé / power-limit templates, self-consistent
models, worker thread setup (``_execute_fit_async``), and the central
dispatcher ``_run_fitting_mode``.

Methods MOVED here from window_fitting_mixin.py (line numbers
refer to the pre-Phase-7 monolith and are frozen as one-time
migration context — they will NOT be kept in sync; see ``git log``
for canonical history):
- _execute_custom_fit                (was line 579)
- _run_linear_definition_fit         (was line 731)
- _execute_custom_polynomial_model   (was line 831)
- _execute_inverse_model             (was line 861)
- _execute_linear_named_model        (was line 890)
- _execute_template_custom_fit       (was line 909)
- _execute_power_limit_model         (was line 1023)
- _execute_pade_model                (was line 1026)
- _prepare_fit_job                   (was line 1307)
- _execute_fit_async                 (was line 1385)
- _run_fitting_mode                  (was line 1808)

Methods provided by sibling mixins (resolved via Python MRO):
- ``self._tr`` — bilingual (host class)
- ``self._collect_custom_parameter_config``, ``self._infer_parameter_names``
  — parameter table + Formatters helpers
- ``self._build_substituted_expression`` — Formatters mixin
- ``self._format_fit_display`` — Formatters mixin
- ``self._build_fit_csv_rows`` — Formatters mixin
- ``self._fit_latex_preamble``, ``self._fit_latex_block`` — Formatters
- worker-result handlers ``self._on_fit_finished``,
  ``self._on_fit_batches_finished``, ``self._on_fit_failed``,
  ``self._on_fit_thread_done`` — Residuals mixin

Methods provided by the host class (``ExtrapolationWindow``):
- ``self._localize_label`` — translate a model label per UI locale
- ``self._collect_variable_mapping``, ``self._column_series``,
  ``self._resolve_uncertainties``, ``self._build_weight_vector``
  — dataset / column extraction helpers
- ``self._collect_batched_fitting_dataset``,
  ``self._build_batches_from_segments``, ``self._peek_user_precision``
  — batch-mode helpers
- ``self._append_log`` — log channel

State variables OWNED:
- ``self._fit_worker`` (worker handle)
- ``self._fit_batch_context`` (batch-job metadata; written here,
  read + cleared by Residuals' result handlers)
- ``self._last_result_kind``, ``self._last_result_payloads`` (cache)

State variables READ from the host class:
- ``self.fit_target_edit``, ``self.fit_expr_edit``,
  ``self.custom_params_table``, ``self.fit_model_combo`` (UI inputs)
- ``self.fit_weighted_checkbox``, ``self.fit_mcmc_refine``,
  ``self.verbose_checkbox`` (checkboxes)
- ``self.poly_degree_spin``, ``self.pade_m_spin``, ``self.pade_n_spin``
  (spinboxes)
"""
from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import Any, TypedDict, cast

import mpmath as mp

from PySide6.QtWidgets import QMessageBox

from data_extrapolation_latex_latest import _dual_msg
from fitting import (
    ImplicitModelDefinition,
    ImplicitSolveOptions,
    build_model_specification,
    build_parameter_state,
    fit_custom_model,
    render_fitting_overview,
)
from fitting.auto_models import (
    AutoModelDefinition,
    build_inverse_series_definition,
    build_polynomial_definition,
    fit_linear_model,
)

from app_desktop.fitting_input_normalization import (
    ParameterInput,
    WorkerInputRequest,
    normalize_fitting_input,
    normalize_fitting_input_from_widgets,
)

from .workers_core import (
    FitBatchTask,
    FitJob,
    _mp_precision_guard,
)
from .parallel_preferences import current_parallel_config_from_widgets
from .workers_qt import FitBatchWorker, FitWorker


class CustomFitConfig(TypedDict):
    expression: str
    variable_names: tuple[str, ...]
    parameter_config: dict[str, dict[str, str]]
    parameter_names: list[str]
    constants: dict[str, str]


class WindowFittingModelsMixin:
    def _current_parallel_config(self):
        return current_parallel_config_from_widgets(self)

    def _collect_custom_constants(self) -> dict[str, str]:
        host = cast(Any, self)
        editor = getattr(host, "custom_constants_editor", None)
        if editor is None or not editor.isChecked():
            return {}
        normalized = normalize_fitting_input_from_widgets(
            model_type="custom",
            expression=host.fit_expr_edit.toPlainText().strip(),
            variable_names=[
                var_edit.text().strip()
                for var_edit, _col_edit, *_ in getattr(host, "variable_rows", [])
                if var_edit.text().strip()
            ] or ["x"],
            constants_editor=editor,
            validate=True,
        )
        return dict(normalized.constants_dict)

    def _collect_custom_fit_config(
        self,
        validate_parameters: bool = True,
        *,
        variable_names: Sequence[str] | None = None,
    ) -> CustomFitConfig:
        host = cast(Any, self)
        model_expr = host.fit_expr_edit.toPlainText().strip()
        if variable_names is None:
            variable_names = [
                var_edit.text().strip()
                for var_edit, _col_edit, *_ in getattr(host, "variable_rows", [])
                if var_edit.text().strip()
            ] or ["x"]
        table = getattr(host, "custom_params_table", None)
        if table is None:
            raise ValueError(host._tr("请在参数列表中添加参数。", "Please add at least one parameter."))
        editor = getattr(host, "custom_constants_editor", None)
        try:
            normalized = normalize_fitting_input_from_widgets(
                model_type="custom",
                expression=model_expr,
                variable_names=variable_names,
                parameter_table=table,
                constants_editor=editor,
                validate=validate_parameters,
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        parameter_config = {name: dict(values) for name, values in normalized.parameter_config.items()}
        constants = dict(normalized.constants_dict)
        if validate_parameters and not parameter_config:
            raise ValueError(host._tr("请在参数列表中添加参数。", "Please add at least one parameter."))
        parameter_names = host._infer_parameter_names(
            model_expr,
            list(variable_names),
            list(parameter_config.keys()),
            constants=sorted(constants),
        )
        return {
            "expression": model_expr,
            "variable_names": tuple(variable_names),
            "parameter_config": parameter_config,
            "parameter_names": list(parameter_names),
            "constants": constants,
        }

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
            custom_config = self._collect_custom_fit_config(
                validate_parameters=True,
                variable_names=list(variable_map.keys()),
            )
            normalized = normalize_fitting_input(
                model_type="custom",
                expression=str(custom_config["expression"]),
                variable_names=list(variable_map.keys()),
                target_column=target_column,
                parameters=ParameterInput(),
                worker_request=WorkerInputRequest(
                    headers=headers,
                    data_rows=data_rows,
                    sigma_rows=sigma_rows,
                    variable_mapping=variable_map,
                ),
                weighted=self.fit_weighted_checkbox.isChecked(),
                validate=False,
            )
            worker_input = normalized.worker_input
            if worker_input is None:
                raise ValueError(_dual_msg("无法准备拟合数据。", "Could not prepare fitting data."))
            target_series = list(worker_input.target_series)
            sigma_series = list(worker_input.sigma_series)
            weights = list(worker_input.weights) if worker_input.weights is not None else None
            variable_data = {key: list(values) for key, values in worker_input.variable_data.items()}
            variable_map = dict(worker_input.variable_map)
            model_expr = str(custom_config["expression"])
            constants = custom_config["constants"]
            parameter_config = custom_config["parameter_config"]
            parameter_names = custom_config["parameter_names"]
            precision = self._read_precision()
            if verbose:
                self._append_log(f"[fit] custom model: expr={model_expr} target={target_column} variables={variable_map}")
                self._append_log(f"[fit] n_points={len(target_series)} precision={precision}")
                self._append_log(f"[fit] initial_params={parameter_config}")
            with _mp_precision_guard(precision):
                self._set_fit_output_precision(precision)
                model_spec = build_model_specification(
                    model_expr,
                    list(variable_map.keys()),
                    parameter_names,
                    constants,
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
                self._append_log(f"[fit] params={fit_result.params}")
                self._append_log(f"[fit] chi2={fit_result.chi2} reduced_chi2={fit_result.reduced_chi2} r2={fit_result.r2}")
            substituted = self._build_substituted_expression(model_expr, fit_result.params)
            fit_result.details["expression"] = model_expr
            fit_result.details["substituted_expression"] = substituted
            summary = self._format_fit_result_text(fit_result, model_expr, substituted)
            self._set_result_text(summary, final_result=True)
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
            self._update_result_plot(plot_data, final_result=True)
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
        self._set_result_text(summary, final_result=True)
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
        self._update_result_plot(plot_data, final_result=True)
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
            self._set_result_text(summary, final_result=True)
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
            self._update_result_plot(plot_data, final_result=True)
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

    def _prepare_fit_job(self, dataset, generate_latex: bool, output_path: str, verbose: bool, render_plots: bool = True) -> FitJob:
        headers, data_rows, sigma_rows = dataset
        precision = self._read_precision()
        self._current_precision = precision
        self._set_fit_output_precision(precision)
        variable_map = self._collect_variable_mapping(headers)
        target_column = self.fit_target_edit.text().strip()
        model_type = self.fit_model_combo.currentData()
        model_expr = self.fit_expr_edit.toPlainText().strip()
        normalized_worker = normalize_fitting_input(
            model_type=str(model_type or ""),
            expression=model_expr,
            variable_names=list(variable_map.keys()),
            target_column=target_column,
            parameters=ParameterInput(),
            worker_request=WorkerInputRequest(
                headers=headers,
                data_rows=data_rows,
                sigma_rows=sigma_rows,
                variable_mapping=variable_map,
            ),
            weighted=self.fit_weighted_checkbox.isChecked(),
            validate=False,
        ).worker_input
        if normalized_worker is None:
            raise ValueError(_dual_msg("无法准备拟合数据。", "Could not prepare fitting data."))
        variable_map = dict(normalized_worker.variable_map)
        variable_data = {key: list(values) for key, values in normalized_worker.variable_data.items()}
        target_series = list(normalized_worker.target_series)
        sigma_series = list(normalized_worker.sigma_series)
        weights = list(normalized_worker.weights) if normalized_worker.weights is not None else None
        primary_variable = next(iter(variable_map), "x")
        x_series = list(variable_data.get("x") or variable_data.get(primary_variable) or [])
        y_series = list(target_series)
        parameter_config: dict[str, dict[str, str]] = {}
        parameter_names: list[str] = []
        template_expr: str | None = None
        template_params: dict[str, object] | None = None
        implicit_definition: ImplicitModelDefinition | None = None
        label = self._localize_label(self.fit_model_combo.currentText())
        is_multidim = len(variable_map) > 1
        custom_constants: dict[str, str] | None = None
        timeout_seconds: float | None = None
        poly_degree = 0
        inverse_min = 1
        inverse_max = 3
        pade_m = 1
        pade_n = 1
        if model_type == "custom":
            custom_config = self._collect_custom_fit_config(
                validate_parameters=True,
                variable_names=list(variable_map.keys()),
            )
            custom_constants = custom_config["constants"]
            parameter_config = custom_config["parameter_config"]
            parameter_names = custom_config["parameter_names"]
        elif model_type == "self_consistent":
            implicit_config = self._collect_implicit_config()
            parameter_names = list(implicit_config["parameter_names"])
            parameter_config = self._collect_implicit_parameter_config(parameter_names)
            constants = dict(implicit_config.get("constants") or {})
            implicit_definition = ImplicitModelDefinition(
                x_variables=tuple(implicit_config["x_variables"]),
                implicit_variable=str(implicit_config["implicit_variable"]),
                equation=str(implicit_config["equation"]),
                output_expression=str(implicit_config["output_expression"]),
                parameters=tuple(parameter_names),
                constants=constants,
                solve_options=ImplicitSolveOptions(
                    method=str(implicit_config["method"]),
                    initial=str(implicit_config["initial"]),
                    tolerance=str(implicit_config["tolerance"]),
                    max_iterations=int(implicit_config["max_iterations"]),
                ),
            )
            model_expr = str(implicit_config["output_expression"])
            timeout_seconds = float(implicit_config["timeout_seconds"])
        elif model_type == "polynomial":
            poly_degree = self.poly_degree_spin.value()
            model_expr = self._mode_expression_preview("polynomial")
        elif model_type == "inverse_power":
            inverse_min, inverse_max = self._inverse_power_range()
            model_expr = self._mode_expression_preview("inverse_power")
        elif model_type == "pade":
            pade_m = self.pade_m_spin.value()
            pade_n = self.pade_n_spin.value()
            payload = self._pade_template(pade_m, pade_n)
            if payload:
                template_expr, template_params = payload
                model_expr = template_expr
        elif model_type == "power_limit":
            template_expr, template_params = self._power_limit_template()
            model_expr = template_expr
        else:
            # fallback to custom
            custom_config = self._collect_custom_fit_config(
                validate_parameters=True,
                variable_names=list(variable_map.keys()),
            )
            custom_constants = custom_config["constants"]
            parameter_config = custom_config["parameter_config"]
            parameter_names = custom_config["parameter_names"]
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
            poly_degree=poly_degree,
            inverse_min=inverse_min,
            inverse_max=inverse_max,
            pade_m=pade_m,
            pade_n=pade_n,
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
            implicit_definition=implicit_definition,
            timeout_seconds=timeout_seconds,
            custom_constants=custom_constants,
            parallel_config=self._current_parallel_config(),
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
        self._start_worker_with_workbench_result_state(worker)
        self._append_log(self._tr("拟合已在后台运行…", "Fit running in background…"))

    def _run_fitting_mode(self, generate_latex: bool, output_path: str, verbose: bool, render_plots: bool = True) -> bool:
        headers, rows, sigma_rows, segments, _ = self._collect_batched_fitting_dataset(precision_hint=self._peek_user_precision())
        batches = self._build_batches_from_segments(headers, rows, sigma_rows, segments)
        if not batches:
            raise ValueError(_dual_msg("没有可用于拟合的数据。", "No data available for fitting."))
        mode = self.fit_model_combo.currentData()
        if len(batches) == 1:
            batch = batches[0]
            dataset = (batch["headers"], batch["rows"], batch["sigma_rows"])
            job = self._prepare_fit_job(dataset, generate_latex, output_path, verbose, render_plots=render_plots)
            self._execute_fit_async(job)
            return True
        tasks: list[FitBatchTask] = []
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
        self._start_worker_with_workbench_result_state(worker)
        self._append_log(self._tr("批量拟合已在后台运行…", "Batch fitting running in background…"))
        return True
