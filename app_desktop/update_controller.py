"""Desktop update-check controller and state machine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

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
        try:
            with UpdateCacheLock():
                path = self.download_installer(payload.asset)
                self._preferences.cache_release_notes(
                    version=payload.version,
                    notes=payload.notes,
                    url=payload.release_url,
                    published_at=payload.published_at,
                )
                self.state = UpdateState.LAUNCHING
                launched = self._launch_installer(path, payload.asset)
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
