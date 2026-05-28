"""Qt worker for installer update downloads."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from shared.update_payload import DownloadProgress, InstallerAsset


logger = logging.getLogger(__name__)


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
            path = self._downloader(self._asset, progress_callback=self._emit_progress)
        except Exception as exc:  # noqa: BLE001 - surface injected downloader errors to UI
            self.failed.emit(str(exc) or type(exc).__name__)
            return
        self.finished.emit(path)

    def _emit_progress(self, progress: DownloadProgress) -> None:
        try:
            self.progress.emit(progress)
        except Exception:  # noqa: BLE001 - progress reporting is best-effort
            logger.exception("Update download progress callback failed")
