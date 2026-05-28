"""Phase 7 #19 split — fit-mode dispatch and worker orchestration
concern.

Methods extracted VERBATIM from the original ``window_fitting_mixin.py``.
This is the largest split file because it owns every fit-execution
path: custom Levenberg-Marquardt fits, polynomial / inverse / Padé /
linear-named templates, auto-fit-across-all-models, plus the worker
thread setup (``_execute_fit_async``, ``_execute_auto_fit_async``)
and the central dispatcher ``_run_fitting_mode`` that decides which
of the above to call based on the user's UI selection.

The auto-fit summary renderer ``_render_auto_fit_summary`` lives
here (it's the engine that builds an ``AutoFitRenderResult`` from a
``summarize_auto_results`` output, which is then consumed by the
Residuals mixin via signal). It is the single biggest method in
this whole subsystem (~180 lines).

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
- _execute_auto_fit                  (was line 1029)
- _render_auto_fit_summary           (was line 1064)
- _prepare_auto_fit_job              (was line 1249)
- _prepare_fit_job                   (was line 1307)
- _execute_fit_async                 (was line 1385)
- _execute_auto_fit_async            (was line 1738)
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
  ``self._on_fit_thread_done``, ``self._on_auto_fit_finished``,
  ``self._on_auto_fit_failed``, ``self._on_auto_fit_thread_done``
  — Residuals mixin

Methods provided by the host class (``ExtrapolationWindow``):
- ``self._localize_label`` — translate a model label per UI locale
- ``self._collect_variable_mapping``, ``self._column_series``,
  ``self._resolve_uncertainties``, ``self._build_weight_vector``
  — dataset / column extraction helpers
- ``self._collect_batched_fitting_dataset``,
  ``self._build_batches_from_segments``, ``self._peek_user_precision``
  — batch-mode helpers
- ``self._append_log`` — log channel
- ``self._auto_model_map`` — host-class lookup of registered AutoModelDefinition

State variables OWNED:
- ``self._fit_worker``, ``self._auto_fit_worker`` (worker handles)
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
    auto_fit_dataset,
    build_model_specification,
    build_parameter_state,
    fit_custom_model,
    render_fitting_overview,
    summarize_auto_results,
)
from fitting.auto_models import (
    AutoModelDefinition,
    build_inverse_series_definition,
    build_polynomial_definition,
    fit_linear_model,
)

from .workers_core import (
    AutoFitJob,
    AutoFitRenderResult,
    FitBatchTask,
    FitJob,
    _mp_precision_guard,
)
from .workers_qt import AutoFitWorker, FitBatchWorker, FitWorker


class CustomFitConfig(TypedDict):
    expression: str
    variable_names: tuple[str, ...]
    parameter_config: dict[str, dict[str, str]]
    parameter_names: list[str]
    constants: dict[str, str]


class WindowFittingModelsMixin:
    def _collect_custom_constants(self) -> dict[str, str]:
        host = cast(Any, self)
        editor = getattr(host, "custom_constants_editor", None)
        if editor is None or not editor.isChecked():
            return {}
        return cast("dict[str, str]", editor.constants_dict(validate=True))

    def _collect_custom_fit_config(
        self,
        validate_parameters: bool = True,
        *,
        variable_names: Sequence[str] | None = None,
    ) -> CustomFitConfig:
        host = cast(Any, self)
        model_expr = host.fit_expr_edit.toPlainText().strip()
        constants = self._collect_custom_constants()
        if variable_names is None:
            variable_names = [
                var_edit.text().strip()
                for var_edit, _col_edit, *_ in getattr(host, "variable_rows", [])
                if var_edit.text().strip()
            ] or ["x"]
        table = getattr(host, "custom_params_table", None)
        if table is None:
            raise ValueError(host._tr("请在参数列表中添加参数。", "Please add at least one parameter."))
        try:
            parameter_config = cast(
                "dict[str, dict[str, str]]",
                table.parameter_config(validate=validate_parameters),
            )
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
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
            custom_config = self._collect_custom_fit_config(
                validate_parameters=True,
                variable_names=list(variable_map.keys()),
            )
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
        parameter_config: dict[str, dict[str, str]] = {}
        model_expr = self.fit_expr_edit.toPlainText().strip()
        if model_expr:
            custom_config = self._collect_custom_fit_config(
                validate_parameters=False,
                variable_names=["x"],
            )
            constants = custom_config["constants"]
            parameter_config = custom_config["parameter_config"]
            parameter_names = custom_config["parameter_names"]
            spec = build_model_specification(model_expr, ["x"], parameter_names, constants)
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
        auto_identifier: str | None = None
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
        elif model_type == "poly":
            poly_degree = self.poly_degree_spin.value()
            model_expr = self._mode_expression_preview("poly")
        elif model_type == "inverse":
            inverse_min, inverse_max = self._inverse_power_range()
            model_expr = self._mode_expression_preview("inverse")
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
        elif model_type in {"log_poly", "exp_combo"}:
            auto_identifier = "M4B" if model_type == "log_poly" else "M7B"
            model_expr = self._mode_expression_preview(model_type)
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
            auto_identifier=auto_identifier,
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
