"""Desktop update-check controller and state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol

from app_desktop.update_dialogs import (
    build_post_update_notice,
    build_update_message,
    build_update_titles,
)
from app_desktop.update_installer import launch_installer as launch_platform_installer
from shared.update_checker import (
    RELEASES_URL,
    ReleaseInfo,
    UpdateCheckResult,
    current_version,
    normalize_version_tag,
)
from shared.update_checker import check_for_updates as default_check_for_updates
from shared.update_payload import (
    InstallerAsset,
    UpdateCacheLock,
    UpdatePayload,
    UpdatePayloadError,
    download_and_verify_installer,
    resolve_update_payload_for_release,
)
from shared.update_preferences import CachedReleaseNotes, UpdatePreferences


class UpdateState(Enum):
    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    LAUNCHING = "launching"


class UpdateWindow(Protocol):
    def is_english(self) -> bool: ...
    def ask_update(self, title: str, message: str, *, was_skipped: bool = False) -> str: ...
    def warning(self, title: str, message: str) -> None: ...
    def information(self, title: str, message: str) -> None: ...
    def exit_for_update(self) -> None: ...


class UpdatePreferencesLike(Protocol):
    def auto_update_enabled(self) -> bool: ...
    def set_auto_update_enabled(self, enabled: bool) -> None: ...
    def should_auto_check(self, now: datetime) -> bool: ...
    def mark_checked(self, when: datetime) -> None: ...
    def is_skipped(self, version: str) -> bool: ...
    def skip_version(self, version: str) -> None: ...
    def cached_release_notes(self) -> CachedReleaseNotes | None: ...
    def consume_version_changed_notice(self, current_version: str) -> bool: ...

    def cache_release_notes(
        self,
        *,
        version: str,
        notes: str,
        url: str,
        published_at: str,
    ) -> None: ...


@dataclass
class UpdateController:
    window: UpdateWindow
    preferences: UpdatePreferencesLike | None = None
    check_for_updates: Callable[[], UpdateCheckResult] = default_check_for_updates
    resolve_payload: Callable[[ReleaseInfo, str], UpdatePayload] | None = None
    download_installer: Callable[[InstallerAsset], Path] = download_and_verify_installer
    launch_installer: Callable[[Path, InstallerAsset], bool] | None = None
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    state: UpdateState = UpdateState.IDLE
    _download_thread: Any | None = field(default=None, init=False, repr=False)
    _download_worker: Any | None = field(default=None, init=False, repr=False)
    _download_bridge: Any | None = field(default=None, init=False, repr=False)
    _download_dialog: Any | None = field(default=None, init=False, repr=False)
    _download_lock: UpdateCacheLock | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.preferences is None:
            self.preferences = UpdatePreferences()
        if self.launch_installer is None:
            self.launch_installer = self._launch_platform

    def auto_update_enabled(self) -> bool:
        return self._preferences.auto_update_enabled()

    def set_auto_update_enabled(self, enabled: bool) -> None:
        self._preferences.set_auto_update_enabled(enabled)

    def check_now(self) -> None:
        if self.state is not UpdateState.IDLE:
            self.window.warning("Update", "An update operation is already in progress.")
            return
        self._run_check(manual=True)

    def maybe_auto_check(self) -> None:
        if self.state is not UpdateState.IDLE:
            return
        if not self._preferences.should_auto_check(self.now()):
            return
        self._run_check(manual=False)

    def maybe_show_startup_update_notice(self) -> None:
        cached = self._preferences.cached_release_notes()
        if cached is None:
            return
        version = current_version()
        if normalize_version_tag(cached.version) != normalize_version_tag(version):
            return
        if not self._preferences.consume_version_changed_notice(version):
            return
        message = build_post_update_notice(
            version=version,
            notes=cached.notes,
            url=cached.url,
            published_at=cached.published_at,
            lang=self._lang(),
        )
        self.window.information("Update Complete", message)

    def _run_check(self, *, manual: bool) -> None:
        self.state = UpdateState.CHECKING
        try:
            try:
                result = self.check_for_updates()
            except Exception as exc:  # noqa: BLE001 - update checks should degrade gracefully
                result = UpdateCheckResult(
                    status="unavailable",
                    current_version="",
                    error=str(exc) or type(exc).__name__,
                )
            if not manual:
                self._preferences.mark_checked(self.now())
            self._handle_result(result, manual=manual)
        finally:
            if self.state not in {UpdateState.DOWNLOADING, UpdateState.LAUNCHING}:
                self.state = UpdateState.IDLE

    def _handle_result(self, result: UpdateCheckResult, *, manual: bool) -> None:
        lang = self._lang()
        titles = build_update_titles(lang)
        if result.status == "unavailable":
            if manual:
                self.window.warning(
                    titles.check_failed,
                    self._check_failed_message(result.error, lang),
                )
            return

        if result.status != "update-available" or result.release is None:
            if manual:
                self.window.information(
                    titles.up_to_date,
                    self._up_to_date_message(result.current_version, lang),
                )
            return

        try:
            payload = self._resolve_payload(result.release, result.current_version)
        except (UpdatePayloadError, OSError) as exc:
            if manual:
                release_url = result.release.html_url or RELEASES_URL
                self.window.warning(
                    titles.manual_update_required,
                    self._manual_update_required_message(exc, release_url, lang),
                )
            return

        was_skipped = self._preferences.is_skipped(payload.version)
        if was_skipped and not manual:
            return

        message = build_update_message(
            payload,
            result.current_version,
            self._lang(),
            was_skipped=was_skipped,
        )
        choice = self.window.ask_update(titles.available, message, was_skipped=was_skipped)
        if choice == "skip":
            self._preferences.skip_version(payload.version)
            return
        if choice != "update":
            return

        self._download_and_launch(payload)

    def _resolve_payload(self, release: ReleaseInfo, current_version: str) -> UpdatePayload:
        if self.resolve_payload is not None:
            return self.resolve_payload(release, current_version)
        return resolve_update_payload_for_release(release, current_version=current_version)

    def _download_and_launch(self, payload: UpdatePayload) -> None:
        self.state = UpdateState.DOWNLOADING
        if not self._qt_application_is_running():
            self._download_and_launch_blocking(payload)
            return

        try:
            lock = UpdateCacheLock()
            lock.__enter__()
        except Exception as exc:  # noqa: BLE001 - injected update hooks must not wedge state
            self.state = UpdateState.IDLE
            self.window.warning(
                build_update_titles(self._lang()).update_failed,
                str(exc) or type(exc).__name__,
            )
            return

        try:
            self._start_download_worker(payload, lock)
        except Exception as exc:  # noqa: BLE001 - injected update hooks must not wedge state
            lock.__exit__(None, None, None)
            self.state = UpdateState.IDLE
            self.window.warning(
                build_update_titles(self._lang()).update_failed,
                str(exc) or type(exc).__name__,
            )
            return

    def _download_and_launch_blocking(self, payload: UpdatePayload) -> None:
        try:
            with UpdateCacheLock():
                path = self.download_installer(payload.asset)
                launched = self._cache_launch_result(path, payload)
        except Exception as exc:  # noqa: BLE001 - injected update hooks must not wedge state
            self.state = UpdateState.IDLE
            self.window.warning(
                build_update_titles(self._lang()).update_failed,
                str(exc) or type(exc).__name__,
            )
            return

        if launched:
            self.window.exit_for_update()
        else:
            self.state = UpdateState.IDLE

    def _start_download_worker(self, payload: UpdatePayload, lock: UpdateCacheLock) -> None:
        from PySide6.QtCore import QObject, QThread, Slot
        from PySide6.QtWidgets import QWidget

        from app_desktop.update_download_worker import UpdateDownloadWorker
        from app_desktop.update_progress_dialog import UpdateProgressDialog

        controller = self

        class DownloadCompletionBridge(QObject):
            @Slot(Path)
            def finished(self, path: Path) -> None:
                controller._download_finished(path, payload)

            @Slot(str)
            def failed(self, error: str) -> None:
                controller._download_failed(error)

        parent = self.window if isinstance(self.window, QWidget) else None
        dialog = UpdateProgressDialog(payload.asset, self._lang(), parent)
        thread = QThread()
        worker = UpdateDownloadWorker(payload.asset, self.download_installer)
        bridge = DownloadCompletionBridge()
        worker.moveToThread(thread)

        self._download_lock = lock
        self._download_dialog = dialog
        self._download_thread = thread
        self._download_worker = worker
        self._download_bridge = bridge

        worker.progress.connect(dialog.update_progress)
        worker.finished.connect(bridge.finished)
        worker.failed.connect(bridge.failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(self._download_thread_finished)
        thread.started.connect(worker.run)

        dialog.show()
        thread.start()

    def _download_finished(self, path: Path, payload: UpdatePayload) -> None:
        self._close_download_dialog()
        self._release_download_lock()
        try:
            launched = self._cache_launch_result(path, payload)
        except Exception as exc:  # noqa: BLE001 - launcher errors should show as update failure
            self.state = UpdateState.IDLE
            self.window.warning(
                build_update_titles(self._lang()).update_failed,
                str(exc) or type(exc).__name__,
            )
            return
        if launched:
            self.window.exit_for_update()
        else:
            self.state = UpdateState.IDLE

    def _download_failed(self, error: str) -> None:
        self._close_download_dialog()
        self._release_download_lock()
        self.state = UpdateState.IDLE
        self.window.warning(
            build_update_titles(self._lang()).update_failed,
            error or "download failed",
        )

    def _cache_launch_result(self, path: Path, payload: UpdatePayload) -> bool:
        self._preferences.cache_release_notes(
            version=payload.version,
            notes=payload.notes,
            url=payload.release_url,
            published_at=payload.published_at,
        )
        self.state = UpdateState.LAUNCHING
        return self._launch_installer(path, payload.asset)

    def _close_download_dialog(self) -> None:
        if self._download_dialog is not None:
            self._download_dialog.close()
            self._download_dialog = None

    def _release_download_lock(self) -> None:
        if self._download_lock is not None:
            self._download_lock.__exit__(None, None, None)
            self._download_lock = None

    def _download_thread_finished(self) -> None:
        self._download_thread = None
        self._download_worker = None
        self._download_bridge = None

    def _qt_application_is_running(self) -> bool:
        try:
            from PySide6.QtWidgets import QApplication, QWidget
        except ImportError:
            return False
        return QApplication.instance() is not None and isinstance(self.window, QWidget)

    def _launch_platform(self, path: Path, asset: InstallerAsset) -> bool:
        launch_platform_installer(
            path,
            platform_key=asset.platform_key,
            expected_sha256=asset.sha256,
            expected_size=asset.size_bytes,
        )
        return True

    def _launch_installer(self, path: Path, asset: InstallerAsset) -> bool:
        if self.launch_installer is None:
            return self._launch_platform(path, asset)
        return self.launch_installer(path, asset)

    def _check_failed_message(self, error: str | None, lang: str) -> str:
        if lang == "en":
            return (
                f"Unable to check for updates: {error or 'unknown error'}\n\n"
                f"{RELEASES_URL}"
            )
        return f"无法检查更新：{error or '未知错误'}\n\n{RELEASES_URL}"

    def _up_to_date_message(self, current_version: str, lang: str) -> str:
        if lang == "en":
            return f"Version {current_version} is already up to date."
        return f"版本 {current_version} 已是最新版本。"

    def _manual_update_required_message(
        self,
        error: Exception,
        release_url: str,
        lang: str,
    ) -> str:
        if lang == "en":
            return f"Automatic installation is unavailable: {error}\n\n{release_url}"
        return f"自动安装不可用：{error}\n\n{release_url}"

    def _lang(self) -> str:
        return "en" if self.window.is_english() else "zh"

    @property
    def _preferences(self) -> UpdatePreferencesLike:
        if self.preferences is None:
            self.preferences = UpdatePreferences()
        return self.preferences
