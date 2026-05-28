"""Qt worker for installer update downloads."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from shared.update_payload import InstallerAsset


class UpdateDownloadWorker(QObject):
    progress = Signal(object)
    finished = Signal(Path)
    failed = Signal(str)

    def __init__(
        self,
        asset: InstallerAsset,
        downloader: Callable[..., Path],
    ) -> None:
        super().__init__()
        self._asset = asset
        self._downloader = downloader

    @Slot()
    def run(self) -> None:
        try:
            path = self._downloader(self._asset, progress_callback=self.progress.emit)
        except Exception as exc:  # noqa: BLE001 - surface injected downloader errors to UI
            self.failed.emit(str(exc) or type(exc).__name__)
            return
        self.finished.emit(path)
