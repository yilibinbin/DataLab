from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEventLoop, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMessageBox,
    QProgressDialog,
)

try:
    from PIL import Image, ImageOps

    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    PIL_AVAILABLE = False
    Image = object  # type: ignore[assignment]
    ImageOps = object  # type: ignore[assignment]

from shared.latex_engine import (
    EngineChoice,
    MissingHomeDirectoryError,
    TectonicInstallCancelled,
    UnsupportedPlatformError,
    ensure_tectonic_installed,
    find_app_root,
    resolve_engine,
    tectonic_compile_argv,
)

from .resources import _ensure_default_path_augmented, _pil_to_qpixmap
from .workers_core import _safe_read_text, _safe_resolve_path


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
            cmd = [str(path), "-interaction=nonstopmode", "-halt-on-error", self._target.name]
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

class WindowLatexPdfMixin:
    # ----------------------------------------------------------- LaTeX ops --
    def open_latex_file(self):
        filename, _ = QFileDialog.getOpenFileName(
            self,
            self._tr("选择 LaTeX 文件", "Select LaTeX File"),
            "",
            "LaTeX (*.tex);;All Files (*)",
        )
        if filename:
            self._load_latex_into_editor(filename, show_message=True)

    def save_latex_editor(self):
        target = self._persist_latex_editor(silent=False)
        if target:
            msg_zh = f"LaTeX 文件已保存到:\n{target}"
            msg_en = f"LaTeX file saved to:\n{target}"
            QMessageBox.information(
                self,
                self._tr("保存成功", "Save Successful"),
                self._tr(msg_zh, msg_en),
            )

    def reload_latex_editor(self, show_message: bool = False):
        if not self.current_latex_path:
            QMessageBox.warning(
                self,
                self._tr("提示", "Notice"),
                self._tr("尚未加载任何 LaTeX 文件。", "No LaTeX file loaded yet."),
            )
            return
        self._load_latex_into_editor(self.current_latex_path, show_message=show_message)

    def compile_latex_to_pdf(self):
        if getattr(self, "_latex_compile_worker", None) is not None:
            QMessageBox.information(
                self,
                self._tr("正在编译", "Compilation Running"),
                self._tr("LaTeX 正在编译，请等待当前任务完成。", "LaTeX is already compiling; wait for it to finish."),
            )
            return
        target = self._persist_latex_editor(silent=True)
        if not target:
            return
        engine = self.latex_engine_combo.currentText()
        engine_exec = self._ensure_latex_engine(engine)
        if not engine_exec:
            msg_zh = f"未找到 {engine}，请安装或指定路径。"
            msg_en = f"{engine} not found. Please install it or specify the path."
            QMessageBox.critical(
                self,
                self._tr("缺少 LaTeX 引擎", "Missing LaTeX Engine"),
                self._tr(msg_zh, msg_en),
            )
            return
        engine_path = _safe_resolve_path(engine_exec)
        if not engine_path.exists():
            QMessageBox.critical(
                self,
                self._tr("缺少 LaTeX 引擎", "Missing LaTeX Engine"),
                self._tr("指定的 LaTeX 引擎不可用。", "Specified LaTeX engine is not available."),
            )
            return
        pdf_dir = target.parent
        pdf_path = pdf_dir / (target.stem + ".pdf")
        fallback = "xelatex" if engine.lower() == "pdflatex" else "pdflatex"
        alt_exec = self._resolve_latex_engine_no_prompt(fallback)
        fallback_path = _safe_resolve_path(alt_exec) if alt_exec else None
        if fallback_path is not None and not fallback_path.exists():
            fallback_path = None

        progress = QProgressDialog(
            self._tr("正在编译 LaTeX…", "Compiling LaTeX…"),
            self._tr("取消", "Cancel"),
            0,
            0,
            self,
        )
        progress.setWindowModality(Qt.NonModal)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)

        worker = _LatexCompileWorker(
            target=target,
            pdf_dir=pdf_dir,
            engine_name=engine,
            engine_path=engine_path,
            pdf_path=pdf_path,
            fallback_name=fallback if fallback_path is not None else None,
            fallback_path=fallback_path,
            parent=self,
        )
        self._latex_compile_worker = worker
        self._latex_compile_progress = progress
        if hasattr(self, "latex_compile_button"):
            self.latex_compile_button.setEnabled(False)
        progress.canceled.connect(worker.request_cancel)
        worker.completed.connect(self._on_latex_compile_completed)
        worker.finished.connect(worker.deleteLater)
        progress.show()
        worker.start()

    def _on_latex_compile_completed(self, outcome: _LatexCompileOutcome) -> None:
        progress = getattr(self, "_latex_compile_progress", None)
        if progress is not None:
            progress.close()
            progress.deleteLater()
        self._latex_compile_progress = None
        self._latex_compile_worker = None
        if hasattr(self, "latex_compile_button"):
            self.latex_compile_button.setEnabled(True)

        for run in outcome.runs:
            output_blob = f"{run.engine} 输出 (returncode={run.returncode}):\n{run.stdout}\n{run.stderr}"
            self._append_log(output_blob)

        if outcome.used_fallback:
            self._append_log(
                self._tr(
                    f"检测到 plain TeX 格式问题，已尝试改用 {outcome.used_fallback}。",
                    f"Detected a plain TeX format issue; retried with {outcome.used_fallback}.",
                )
            )

        if outcome.cancelled:
            self._append_log(self._tr("LaTeX 编译已取消。", "LaTeX compilation canceled."))
            return

        if outcome.timed_out:
            QMessageBox.critical(
                self,
                self._tr("编译失败", "Compilation Failed"),
                self._tr("LaTeX 编译超时。", "LaTeX compilation timed out."),
            )
            return

        if outcome.error:
            self._append_log(outcome.error)
            QMessageBox.critical(self, self._tr("编译失败", "Compilation Failed"), outcome.error)
            return

        if outcome.succeeded:
            pdf_path = outcome.pdf_path
            if pdf_path is None:
                QMessageBox.critical(
                    self,
                    self._tr("编译失败", "Compilation Failed"),
                    self._tr("缺少 PDF 输出路径。", "Missing PDF output path."),
                )
                return
            self.last_pdf_path = pdf_path
            if self._render_pdf_preview(pdf_path, force_reload=True):
                QMessageBox.information(
                    self,
                    self._tr("编译完成", "Compilation Complete"),
                    self._tr("PDF 已生成并加载到预览标签页。", "PDF generated and loaded in preview tab."),
                )
            else:
                msg_zh = f"PDF 已生成于 {pdf_path}."
                msg_en = f"PDF generated at {pdf_path}."
                QMessageBox.information(
                    self,
                    self._tr("编译完成", "Compilation Complete"),
                    self._tr(msg_zh, msg_en),
                )
        else:
            QMessageBox.critical(
                self,
                self._tr("编译失败", "Compilation Failed"),
                self._tr(
                    "LaTeX 编译失败，请查看日志并检查 pdflatex/xelatex 格式是否可用。",
                    "LaTeX compilation failed; check logs and ensure pdflatex/xelatex formats are available.",
                ),
            )

    def open_compiled_pdf(self):
        if not self.last_pdf_path or not self.last_pdf_path.exists():
            QMessageBox.warning(
                self,
                self._tr("提示", "Notice"),
                self._tr("还没有可查看的 PDF。", "No PDF available to view yet."),
            )
            return
        if sys.platform.startswith("darwin"):
            subprocess.Popen(["open", str(self.last_pdf_path)])
        elif os.name == "nt":
            os.startfile(self.last_pdf_path)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(self.last_pdf_path)])

    def _persist_latex_editor(self, silent: bool):
        target = self.current_latex_path
        if target is None:
            filename, _ = QFileDialog.getSaveFileName(
                self,
                self._tr("保存 LaTeX 文件", "Save LaTeX File"),
                "",
                "LaTeX (*.tex);;All Files (*)",
            )
            if not filename:
                return None
            target = _safe_resolve_path(filename)
            self.current_latex_path = target
            self.output_file_edit.setText(str(target))
        if not target.parent.exists():
            QMessageBox.critical(
                self,
                self._tr("保存失败", "Save Failed"),
                self._tr("目标目录不存在。", "Target directory does not exist."),
            )
            return None
        try:
            content = self.latex_edit.toPlainText()
            target.write_text(content, encoding="utf-8")
            self.latex_status_label.setText(self._tr(f"当前文件: {target.name}", f"Current file: {target.name}"))
            if not silent:
                self._append_log(self._tr(f"LaTeX 文件已保存: {target}", f"LaTeX file saved: {target}"))
            return target
        except Exception as exc:
            QMessageBox.critical(self, self._tr("保存失败", "Save Failed"), str(exc))
            return None

    def _load_latex_into_editor(self, path, show_message: bool = False):
        target = _safe_resolve_path(str(path))
        if not target.exists():
            msg_zh = f"找不到 LaTeX 文件:\n{target}"
            msg_en = f"LaTeX file not found:\n{target}"
            QMessageBox.critical(
                self,
                self._tr("读取失败", "Load Failed"),
                self._tr(msg_zh, msg_en),
            )
            return
        try:
            content = _safe_read_text(target)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, self._tr("读取失败", "Load Failed"), str(exc))
            return
        self.current_latex_path = target
        self.latex_edit.setPlainText(content)
        self.latex_status_label.setText(self._tr(f"当前文件: {target.name}", f"Current file: {target.name}"))
        self.output_file_edit.setText(str(target))
        self.last_pdf_path = None
        self.pdf_base_images = []
        self.pdf_status_label.setText(self._tr("暂无 PDF 预览", "No PDF preview"))
        self._append_log(self._tr(f"已加载 LaTeX 文件: {target}", f"Loaded LaTeX file: {target}"))
        if show_message:
            QMessageBox.information(
                self,
                self._tr("已载入", "Reloaded"),
                self._tr(f"重新载入: {target}", f"Reloaded: {target}"),
            )

    # ----------------------------------------------------------- PDF Preview --
    def _apply_pdf_zoom(self, value: float):
        value = max(0.35, min(value, 4.0))
        if abs(self.pdf_zoom - value) < 0.01:
            return
        self.pdf_zoom = round(value, 2)
        if hasattr(self, "pdf_zoom_spin"):
            try:
                self.pdf_zoom_spin.blockSignals(True)
                self.pdf_zoom_spin.setValue(self.pdf_zoom * 100.0)
            finally:
                self.pdf_zoom_spin.blockSignals(False)
        if self.last_pdf_path and self.last_pdf_path.exists():
            self._render_pdf_preview(self.last_pdf_path, force_reload=True, keep_zoom=True)
        else:
            self._display_pdf_images()

    def _reset_pdf_zoom(self):
        self._apply_pdf_zoom(self._pdf_default_zoom)

    def _set_pdf_default_zoom(self):
        if not self.pdf_base_images:
            self._pdf_default_zoom = 1.0
            return
        viewport = self.pdf_scroll.viewport()
        viewport_width = viewport.width() if viewport else 0
        first_page = self.pdf_base_images[0]
        page_width = getattr(first_page, "width", 0)
        if viewport_width > 0 and page_width > 0:
            zoom = viewport_width / page_width
        else:
            zoom = 1.0
        zoom = max(0.35, min(4.0, zoom))
        self._pdf_default_zoom = zoom
        self.pdf_zoom = zoom
        if hasattr(self, "pdf_zoom_spin"):
            try:
                self.pdf_zoom_spin.blockSignals(True)
                self.pdf_zoom_spin.setValue(self.pdf_zoom * 100.0)
            finally:
                self.pdf_zoom_spin.blockSignals(False)

    def _render_pdf_preview(self, pdf_path: Path, force_reload: bool = False, keep_zoom: bool = False) -> bool:
        if not pdf_path.exists():
            self.pdf_status_label.setText(self._tr("未找到 PDF 文件", "PDF not found"))
            return False
        if not PIL_AVAILABLE:
            self.pdf_status_label.setText(self._tr("缺少 Pillow，无法预览 PDF", "Pillow not available, cannot preview PDF"))
            return False
        reuse = bool(self.pdf_base_images) and not force_reload and pdf_path == self.last_pdf_path
        if not reuse:
            if not self._generate_pdf_base_images(pdf_path):
                return False
            self.last_pdf_path = pdf_path
            if not keep_zoom:
                self._set_pdf_default_zoom()
        return self._display_pdf_images()

    def _generate_pdf_base_images(self, pdf_path: Path) -> bool:
        tool = self._locate_pdf_preview_tool()
        if not tool:
            self.pdf_status_label.setText(
                self._tr("缺少 pdftoppm/gs，无法生成预览", "Missing pdftoppm/gs; cannot generate preview")
            )
            return False
        converter, mode = tool
        dpi = int(round(self._pdf_base_dpi * self.pdf_zoom))
        dpi = max(72, min(dpi, 600))
        try:
            with tempfile.TemporaryDirectory(prefix="pdf_preview_") as tempdir:
                tempdir_path = Path(tempdir)
                prefix = tempdir_path / "page"
                if mode == "pdftoppm":
                    cmd = [converter, "-png", "-r", str(dpi), str(pdf_path), str(prefix)]
                else:
                    output_pattern = str(prefix) + "-%03d.png"
                    cmd = [
                        converter,
                        "-dSAFER",
                        "-dBATCH",
                        "-dNOPAUSE",
                        "-sDEVICE=pngalpha",
                        f"-r{dpi}",
                        f"-sOutputFile={output_pattern}",
                        str(pdf_path),
                    ]
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                except FileNotFoundError as exc:
                    self.pdf_status_label.setText(self._tr("未找到 PDF 转换工具", "PDF converter missing"))
                    self._append_log(self._tr(f"PDF 预览工具缺失: {exc}", f"PDF preview tool missing: {exc}"))
                    self.pdf_base_images = []
                    return False
                except subprocess.TimeoutExpired:
                    self.pdf_status_label.setText(self._tr("PDF 转换超时", "PDF conversion timed out"))
                    self._append_log(self._tr("PDF 预览转换超时。", "PDF preview conversion timed out."))
                    self.pdf_base_images = []
                    return False
                if result.returncode != 0:
                    self.pdf_status_label.setText(self._tr("PDF 转换失败", "PDF conversion failed"))
                    self._append_log(
                        self._tr(
                            f"PDF 预览转换失败:\n{result.stdout}\n{result.stderr}",
                            f"PDF preview conversion failed:\n{result.stdout}\n{result.stderr}",
                        )
                    )
                    self.pdf_base_images = []
                    return False
                png_files = sorted(tempdir_path.glob("page*.png")) or sorted(tempdir_path.glob("*.png"))
                if not png_files:
                    self.pdf_status_label.setText(self._tr("未生成 PDF 预览图像", "No PDF preview image generated"))
                    self.pdf_base_images = []
                    return False
                base_images = []
                for img_path in png_files:
                    try:
                        with Image.open(img_path) as pil_img:
                            base_images.append(pil_img.convert("RGBA"))
                    except Exception as exc:
                        self._append_log(
                            self._tr(
                                f"加载预览图片失败: {img_path} -> {exc}",
                                f"Failed to load preview image: {img_path} -> {exc}",
                            )
                        )
                if not base_images:
                    self.pdf_status_label.setText(self._tr("预览加载失败", "Preview load failed"))
                    self.pdf_base_images = []
                    return False
                self.pdf_base_images = base_images
                return True
        except Exception as exc:
            self._append_log(self._tr(f"PDF 预览生成异常: {exc}", f"PDF preview generation error: {exc}"))
            self.pdf_base_images = []
            return False

    def _display_pdf_images(self) -> bool:
        if not self.pdf_base_images:
            self.pdf_status_label.setText(self._tr("暂无 PDF 预览", "No PDF preview"))
            for i in reversed(range(self.pdf_container_layout.count())):
                item = self.pdf_container_layout.takeAt(i)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            return False
        invert = self.pdf_dark_mode
        zoom = max(0.35, min(self.pdf_zoom, 4.0))
        self.pdf_zoom = zoom
        bg_color = "#1b1b1b" if invert else "#f7f7f7"
        self.pdf_scroll.viewport().setStyleSheet(f"background:{bg_color};")
        for i in reversed(range(self.pdf_container_layout.count())):
            item = self.pdf_container_layout.takeAt(i)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        resample = getattr(Image, "LANCZOS", getattr(Image, "BICUBIC", Image.NEAREST))
        for idx, base_image in enumerate(self.pdf_base_images, start=1):
            working = base_image.copy() if (zoom != 1.0 or invert) else base_image
            if zoom != 1.0:
                width = max(1, int(working.width * zoom))
                height = max(1, int(working.height * zoom))
                working = working.resize((width, height), resample=resample)
            if invert:
                working = self._invert_image_for_dark_mode(working)
            pixmap = _pil_to_qpixmap(working)
            label = QLabel()
            label.setPixmap(pixmap)
            label.setAlignment(Qt.AlignCenter)
            caption = QLabel(self._tr(f"页 {idx}", f"Page {idx}"))
            caption.setAlignment(Qt.AlignLeft)
            caption.setStyleSheet("font-weight: bold; margin-top: 12px;")
            self.pdf_container_layout.addWidget(caption)
            self.pdf_container_layout.addWidget(label)
        name = self.last_pdf_path.name if self.last_pdf_path else "PDF"
        self.pdf_status_label.setText(
            self._tr(
                f"预览 {len(self.pdf_base_images)} 页（{name}） @ {int(zoom * 100)}%",
                f"{len(self.pdf_base_images)} page(s) ({name}) @ {int(zoom * 100)}%",
            )
        )
        result_tabs = getattr(self, "result_tabs", None)
        result_indices = getattr(self, "result_tabs_indices", {})
        pdf_index = result_indices.get("pdf")
        if result_tabs is not None and pdf_index is not None:
            result_tabs.setCurrentIndex(pdf_index)
            if hasattr(self, "main_tabs_indices") and "result" in self.main_tabs_indices:
                self.tabs.setCurrentIndex(self.main_tabs_indices["result"])
        elif self.tabs.count() > 3:
            self.tabs.setCurrentWidget(self.tabs.widget(3))
        return True

    def _invert_image_for_dark_mode(self, image: Image.Image) -> Image.Image:
        if image.mode in ("RGBA", "LA"):
            alpha = image.split()[-1]
            base = image.convert("RGB")
            inverted = ImageOps.invert(base)
            inverted.putalpha(alpha)
            return inverted
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        return ImageOps.invert(image)

    # ---------------------------------------------------- External tools ----
    def _locate_pdf_preview_tool(self):
        if self.pdf_preview_tool:
            tool_path, mode = self.pdf_preview_tool
            if Path(tool_path).exists():
                return self.pdf_preview_tool
        pdftoppm = shutil.which("pdftoppm")
        if pdftoppm:
            self.pdf_preview_tool = (pdftoppm, "pdftoppm")
            return self.pdf_preview_tool
        gs_names = ["gswin64c", "gswin32c", "gs"] if os.name == "nt" else ["gs"]
        for name in gs_names:
            gs_path = shutil.which(name)
            if gs_path:
                self.pdf_preview_tool = (gs_path, "gs")
                return self.pdf_preview_tool
        self.pdf_preview_tool = None
        return None

    def _prompt_engine_selection(self):
        engine = self.latex_engine_combo.currentText()
        selected, _ = QFileDialog.getOpenFileName(
            self,
            self._tr(f"选择 {engine} 可执行文件", f"Select {engine} Executable"),
            "",
            "Executable (*)",
        )
        if selected:
            self._latex_engine_paths[engine] = selected
            self._append_log(f"{engine} 路径更新为: {selected}")

    def _ensure_latex_engine(self, engine: str):
        """Resolve a usable LaTeX engine across three install tiers.

        Resolution order:
          1. Manual override (cached from a prior file-picker selection).
          2. ``shared.latex_engine.resolve_engine`` — system PATH, then
             bundled TinyTeX inside ``<app>/resources/tinytex/``, then
             auto-installed Tectonic at ``~/.datalab/bin``.
          3. Engine-specific auto-installer: for ``tectonic`` we offer
             a one-shot download (~30 MB) instead of failing.
          4. Last-resort: prompt the user to point at a binary.
        """
        _ensure_default_path_augmented()
        cached = self._latex_engine_paths.get(engine)
        if cached and Path(cached).exists():
            return cached

        choice = resolve_engine(engine, bundle_root=find_app_root())
        if choice is not None:
            self._latex_engine_paths[engine] = choice.path
            self._append_log(
                self._tr(
                    f"使用 {engine}: {choice.path} (来源: {choice.source})",
                    f"Using {engine}: {choice.path} (source: {choice.source})",
                )
            )
            return choice.path

        # Engine missing. For Tectonic specifically we can offer a
        # one-shot installer because it's a single binary; for the
        # heavier engines (pdflatex/xelatex) we fall back to the file
        # picker like before.
        if engine == "tectonic":
            installed = self._offer_tectonic_install()
            if installed:
                self._latex_engine_paths[engine] = installed.path
                return installed.path

        msg_zh = (
            f"未在系统 PATH 或捆绑资源中找到 {engine}。请安装、选择可执行文件，"
            "或在引擎下拉框中切换到 Tectonic（自动下载约 30 MB）。"
        )
        msg_en = (
            f"{engine} not found on PATH or in bundled resources. "
            "Please install it, point to the executable manually, or "
            "switch the engine to Tectonic (auto-downloads ~30 MB)."
        )
        QMessageBox.warning(self, self._tr("提示", "Notice"), self._tr(msg_zh, msg_en))
        self._prompt_engine_selection()
        return self._latex_engine_paths.get(engine)

    def _resolve_latex_engine_no_prompt(self, engine: str) -> str | None:
        """Resolve an optional fallback engine without showing dialogs."""
        _ensure_default_path_augmented()
        cached = self._latex_engine_paths.get(engine)
        if cached and Path(cached).exists():
            return cached
        choice = resolve_engine(engine, bundle_root=find_app_root())
        if choice is None:
            return None
        self._latex_engine_paths[engine] = choice.path
        return choice.path

    def _offer_tectonic_install(self) -> "EngineChoice | None":
        """Ask the user before downloading Tectonic.

        Runs the download + extract on a ``_TectonicInstallWorker``
        QThread and drives a modal ``QProgressDialog``. The dialog's
        Cancel button is wired to the worker's stop flag, which the
        engine streamer polls between chunks — a click aborts the
        install within ~10 ms and cleans up the staging dir.

        Returns the resolved ``EngineChoice`` on success, ``None``
        when the user declines, cancels, or the install fails.
        """
        prompt_zh = (
            "未检测到 Tectonic。是否立即下载约 30 MB 的 Tectonic 二进制到\n"
            "~/.datalab/bin/，以便无需安装 TeX Live 即可编译 PDF？"
        )
        prompt_en = (
            "Tectonic was not found. Download the ~30 MB Tectonic binary\n"
            "to ~/.datalab/bin/ now? This lets you compile PDFs without\n"
            "installing TeX Live."
        )
        reply = QMessageBox.question(
            self,
            self._tr("自动安装 Tectonic", "Install Tectonic"),
            self._tr(prompt_zh, prompt_en),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return None

        progress = QProgressDialog(
            self._tr("正在准备 Tectonic…", "Preparing Tectonic…"),
            self._tr("取消", "Cancel"),
            0, 0, self,
        )
        progress.setWindowTitle(self._tr("自动安装 Tectonic", "Install Tectonic"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setAutoClose(False)
        progress.setMinimumDuration(0)

        worker = _TectonicInstallWorker(self)

        def _on_stage(stage: str) -> None:
            zh, en = _TECTONIC_STAGE_LABELS.get(stage, (stage, stage))
            label = self._tr(f"Tectonic: {zh}", f"Tectonic: {en}")
            self._append_log(label)
            progress.setLabelText(label)

        worker.stage.connect(_on_stage)
        progress.canceled.connect(worker.request_stop)

        # Local event loop driven by the worker's ``finished`` signal
        # keeps the GUI responsive without a busy ``processEvents``
        # poll. ``loop.exec()`` returns when the worker exits run().
        # ``worker.wait()`` after ``loop.exec()`` guarantees the
        # underlying OS thread has actually terminated before we
        # touch ``worker.result`` / ``worker.error`` — between
        # ``finished`` emission and ``isFinished`` returning True
        # there is a brief teardown window where the worker is
        # still technically running.
        loop = QEventLoop(self)
        worker.finished.connect(loop.quit)
        worker.start()
        loop.exec()
        # Bounded wait: ``finished`` has fired so this is microseconds
        # in practice, but the timeout guarantees a misbehaving worker
        # can't wedge the GUI thread permanently.
        worker.wait(5000)
        progress.close()

        err = worker.error
        if isinstance(err, TectonicInstallCancelled):
            self._append_log(
                self._tr("Tectonic: 用户已取消安装。", "Tectonic: install cancelled by user.")
            )
            return None
        if err is not None:
            # Pick a localized title + body per error type, then dispatch
            # the QMessageBox once to avoid the four near-duplicate calls
            # the prior revision had drift-prone copies of.
            if isinstance(err, UnsupportedPlatformError):
                title_zh, title_en = "不支持的平台", "Unsupported Platform"
                body_zh = f"当前平台没有可用的 Tectonic 预编译版本：{err}"
                body_en = f"No prebuilt Tectonic available for this platform: {err}"
            elif isinstance(err, MissingHomeDirectoryError):
                # Surfaces in CI / sandboxed environments where neither
                # HOME nor USERPROFILE is set so the runtime can't pick
                # a stable install location. Actionable hint > opaque
                # generic-error string.
                title_zh, title_en = "Tectonic 安装失败", "Tectonic Install Failed"
                body_zh = (
                    "无法确定用户主目录（未设置 HOME / USERPROFILE 环境变量）。"
                    "请设置任一环境变量后重试。"
                )
                body_en = (
                    "Cannot determine the user home directory (HOME and "
                    "USERPROFILE are both unset). Set one and retry."
                )
            else:
                title_zh, title_en = "Tectonic 安装失败", "Tectonic Install Failed"
                body_zh = f"安装失败：{err}"
                body_en = f"Install failed: {err}"
            QMessageBox.critical(
                self, self._tr(title_zh, title_en), self._tr(body_zh, body_en),
            )
            return None
        return worker.result
