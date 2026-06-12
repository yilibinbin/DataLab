from __future__ import annotations

import io
import os
import signal
import subprocess
import tempfile
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QThread, Signal

from datalab_latex.formula_render_service import sanitize_formula_latex_source
from shared import latex_engine, pdf_preview_raster


@dataclass(frozen=True)
class TexRenderRequest:
    latex: str
    engine: str = "tectonic"
    dpi: int = 180
    timeout_seconds: float = 8.0


@dataclass(frozen=True)
class TexRenderResult:
    ok: bool
    latex: str
    png_bytes: bytes = b""
    engine: str = "tectonic"
    engine_path: str = ""
    error_message: str = ""
    cancelled: bool = False
    from_cache: bool = False


_TEX_RENDER_CACHE: dict[tuple[str, str, str, int], TexRenderResult] = {}
_TEX_RENDER_CACHE_LOCK = threading.Lock()


def clear_formula_tex_render_cache() -> None:
    with _TEX_RENDER_CACHE_LOCK:
        _TEX_RENDER_CACHE.clear()


def render_latex_to_png_bytes(
    request: TexRenderRequest,
    *,
    should_cancel: Callable[[], bool] | None = None,
) -> TexRenderResult:
    latex = request.latex or ""
    engine = (request.engine or "tectonic").strip() or "tectonic"
    if should_cancel is not None and should_cancel():
        return TexRenderResult(ok=False, latex=latex, engine=engine, cancelled=True)

    try:
        sanitized = sanitize_formula_latex_source(latex)
    except Exception as exc:  # noqa: BLE001
        return TexRenderResult(
            ok=False,
            latex=latex,
            engine=engine,
            error_message=str(exc) or exc.__class__.__name__,
        )
    if not sanitized.strip():
        return TexRenderResult(
            ok=False,
            latex=sanitized,
            engine=engine,
            error_message="Formula is empty.",
        )

    dpi = max(72, min(300, int(request.dpi)))
    try:
        choice = latex_engine.resolve_engine(engine)
    except Exception as exc:  # noqa: BLE001
        return TexRenderResult(
            ok=False,
            latex=sanitized,
            engine=engine,
            error_message=str(exc) or exc.__class__.__name__,
        )
    if choice is None:
        return TexRenderResult(
            ok=False,
            latex=sanitized,
            engine=engine,
            error_message=f"LaTeX engine '{engine}' is unavailable.",
        )

    if should_cancel is not None and should_cancel():
        return TexRenderResult(ok=False, latex=sanitized, engine=engine, cancelled=True)

    key = (sanitized, engine, choice.path, dpi)
    with _TEX_RENDER_CACHE_LOCK:
        cached = _TEX_RENDER_CACHE.get(key)
    if cached is not None:
        return replace(cached, from_cache=True)

    try:
        with tempfile.TemporaryDirectory(prefix="datalab-formula-tex-") as tmp:
            tex_path = _write_formula_document(sanitized, Path(tmp))
            pdf_path = _compile_formula_document(
                tex_path=tex_path,
                engine_path=choice.path,
                engine=engine,
                timeout_seconds=float(request.timeout_seconds),
            )
            if should_cancel is not None and should_cancel():
                return TexRenderResult(ok=False, latex=sanitized, engine=engine, cancelled=True)
            images = pdf_preview_raster.convert_pdf_to_images(pdf_path, dpi=dpi, max_pages=1)
            if not images:
                raise RuntimeError("High-fidelity preview produced no pages.")
            buffer = io.BytesIO()
            images[0].save(buffer, format="PNG")
            result = TexRenderResult(
                ok=True,
                latex=sanitized,
                png_bytes=buffer.getvalue(),
                engine=engine,
                engine_path=choice.path,
            )
            with _TEX_RENDER_CACHE_LOCK:
                _TEX_RENDER_CACHE[key] = result
            return result
    except Exception as exc:  # noqa: BLE001
        return TexRenderResult(
            ok=False,
            latex=sanitized,
            engine=engine,
            engine_path=choice.path,
            error_message=str(exc) or exc.__class__.__name__,
        )


def _write_formula_document(latex: str, directory: Path) -> Path:
    tex_path = directory / "formula.tex"
    tex_path.write_text(
        "\n".join(
            [
                r"\documentclass{article}",
                r"\usepackage{amsmath}",
                r"\pagestyle{empty}",
                r"\begin{document}",
                r"\[",
                latex,
                r"\]",
                r"\end{document}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return tex_path


def _compile_formula_document(
    *,
    tex_path: Path,
    engine_path: str,
    engine: str,
    timeout_seconds: float,
) -> Path:
    argv = _build_compile_argv(engine_path, engine, tex_path)
    completed = _run_compile_process(argv, cwd=tex_path.parent, timeout_seconds=timeout_seconds)
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or f"{engine} failed with exit code {completed.returncode}"
        raise RuntimeError(detail)
    pdf_path = tex_path.with_suffix(".pdf")
    if not pdf_path.exists():
        raise RuntimeError("LaTeX engine did not produce a PDF.")
    return pdf_path


def _build_compile_argv(engine_path: str, engine: str, tex_path: Path) -> list[str]:
    engine_name = (engine or "").lower()
    if engine_name == "tectonic":
        argv = latex_engine.tectonic_compile_argv(engine_path, tex_path)
        if "--only-cached" not in argv:
            insert_at = argv.index("--") if "--" in argv else len(argv)
            argv.insert(insert_at, "--only-cached")
        return argv
    return [
        engine_path,
        "-interaction=nonstopmode",
        "-halt-on-error",
        "-no-shell-escape",
        tex_path.name,
    ]


def _run_compile_process(
    argv: list[str],
    *,
    cwd: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    creationflags = 0
    popen_kwargs: dict[str, object] = {
        "cwd": cwd,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        popen_kwargs["creationflags"] = creationflags
    else:
        popen_kwargs["start_new_session"] = True
    process = subprocess.Popen(argv, **popen_kwargs)
    try:
        stdout, stderr = process.communicate(timeout=max(0.1, float(timeout_seconds)))
    except subprocess.TimeoutExpired as exc:
        _terminate_process_group(process)
        raise RuntimeError("LaTeX formula preview timed out.") from exc
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    try:
        if os.name == "nt":
            process.kill()
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except OSError:
        process.kill()
    try:
        process.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "nt":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        except ProcessLookupError:
            return
        except OSError:
            process.kill()
            process.wait()


class FormulaTexRenderWorker(QThread):
    finished_ok = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, request: TexRenderRequest) -> None:
        super().__init__()
        self.request = request
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        result = render_latex_to_png_bytes(
            self.request,
            should_cancel=lambda: self._stop_requested,
        )
        if result.cancelled:
            self.cancelled.emit()
        elif result.ok:
            self.finished_ok.emit(result)
        else:
            self.failed.emit(result.error_message)
