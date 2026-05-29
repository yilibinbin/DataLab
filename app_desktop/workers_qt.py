from __future__ import annotations

import io
from contextlib import redirect_stdout, redirect_stderr, nullcontext
from pathlib import Path

import mpmath as mp
from PySide6.QtCore import QThread, Signal

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
    FitJob,
    FitResultPayload,
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
        contrib_sum: dict[str, mp.mpf] = {}
        for entry in results:
            contribs = getattr(entry, "contributions", None)
            if not contribs:
                continue
            for name, value in contribs.items():
                try:
                    contrib_sum[name] = contrib_sum.get(name, mp.mpf("0")) + mp.mpf(value)
                except Exception:
                    continue
        if not contrib_sum:
            return [], None
        summary = self._build_contribution_summary(contrib_sum)
        plot_bytes: bytes | None = None
        if render_plot:
            try:
                plot_bytes = self._render_contribution_plot(summary, lang)
            except Exception:
                plot_bytes = None
        return summary, plot_bytes

    def _build_contribution_summary(self, contrib_map: dict[str, mp.mpf]) -> list[dict[str, object]]:
        if not contrib_map:
            return []
        total_var = sum(contrib_map.values())
        if total_var <= 0:
            total_var = mp.mpf("0")
        summary: list[dict[str, object]] = []
        for name, var in contrib_map.items():
            sigma = mp.sqrt(var) if var >= 0 else mp.mpf("0")
            percent = float(var / total_var * 100) if total_var != 0 else 0.0
            summary.append({"name": name, "variance": var, "sigma": sigma, "percent": percent})
        summary.sort(key=lambda item: item.get("variance", mp.mpf("0")), reverse=True)
        return summary

    def _render_contribution_plot(
        self, summary: list[dict[str, object]], lang: str, title_suffix: str | None = None
    ) -> bytes | None:
        if not summary:
            return None
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception:
            return None
        try:
            labels = [entry["name"] for entry in summary]
            percents = [float(entry.get("percent", 0.0)) for entry in summary]
            fig, ax = plt.subplots(figsize=(6.0, 0.45 * len(summary) + 1.2), dpi=180)
            y_pos = list(range(len(labels)))
            bars = ax.barh(y_pos, percents, color="#4f6bed")
            ax.invert_yaxis()
            xlabel = "Uncertainty contribution (%)" if lang == "en" else "不确定度贡献 (%)"
            ax.set_xlabel(xlabel)
            ax.set_xlim(0, max(100.0, (max(percents) if percents else 0) * 1.1))
            ax.set_yticks(y_pos, labels)
            for bar, pct in zip(bars, percents):
                ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2, f"{pct:.2f}%", va="center")
            ax.grid(axis="x", alpha=0.3, linestyle="--")
            base_title = "Uncertainty breakdown" if lang == "en" else "不确定度贡献分解"
            if title_suffix:
                base_title = f"{base_title} - {title_suffix}"
            ax.set_title(base_title)
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()
        except Exception:
            return None

    def _render_statistics_plot(
        self,
        values: list[mp.mpf],
        sigmas: list[mp.mpf | None] | None,
        stats_result: dict[str, object],
        batch_idx: int | None = None,
    ) -> bytes | None:
        if not values:
            return None
        try:
            import matplotlib

            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except Exception:
            return None
        try:
            xs = list(range(1, len(values) + 1))
            ys = [float(mp.mpf(v)) for v in values]
            yerr = None
            if sigmas and any(s is not None for s in sigmas):
                yerr = [abs(float(mp.mpf(s))) if s is not None else 0.0 for s in sigmas]
            mean_val = stats_result.get("mean", None)
            std_mean = stats_result.get("std_mean", None)
            mean_f = float(mean_val) if mean_val is not None else None
            std_mean_f = abs(float(std_mean)) if std_mean is not None else None

            fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=180)
            if yerr:
                ax.errorbar(
                    xs,
                    ys,
                    yerr=yerr,
                    fmt="o-",
                    color="#1f77b4",
                    ecolor="#555555",
                    capsize=4,
                    label=self._tr("数据", "Data"),
                )
            else:
                ax.plot(xs, ys, "o-", color="#1f77b4", label=self._tr("数据", "Data"))
            if mean_f is not None:
                ax.axhline(mean_f, color="#d62728", linestyle="--", label=self._tr("平均值", "Mean"))
                if std_mean_f is not None and std_mean_f > 0:
                    ax.fill_between(
                        [min(xs) - 0.2, max(xs) + 0.2],
                        mean_f - std_mean_f,
                        mean_f + std_mean_f,
                        color="#d62728",
                        alpha=0.15,
                        label=self._tr("平均值±标准误差", "Mean ± standard error"),
                    )
            ax.set_xlabel(self._tr("点序号", "Point index"))
            ax.set_ylabel(self._tr("数值", "Value"))
            title = self._tr("统计平均", "Statistical mean")
            if batch_idx is not None:
                title = f"{title} - {batch_idx}"
            ax.set_title(title)
            ax.grid(True, alpha=0.3)
            ax.legend(frameon=False)
            fig.tight_layout()
            buf = io.BytesIO()
            fig.savefig(buf, format="png")
            plt.close(fig)
            buf.seek(0)
            return buf.getvalue()
        except Exception:
            return None

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
        return workers_core._execute_fit_job_payload(self.job)


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
        return workers_core._execute_fit_job_payload(job)


__all__ = [
    "CalcWorker",
    "FitBatchWorker",
    "FitWorker",
]
