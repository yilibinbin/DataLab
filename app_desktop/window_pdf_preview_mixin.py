"""Batch-10 Stage 3 split — PDF-preview / zoom / image concern.

Methods extracted VERBATIM from the original ``window_latex_pdf_mixin.py``.
This file owns the read-only side that renders a compiled PDF into the preview
tab: zoom control, base-image generation via pdftoppm/gs, image display, dark
-mode inversion, and preview-tool discovery.

It is composed (rightmost) into ``WindowLatexPdfMixin`` behind the shim in
``window_latex_pdf_mixin.py``. The compile side calls into this mixin via
``self._render_pdf_preview`` after a successful compile; this mixin never calls
back into the compile side. See the shim's module docstring for the MRO
rationale.

State touched (all owned by ``ExtrapolationWindow.__init__``, resolved through
the composed instance): ``pdf_zoom``, ``_pdf_default_zoom``, ``pdf_base_images``,
``pdf_scroll``, ``pdf_zoom_spin``, ``pdf_container_layout``, ``pdf_status_label``,
``pdf_dark_mode``, ``pdf_preview_tool``, ``_pdf_base_dpi``, ``last_pdf_path``.

Methods provided by sibling mixins / the host window (resolved via Python MRO):
- ``self._tr`` — bilingual host helper
- ``self._append_log`` — host logging
- ``self.last_pdf_path`` — set by the compile side
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

try:
    from PIL import Image, ImageOps

    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    PIL_AVAILABLE = False
    Image = object  # type: ignore[assignment]
    ImageOps = object  # type: ignore[assignment]

from . import theme
from .resources import _pil_to_qpixmap


class WindowPdfPreviewMixin:
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
        self.pdf_scroll.viewport().setStyleSheet(theme.pdf_preview_viewport_style(inverted=invert))
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
            caption.setStyleSheet(theme.pdf_preview_caption_style())
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
