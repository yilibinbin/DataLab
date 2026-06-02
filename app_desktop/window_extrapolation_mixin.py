from __future__ import annotations

import io
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import mpmath as mp

from PySide6.QtWidgets import QMessageBox

from data_extrapolation_latex_latest import ExtrapolationOptions, format_uncertainty_display_latex

from .workers_core import (
    CalcResult,
    split_extrapolation_result,
    _mp_precision_guard,
    _render_extrapolation_plot_bytes,
    _safe_resolve_path,
    CalcJob,
)
from .workers_qt import CalcWorker, RootSolvingWorker


class WindowExtrapolationMixin:
    # --------------------------------------------------------- Worker Control Methods --
    def _has_running_worker(self) -> bool:
        """Check if any worker is currently running."""
        return (
            (self._calc_worker and self._calc_worker.isRunning())
            or (self._fit_worker and self._fit_worker.isRunning())
            or (getattr(self, "_root_worker", None) and self._root_worker.isRunning())
        )

    def _set_button_to_stop_mode(self):
        """Change the run button to stop mode (red color, stop text)."""
        if hasattr(self, "run_button"):
            self.run_button.setText(self._tr("停止", "Stop"))
            self.run_button.setStyleSheet("background-color: #d32f2f; color: white; font-weight: bold;")

    def _set_button_to_run_mode(self):
        """Restore the run button to normal run mode."""
        if hasattr(self, "run_button"):
            self.run_button.setText(self._tr("开始执行", "Run"))
            self.run_button.setStyleSheet("")

    def _stop_current_worker(self):
        """Request all running workers to stop."""
        stopped = False
        if self._calc_worker and self._calc_worker.isRunning():
            self._calc_worker.request_stop()
            stopped = True
        if self._fit_worker and self._fit_worker.isRunning():
            self._fit_worker.request_stop()
            stopped = True
        if getattr(self, "_root_worker", None) and self._root_worker.isRunning():
            self._root_worker.request_stop()
            stopped = True
        if stopped:
            self._append_log(self._tr("正在停止任务...", "Stopping task..."))

    def _on_worker_cancelled(self):
        """Handle worker cancellation."""
        self._append_log(self._tr("任务已取消", "Task cancelled"))

    # --------------------------------------------------------- Main Action --
    def run_calculation(self):
        # Check if a worker is running - if so, stop it
        if self._has_running_worker():
            self._stop_current_worker()
            return

        self._reset_csv_data()

        mode = self.mode_combo.currentData()
        data_path, manual_content = self._active_data_source()
        if mode == "root_solving":
            self._run_root_solving_mode(data_path=data_path, manual_content=manual_content)
            return

        constants_editor = getattr(self, "error_constants_editor", None)
        manual_constants_content = (
            constants_editor.text().strip()
            if constants_editor is not None and constants_editor.isChecked()
            else ""
        )
        use_file_mode = getattr(self, "use_file_checkbox", None).isChecked() if hasattr(self, "use_file_checkbox") else False

        if data_path:
            data_path = _safe_resolve_path(str(data_path))
            if not data_path.exists() or data_path.is_dir():
                QMessageBox.critical(
                    self,
                    self._tr("错误", "Error"),
                    self._tr("请选择有效的数据文件路径。", "Please select a valid data file path."),
                )
                return
        if use_file_mode and not data_path:
            QMessageBox.critical(
                self,
                self._tr("错误", "Error"),
                self._tr("已勾选「使用数据文件」，但未提供有效路径。", "Data file is enabled but no valid path provided."),
            )
            return
        if not data_path and not manual_content:
            QMessageBox.critical(
                self,
                self._tr("错误", "Error"),
                self._tr("请至少提供数据文件或手动输入数据。", "Please provide at least a data file or manual input."),
            )
            return

        generate_latex = self.generate_latex_checkbox.isChecked()
        generate_plots = self.generate_plots_checkbox.isChecked() if hasattr(self, "generate_plots_checkbox") else True
        try:
            caption = self._caption_value(require=generate_latex)
        except ValueError as exc:
            QMessageBox.critical(self, self._tr("错误", "Error"), self._localize_text(str(exc)))
            return
        output_path_text = self.output_file_edit.text().strip()
        if generate_latex:
            if not output_path_text:
                QMessageBox.critical(
                    self,
                    self._tr("错误", "Error"),
                    self._tr("请在「选项」中设置 LaTeX 输出路径。", "Please set LaTeX output path in Options."),
                )
                return
            output_candidate = _safe_resolve_path(output_path_text)
            if not output_candidate.parent.exists():
                msg_zh = f"输出目录不存在: {output_candidate.parent}"
                msg_en = f"Output directory does not exist: {output_candidate.parent}"
                QMessageBox.critical(
                    self,
                    self._tr("错误", "Error"),
                    self._tr(msg_zh, msg_en),
                )
                return
            output_path = str(output_candidate)
        else:
            output_path = ""

        use_dcolumn = self.dcolumn_checkbox.isChecked()
        verbose = self.verbose_checkbox.isChecked()
        uncertainty_digits = self.uncertainty_digits_spin.value() if hasattr(self, "uncertainty_digits_spin") else 3
        method_choice = self.method_combo.currentData()
        mp_precision = None
        try:
            if mode == "statistics":
                mp_precision = self._read_precision()
            if method_choice in self.mpmath_methods or method_choice == "custom":
                mp_precision = self._read_precision()
            power_config = None
            custom_formula = None
            if method_choice == "power_law":
                power_config = self._build_power_law_config(mp_precision)
            elif method_choice == "custom":
                custom_formula = self.custom_formula_edit.toPlainText().strip()
                if not custom_formula:
                    QMessageBox.critical(
                        self,
                        self._tr("错误", "Error"),
                        self._tr("请填写自定义公式。", "Please enter a custom formula."),
                    )
                    return
        except Exception as exc:  # noqa: BLE001
            localized = self._localize_text(str(exc))
            QMessageBox.critical(self, self._tr("错误", "Error"), localized)
            return
        uncertainty_col = None
        if hasattr(self, "uncertainty_combo"):
            data = self.uncertainty_combo.currentData()
            if isinstance(data, str) and data.strip():
                uncertainty_col = data.strip()
            else:
                uncertainty_col = self.uncertainty_combo.currentText().strip() or None

        # Get Levin u-transform parameters if applicable
        levin_variant = "u"  # default
        if hasattr(self, "levin_variant_combo"):
            levin_variant = self.levin_variant_combo.currentData() or "u"

        # Note: levin_order is currently UI-only; backend support may be needed
        # levin_order = self.levin_order_spin.value() if hasattr(self, "levin_order_spin") else 2

        options = ExtrapolationOptions(
            method=method_choice,
            power_law_config=power_config,
            uncertainty_column=uncertainty_col,
            mp_precision=mp_precision,
            levin_variant=levin_variant,
            custom_formula=custom_formula,
            uncertainty_digits=uncertainty_digits,
        )

        capture_stream = io.StringIO() if verbose else None
        stdout_cm = redirect_stdout(capture_stream) if capture_stream else nullcontext()
        stderr_cm = redirect_stderr(capture_stream) if capture_stream else nullcontext()
        precision_cm = _mp_precision_guard(mp_precision)

        target_tab_index = self.result_tab_index
        try:
            mode = self.mode_combo.currentData()
            if mode in {"extrapolation", "error"}:
                error_method = "taylor"
                error_order = 1
                error_mc_samples = None
                error_mc_seed = None
                if mode == "error":
                    if hasattr(self, "error_method_combo"):
                        error_method = self.error_method_combo.currentData() or "taylor"
                    if hasattr(self, "error_order_spin"):
                        error_order = int(self.error_order_spin.value())
                    if hasattr(self, "error_mc_samples_spin"):
                        error_mc_samples = int(self.error_mc_samples_spin.value())
                    if hasattr(self, "error_mc_seed_edit"):
                        seed_text = (self.error_mc_seed_edit.text() or "").strip()
                        if seed_text:
                            try:
                                error_mc_seed = int(seed_text)
                            except ValueError:
                                QMessageBox.critical(
                                    self,
                                    self._tr("错误", "Error"),
                                    self._tr("随机种子必须是整数（或留空）。", "Seed must be an integer (or left blank)."),
                                )
                                return
                job = CalcJob(
                    mode=mode,
                    data_path=data_path,
                    manual_content=manual_content,
                    manual_constants=manual_constants_content,
                    constants_file_path=self.constants_file_edit.text().strip() if hasattr(self, "constants_file_edit") else None,
                    options=options,
                    caption=caption,
                    generate_latex=generate_latex,
                    output_path=output_path,
                    use_dcolumn=use_dcolumn,
                    verbose=verbose,
                    render_plots=generate_plots,
                    constants_enabled=constants_editor.isChecked() if constants_editor is not None else False,
                    use_constants_file=self.use_constants_file_checkbox.isChecked() if hasattr(self, "use_constants_file_checkbox") else False,
                    formula=self.formula_edit.toPlainText().strip() if mode == "error" else None,
                    error_propagation_method=error_method,
                    error_propagation_order=error_order,
                    error_mc_samples=error_mc_samples,
                    error_mc_seed=error_mc_seed,
                    lang="en" if self._is_en() else "zh",
                    latex_digits=self.latex_input_precision_spin.value() if hasattr(self, "latex_input_precision_spin") else 16,
                    latex_group_size=self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3,
                    uncertainty_digits=uncertainty_digits,
                )
                worker = CalcWorker(job)
                worker.finished_ok.connect(self._on_calc_finished)
                worker.failed.connect(self._on_calc_failed)
                worker.finished.connect(self._on_calc_thread_done)
                worker.cancelled.connect(self._on_worker_cancelled)
                if verbose:
                    worker.log_ready.connect(self._append_log)
                self._calc_worker = worker
                self._set_button_to_stop_mode()
                worker.start()
                return
            if mode == "statistics":
                headers, rows, sigma_rows, segments, _ = self._collect_batched_fitting_dataset(precision_hint=self._peek_user_precision())
                dataset = (headers, rows, sigma_rows)
                job = CalcJob(
                    mode=mode,
                    data_path=None,
                    manual_content="",
                    manual_constants="",
                    constants_file_path=None,
                    options=SimpleNamespace(mp_precision=mp_precision or mp.mp.dps, warnings=[]),
                    caption=caption,
                    generate_latex=generate_latex,
                    output_path=output_path,
                    use_dcolumn=use_dcolumn,
                    verbose=verbose,
                    render_plots=generate_plots,
                    constants_enabled=False,
                    use_constants_file=False,
                    lang="en" if self._is_en() else "zh",
                    stats_value_col=self.stats_value_column_edit.text().strip(),
                    stats_sigma_col=self.stats_sigma_column_edit.text().strip(),
                    stats_mode=self.stats_mode_combo.currentData(),
                    stats_sample=self.stats_sample_checkbox.isChecked(),
                    stats_weighted_variance=self.stats_weight_variance_checkbox.isChecked(),
                    dataset=dataset,
                    latex_digits=self.latex_input_precision_spin.value(),
                    latex_group_size=self.latex_group_size_spin.value() if hasattr(self, "latex_group_size_spin") else 3,
                    segments=segments,
                    uncertainty_digits=uncertainty_digits,
                )
                worker = CalcWorker(job)
                worker.finished_ok.connect(self._on_calc_finished)
                worker.failed.connect(self._on_calc_failed)
                worker.finished.connect(self._on_calc_thread_done)
                worker.cancelled.connect(self._on_worker_cancelled)
                if verbose:
                    worker.log_ready.connect(self._append_log)
                self._calc_worker = worker
                self._set_button_to_stop_mode()
                worker.start()
                return
            if mode == "fitting":
                started = self._run_fitting_mode(generate_latex, output_path, verbose, render_plots=generate_plots)
                background_running = bool(
                    self._fit_worker and self._fit_worker.isRunning()
                )
                if background_running and started:
                    self._append_log(self._tr("拟合已在后台运行…", "Fitting is running in the background…"))
                return
            with precision_cm, stdout_cm, stderr_cm:
                # fallback for any remaining synchronous paths
                self._run_fitting_mode(generate_latex, output_path, verbose)
                target_tab_index = self.result_tab_index
            QMessageBox.information(
                self,
                self._tr("完成", "Done"),
                self._tr("计算完成，请查看结果。", "Finished. Please check the results."),
            )
            self.tabs.setCurrentIndex(target_tab_index)
        except Exception as exc:
            import traceback

            tb = traceback.format_exc()
            if tb:
                self._append_log(tb)
            message = str(exc).strip() or f"{exc.__class__.__name__}"
            QMessageBox.critical(
                self,
                self._tr("计算失败", "Calculation failed"),
                message,
            )
            self._append_log(self._tr(f"发生错误: {message}", f"Error: {message}"))
        finally:
            if capture_stream:
                captured = capture_stream.getvalue().strip()
                if captured:
                    self._append_log(captured)

    def _on_calc_finished(self, result: CalcResult):
        for log in result.logs:
            self._append_log(log)
        latex_path = result.latex_path
        try:
            if result.mode == "extrapolation":
                headers = result.payload.get("headers", [])
                data_rows = result.payload.get("data_rows", [])
                results = result.payload.get("results", [])
                plot_bytes = result.payload.get("plots")
                render_plots = result.payload.get("render_plots", True)
                precision_used = result.payload.get("precision_used")
                if precision_used:
                    self._current_precision = precision_used
                current_ref: object | None = None
                if hasattr(self, "uncertainty_combo") and self.uncertainty_combo.count() > 0:
                    current_ref = self.uncertainty_combo.currentData()
                    if current_ref is None:
                        current_ref = self.uncertainty_combo.currentText().strip()
                self._refresh_uncertainty_selector(headers)
                if current_ref and hasattr(self, "uncertainty_combo"):
                    idx = self.uncertainty_combo.findData(current_ref)
                    if idx < 0 and isinstance(current_ref, str) and current_ref.strip():
                        idx = self.uncertainty_combo.findText(current_ref.strip())
                    if idx >= 0:
                        self.uncertainty_combo.setCurrentIndex(idx)
                self._show_extrapolation_results(
                    headers,
                    data_rows,
                    results,
                    precision_used=precision_used,
                    plot_bytes_list=plot_bytes,
                    render_plots=render_plots,
                )
            elif result.mode == "error":
                headers = result.payload.get("headers", [])
                parsed = result.payload.get("parsed_data", [])
                results = result.payload.get("results", [])
                formula = result.payload.get("formula", "")
                precision_used = result.payload.get("precision_used")
                if precision_used:
                    self._current_precision = precision_used
                self._show_error_results(headers, parsed, results, formula)
                breakdown = result.payload.get("contribution_breakdown")
                plot_bytes = result.payload.get("contribution_plot")
                row_plots = result.payload.get("row_contribution_plots")
                if breakdown or plot_bytes:
                    self._display_error_contributions(breakdown or [], plot_bytes)
                if row_plots:
                    figure_paths: list[Path] = []
                    for idx, plot in enumerate(row_plots, 1):
                        if not plot:
                            continue
                        img_path = self._save_batch_figure(plot, "", idx, prefix="error")
                        if img_path:
                            figure_paths.append(img_path)
                    self._set_image_list("error", figure_paths)
            elif result.mode == "statistics":
                precision_used = result.payload.get("precision_used")
                if precision_used:
                    self._current_precision = precision_used
                render_plots = result.payload.get("render_plots", True)
                if "batches" in result.payload:
                    value_col = result.payload.get("value_col", "")
                    batches = result.payload.get("batches", [])
                    self._display_statistics_batches(batches, value_col, render_plots=render_plots)
                else:
                    stats_result = result.payload.get("result", {})
                    value_col = result.payload.get("value_col", "")
                    row_count = result.payload.get("row_count", 0)
                    values = result.payload.get("values")
                    sigmas = result.payload.get("sigmas")
                    self._display_statistics_result(
                        stats_result,
                        value_col,
                        row_count,
                        values=values,
                        sigmas=sigmas,
                        render_plots=render_plots,
                    )
            if latex_path:
                self._load_latex_into_editor(latex_path)
            if result.warnings:
                self._emit_option_warnings(SimpleNamespace(warnings=list(result.warnings)))
            QMessageBox.information(self, self._tr("完成", "Done"), self._tr("计算完成，请查看结果。", "Finished. Please check the results."))
            self.tabs.setCurrentIndex(self.result_tab_index)
        except Exception as exc:  # noqa: BLE001
            import traceback

            self._append_log(traceback.format_exc())
            localized = self._localize_text(str(exc))
            QMessageBox.critical(self, self._tr("计算失败", "Calculation failed"), localized)

    def _on_calc_failed(self, message: str):
        localized = self._localize_text(message)
        QMessageBox.critical(self, self._tr("计算失败", "Calculation failed"), localized)
        log_msg = self._tr(f"发生错误: {localized}", f"Error: {localized}")
        self._append_log(log_msg)

    def _on_calc_thread_done(self):
        self._set_button_to_run_mode()
        if self._calc_worker:
            try:
                self._calc_worker.finished_ok.disconnect()
                self._calc_worker.failed.disconnect()
                self._calc_worker.finished.disconnect()
                self._calc_worker.cancelled.disconnect()
            except (RuntimeError, TypeError):
                pass
            try:
                self._calc_worker.deleteLater()
            except Exception:
                pass
        self._calc_worker = None

    def _run_root_solving_mode(self, *, data_path=None, manual_content: str = ""):
        try:
            job = self._build_root_solving_job(data_path=data_path, manual_content=manual_content)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self._tr("错误", "Error"), self._localize_text(str(exc)))
            return
        worker = RootSolvingWorker(job)
        worker.finished_ok.connect(self._on_root_solving_finished)
        worker.failed.connect(self._on_root_solving_failed)
        worker.finished.connect(self._on_root_solving_thread_done)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.log_ready.connect(self._append_log)
        self._root_worker = worker
        self._set_button_to_stop_mode()
        worker.start()

    def _on_root_solving_finished(self, payload: dict[str, object]):
        log = str(payload.get("log", "")).strip()
        if log:
            self._append_log(log)
        warnings = payload.get("warnings")
        if isinstance(warnings, list):
            for warning in warnings:
                if warning:
                    self._append_log(self._tr(f"警告: {warning}", f"Warning: {warning}"))
        markdown = str(payload.get("markdown", ""))
        csv_rows = payload.get("csv_rows")
        csv_headers = payload.get("csv_headers")
        self._set_result_text(markdown)
        if isinstance(csv_rows, list) and csv_rows:
            headers = [str(header) for header in csv_headers] if isinstance(csv_headers, list) else None
            self._set_csv_data(csv_rows, headers, suggestion="root_solving_results.csv")
        else:
            self._reset_csv_data()
        self._remember_last_result("root_solving", dict(payload))
        QMessageBox.information(
            self,
            self._tr("完成", "Done"),
            self._tr("计算完成，请查看结果。", "Finished. Please check the results."),
        )
        self.tabs.setCurrentIndex(self.result_tab_index)

    def _on_root_solving_failed(self, message: str):
        localized = self._localize_text(message)
        QMessageBox.critical(self, self._tr("计算失败", "Calculation failed"), localized)
        self._append_log(self._tr(f"发生错误: {localized}", f"Error: {localized}"))

    def _on_root_solving_thread_done(self):
        self._set_button_to_run_mode()
        worker = getattr(self, "_root_worker", None)
        if worker:
            try:
                worker.finished_ok.disconnect()
                worker.failed.disconnect()
                worker.finished.disconnect()
                worker.cancelled.disconnect()
                worker.log_ready.disconnect()
            except (RuntimeError, TypeError):
                pass
            try:
                worker.deleteLater()
            except Exception:
                pass
        self._root_worker = None

    def _cleanup_workers(self):
        """Ensure background threads are stopped when the app exits."""
        for attr in ("_fit_worker", "_calc_worker", "_root_worker"):
            worker = getattr(self, attr, None)
            if not worker:
                continue
            try:
                if worker.isRunning():
                    worker.requestInterruption()
                    worker.wait(2000)
                    if worker.isRunning():
                        worker.terminate()
                        worker.wait(500)
            except Exception:
                pass
            try:
                worker.deleteLater()
            except Exception:
                pass
            setattr(self, attr, None)
        # 清理临时批次图像
        self._cleanup_temp_batch_images()

    def _show_extrapolation_results(
        self,
        headers,
        data_rows,
        results,
        precision_used: int | None = None,
        plot_bytes_list: list[bytes | None] | None = None,
        render_plots: bool = True,
    ):
        ref_col = ""
        if hasattr(self, "uncertainty_combo") and self.uncertainty_combo.count() > 0:
            ref_col = self.uncertainty_combo.currentText().strip()
        self._cleanup_temp_batch_images()
        figure_paths: list[Path] = []
        text, csv_rows = self._format_extrapolation_display(headers=headers, data_rows=data_rows, results=results, ref_col=ref_col)
        if render_plots:
            for idx, result in enumerate(results, 1):
                value, sigma, _ = self._split_extrapolation_result(result)
                plot_data = None
                if plot_bytes_list is not None and idx - 1 < len(plot_bytes_list):
                    plot_data = plot_bytes_list[idx - 1]
                if plot_data is None and render_plots:
                    plot_data = _render_extrapolation_plot_bytes(
                        data_rows[idx - 1],
                        value,
                        sigma,
                        idx,
                        is_en=self._is_en(),
                    )
                if plot_data:
                    img_path = self._save_batch_figure(plot_data, "", idx, prefix="extrap")
                    if img_path:
                        figure_paths.append(img_path)
        self._set_result_text(text)
        if csv_rows:
            self._set_csv_data(csv_rows, ["index", "value", "uncertainty", "latex"], suggestion="extrapolation_results.csv")
        else:
            self._reset_csv_data()
        if render_plots and figure_paths:
            self._set_image_list("extrap", figure_paths)
        else:
            self._image_mode = "extrap"
            self.current_extrap_figures = []
            self.current_extrap_index = 0
            self._result_plot_base_pixmap = None
            self.result_plot_bytes = None
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self._update_image_status()
        self._remember_last_result("extrapolation", {"headers": headers, "data_rows": data_rows, "results": results, "ref_col": ref_col})

    def _emit_option_warnings(self, options: ExtrapolationOptions | None):
        if not options or not getattr(options, "warnings", None):
            return

        def _localize(message: str) -> str:
            if " / " in message:
                zh, en = message.split(" / ", 1)
                return en if self._is_en() else zh
            return message

        def _is_info_message(msg: str) -> bool:
            """Check if a message is informational (not a real warning)."""
            # Filter out formula rewriting messages - these are info, not warnings
            info_keywords = [
                "rewritten to canonical",
                "已重写为使用列名",
                "Formula variables rewritten",
                "公式变量已重写",
                # Reference-column auto selection fallback (log only)
                "最大差异列",
                "Max-diff column",
            ]
            return any(keyword in msg for keyword in info_keywords)

        # Separate info messages (for log only) from real warnings
        warning_messages = []
        for msg in options.warnings:
            if not _is_info_message(msg):
                warning_messages.append(msg)

        # Log all messages (both info and warnings)
        for message in options.warnings:
            localized = _localize(message)
            is_info = _is_info_message(message)
            prefix = self._tr("信息", "Info") if is_info else self._tr("警告", "Warning")
            self._append_log(f"{prefix}: {localized}")

        # Only show dialog for real warnings, not info messages
        if warning_messages:
            localized_warnings = [_localize(msg) for msg in warning_messages]
            aggregated = "\n".join(localized_warnings)
            QMessageBox.warning(self, self._tr("警告", "Warning"), aggregated)

        options.warnings.clear()

    def _format_extrapolation_display(
        self,
        headers,
        data_rows,
        results,
        ref_col: str = "",
    ) -> tuple[str, list[dict[str, object]]]:
        """Return Markdown-formatted text and CSV rows for extrapolation results."""
        lines = [
            self._tr("## 外推结果", "## Extrapolation Results"),
            "",
            self._tr(f"**输入列**: {', '.join(headers)}", f"**Columns**: {', '.join(headers)}"),
            self._tr(f"**成功外推行数**: {len(results)}", f"**Successful rows**: {len(results)}"),
        ]
        if ref_col:
            lines.append(self._tr(f"**不确定度参考列**: {ref_col}", f"**Uncertainty reference**: {ref_col}"))
        lines.append("")

        precision_hint = getattr(self, "_current_precision", None)
        latex_digits = self.latex_input_precision_spin.value() if hasattr(self, "latex_input_precision_spin") else 16
        unc_digits = self._uncertainty_digits_value()
        csv_rows: list[dict[str, object]] = []

        # Markdown table header
        h_idx = self._tr("#", "#")
        h_val = self._tr("外推值", "Value")
        h_unc = self._tr("不确定度", "Uncertainty")
        h_ltx = self._tr("LaTeX", "LaTeX")
        lines.append(f"| {h_idx} | {h_val} | {h_unc} | {h_ltx} |")
        lines.append("| --- | --- | --- | --- |")

        for idx, result in enumerate(results, 1):
            value, sigma, _ = self._split_extrapolation_result(result)
            value_str = self._format_display_value(value)
            sigma_str = self._format_display_uncertainty(sigma)
            latex_text, is_latex = format_uncertainty_display_latex(
                value,
                sigma,
                mp_precision=precision_hint,
                latex_digits=latex_digits,
                uncertainty_digits=unc_digits,
            )
            latex_display = self._latex_to_plain_uncertainty(latex_text) if is_latex else latex_text
            _v = value_str.replace("|", "\\|")
            _s = sigma_str.replace("|", "\\|")
            _l = latex_display.replace("|", "\\|")
            lines.append(f"| {idx} | {_v} | {_s} | {_l} |")
            csv_rows.append(
                {
                    "index": idx,
                    "value": value_str,
                    "uncertainty": sigma_str,
                    "latex": latex_display,
                }
            )
        lines.append("")
        return "\n".join(lines), csv_rows

    def _format_error_display(
        self,
        headers,
        data_rows,
        results,
        formula: str,
    ) -> tuple[str, list[dict[str, object]]]:
        """Return Markdown-formatted text and CSV rows for error propagation results."""
        lines = [
            self._tr("## 误差传递结果", "## Error Propagation Results"),
            "",
            self._tr(f"**公式**: `{formula}`", f"**Formula**: `{formula}`"),
            self._tr(f"**数据行数**: {len(data_rows)}", f"**Rows**: {len(data_rows)}"),
            "",
        ]
        latex_digits = self.latex_input_precision_spin.value() if hasattr(self, "latex_input_precision_spin") else 16
        unc_digits = self._uncertainty_digits_value()
        precision_hint = getattr(self, "_current_precision", None)
        csv_rows: list[dict[str, object]] = []

        # Markdown table
        h_idx = self._tr("#", "#")
        h_val = self._tr("值", "Value")
        h_unc = self._tr("不确定度", "Uncertainty")
        h_ltx = self._tr("LaTeX", "LaTeX")
        lines.append(f"| {h_idx} | {h_val} | {h_unc} | {h_ltx} |")
        lines.append("| --- | --- | --- | --- |")

        for idx, (_, result) in enumerate(zip(data_rows, results), 1):
            value = getattr(result, "value", result)
            sigma = getattr(result, "uncertainty", mp.mpf("0"))
            if sigma is None:
                sigma = mp.mpf("0")
            value_str = self._format_display_value(value)
            sigma_str = self._format_display_uncertainty(sigma)
            latex_text, is_latex = format_uncertainty_display_latex(
                value,
                sigma,
                mp_precision=precision_hint,
                latex_digits=latex_digits,
                uncertainty_digits=unc_digits,
            )
            latex_display = self._latex_to_plain_uncertainty(latex_text) if is_latex else latex_text
            _v = value_str.replace("|", "\\|")
            _s = sigma_str.replace("|", "\\|")
            _l = latex_display.replace("|", "\\|")
            lines.append(f"| {idx} | {_v} | {_s} | {_l} |")
            csv_rows.append(
                {
                    "index": idx,
                    "value": value_str,
                    "uncertainty": sigma_str,
                    "latex": latex_display,
                }
            )
        lines.append("")
        return "\n".join(lines), csv_rows

    def _show_error_results(self, headers, data_rows, results, formula):
        text, csv_rows = self._format_error_display(headers=headers, data_rows=data_rows, results=results, formula=formula)
        self._set_result_text(text)
        if csv_rows:
            self._set_csv_data(csv_rows, ["index", "value", "uncertainty", "latex"], suggestion="error_propagation_results.csv")
        else:
            self._reset_csv_data()
        self._remember_last_result("error", {"headers": headers, "data_rows": data_rows, "results": results, "formula": formula})

    def _split_extrapolation_result(self, result):
        return split_extrapolation_result(result)

    def _render_extrapolation_plot(self, row_values: tuple[mp.mpf, ...], value: mp.mpf, sigma: mp.mpf, idx: int) -> bytes | None:
        """Render a simple per-row extrapolation trend plot with error bar."""
        return _render_extrapolation_plot_bytes(row_values, value, sigma, idx, is_en=self._is_en())
