from __future__ import annotations

import subprocess
from contextlib import redirect_stdout, redirect_stderr, nullcontext
from dataclasses import dataclass
from pathlib import Path

import mpmath as mp
from PySide6.QtCore import QThread, Signal

from shared.latex_engine import (
    EngineChoice,
    ensure_tectonic_installed,
    tectonic_compile_argv,
)

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


# Bilingual labels for every Tectonic install stage in one place — adding
# a new stage requires editing only this table (was two parallel dicts in
# the previous revision; quality reviewer flagged the drift risk).
_TECTONIC_STAGE_LABELS: dict[str, tuple[str, str]] = {
    "downloading": ("下载中…", "Downloading…"),
    "extracting": ("解压中…", "Extracting…"),
    "installed": ("安装完成。", "Installed."),
    "already-installed": ("已安装。", "Already installed."),
}


class _TectonicInstallWorker(QThread):
    """Background worker for ``ensure_tectonic_installed``.

    Runs the synchronous urllib download + tar/zip extract on a Qt
    thread so the GUI event loop stays responsive — a 30 MB pull on a
    slow connection would otherwise freeze the main thread for tens
    of seconds, and ``QApplication.processEvents()`` from a foreground
    busy-loop opens the door to re-entrant event-processing bugs.

    The worker exposes its outcome via two attributes:
    - ``result``: ``EngineChoice`` on success, ``None`` on failure
    - ``error``: the exception raised, or ``None`` on success
    Storing the exception itself (rather than a stringly-typed
    discriminator) lets the caller branch with ``isinstance`` against
    ``UnsupportedPlatformError`` / ``TectonicInstallCancelled``
    without re-encoding the type as a string.

    Cancellation is cooperative: ``request_stop()`` flips a flag that
    ``ensure_tectonic_installed`` polls between download chunks and
    raises ``TectonicInstallCancelled`` from. The caller wires the
    ``QProgressDialog.canceled`` signal to ``request_stop`` so the
    visible Cancel button actually does something.
    """

    stage = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.result: EngineChoice | None = None
        self.error: BaseException | None = None
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        # Reset state so a reused worker doesn't leak the previous
        # run's outcome into the next.
        self.result = None
        self.error = None
        try:
            self.result = ensure_tectonic_installed(
                progress_callback=self.stage.emit,
                cancel_check=lambda: self._stop_requested,
            )
        except Exception as exc:  # noqa: BLE001 — surface any error/cancel
            # Catch ``Exception`` (not ``BaseException``) so SystemExit
            # and KeyboardInterrupt propagate normally — swallowing
            # them into ``worker.error`` would silently subvert
            # interpreter-level shutdown.
            self.error = exc


@dataclass(frozen=True)
class _LatexEngineRun:
    engine: str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class _LatexCompileOutcome:
    runs: tuple[_LatexEngineRun, ...] = ()
    pdf_path: Path | None = None
    error: str | None = None
    timed_out: bool = False
    cancelled: bool = False
    used_fallback: str | None = None

    @property
    def succeeded(self) -> bool:
        return bool(self.runs) and self.runs[-1].returncode == 0 and not self.error


def _looks_like_plain_tex_output(output: str) -> bool:
    lower = output.lower()
    return "format=pdftex" in lower or "\\documentclass" in lower and "undefined control sequence" in lower


class _LatexCompileWorker(QThread):
    """Run external LaTeX compilers without blocking the Qt GUI thread."""

    completed = Signal(object)

    def __init__(
        self,
        *,
        target: Path,
        pdf_dir: Path,
        engine_name: str,
        engine_path: Path,
        pdf_path: Path,
        fallback_name: str | None = None,
        fallback_path: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._target = target
        self._pdf_dir = pdf_dir
        self._engine_name = engine_name
        self._engine_path = engine_path
        self._pdf_path = pdf_path
        self._fallback_name = fallback_name
        self._fallback_path = fallback_path
        self._process: subprocess.Popen[str] | None = None
        self._cancel_requested = False

    def request_cancel(self) -> None:
        self._cancel_requested = True
        proc = self._process
        if proc is not None and proc.poll() is None:
            proc.terminate()

    def request_kill(self) -> None:
        self._cancel_requested = True
        proc = self._process
        if proc is not None and proc.poll() is None:
            proc.kill()

    def run(self) -> None:
        runs: list[_LatexEngineRun] = []
        try:
            first = self._run_engine(self._engine_name, self._engine_path)
            runs.append(first)
            output_blob = f"{first.stdout}\n{first.stderr}"
            if (
                first.returncode != 0
                and self._fallback_name
                and self._fallback_path
                and self._fallback_path.exists()
                and _looks_like_plain_tex_output(output_blob)
                and not self._cancel_requested
            ):
                runs.append(self._run_engine(self._fallback_name, self._fallback_path))
                self.completed.emit(
                    _LatexCompileOutcome(
                        runs=tuple(runs),
                        pdf_path=self._pdf_path,
                        cancelled=self._cancel_requested,
                        used_fallback=self._fallback_name,
                    )
                )
                return
            self.completed.emit(
                _LatexCompileOutcome(
                    runs=tuple(runs),
                    pdf_path=self._pdf_path,
                    cancelled=self._cancel_requested,
                )
            )
        except FileNotFoundError as exc:
            self.completed.emit(_LatexCompileOutcome(runs=tuple(runs), pdf_path=self._pdf_path, error=str(exc)))
        except subprocess.TimeoutExpired:
            self.completed.emit(_LatexCompileOutcome(runs=tuple(runs), pdf_path=self._pdf_path, timed_out=True))
        except Exception as exc:  # noqa: BLE001
            import traceback

            self.completed.emit(
                _LatexCompileOutcome(
                    runs=tuple(runs),
                    pdf_path=self._pdf_path,
                    error=f"{exc}\n{traceback.format_exc()}",
                )
            )

    def _run_engine(self, engine: str, path: Path) -> _LatexEngineRun:
        if path.stem.lower().endswith("tectonic"):
            cmd = tectonic_compile_argv(str(path), self._target)
            timeout = 300
        else:
            # -no-shell-escape disables \write18 / \input{|...} so opening and compiling
            # an untrusted .tex cannot run shell commands, matching the hardened web path.
            cmd = [
                str(path),
                "-no-shell-escape",
                "-interaction=nonstopmode",
                "-halt-on-error",
                self._target.name,
            ]
            timeout = 120
        proc = subprocess.Popen(
            cmd,
            cwd=str(self._pdf_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._process = proc
        if self._cancel_requested and proc.poll() is None:
            proc.kill()
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            raise
        except Exception:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            raise
        finally:
            self._process = None
        if self._cancel_requested:
            return _LatexEngineRun(engine=engine, returncode=-15, stdout=stdout or "", stderr=stderr or "")
        return _LatexEngineRun(
            engine=engine,
            returncode=proc.returncode if proc is not None and proc.returncode is not None else -1,
            stdout=stdout or "",
            stderr=stderr or "",
        )


__all__ = [
    "CalcWorker",
    "FitBatchWorker",
    "FittingComparisonWorker",
    "FitWorker",
    "RootSolvingWorker",
    "_LatexCompileOutcome",
    "_LatexCompileWorker",
    "_LatexEngineRun",
    "_TectonicInstallWorker",
    "_TECTONIC_STAGE_LABELS",
    "_looks_like_plain_tex_output",
]
