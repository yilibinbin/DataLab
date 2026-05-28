from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, cast

from PySide6.QtCore import QThread

from app_desktop.update_download_worker import UpdateDownloadWorker
from shared.update_payload import DownloadProgress, InstallerAsset


def _asset() -> InstallerAsset:
    return InstallerAsset(
        platform_key="macos",
        name="DataLab-test.pkg",
        url="https://example.invalid/DataLab-test.pkg",
        sha256="0" * 64,
        size_bytes=100,
    )


def test_worker_emits_progress_and_finished(qtbot: Any, tmp_path: Path) -> None:
    progress_events: list[DownloadProgress] = []
    finished_paths: list[Path] = []

    def downloader(
        asset: InstallerAsset,
        *,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
    ) -> Path:
        assert asset.name == "DataLab-test.pkg"
        assert progress_callback is not None
        progress_callback(DownloadProgress(25, 100, 1.0))
        progress_callback(DownloadProgress(100, 100, 2.0))
        return tmp_path / asset.name

    worker = UpdateDownloadWorker(_asset(), downloader)
    thread = QThread()
    worker.moveToThread(thread)
    worker.progress.connect(progress_events.append)
    worker.finished.connect(finished_paths.append)
    thread.started.connect(worker.run)

    with qtbot.waitSignal(worker.finished, timeout=3000):
        thread.start()

    thread.quit()
    thread.wait(3000)
    assert [event.downloaded_bytes for event in progress_events] == [25, 100]
    assert finished_paths == [tmp_path / "DataLab-test.pkg"]


def test_worker_emits_failed(qtbot: Any) -> None:
    errors: list[str] = []

    def downloader(
        asset: InstallerAsset,
        *,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
    ) -> Path:
        raise RuntimeError("network down")

    worker = UpdateDownloadWorker(_asset(), downloader)
    thread = QThread()
    worker.moveToThread(thread)
    worker.failed.connect(errors.append)
    thread.started.connect(worker.run)

    with qtbot.waitSignal(worker.failed, timeout=3000):
        thread.start()

    thread.quit()
    thread.wait(3000)
    assert errors == ["network down"]


def test_worker_progress_emit_exception_does_not_abort_download(tmp_path: Path) -> None:
    finished_paths: list[Path] = []
    errors: list[str] = []
    progress_seen: list[DownloadProgress] = []

    class FailingProgressSignal:
        def emit(self, progress: DownloadProgress) -> None:
            progress_seen.append(progress)
            raise RuntimeError("progress slot failed")

    def downloader(
        asset: InstallerAsset,
        *,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
    ) -> Path:
        assert progress_callback is not None
        progress_callback(DownloadProgress(100, 100, 1.0))
        return tmp_path / asset.name

    worker = UpdateDownloadWorker(_asset(), downloader)
    cast(Any, worker).progress = FailingProgressSignal()
    worker.finished.connect(finished_paths.append)
    worker.failed.connect(errors.append)

    worker.run()

    assert progress_seen[-1].fraction == 1.0
    assert finished_paths == [tmp_path / "DataLab-test.pkg"]
    assert errors == []
