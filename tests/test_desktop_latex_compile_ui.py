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
    import app_desktop.window_latex_pdf_mixin as latex_mixin

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
        assert window._latex_compile_worker is worker
        assert window.latex_compile_button.isEnabled() is False
        assert ensure_calls == [selected_engine]
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
    import app_desktop.window_latex_pdf_mixin as latex_mixin

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
