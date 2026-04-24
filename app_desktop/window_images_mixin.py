from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileDialog, QMessageBox


class WindowImagesMixin:
    def _update_result_plot(self, image_data: bytes):
        self.result_plot_bytes = image_data
        if not image_data:
            self._result_plot_base_pixmap = None
            self.result_plot_label.setText(self._tr("无法生成拟合图像。", "Unable to render fitting image."))
            self._update_image_status()
            return
        pixmap = QPixmap()
        pixmap.loadFromData(image_data, "PNG")
        self._result_plot_base_pixmap = pixmap
        self._image_mode = self._image_mode or "fit"
        self._apply_result_plot_best_fit_zoom()
        self._update_image_status()

    def _apply_result_plot_zoom(self):
        if not self._result_plot_base_pixmap:
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            return
        width = max(1, int(self._result_plot_base_pixmap.width() * self.result_plot_zoom))
        height = max(1, int(self._result_plot_base_pixmap.height() * self.result_plot_zoom))
        scaled = self._result_plot_base_pixmap.scaled(width, height, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.result_plot_label.setPixmap(scaled)
        self.result_plot_label.setMinimumSize(scaled.size())
        self.result_plot_label.adjustSize()
        self._sync_zoom_spin()

    def _apply_result_plot_best_fit_zoom(self):
        if not self._result_plot_base_pixmap:
            self._result_plot_default_zoom = 1.0
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            return
        viewport = self.result_plot_scroll.viewport()
        viewport_height = viewport.height() if viewport else 0
        pixmap_height = self._result_plot_base_pixmap.height()
        if viewport_height > 0 and pixmap_height > 0:
            zoom = viewport_height / pixmap_height
        else:
            zoom = 1.0
        zoom = max(0.25, min(4.0, zoom))
        self._result_plot_default_zoom = zoom
        # Preserve user-selected zoom across pages; if none, use best-fit
        if not self._user_zoom_override:
            self.result_plot_zoom = zoom
        self._apply_result_plot_zoom()

    def _adjust_result_plot_zoom(self, factor: float):
        if not self._result_plot_base_pixmap:
            return
        self.result_plot_zoom = max(0.25, min(4.0, self.result_plot_zoom * factor))
        self._user_zoom_override = True
        self._apply_result_plot_zoom()

    def _reset_result_plot_zoom(self):
        if not self._result_plot_base_pixmap:
            return
        self.result_plot_zoom = self._result_plot_default_zoom
        self._user_zoom_override = False
        self._apply_result_plot_zoom()

    def _sync_zoom_spin(self):
        if not hasattr(self, "zoom_percent_spin"):
            return
        if self._zoom_spin_syncing:
            return
        self._zoom_spin_syncing = True
        try:
            val = int(round(self.result_plot_zoom * 100))
            self.zoom_percent_spin.blockSignals(True)
            self.zoom_percent_spin.setValue(
                max(self.zoom_percent_spin.minimum(), min(self.zoom_percent_spin.maximum(), val))
            )
            self.zoom_percent_spin.blockSignals(False)
        finally:
            self._zoom_spin_syncing = False

    def _on_zoom_percent_changed(self, value: int):
        if self._zoom_spin_syncing:
            return
        if not self._result_plot_base_pixmap:
            return
        self.result_plot_zoom = max(0.25, min(4.0, value / 100.0))
        self._user_zoom_override = True
        self._apply_result_plot_zoom()

    def _export_result_plot(self):
        if not self.result_plot_bytes:
            QMessageBox.information(
                self,
                self._tr("提示", "Notice"),
                self._tr("暂无可导出的拟合图像。", "No fitting plot available to export."),
            )
            return
        filename, _ = QFileDialog.getSaveFileName(
            self,
            self._tr("导出拟合图像", "Export Fitting Plot"),
            "",
            "PNG (*.png);;All Files (*)",
        )
        if not filename:
            return
        try:
            with open(filename, "wb") as fh:
                fh.write(self.result_plot_bytes)
            log_msg = self._tr(f"拟合图像已导出: {filename}", f"Fitting plot exported: {filename}")
            self._append_log(log_msg)
        except OSError as exc:
            QMessageBox.warning(self, self._tr("导出失败", "Export Failed"), str(exc))

    def _update_image_status(self):
        if not hasattr(self, "image_status_label"):
            return
        if self._image_mode:
            mode = self._image_mode
        elif self.current_stats_figures:
            mode = "stats"
        elif self.current_error_figures:
            mode = "error"
        elif self.current_extrap_figures:
            mode = "extrap"
        else:
            mode = "fit"
        if mode == "stats":
            figures = self.current_stats_figures
        elif mode == "error":
            figures = self.current_error_figures
        elif mode == "extrap":
            figures = self.current_extrap_figures
        else:
            figures = self.current_fit_figures
        if figures:
            if mode == "stats":
                idx = self.current_stats_index
                label_prefix = self._tr("统计图", "Stats plot")
            elif mode == "error":
                idx = self.current_error_index
                label_prefix = self._tr("误差图", "Error plot")
            elif mode == "extrap":
                idx = self.current_extrap_index
                label_prefix = self._tr("外推图", "Extrap plot")
            else:
                idx = self.current_fit_index
                label_prefix = self._tr("拟合图", "Fit plot")
            self.image_status_label.setText(f"{label_prefix} {idx + 1} / {len(figures)}")
            enabled = len(figures) > 1
            if hasattr(self, "image_page_spin"):
                self.image_page_spin.blockSignals(True)
                self.image_page_spin.setRange(1, max(1, len(figures)))
                self.image_page_spin.setValue(idx + 1)
                self.image_page_spin.setEnabled(True)
                self.image_page_spin.blockSignals(False)
        elif self._result_plot_base_pixmap:
            self.image_status_label.setText(self._tr("单张图像", "Single image"))
            enabled = False
            if hasattr(self, "image_page_spin"):
                self.image_page_spin.blockSignals(True)
                self.image_page_spin.setRange(1, 1)
                self.image_page_spin.setValue(1)
                self.image_page_spin.setEnabled(False)
                self.image_page_spin.blockSignals(False)
        else:
            self.image_status_label.setText(self._tr("暂无图片", "No image"))
            enabled = False
            if hasattr(self, "image_page_spin"):
                self.image_page_spin.blockSignals(True)
                self.image_page_spin.setRange(1, 1)
                self.image_page_spin.setValue(1)
                self.image_page_spin.setEnabled(False)
                self.image_page_spin.blockSignals(False)
        if hasattr(self, "image_prev_btn"):
            self.image_prev_btn.setEnabled(enabled)
        if hasattr(self, "image_next_btn"):
            self.image_next_btn.setEnabled(enabled)

    def _show_image_at(self, mode: str, index: int):
        if mode == "stats":
            figures = self.current_stats_figures
        elif mode == "error":
            figures = self.current_error_figures
        elif mode == "extrap":
            figures = self.current_extrap_figures
        else:
            figures = self.current_fit_figures
        if not figures:
            self._update_image_status()
            return
        index = index % len(figures)
        path = Path(figures[index])
        try:
            data = path.read_bytes()
        except Exception as exc:  # noqa: BLE001
            self.result_plot_bytes = None
            self._result_plot_base_pixmap = None
            self.result_plot_label.setText(self._tr("无法加载图片", "Unable to load image"))
            self._append_log(self._tr(f"读取图片失败 {path}: {exc}", f"Failed to read image {path}: {exc}"))
            self._update_image_status()
            return
        pixmap = QPixmap()
        if not pixmap.loadFromData(data, "PNG"):
            self.result_plot_bytes = None
            self._result_plot_base_pixmap = None
            self.result_plot_label.setText(self._tr("无法生成拟合图像。", "Unable to render image."))
            self._update_image_status()
            return
        self.result_plot_bytes = data
        self._result_plot_base_pixmap = pixmap
        self._apply_result_plot_best_fit_zoom()
        if mode == "stats":
            self.current_stats_index = index
        elif mode == "error":
            self.current_error_index = index
        elif mode == "extrap":
            self.current_extrap_index = index
        else:
            self.current_fit_index = index
        self._image_mode = mode
        self._update_image_status()

    def _set_image_list(self, mode: str, figures: list[Path]):
        if mode == "stats":
            self.current_stats_figures = list(figures)
            self.current_stats_index = 0
        elif mode == "error":
            self.current_error_figures = list(figures)
            self.current_error_index = 0
        elif mode == "extrap":
            self.current_extrap_figures = list(figures)
            self.current_extrap_index = 0
        else:
            self.current_fit_figures = list(figures)
            self.current_fit_index = 0
        self._image_mode = mode
        if figures:
            self._show_image_at(mode, 0)
        else:
            self._result_plot_base_pixmap = None
            self.result_plot_bytes = None
            self.result_plot_label.setText(self._tr("尚无图片", "No image yet"))
            self._update_image_status()

    def _on_image_prev(self):
        mode = self._image_mode or (
            "stats"
            if self.current_stats_figures
            else (
                "error"
                if self.current_error_figures
                else ("extrap" if self.current_extrap_figures else "fit")
            )
        )
        if mode == "stats":
            figures = self.current_stats_figures
        elif mode == "error":
            figures = self.current_error_figures
        elif mode == "extrap":
            figures = self.current_extrap_figures
        else:
            figures = self.current_fit_figures
        if not figures:
            self._update_image_status()
            return
        if mode == "stats":
            current_idx = self.current_stats_index
        elif mode == "error":
            current_idx = self.current_error_index
        elif mode == "extrap":
            current_idx = self.current_extrap_index
        else:
            current_idx = self.current_fit_index
        self._show_image_at(mode, current_idx - 1)

    def _on_image_next(self):
        mode = self._image_mode or (
            "stats"
            if self.current_stats_figures
            else (
                "error"
                if self.current_error_figures
                else ("extrap" if self.current_extrap_figures else "fit")
            )
        )
        if mode == "stats":
            figures = self.current_stats_figures
        elif mode == "error":
            figures = self.current_error_figures
        elif mode == "extrap":
            figures = self.current_extrap_figures
        else:
            figures = self.current_fit_figures
        if not figures:
            self._update_image_status()
            return
        if mode == "stats":
            current_idx = self.current_stats_index
        elif mode == "error":
            current_idx = self.current_error_index
        elif mode == "extrap":
            current_idx = self.current_extrap_index
        else:
            current_idx = self.current_fit_index
        self._show_image_at(mode, current_idx + 1)

    def _on_image_page_changed(self, value: int):
        mode = self._image_mode or (
            "stats"
            if self.current_stats_figures
            else (
                "error"
                if self.current_error_figures
                else ("extrap" if self.current_extrap_figures else "fit")
            )
        )
        if mode == "stats":
            figures = self.current_stats_figures
        elif mode == "error":
            figures = self.current_error_figures
        elif mode == "extrap":
            figures = self.current_extrap_figures
        else:
            figures = self.current_fit_figures
        if not figures:
            self._update_image_status()
            return
        self._show_image_at(mode, value - 1)

    def _cleanup_temp_batch_images(self):
        if not getattr(self, "_temp_batch_images", None):
            return
        for path in list(self._temp_batch_images):
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
        self._temp_batch_images = []
        self.current_extrap_figures = []
        self.current_extrap_index = 0
        self.current_error_figures = []
        self.current_error_index = 0

    def _save_batch_figure(self, plot_bytes: bytes | None, output_path: str, batch_idx: int, prefix: str) -> Path | None:
        if not plot_bytes:
            return None
        try:
            base_path = Path(output_path).expanduser() if output_path else None
        except Exception:
            base_path = None
        if base_path:
            image_path = base_path.with_name(f"{base_path.stem}_{prefix}_batch{batch_idx}.png")
        else:
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f"_{prefix}_batch{batch_idx}.png")
            tmp.write(plot_bytes)
            tmp.flush()
            tmp.close()
            image_path = Path(tmp.name)
            if not hasattr(self, "_temp_batch_images"):
                self._temp_batch_images = []
            self._temp_batch_images.append(image_path)
        try:
            image_path.write_bytes(plot_bytes)
        except OSError as exc:  # noqa: BLE001
            self._append_log(self._tr(f"写入批次图像失败: {exc}", f"Failed to write batch image: {exc}"))
            return None
        return image_path
