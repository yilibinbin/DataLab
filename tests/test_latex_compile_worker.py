from __future__ import annotations

import subprocess
from pathlib import Path

from app_desktop.window_latex_pdf_mixin import (
    _LatexCompileWorker,
    _looks_like_plain_tex_output,
)


class _FakeProcess:
    def __init__(
        self,
        *,
        returncode: int = 0,
        stdout: str = "",
        stderr: str = "",
        timeout: bool = False,
        error: Exception | None = None,
        running: bool | None = None,
    ) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timeout = timeout
        self.error = error
        self.running = timeout if running is None else running
        self.killed = False
        self.terminated = False
        self.waited = False

    def communicate(self, timeout: int) -> tuple[str, str]:
        if self.timeout:
            raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
        if self.error is not None:
            self.running = True
            raise self.error
        return self.stdout, self.stderr

    def poll(self) -> int | None:
        return None if self.running else self.returncode

    def kill(self) -> None:
        self.killed = True
        self.running = False
        self.returncode = -9

    def wait(self) -> int:
        self.waited = True
        self.running = False
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.running = False
        self.returncode = -15


def test_plain_tex_detection_matches_existing_fallback_signal() -> None:
    assert _looks_like_plain_tex_output("format=pdftex")
    assert _looks_like_plain_tex_output("Undefined control sequence near \\documentclass")
    assert not _looks_like_plain_tex_output("LaTeX Warning: rerun to get cross-references right")


def test_latex_compile_worker_runs_fallback_after_plain_tex_failure(monkeypatch) -> None:
    processes = [
        _FakeProcess(returncode=1, stdout="format=pdftex"),
        _FakeProcess(returncode=0, stdout="ok"),
    ]

    def fake_popen(*args, **kwargs):
        return processes.pop(0)

    monkeypatch.setattr("app_desktop.window_latex_pdf_mixin.subprocess.Popen", fake_popen)
    worker = _LatexCompileWorker(
        target=Path("report.tex"),
        pdf_dir=Path("."),
        engine_name="pdflatex",
        engine_path=Path("/bin/pdflatex"),
        pdf_path=Path("report.pdf"),
        fallback_name="xelatex",
        fallback_path=Path("/bin/sh"),
    )
    outcomes = []
    worker.completed.connect(outcomes.append)

    worker.run()

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome.succeeded is True
    assert outcome.used_fallback == "xelatex"
    assert [run.engine for run in outcome.runs] == ["pdflatex", "xelatex"]
    assert outcome.pdf_path == Path("report.pdf")


def test_latex_compile_worker_reports_timeout_and_kills_process(monkeypatch) -> None:
    process = _FakeProcess(timeout=True)
    monkeypatch.setattr("app_desktop.window_latex_pdf_mixin.subprocess.Popen", lambda *args, **kwargs: process)
    worker = _LatexCompileWorker(
        target=Path("report.tex"),
        pdf_dir=Path("."),
        engine_name="xelatex",
        engine_path=Path("/bin/sh"),
        pdf_path=Path("report.pdf"),
    )
    outcomes = []
    worker.completed.connect(outcomes.append)

    worker.run()

    assert process.killed is True
    assert process.waited is True
    assert len(outcomes) == 1
    assert outcomes[0].timed_out is True
    assert outcomes[0].pdf_path == Path("report.pdf")


def test_latex_compile_worker_kills_process_on_generic_communicate_error(monkeypatch) -> None:
    process = _FakeProcess(error=RuntimeError("pipe broke"))
    monkeypatch.setattr("app_desktop.window_latex_pdf_mixin.subprocess.Popen", lambda *args, **kwargs: process)
    worker = _LatexCompileWorker(
        target=Path("report.tex"),
        pdf_dir=Path("."),
        engine_name="xelatex",
        engine_path=Path("/bin/sh"),
        pdf_path=Path("report.pdf"),
    )
    outcomes = []
    worker.completed.connect(outcomes.append)

    worker.run()

    assert process.killed is True
    assert process.waited is True
    assert len(outcomes) == 1
    assert "pipe broke" in outcomes[0].error


def test_latex_compile_worker_honors_cancel_requested_before_process_assignment(monkeypatch) -> None:
    process = _FakeProcess(returncode=0, stdout="ok", running=True)
    monkeypatch.setattr("app_desktop.window_latex_pdf_mixin.subprocess.Popen", lambda *args, **kwargs: process)
    worker = _LatexCompileWorker(
        target=Path("report.tex"),
        pdf_dir=Path("."),
        engine_name="xelatex",
        engine_path=Path("/bin/sh"),
        pdf_path=Path("report.pdf"),
    )
    outcomes = []
    worker.completed.connect(outcomes.append)

    worker.request_cancel()
    worker.run()

    assert process.killed is True
    assert len(outcomes) == 1
    assert outcomes[0].cancelled is True
