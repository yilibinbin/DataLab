from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr, nullcontext
from pathlib import Path

import mpmath as mp
from PySide6.QtCore import QThread, Signal

from shared.error_contributions import (
    aggregate_contribution_summary,
    contribution_summary_rows,
    render_error_contribution_plot,
)

from data_extrapolation_latex_latest import (
    detect_used_error_propagation_inputs,
    UncertainValue,
)

from . import workers_core
from .workers_core import (
    CalcJob,
    CalcResult,
    FitBatchResultEntry,
    FitBatchTask,
    FittingComparisonJob,
    FittingComparisonResultPayload,
    FitJob,
    FitResultPayload,
    RootSolvingJob,
    _execute_calc_job,
    _safe_read_text,
)


class _StopRequested(Exception):
    """Internal exception used for cooperative cancellation."""


class _SignalLogger:
    """Forward writes to a Qt signal while keeping an in-memory copy."""

    def __init__(self, emit_callable):
        self._emit = emit_callable
        self._chunks: list[str] = []
        self._buffer = ""

    def write(self, data):
        if data is None:
            return
        text = str(data)
        if not text:
            return
        self._chunks.append(text)
        self._buffer += text
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line:
                self._emit(line)

    def flush(self):
        pass

    def consume_buffer(self):
        if self._buffer:
            self._emit(self._buffer)
            self._buffer = ""

    def captured_text(self) -> str:
        return "".join(self._chunks)



class CalcWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    log_ready = Signal(str)
    cancelled = Signal()

    def __init__(self, job: CalcJob):
        super().__init__()
        self.job = job
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def _check_cancelled(self):
        if self._stop_requested:
            raise _StopRequested()

    def _tr(self, zh: str, en: str) -> str:
        return en if getattr(self.job, "lang", "en") == "en" else zh

    def run(self):
        logger = _SignalLogger(self.log_ready.emit) if getattr(self.job, "verbose", False) else None
        stdout_cm = redirect_stdout(logger) if logger else nullcontext()
        stderr_cm = redirect_stderr(logger) if logger else nullcontext()

        if self._stop_requested:
            if logger:
                try:
                    self.log_ready.emit("[calc] cancelled before start")
                except Exception:
                    pass
            self.cancelled.emit()
            return

        try:
            with stdout_cm, stderr_cm:
                result = self._run_job()

            if self._stop_requested:
                if logger:
                    try:
                        self.log_ready.emit("[calc] cancelled")
                    except Exception:
                        pass
                self.cancelled.emit()
                return

            if logger:
                logger.consume_buffer()
                captured = logger.captured_text().strip()
                if captured:
                    result.logs.append(captured)
                    self.log_ready.emit(captured)
            self.finished_ok.emit(result)
        except _StopRequested:
            if logger:
                try:
                    self.log_ready.emit("[calc] cancelled")
                except Exception:
                    pass
            self.cancelled.emit()
            return
        except Exception as exc:  # noqa: BLE001
            if self._stop_requested:
                if logger:
                    try:
                        self.log_ready.emit("[calc] cancelled")
                    except Exception:
                        pass
                self.cancelled.emit()
                return
            captured = ""
            if logger:
                logger.consume_buffer()
                captured = logger.captured_text().strip()
            message = str(exc)
            if captured:
                self.log_ready.emit(captured)
            self.failed.emit(message)

    def _load_text(self, path: Path) -> str:
        return _safe_read_text(path)

    def _aggregate_error_contributions(
        self, results: list[UncertainValue], lang: str, render_plot: bool = True
    ) -> tuple[list[dict[str, object]], bytes | None]:
        summary = aggregate_contribution_summary(results)
        if not summary:
            return [], None
        plot_bytes: bytes | None = None
        if render_plot:
            try:
                plot_bytes = self._render_contribution_plot(summary, lang)
            except Exception:
                plot_bytes = None
        return summary, plot_bytes

    def _build_contribution_summary(self, contrib_map: dict[str, mp.mpf]) -> list[dict[str, object]]:
        return contribution_summary_rows(contrib_map)

    def _render_contribution_plot(
        self, summary: list[dict[str, object]], lang: str, title_suffix: str | None = None
    ) -> bytes | None:
        return render_error_contribution_plot(summary, lang, title_suffix=title_suffix)

    def _render_statistics_plot(
        self,
        values: list[mp.mpf],
        sigmas: list[mp.mpf | None] | None,
        stats_result: dict[str, object],
        batch_idx: int | None = None,
        value_unit: str | None = None,
    ) -> bytes | None:
        try:
            from shared.plotting import (
                render_statistics_plot_from_spec,
                statistics_plot_labels_with_unit,
                statistics_plot_spec_from_result,
                StatisticsPlotLabels,
            )
        except Exception:
            return None
        labels = StatisticsPlotLabels(
            data=self._tr("数据", "Data"),
            mean=self._tr("平均值", "Mean"),
            mean_band=self._tr("平均值±标准误差", "Mean ± standard error"),
            x_axis=self._tr("点序号", "Point index"),
            y_axis=self._tr("数值", "Value"),
            title=self._tr("统计平均", "Statistical mean"),
        )
        spec = statistics_plot_spec_from_result(
            values,
            sigmas,
            stats_result,
            statistics_plot_labels_with_unit(labels, value_unit),
            batch_suffix=f" - {batch_idx}" if batch_idx is not None else "",
        )
        if spec is None:
            return None
        return render_statistics_plot_from_spec(spec)

    def _render_statistics_plots(
        self,
        values: list[mp.mpf],
        sigmas: list[mp.mpf | None] | None,
        stats_result: dict[str, object],
        batch_idx: int | None = None,
        value_unit: str | None = None,
    ) -> list[bytes]:
        try:
            from shared.plotting import (
                render_statistics_plots_from_specs,
                statistics_plot_labels_with_unit,
                statistics_plot_specs_from_result,
                StatisticsPlotLabels,
            )
        except Exception:
            return []
        labels = StatisticsPlotLabels(
            data=self._tr("数据", "Data"),
            mean=self._tr("平均值", "Mean"),
            mean_band=self._tr("平均值±标准误差", "Mean ± standard error"),
            x_axis=self._tr("点序号", "Point index"),
            y_axis=self._tr("数值", "Value"),
            title=self._tr("统计平均", "Statistical mean"),
            median=self._tr("中位数", "Median"),
            histogram_title=self._tr("直方图", "Histogram"),
            box_title=self._tr("箱线图", "Box plot"),
            qq_title=self._tr("正态 QQ 图", "Normal QQ plot"),
            weighted_residual_title=self._tr("加权残差", "Weighted residuals"),
            frequency_axis=self._tr("频数", "Frequency"),
            theoretical_quantile_axis=self._tr("理论正态分位数", "Theoretical normal quantile"),
            sample_quantile_axis=self._tr("样本标准化分位数", "Sample standardized quantile"),
            residual_axis=self._tr("标准化残差", "Standardized residual"),
        )
        spec = statistics_plot_specs_from_result(
            values,
            sigmas,
            stats_result,
            statistics_plot_labels_with_unit(labels, value_unit),
            batch_suffix=f" - {batch_idx}" if batch_idx is not None else "",
        )
        return render_statistics_plots_from_specs(spec)

    def _detect_error_used_headers(self, headers: list[str], formula: str | None) -> list[str]:
        """Return headers referenced in the error formula based on AST parsing."""
        used_headers, _ = detect_used_error_propagation_inputs(headers, {}, formula or "")
        return used_headers

    def _run_job(self) -> CalcResult:
        return _execute_calc_job(
            self.job,
            stop_checker=self._check_cancelled,
            emit_log=self.log_ready.emit,
        )


class FitWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    log_ready = Signal(str)
    cancelled = Signal()

    def __init__(self, job: FitJob):
        super().__init__()
        self.job = job
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        verbose = getattr(self.job, "verbose", False)
        logger = _SignalLogger(self.log_ready.emit) if verbose else None
        stdout_cm = redirect_stdout(logger) if logger else nullcontext()
        stderr_cm = redirect_stderr(logger) if logger else nullcontext()
        if verbose:
            try:
                self.log_ready.emit(f"[fit] start rows={len(self.job.data_rows)} headers={self.job.headers}")
            except Exception:
                pass

        if self._stop_requested:
            if verbose:
                try:
                    self.log_ready.emit("[fit] cancelled before start")
                except Exception:
                    pass
            self.cancelled.emit()
            return

        try:
            with stdout_cm, stderr_cm:
                payload = self._run_fit()

            if self._stop_requested:
                if verbose:
                    try:
                        self.log_ready.emit("[fit] cancelled")
                    except Exception:
                        pass
                self.cancelled.emit()
                return

            if logger:
                logger.consume_buffer()
                captured = logger.captured_text().strip()
                if captured:
                    payload.logs.append(captured)
                    self.log_ready.emit(captured)
            self.finished_ok.emit(payload)
        except Exception as exc:  # noqa: BLE001
            if self._stop_requested:
                if verbose:
                    try:
                        self.log_ready.emit("[fit] cancelled")
                    except Exception:
                        pass
                self.cancelled.emit()
                return
            if logger:
                logger.consume_buffer()
                captured = logger.captured_text().strip()
            else:
                captured = ""
            message = f"{exc}"
            if captured:
                message += f"\n{captured}"
                self.log_ready.emit(captured)
            self.failed.emit(message)
        else:
            if verbose:
                try:
                    self.log_ready.emit("[fit] finished")
                except Exception:
                    pass

    def _run_fit(self) -> FitResultPayload:
        if workers_core._fit_job_requires_process_boundary(self.job):
            return workers_core._execute_fit_job_payload_subprocess(
                self.job,
                timeout_seconds=self.job.timeout_seconds,
                should_cancel=lambda: self._stop_requested,
            )
        return workers_core._execute_fit_job_payload(
            self.job,
            should_cancel=lambda: self._stop_requested,
        )


class FittingComparisonWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    log_ready = Signal(str)
    cancelled = Signal()

    def __init__(self, job: FittingComparisonJob):
        super().__init__()
        self.job = job
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        if self._stop_requested:
            self.cancelled.emit()
            return
        try:
            if self.job.verbose:
                self.log_ready.emit("[fit-comparison] start")
            payload = self._run_comparison()
            if self._stop_requested:
                self.cancelled.emit()
                return
            if self.job.verbose:
                self.log_ready.emit("[fit-comparison] finished")
            self.finished_ok.emit(payload)
        except Exception as exc:  # noqa: BLE001
            if self._stop_requested:
                self.cancelled.emit()
                return
            self.failed.emit(str(exc))

    def _run_comparison(self) -> FittingComparisonResultPayload:
        return workers_core._execute_fitting_comparison_job_payload(
            self.job,
            should_cancel=lambda: self._stop_requested,
        )


class RootSolvingWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    log_ready = Signal(str)
    cancelled = Signal()

    def __init__(self, job: RootSolvingJob):
        super().__init__()
        self.job = job
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        try:
            payload = self._run_root_solving()
            if self._stop_requested:
                self.cancelled.emit()
                return
            self.finished_ok.emit(payload)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            if self._stop_requested:
                self.cancelled.emit()
                return
            self.failed.emit(str(exc))

    def _run_root_solving(self) -> dict[str, object]:
        return workers_core._execute_root_solving_job_payload_subprocess(
            self.job,
            timeout_seconds=workers_core.ROOT_SOLVING_SUBPROCESS_TIMEOUT_SECONDS,
            should_cancel=lambda: self._stop_requested,
        )


class FitBatchWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    log_ready = Signal(str)
    cancelled = Signal()

    def __init__(self, tasks: list[FitBatchTask], capture_output: bool = False):
        super().__init__()
        self.tasks = tasks
        self.capture_output = capture_output
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def run(self):
        results: list[FitBatchResultEntry] = []

        if self._stop_requested:
            if self.capture_output:
                try:
                    self.log_ready.emit("[fit-batch] cancelled before start")
                except Exception:
                    pass
            self.cancelled.emit()
            return

        try:
            for task in self.tasks:
                if self._stop_requested:
                    if self.capture_output:
                        try:
                            self.log_ready.emit(f"[fit-batch] cancelled at task {task.index}")
                        except Exception:
                            pass
                    self.cancelled.emit()
                    return

                logger = _SignalLogger(self.log_ready.emit) if self.capture_output else None
                stdout_cm = redirect_stdout(logger) if logger else nullcontext()
                stderr_cm = redirect_stderr(logger) if logger else nullcontext()
                if self.capture_output:
                    try:
                        self.log_ready.emit(f"[fit-batch] start index={task.index} type=fit")
                    except Exception:
                        pass
                if task.fit_job is not None:
                    try:
                        with stdout_cm, stderr_cm:
                            payload = self._run_fit_task(task.fit_job)
                        captured = logger.captured_text().strip() if logger else ""
                        if logger:
                            logger.consume_buffer()
                        if captured:
                            payload.logs.append(captured)
                            self.log_ready.emit(captured)
                        results.append(
                            FitBatchResultEntry(
                                index=task.index,
                                kind="fit",
                                fit_payload=payload,
                                captured_log=captured,
                            )
                        )
                    except InterruptedError:
                        if logger:
                            logger.consume_buffer()
                        if self.capture_output:
                            try:
                                self.log_ready.emit(f"[fit-batch] cancelled at task {task.index}")
                            except Exception:
                                pass
                        self.cancelled.emit()
                        return
                    except Exception as exc:  # noqa: BLE001
                        captured = logger.captured_text().strip() if logger else ""
                        if logger:
                            logger.consume_buffer()
                        if self._stop_requested:
                            if self.capture_output:
                                try:
                                    self.log_ready.emit(f"[fit-batch] cancelled at task {task.index}")
                                except Exception:
                                    pass
                            self.cancelled.emit()
                            return
                        results.append(
                            FitBatchResultEntry(index=task.index, kind="error", error=str(exc), captured_log=captured)
                        )
                else:
                    results.append(
                        FitBatchResultEntry(index=task.index, kind="error", error="缺少任务配置 / Missing task configuration")
                    )
            self.finished_ok.emit(results)
        except Exception as exc:  # noqa: BLE001
            if self._stop_requested:
                if self.capture_output:
                    try:
                        self.log_ready.emit("[fit-batch] cancelled")
                    except Exception:
                        pass
                self.cancelled.emit()
                return
            self.failed.emit(str(exc))

    def _run_fit_task(self, job: FitJob) -> FitResultPayload:
        if workers_core._fit_job_requires_process_boundary(job):
            return workers_core._execute_fit_job_payload_subprocess(
                job,
                timeout_seconds=job.timeout_seconds,
                should_cancel=lambda: self._stop_requested,
            )
        return workers_core._execute_fit_job_payload(
            job,
            should_cancel=lambda: self._stop_requested,
        )


__all__ = [
    "CalcWorker",
    "FitBatchWorker",
    "FittingComparisonWorker",
    "FitWorker",
    "RootSolvingWorker",
]
