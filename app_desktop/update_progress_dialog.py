"""Installer update download progress dialog."""

from __future__ import annotations

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QLabel, QProgressBar, QVBoxLayout, QWidget

from shared.update_payload import DownloadProgress, InstallerAsset


class UpdateProgressDialog(QDialog):
    def __init__(self, asset: InstallerAsset, lang: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._lang = lang
        self._allow_close = False
        self.setWindowTitle("Updating DataLab" if lang == "en" else "正在更新 DataLab")
        self.setModal(True)

        self._label = QLabel(self)
        self._bar = QProgressBar(self)
        self._bar.setRange(0, 100)

        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._bar)

        self.update_progress(DownloadProgress(0, asset.size_bytes, 0.0))

    def reject(self) -> None:
        if self._allow_close:
            super().reject()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt naming
        if self._allow_close:
            event.accept()
            return
        event.ignore()

    def finish_and_close(self) -> None:
        self._allow_close = True
        self.close()

    def update_progress(self, progress: DownloadProgress) -> None:
        percent = int(progress.fraction * 100)
        done = progress.downloaded_bytes / (1024 * 1024)
        total = progress.total_bytes / (1024 * 1024) if progress.total_bytes else 0.0
        speed = progress.bytes_per_second / (1024 * 1024)
        self._bar.setValue(percent)
        if self._lang == "en":
            self._label.setText(
                f"Downloading update: {done:.2f} / {total:.2f} MB, {speed:.2f} MB/s"
            )
            return
        self._label.setText(f"正在下载更新：{done:.2f} / {total:.2f} MB，{speed:.2f} MB/s")
