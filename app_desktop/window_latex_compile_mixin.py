"""Batch-10 Stage 3 split — LaTeX compile-orchestration + engine-resolution.

Methods extracted VERBATIM from the original ``window_latex_pdf_mixin.py``.
This file owns the write/compile side: opening/saving/reloading the editor,
driving the ``_LatexCompileWorker`` background thread, handling the compile
outcome, opening the compiled PDF externally, and resolving/installing a usable
LaTeX engine (including the Tectonic auto-installer).

It is composed (leftmost) into ``WindowLatexPdfMixin`` behind the shim in
``window_latex_pdf_mixin.py``. After a successful compile,
``_on_latex_compile_completed`` calls into the preview side via
``self._render_pdf_preview`` — that method lives in ``WindowPdfPreviewMixin``
and resolves through the composed instance's MRO. This mixin is placed leftmost
precisely because it drives that call flow.

The two QThread workers it uses (``_LatexCompileWorker``,
``_TectonicInstallWorker``) and their helpers now live in ``workers_qt.py``;
they are imported here so ``compile_latex_to_pdf`` / ``_offer_tectonic_install``
resolve them as module globals (call-time lookup, which the desktop UI tests
monkeypatch).

Methods provided by the sibling preview mixin / the host window (via MRO):
- ``self._render_pdf_preview`` — WindowPdfPreviewMixin (post-compile display)
- ``self._tr`` — bilingual host helper
- ``self._append_log`` — host logging
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QEventLoop, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QProgressDialog,
)

from shared.latex_engine import (
    EngineChoice,
    MissingHomeDirectoryError,
    TectonicInstallCancelled,
    UnsupportedPlatformError,
    find_app_root,
    resolve_engine,
)

from .resources import _ensure_default_path_augmented
from .workers_core import _safe_read_text, _safe_resolve_path
from .workers_qt import (
    _TECTONIC_STAGE_LABELS,
    _LatexCompileOutcome,
    _LatexCompileWorker,
    _TectonicInstallWorker,
)


class WindowLatexCompileMixin:
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
        requested_engine = self.latex_engine_combo.currentText()
        engine = requested_engine
        used_default_engine_fallback = False
        is_default_tectonic = requested_engine.strip().lower() == "tectonic"
        if is_default_tectonic:
            engine_exec = self._resolve_latex_engine_no_prompt(engine)
        else:
            engine_exec = self._ensure_latex_engine(engine)
        if not engine_exec and is_default_tectonic:
            for fallback_engine in self._latex_compile_fallback_candidates(requested_engine):
                fallback_exec = self._resolve_latex_engine_no_prompt(fallback_engine)
                fallback_path = _safe_resolve_path(fallback_exec) if fallback_exec else None
                if fallback_path is not None and fallback_path.exists():
                    engine = fallback_engine
                    engine_exec = str(fallback_path)
                    used_default_engine_fallback = True
                    self._append_log(
                        self._tr(
                            f"请求的 LaTeX 引擎 {requested_engine} 不可用，改用 {engine}: {fallback_path}",
                            f"Requested LaTeX engine {requested_engine} is unavailable; using {engine}: {fallback_path}",
                        )
                    )
                    break
        if not engine_exec and is_default_tectonic:
            engine_exec = self._ensure_latex_engine(engine)
        if not engine_exec:
            msg_zh = f"未找到 {requested_engine}，请安装或指定路径。"
            msg_en = f"{requested_engine} not found. Please install it or specify the path."
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
        self._append_log(
            self._tr(
                f"LaTeX 引擎: {engine} ({engine_path})",
                f"LaTeX engine: {engine} ({engine_path})",
            )
        )
        pdf_dir = target.parent
        pdf_path = pdf_dir / (target.stem + ".pdf")
        fallback: str | None = None
        fallback_path: Path | None = None
        if used_default_engine_fallback:
            fallback = "xelatex" if engine.lower() == "pdflatex" else "pdflatex"
            alt_exec = self._resolve_latex_engine_no_prompt(fallback)
            fallback_path = _safe_resolve_path(alt_exec) if alt_exec else None
            if fallback_path is not None and not fallback_path.exists():
                fallback_path = None
            if fallback_path is not None:
                self._append_log(
                    self._tr(
                        f"LaTeX 备用引擎: {fallback} ({fallback_path})",
                        f"LaTeX fallback engine: {fallback} ({fallback_path})",
                    )
                )

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

    def _latex_compile_fallback_candidates(self, requested_engine: str) -> tuple[str, ...]:
        requested = (requested_engine or "").strip().lower()
        candidates = ("xelatex", "pdflatex", "tectonic")
        return tuple(candidate for candidate in candidates if candidate != requested)

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

    # -------------------------------------------------------- Engine resolve --
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
