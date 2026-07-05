"""Phase 7 #19 split — result rendering / residual plots / LaTeX
output / batch-result handling concern.

Methods extracted VERBATIM from the original ``window_fitting_mixin.py``.
This mixin owns the post-compute side of fitting: receive a
``FitResultPayload`` from the worker thread, render the plot
(``_render_fit_plot_bytes``), update the result panel
(``_format_fit_display`` is in Formatters and called via MRO),
write LaTeX, and handle worker lifecycle (``_on_fit_thread_done``,
and fit batch cleanup).

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

Methods provided by sibling mixins (resolved via Python MRO):
- ``self._tr`` — bilingual helper (host class)
- ``self._build_substituted_expression``, ``self._format_fit_display``,
  ``self._format_fit_result_text``, ``self._build_fit_csv_rows``,
  ``self._fit_latex_preamble``, ``self._fit_latex_block`` —
  Formatters mixin

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
- ``self._fit_worker``
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
from typing import TYPE_CHECKING
import traceback

from PySide6.QtWidgets import QMessageBox

from datalab_core.fitting_comparison import (
    build_fitting_comparison_result_snapshot,
    render_fitting_comparison_snapshot_outputs,
)
from datalab_latex.latex_tables_fitting import build_fitting_comparison_latex_block
from fitting import render_fitting_overview
from fitting.auto_models import (
    build_inverse_series_definition,
    build_polynomial_definition,
)
from fitting.comparison_formatting import build_comparison_table_rows_from_payload
from fitting.hp_fitter import FitResult
from shared.plotting import FittingPlotLabels, fitting_plot_labels_with_units

from .workers_core import (
    FitBatchResultEntry,
    FittingComparisonJob,
    FittingComparisonResultPayload,
    FitJob,
    FitResultPayload,
)

if TYPE_CHECKING:
    import mpmath as mp


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
                text, rows = self._format_fit_display(
                    payload.fit_result,
                    expression,
                    substituted,
                    batch_idx=entry.index,
                    units=payload.units,
                )
                batch_texts.append(header + "\n" + text)
                csv_rows.extend(rows)
            else:
                batch_texts.append(header + "\n" + self._tr("未获得该批次结果。", "No result for this batch."))
        combined = "\n\n".join(batch_texts)
        self._set_result_text(combined, final_result=True)
        if csv_rows:
            self._set_csv_data(
                csv_rows,
                self._fit_csv_headers(csv_rows),
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
        units: dict | None = None,
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
                units=units,
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
                    units=entry.get("units"),
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

    def _write_fitting_comparison_latex(
        self,
        payload: dict[str, object],
        job: FittingComparisonJob,
    ) -> Path | None:
        digits = int(getattr(job, "latex_digits", 16) or 16)
        group_size = int(getattr(job, "latex_group_size", 3) or 3)
        tex_path = Path(job.output_path).expanduser()
        try:
            comparison_rows = build_comparison_table_rows_from_payload(payload)
        except ValueError as exc:
            QMessageBox.warning(
                self,
                self._tr("写入失败", "Write Failed"),
                str(exc),
            )
            return None
        lines = self._fit_latex_preamble(job.use_dcolumn, digits, group_size)
        lines.extend(
            build_fitting_comparison_latex_block(
                comparison_rows,
                use_dcolumn=job.use_dcolumn,
                caption_text=job.caption or self._tr("选定拟合比较", "Selected fit comparison"),
            )
        )
        lines.append("\\end{document}")
        try:
            with open(tex_path, "w", encoding="utf-8") as fh:
                fh.write("\n".join(lines))
            self._append_log(f"拟合比较 LaTeX 已写入: {tex_path}")
            self._load_latex_into_editor(tex_path)
            return tex_path
        except OSError as exc:
            QMessageBox.warning(
                self,
                self._tr("写入失败", "Write Failed"),
                str(exc),
            )
            return None

    def _render_fit_plot_bytes(self, job: FitJob, fit_result: FitResult, comparison=None, log_scale: str | None = None, units: dict | None = None) -> bytes | None:
        x_values = [float(v) for v in job.x_series]
        y_values = [float(v) for v in job.y_series]
        show_curves = not job.is_multidim
        plot_labels = fitting_plot_labels_with_units(
            FittingPlotLabels(),
            x_unit=self._fit_input_unit_for_job(units, job),
            y_unit=self._fit_output_unit(units, getattr(job, "target_column", "")),
            parameter_unit=self._fit_single_parameter_axis_unit(units, fit_result.params.keys()),
        )
        try:
            # Validate log-scale selection against current data to avoid log(<=0) failures
            safe_log_scale = self._sanitize_log_scale(log_scale if log_scale is not None else self._current_log_scale(), job.x_series, job.y_series)
            if show_curves:
                if job.model_type in {"polynomial", "inverse_power"}:
                    if job.model_type == "polynomial":
                        definition = build_polynomial_definition(job.poly_degree)
                    else:
                        definition = build_inverse_series_definition(job.inverse_min, job.inverse_max)
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
                    diagnostics=fit_result.details.get("diagnostics") if isinstance(fit_result.details, dict) else None,
                    covariance=fit_result.covariance,
                    labels=plot_labels,
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
                diagnostics=fit_result.details.get("diagnostics") if isinstance(fit_result.details, dict) else None,
                covariance=fit_result.covariance,
                labels=plot_labels,
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
                plot_bytes = self._render_fit_plot_bytes(job, fit_result, log_scale=log_scale, units=payload.get("units"))
                if plot_bytes:
                    self._image_mode = "fit"
                    self._update_result_plot(plot_bytes)
        elif kind == "fit_auto":
            payload = payloads[kind]
            job = payload.get("job")
            fit_result = payload.get("fit_result")
            if job and fit_result and getattr(job, "render_plots", True):
                plot_bytes = self._render_fit_plot_bytes(job, fit_result, log_scale=log_scale, units=payload.get("units"))
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
                    plot_bytes = self._render_fit_plot_bytes(job, fit_res, log_scale=log_scale, units=entry.fit_payload.units)
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
        try:
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
                    summary = self._format_fit_result_text(payload.fit_result, expression, substituted, units=payload.units)
                    batch_texts.append(header + "\n" + summary)
                    plot_bytes = self._render_fit_plot_bytes(job, payload.fit_result, units=payload.units) if getattr(job, "render_plots", True) else None
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
                            "units": payload.units,
                        }
                    )
                    csv_rows.extend(
                        self._build_fit_csv_rows(
                            payload.fit_result,
                            expression or "",
                            batch_idx=entry.index,
                            units=payload.units,
                        )
                    )
                else:
                    batch_texts.append(header + "\n" + self._tr("未获得该批次结果。", "No result for this batch."))
            combined = "\n\n".join(batch_texts)
            self._set_result_text(combined, final_result=True)
            self._set_image_list("fit", figure_paths)
            if csv_rows:
                self._set_csv_data(
                    csv_rows,
                    self._fit_csv_headers(csv_rows),
                    suggestion="fitting_results.csv",
                )
            else:
                self._reset_csv_data()
        except Exception as exc:  # noqa: BLE001
            self._mark_workbench_result_failed()
            self._append_log(traceback.format_exc())
            localized = self._localize_text(str(exc))
            QMessageBox.critical(self, self._tr("拟合失败", "Fit failed"), localized)
            self._fit_batch_context = None
            return False
        try:
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
        except Exception as exc:  # noqa: BLE001
            self._append_log(traceback.format_exc())
            localized = self._localize_text(str(exc))
            self._append_log(self._tr(f"拟合后处理警告: {localized}", f"Fit post-processing warning: {localized}"))
        finally:
            self._fit_batch_context = None
        return True

    def generate_fitting_latex_on_demand(self) -> str | None:
        """Rebuild the single-fit LaTeX tex ON DEMAND from the stashed result-data + the
        RUN's target_column/variable_pairs/group_size/uncertainty_digits (NOT edited
        widgets) + LIVE dcolumn/digits — reproducing the run-time tex without recompute."""
        store = getattr(self, "_last_latex_inputs", {}) or {}
        latex_inputs = store.get("fit_single")
        if not isinstance(latex_inputs, dict):
            return None
        fit_result = latex_inputs.get("fit_result")
        if fit_result is None:
            return None
        headers = latex_inputs.get("headers") or []
        rows = latex_inputs.get("rows") or []
        sigma_rows = latex_inputs.get("sigma_rows") or []
        # Format options: dcolumn + digits are read LIVE (options); group_size +
        # uncertainty_digits come from the RUN (stash) so the table layout matches.
        use_dcolumn = (
            self.dcolumn_checkbox.isChecked()
            if hasattr(self, "dcolumn_checkbox")
            else bool(latex_inputs.get("use_dcolumn"))
        )
        digits = (
            self.latex_input_precision_spin.value()
            if hasattr(self, "latex_input_precision_spin")
            else int(latex_inputs.get("latex_digits") or 16)
        )
        group_size = int(latex_inputs.get("latex_group_size") or 3)
        output_path = self.latex_output_path_for_run(True)
        lines = self._fit_latex_preamble(use_dcolumn, digits, group_size)
        lines.extend(
            self._fit_latex_block(
                headers,
                rows,
                sigma_rows,
                fit_result,
                str(latex_inputs.get("expression") or ""),
                str(latex_inputs.get("substituted") or ""),
                None,  # image_path — no image embedded
                use_dcolumn,
                digits,
                latex_group_size=group_size,
                units=latex_inputs.get("units"),
                target_column=latex_inputs.get("target_column"),
                variable_pairs=latex_inputs.get("variable_pairs"),
                default_uncertainty_digits=latex_inputs.get("uncertainty_digits"),
            )
        )
        lines.append("\\end{document}")
        from pathlib import Path

        tex_path = Path(output_path).expanduser()
        try:
            tex_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self._append_log(self._tr(f"拟合 LaTeX 写入失败: {exc}", f"Fit LaTeX write failed: {exc}"))
            return None
        self._load_latex_into_editor(tex_path)
        return str(tex_path)

    def generate_fitting_comparison_latex_on_demand(self) -> str | None:
        """Rebuild the fitting-comparison LaTeX tex ON DEMAND from the stashed payload +
        LIVE dcolumn/digits (group_size/caption from the run) — no recompute."""
        store = getattr(self, "_last_latex_inputs", {}) or {}
        latex_inputs = store.get("fitting_comparison")
        if not isinstance(latex_inputs, dict):
            return None
        payload = latex_inputs.get("payload")
        if not isinstance(payload, dict):
            return None
        use_dcolumn = (
            self.dcolumn_checkbox.isChecked()
            if hasattr(self, "dcolumn_checkbox")
            else bool(latex_inputs.get("use_dcolumn"))
        )
        digits = (
            self.latex_input_precision_spin.value()
            if hasattr(self, "latex_input_precision_spin")
            else int(latex_inputs.get("latex_digits") or 16)
        )
        group_size = int(latex_inputs.get("latex_group_size") or 3)
        try:
            comparison_rows = build_comparison_table_rows_from_payload(payload)
        except ValueError:
            return None
        lines = self._fit_latex_preamble(use_dcolumn, digits, group_size)
        lines.extend(
            build_fitting_comparison_latex_block(
                comparison_rows,
                use_dcolumn=use_dcolumn,
                caption_text=latex_inputs.get("caption")
                or self._tr("选定拟合比较", "Selected fit comparison"),
            )
        )
        lines.append("\\end{document}")
        output_path = self.latex_output_path_for_run(True)
        from pathlib import Path

        tex_path = Path(output_path).expanduser()
        try:
            tex_path.write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self._append_log(self._tr(f"拟合比较 LaTeX 写入失败: {exc}", f"Fit comparison LaTeX write failed: {exc}"))
            return None
        self._load_latex_into_editor(tex_path)
        return str(tex_path)

    def _on_fit_finished(self, payload: FitResultPayload):
        try:
            job = payload.job
            fit_result = payload.fit_result
            expression = payload.expression or job.model_expr
            units = payload.units
            for entry in payload.logs:
                self._append_log(entry)
            for warn in payload.warnings:
                self._append_log(self._tr(f"警告: {warn}", f"Warning: {warn}"))
            substituted = self._build_substituted_expression(expression, fit_result.params) if expression else None
            summary = self._format_fit_result_text(fit_result, expression, substituted, units=units)
            self._set_result_text(summary, final_result=True)
            csv_rows = self._build_fit_csv_rows(fit_result, expression, batch_idx=1, units=units)
            if csv_rows:
                self._set_csv_data(
                    csv_rows,
                    self._fit_csv_headers(csv_rows),
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
            plot_bytes = self._render_fit_plot_bytes(job, fit_result, units=units) if getattr(job, "render_plots", True) else None
            if plot_bytes is not None:
                self._image_mode = "fit"
                self.current_fit_figures = []
                self.current_fit_index = 0
                self._update_result_plot(plot_bytes, final_result=True)
        except Exception as exc:  # noqa: BLE001
            self._mark_workbench_result_failed()
            self._append_log(traceback.format_exc())
            localized = self._localize_text(str(exc))
            QMessageBox.critical(self, self._tr("拟合失败", "Fit failed"), localized)
            return False
        try:
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
                    units=units,
                )
            self.tabs.setCurrentIndex(self.result_tab_index)
            self._remember_last_result(
                "fit_single",
                {"fit_result": fit_result, "expression": expression, "substituted": substituted, "job": job, "units": units},
            )
            # Stash tex-rebuild DATA from the RUN (not edited widgets): target_column +
            # ORDERED variable_pairs + group_size + uncertainty_digits come from the job so
            # 生成 TeX reproduces the run-time tex even after widget edits.
            self.remember_latex_inputs(
                "fit_single",
                {
                    "headers": job.headers,
                    "rows": job.data_rows,
                    "sigma_rows": job.sigma_rows,
                    "fit_result": fit_result,
                    "expression": expression or "",
                    "substituted": substituted or "",
                    "units": units,
                    "target_column": job.target_column,
                    "variable_pairs": list(job.variable_map.items()),
                    "latex_group_size": job.latex_group_size,
                    "uncertainty_digits": job.uncertainty_digits,
                    "latex_digits": job.latex_digits,
                    "use_dcolumn": job.use_dcolumn,
                    "caption": job.caption,
                },
            )
            QMessageBox.information(self, self._tr("完成", "Done"), self._tr("拟合完成。", "Fit completed."))
        except Exception as exc:  # noqa: BLE001
            self._append_log(traceback.format_exc())
            localized = self._localize_text(str(exc))
            self._append_log(self._tr(f"拟合后处理警告: {localized}", f"Fit post-processing warning: {localized}"))
        return True

    def _on_fitting_comparison_finished(self, payload: FittingComparisonResultPayload):
        try:
            job = payload.job
            for entry in payload.logs:
                self._append_log(entry)
            for warn in payload.warnings:
                self._append_log(self._tr(f"警告: {warn}", f"Warning: {warn}"))
            snapshot = build_fitting_comparison_result_snapshot(
                "fitting_comparison",
                payload.payload,
                overview_state="complete",
                precision={
                    "compute_digits": job.precision,
                    "uncertainty_digits": job.uncertainty_digits,
                },
            )
            outputs = render_fitting_comparison_snapshot_outputs(snapshot or {})
            if outputs is None:
                raise ValueError(
                    self._tr(
                        "无法渲染选定拟合比较结果。",
                        "Could not render selected-fit comparison results.",
                    )
                )
            text, csv_rows, headers = outputs
            self._set_result_text(text, final_result=True)
            self._set_csv_data(csv_rows, headers, suggestion="fitting_comparison_results.csv")
            self._set_image_list("fit", [])
        except Exception as exc:  # noqa: BLE001
            self._mark_workbench_result_failed()
            self._append_log(traceback.format_exc())
            localized = self._localize_text(str(exc))
            QMessageBox.critical(self, self._tr("拟合比较失败", "Fit comparison failed"), localized)
            return False
        try:
            if job.generate_latex and job.output_path:
                self._write_fitting_comparison_latex(payload.payload, job)
            self.tabs.setCurrentIndex(self.result_tab_index)
            self._remember_last_result("fitting_comparison", dict(payload.payload))
            # Stash tex-rebuild DATA (payload + the run's format opts) so 生成 TeX rebuilds
            # the comparison table on demand without recompute.
            self.remember_latex_inputs(
                "fitting_comparison",
                {
                    "payload": dict(payload.payload),
                    "latex_digits": int(getattr(job, "latex_digits", 16) or 16),
                    "latex_group_size": int(getattr(job, "latex_group_size", 3) or 3),
                    "use_dcolumn": bool(getattr(job, "use_dcolumn", True)),
                    "caption": getattr(job, "caption", None),
                },
            )
            QMessageBox.information(
                self,
                self._tr("完成", "Done"),
                self._tr("选定拟合比较完成。", "Selected-fit comparison completed."),
            )
        except Exception as exc:  # noqa: BLE001
            self._append_log(traceback.format_exc())
            localized = self._localize_text(str(exc))
            self._append_log(self._tr(f"拟合比较后处理警告: {localized}", f"Fit comparison post-processing warning: {localized}"))
        return True

    def _on_fit_failed(self, message: str):
        self._mark_workbench_result_failed()
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
