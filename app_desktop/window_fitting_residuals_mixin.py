"""Phase 7 #19 split — result rendering / residual plots / LaTeX
output / batch-result handling concern.

Methods extracted VERBATIM from the original ``window_fitting_mixin.py``.
This mixin owns the post-compute side of fitting: receive a
``FitResultPayload`` from the worker thread, render the plot
(``_render_fit_plot_bytes``), update the result panel
(``_format_fit_display`` is in Formatters and called via MRO),
write LaTeX, and handle worker lifecycle (``_on_fit_thread_done``,
``_on_auto_fit_thread_done``).

Methods MOVED here from window_fitting_mixin.py (line numbers
refer to the pre-Phase-7 monolith and are frozen as one-time
migration context — they will NOT be kept in sync; see ``git log``
for canonical history):
- _reformat_fit_batches              (was line 250)
- _write_fitting_latex               (was line 487)
- _write_fitting_latex_batches       (was line 533)
- _render_fit_plot_bytes             (was line 1401)
- _refresh_fit_plot_log_scale        (was line 1459)
- _rebuild_fit_batch_plots           (was line 1489)
- _on_fit_batches_finished           (was line 1556)
- _on_fit_finished                   (was line 1671)
- _on_fit_failed                     (was line 1722)
- _on_fit_thread_done                (was line 1729)
- _on_auto_fit_finished              (was line 1765)
- _on_auto_fit_failed                (was line 1793)
- _on_auto_fit_thread_done           (was line 1799)

Methods provided by sibling mixins (resolved via Python MRO):
- ``self._tr`` — bilingual helper (host class)
- ``self._build_substituted_expression``, ``self._format_fit_display``,
  ``self._format_fit_result_text``, ``self._build_fit_csv_rows``,
  ``self._fit_latex_preamble``, ``self._fit_latex_block`` —
  Formatters mixin
- ``self._render_auto_fit_summary`` — Models mixin

Methods provided by the host class (``ExtrapolationWindow``):
- result-panel updaters: ``self._set_result_text``,
  ``self._set_csv_data``, ``self._reset_csv_data``,
  ``self._append_log``, ``self._load_latex_into_editor``,
  ``self._set_image_list``, ``self._update_image_status``,
  ``self._update_result_plot``, ``self._set_button_to_run_mode``,
  ``self._remember_last_result``
- plot helpers: ``self._sanitize_log_scale``,
  ``self._current_log_scale``, ``self._build_linear_plot_series``,
  ``self._build_standard_plot_series``, ``self._save_batch_figure``,
  ``self._cleanup_temp_batch_images``, ``self._is_fit_mode_active``
- localisation: ``self._localize_text``, ``self._is_en``,
  ``self._format_uncertainty_value``, ``self._format_precision_value``,
  ``self._format_display_value``, ``self._uncertainty_digits_value``,
  ``self._caption_value``, ``self._ordered_variable_pairs``

State variables READ/WRITTEN:
- ``self._fit_worker``, ``self._auto_fit_worker``
- ``self._fit_batch_context`` (read + cleared here; WRITTEN by the
  Models mixin in ``_run_fitting_mode`` / ``_prepare_*`` helpers)
- ``self.latex_input_precision_spin``, ``self.latex_group_size_spin``
- ``self.verbose_checkbox`` (read for batch verbose mode)
- ``self.fit_target_edit`` (read by ``_render_fit_plot_bytes`` for
  axis labelling)
- plot widgets and result panel widgets owned by host class
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import mpmath as mp

from PySide6.QtWidgets import QMessageBox

from fitting import render_fitting_overview
from fitting.auto_models import (
    AUTO_MODELS,
    build_inverse_series_definition,
    build_polynomial_definition,
)
from fitting.hp_fitter import FitResult

from .workers_core import (
    FitBatchResultEntry,
    FitJob,
    FitResultPayload,
)


class WindowFittingResidualsMixin:
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

