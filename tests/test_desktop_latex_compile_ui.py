from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


class _DummySignal:
    def __init__(self) -> None:
        self.callbacks: list[Any] = []

    def connect(self, callback: Any) -> None:
        self.callbacks.append(callback)


class _DummyLatexCompileWorker:
    instances: list["_DummyLatexCompileWorker"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.completed = _DummySignal()
        self.finished = _DummySignal()
        self.started = False
        self.cancelled = False
        _DummyLatexCompileWorker.instances.append(self)

    def request_cancel(self) -> None:
        self.cancelled = True

    def request_kill(self) -> None:
        self.cancelled = True

    def isRunning(self) -> bool:
        return self.started

    def deleteLater(self) -> None:
        pass

    def start(self) -> None:
        self.started = True


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def test_compile_latex_to_pdf_returns_after_starting_background_worker(
    window: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Batch-10 Stage 3: compile_latex_to_pdf now lives in the compile mixin, so
    # its module namespace is where _LatexCompileWorker is resolved/patched.
    import app_desktop.window_latex_compile_mixin as latex_mixin

    fake_engine = tmp_path / "xelatex"
    fake_engine.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_engine.chmod(0o755)
    tex_path = tmp_path / "report.tex"
    window.current_latex_path = tex_path
    window.latex_edit.setPlainText(r"\documentclass{article}\begin{document}x\end{document}")
    selected_engine = window.latex_engine_combo.currentText()
    ensure_calls: list[str] = []

    def fake_ensure(engine: str) -> str:
        ensure_calls.append(engine)
        assert engine == selected_engine
        return str(fake_engine)

    monkeypatch.setattr(window, "_ensure_latex_engine", fake_ensure)
    monkeypatch.setattr(window, "_resolve_latex_engine_no_prompt", lambda _engine: None)
    _DummyLatexCompileWorker.instances.clear()
    monkeypatch.setattr(latex_mixin, "_LatexCompileWorker", _DummyLatexCompileWorker)

    window.compile_latex_to_pdf()
    worker = _DummyLatexCompileWorker.instances[0]
    try:
        assert tex_path.read_text(encoding="utf-8")
        assert len(_DummyLatexCompileWorker.instances) == 1
        assert worker.started is True
        assert worker.kwargs["target"] == tex_path
        assert worker.kwargs["pdf_path"] == tmp_path / "report.pdf"
        assert worker.kwargs["engine_name"] == selected_engine
        assert worker.kwargs["engine_path"] == fake_engine
        assert window._latex_compile_worker is worker
        assert window.latex_compile_button.isEnabled() is False
        assert worker.completed.callbacks == [window._on_latex_compile_completed]
        assert ensure_calls == [selected_engine]
        log_text = window.log_edit.toPlainText()
        assert selected_engine in log_text
        assert str(fake_engine) in log_text
    finally:
        worker.started = False
        window._latex_compile_worker = None
        progress = getattr(window, "_latex_compile_progress", None)
        if progress is not None:
            progress.close()
            window._latex_compile_progress = None


def test_compile_latex_falls_back_when_default_tectonic_missing(
    window: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Batch-10 Stage 3: compile_latex_to_pdf now lives in the compile mixin, so
    # its module namespace is where _LatexCompileWorker is resolved/patched.
    import app_desktop.window_latex_compile_mixin as latex_mixin

    fake_xelatex = tmp_path / "xelatex"
    fake_xelatex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_xelatex.chmod(0o755)
    fake_pdflatex = tmp_path / "pdflatex"
    fake_pdflatex.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_pdflatex.chmod(0o755)
    window.current_latex_path = tmp_path / "report.tex"
    window.latex_edit.setPlainText(r"\documentclass{article}\begin{document}x\end{document}")
    window.latex_engine_combo.setCurrentText("tectonic")

    ensure_calls: list[str] = []

    def fake_ensure(engine: str) -> str | None:
        ensure_calls.append(engine)
        return None

    def fake_resolve(engine: str) -> str | None:
        if engine == "xelatex":
            return str(fake_xelatex)
        if engine == "pdflatex":
            return str(fake_pdflatex)
        return None

    monkeypatch.setattr(window, "_ensure_latex_engine", fake_ensure)
    monkeypatch.setattr(window, "_resolve_latex_engine_no_prompt", fake_resolve)
    _DummyLatexCompileWorker.instances.clear()
    monkeypatch.setattr(latex_mixin, "_LatexCompileWorker", _DummyLatexCompileWorker)

    window.compile_latex_to_pdf()
    worker = _DummyLatexCompileWorker.instances[0]
    try:
        assert ensure_calls == []
        assert worker.started is True
        assert worker.kwargs["engine_name"] == "xelatex"
        assert worker.kwargs["engine_path"] == fake_xelatex
        assert worker.kwargs["fallback_name"] == "pdflatex"
        assert worker.kwargs["fallback_path"] == fake_pdflatex
        log_text = window.log_edit.toPlainText()
        assert "tectonic" in log_text
        assert "xelatex" in log_text
        assert "pdflatex" in log_text
        assert str(fake_xelatex) in log_text
        assert str(fake_pdflatex) in log_text
    finally:
        worker.started = False
        window._latex_compile_worker = None
        progress = getattr(window, "_latex_compile_progress", None)
        if progress is not None:
            progress.close()
            window._latex_compile_progress = None


@pytest.mark.parametrize(
    ("requested_engine", "available_fallback"),
    [("pdflatex", "xelatex"), ("xelatex", "pdflatex")],
)
def test_compile_latex_does_not_silently_fallback_for_missing_explicit_engine(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    requested_engine: str,
    available_fallback: str,
) -> None:
    # Batch-10 Stage 3: compile_latex_to_pdf now lives in the compile mixin, so
    # its module namespace is where _LatexCompileWorker is resolved/patched.
    import app_desktop.window_latex_compile_mixin as latex_mixin

    fake_fallback = tmp_path / available_fallback
    fake_fallback.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_fallback.chmod(0o755)
    window.current_latex_path = tmp_path / "report.tex"
    window.latex_edit.setPlainText(r"\documentclass{article}\begin{document}x\end{document}")
    window.latex_engine_combo.setCurrentText(requested_engine)
    ensure_calls: list[str] = []
    critical_calls: list[tuple[Any, ...]] = []

    def fake_ensure(engine: str) -> None:
        ensure_calls.append(engine)
        return None

    def fake_resolve(engine: str) -> str | None:
        return str(fake_fallback) if engine == available_fallback else None

    monkeypatch.setattr(window, "_ensure_latex_engine", fake_ensure)
    monkeypatch.setattr(window, "_resolve_latex_engine_no_prompt", fake_resolve)
    monkeypatch.setattr(latex_mixin.QMessageBox, "critical", lambda *args: critical_calls.append(args))
    _DummyLatexCompileWorker.instances.clear()
    monkeypatch.setattr(latex_mixin, "_LatexCompileWorker", _DummyLatexCompileWorker)

    window.compile_latex_to_pdf()

    assert ensure_calls == [requested_engine]
    assert _DummyLatexCompileWorker.instances == []
    assert getattr(window, "_latex_compile_worker", None) is None
    assert window.latex_compile_button.isEnabled() is True
    assert critical_calls
    assert requested_engine in window.log_edit.toPlainText() or window.log_edit.toPlainText() == ""
    assert str(fake_fallback) not in window.log_edit.toPlainText()


@pytest.mark.parametrize(
    ("requested_engine", "available_fallback"),
    [("pdflatex", "xelatex"), ("xelatex", "pdflatex")],
)
def test_compile_latex_explicit_engine_worker_has_no_retry_fallback(
    window: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    requested_engine: str,
    available_fallback: str,
) -> None:
    # Batch-10 Stage 3: compile_latex_to_pdf now lives in the compile mixin, so
    # its module namespace is where _LatexCompileWorker is resolved/patched.
    import app_desktop.window_latex_compile_mixin as latex_mixin

    fake_engine = tmp_path / requested_engine
    fake_engine.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_engine.chmod(0o755)
    fake_fallback = tmp_path / available_fallback
    fake_fallback.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_fallback.chmod(0o755)
    window.current_latex_path = tmp_path / "report.tex"
    window.latex_edit.setPlainText(r"\documentclass{article}\begin{document}x\end{document}")
    window.latex_engine_combo.setCurrentText(requested_engine)

    monkeypatch.setattr(window, "_ensure_latex_engine", lambda engine: str(fake_engine) if engine == requested_engine else None)
    monkeypatch.setattr(window, "_resolve_latex_engine_no_prompt", lambda engine: str(fake_fallback) if engine == available_fallback else None)
    _DummyLatexCompileWorker.instances.clear()
    monkeypatch.setattr(latex_mixin, "_LatexCompileWorker", _DummyLatexCompileWorker)

    window.compile_latex_to_pdf()
    worker = _DummyLatexCompileWorker.instances[0]
    try:
        assert worker.started is True
        assert worker.kwargs["engine_name"] == requested_engine
        assert worker.kwargs["engine_path"] == fake_engine
        assert worker.kwargs["fallback_name"] is None
        assert worker.kwargs["fallback_path"] is None
        assert str(fake_fallback) not in window.log_edit.toPlainText()
    finally:
        worker.started = False
        window._latex_compile_worker = None
        progress = getattr(window, "_latex_compile_progress", None)
        if progress is not None:
            progress.close()
            window._latex_compile_progress = None


def test_latex_compile_worker_participates_in_window_stop_lifecycle(
    window: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Batch-10 Stage 3: compile_latex_to_pdf now lives in the compile mixin, so
    # its module namespace is where _LatexCompileWorker is resolved/patched.
    import app_desktop.window_latex_compile_mixin as latex_mixin

    fake_engine = tmp_path / "xelatex"
    fake_engine.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_engine.chmod(0o755)
    window.current_latex_path = tmp_path / "report.tex"
    window.latex_edit.setPlainText(r"\documentclass{article}\begin{document}x\end{document}")
    monkeypatch.setattr(window, "_ensure_latex_engine", lambda _engine: str(fake_engine))
    _DummyLatexCompileWorker.instances.clear()
    monkeypatch.setattr(latex_mixin, "_LatexCompileWorker", _DummyLatexCompileWorker)

    window.compile_latex_to_pdf()
    worker = _DummyLatexCompileWorker.instances[0]
    try:
        assert window._has_running_worker() is True
        window._stop_current_worker()
        assert worker.cancelled is True
    finally:
        worker.started = False
        window._latex_compile_worker = None
        progress = getattr(window, "_latex_compile_progress", None)
        if progress is not None:
            progress.close()
            window._latex_compile_progress = None


def test_root_latex_ui_language_and_options_affect_generated_source_before_compile(
    window: Any, tmp_path: Path
) -> None:
    raw_rows = [
        {
            "input_row_index": "1",
            "root_index": "1",
            "name": "x",
            "value": "1234567.890123",
            "uncertainty": "0.00000123",
            "backend": "mpmath",
            "mode": "scalar",
        }
    ]

    window.root_equations_edit.setPlainText("x**2 - 2")
    window.root_unknowns_table.set_rows([{"name": "x", "initial": "1", "lower": "", "upper": ""}])
    window.caption_checkbox.setChecked(True)
    window.latex_group_size_spin.setValue(4)
    window.dcolumn_checkbox.setChecked(False)
    window.caption_edit.setText("中文标题")
    window._apply_language("zh")
    zh_job = window._build_root_solving_job(
        generate_latex=True,
        output_path=str(tmp_path / "zh.tex"),
    )
    assert zh_job.latex_language == "zh"
    window._write_root_latex_if_requested(
        {
            "generate_latex": True,
            "output_path": zh_job.output_path,
            "raw_rows": raw_rows,
            "latex_caption": zh_job.latex_caption,
            "latex_digits": zh_job.latex_digits,
            "uncertainty_digits": zh_job.uncertainty_digits,
            "latex_group_size": zh_job.latex_group_size,
            "latex_include_dcolumn": zh_job.latex_include_dcolumn,
            "latex_language": zh_job.latex_language,
        }
    )
    zh_source = window.latex_edit.toPlainText()

    window.latex_group_size_spin.setValue(0)
    window.dcolumn_checkbox.setChecked(True)
    window.caption_edit.setText("English caption")
    window._apply_language("en")
    en_job = window._build_root_solving_job(
        generate_latex=True,
        output_path=str(tmp_path / "en.tex"),
    )
    assert en_job.latex_language == "en"
    window._write_root_latex_if_requested(
        {
            "generate_latex": True,
            "output_path": en_job.output_path,
            "raw_rows": raw_rows,
            "latex_caption": en_job.latex_caption,
            "latex_digits": en_job.latex_digits,
            "uncertainty_digits": en_job.uncertainty_digits,
            "latex_group_size": en_job.latex_group_size,
            "latex_include_dcolumn": en_job.latex_include_dcolumn,
            "latex_language": en_job.latex_language,
        }
    )
    en_source = window.latex_edit.toPlainText()

    assert "中文标题" in zh_source
    assert "输入行" in zh_source
    assert "group-minimum-digits = 4" in zh_source
    assert "digit-group-size = 4" in zh_source
    assert r"\usepackage{dcolumn}" not in zh_source
    assert "English caption" in en_source
    assert "Input row" in en_source
    assert r"\usepackage{dcolumn}" in en_source
    assert "1.234567890123" in en_source


def test_run_engine_pdflatex_argv_includes_no_shell_escape(tmp_path: Path, monkeypatch: Any) -> None:
    # Opening and compiling an untrusted .tex must not be able to run shell commands,
    # so the pdflatex/xelatex argv passes -no-shell-escape (parity with the web path).
    from app_desktop import window_latex_pdf_mixin as mod

    QApplication.instance() or QApplication([])
    target = tmp_path / "doc.tex"
    target.write_text("\\documentclass{article}\\begin{document}x\\end{document}", encoding="utf-8")
    engine_path = tmp_path / "pdflatex"

    worker = mod._LatexCompileWorker(
        target=target,
        pdf_dir=tmp_path,
        engine_name="pdflatex",
        engine_path=engine_path,
        pdf_path=tmp_path / "doc.pdf",
    )

    captured: dict[str, Any] = {}

    class _FakeProc:
        returncode = 0

        def poll(self) -> int:
            return 0

        def communicate(self, timeout: Any = None) -> tuple[str, str]:
            return ("", "")

    def _fake_popen(cmd: Any, **kwargs: Any) -> _FakeProc:
        captured["cmd"] = list(cmd)
        return _FakeProc()

    monkeypatch.setattr(mod.subprocess, "Popen", _fake_popen)

    worker._run_engine("pdflatex", engine_path)

    assert "-no-shell-escape" in captured["cmd"]
    # The flag must precede the input filename so it is honored by the engine.
    assert captured["cmd"].index("-no-shell-escape") < captured["cmd"].index(target.name)
