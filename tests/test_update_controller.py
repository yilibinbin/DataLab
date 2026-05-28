from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from app_desktop.update_controller import UpdateController
from shared.update_checker import ReleaseInfo, UpdateCheckResult
from shared.update_payload import InstallerAsset, UpdatePayload
from shared.update_preferences import CachedReleaseNotes


class FakePreferences:
    def __init__(self) -> None:
        self.enabled = False
        self.checked = False
        self.checked_at: datetime | None = None
        self.skipped: set[str] = set()
        self.cached: list[tuple[str, str, str, str]] = []
        self.cached_notice: CachedReleaseNotes | None = None
        self.last_seen_versions: list[str] = []
        self.consume_notice = True

    def auto_update_enabled(self) -> bool:
        return self.enabled

    def set_auto_update_enabled(self, enabled: bool) -> None:
        self.enabled = enabled

    def should_auto_check(self, now: datetime) -> bool:
        return self.enabled

    def mark_checked(self, when: datetime) -> None:
        self.checked = True
        self.checked_at = when

    def is_skipped(self, version: str) -> bool:
        return version in self.skipped

    def skip_version(self, version: str) -> None:
        self.skipped.add(version)

    def cached_release_notes(self) -> CachedReleaseNotes | None:
        return self.cached_notice

    def consume_version_changed_notice(self, current_version: str) -> bool:
        self.last_seen_versions.append(current_version)
        return self.consume_notice

    def cache_release_notes(
        self,
        *,
        version: str,
        notes: str,
        url: str,
        published_at: str,
    ) -> None:
        self.cached.append((version, notes, url, published_at))


class FakeWindow:
    def __init__(self, *, choice: str = "update", english: bool = False) -> None:
        self.choice = choice
        self.english = english
        self.questions: list[tuple[str, str, bool]] = []
        self.warnings: list[tuple[str, str]] = []
        self.infos: list[tuple[str, str]] = []
        self.opened: list[str] = []
        self.exited = False

    def is_english(self) -> bool:
        return self.english

    def ask_update(self, title: str, message: str, *, was_skipped: bool = False) -> str:
        self.questions.append((title, message, was_skipped))
        return self.choice

    def warning(self, title: str, message: str) -> None:
        self.warnings.append((title, message))

    def information(self, title: str, message: str) -> None:
        self.infos.append((title, message))

    def open_url(self, url: str) -> None:
        self.opened.append(url)

    def exit_for_update(self) -> None:
        self.exited = True


def release(*, html_url: str = "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0") -> ReleaseInfo:
    return ReleaseInfo(
        tag_name="v2.3.0",
        name="DataLab v2.3.0",
        version="2.3.0",
        html_url=html_url,
        body="Release body",
        published_at="2026-05-26T00:00:00Z",
        assets=(),
    )


def payload() -> UpdatePayload:
    return UpdatePayload(
        version="2.3.0",
        notes="Installer updater notes",
        published_at="2026-05-26T00:00:00Z",
        release_url="https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
        asset=InstallerAsset(
            platform_key="macos",
            name="DataLab.pkg",
            url="https://example.invalid/pkg",
            sha256="0" * 64,
            size_bytes=10,
        ),
    )


def test_manual_update_available_runs_download_and_launch(tmp_path: Path) -> None:
    from app_desktop.update_controller import UpdateController

    window = FakeWindow(choice="update")
    prefs = FakePreferences()
    installer = tmp_path / "DataLab.pkg"
    installer.write_bytes(b"installer")
    launched: list[tuple[Path, InstallerAsset]] = []

    def fake_launch(path: Path, asset: InstallerAsset) -> bool:
        launched.append((path, asset))
        return True

    controller = UpdateController(
        window,
        preferences=prefs,
        check_for_updates=lambda: UpdateCheckResult(
            status="update-available",
            current_version="2.2.0",
            latest_version="2.3.0",
            release=release(),
        ),
        resolve_payload=lambda _release, current_version: payload(),
        download_installer=lambda asset: installer,
        launch_installer=fake_launch,
        now=lambda: datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    controller.check_now()

    assert window.questions[0][0] == "发现新版本"
    assert "Installer updater notes" in window.questions[0][1]
    assert launched == [(installer, payload().asset)]
    assert window.exited is True
    assert prefs.cached == [
        (
            "2.3.0",
            "Installer updater notes",
            "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
            "2026-05-26T00:00:00Z",
        )
    ]


def test_qt_window_update_download_runs_in_worker_thread(
    monkeypatch,
    qtbot,
    tmp_path: Path,
) -> None:
    from PySide6.QtWidgets import QWidget

    from app_desktop.update_controller import UpdateController, UpdateState
    from shared.update_payload import DownloadProgress

    class QtFakeWindow(QWidget):
        def __init__(self) -> None:
            super().__init__()
            self.questions: list[tuple[str, str, bool]] = []
            self.warnings: list[tuple[str, str]] = []
            self.exited = False

        def is_english(self) -> bool:
            return True

        def ask_update(self, title: str, message: str, *, was_skipped: bool = False) -> str:
            self.questions.append((title, message, was_skipped))
            return "update"

        def warning(self, title: str, message: str) -> None:
            self.warnings.append((title, message))

        def information(self, title: str, message: str) -> None:
            raise AssertionError("information dialog not expected")

        def exit_for_update(self) -> None:
            self.exited = True

    class FakeLock:
        def __enter__(self) -> FakeLock:
            calls.append("lock-enter")
            return self

        def __exit__(self, *_: object) -> bool:
            calls.append("lock-exit")
            return False

    window = QtFakeWindow()
    qtbot.addWidget(window)
    prefs = FakePreferences()
    installer = tmp_path / "DataLab.pkg"
    installer.write_bytes(b"installer")
    calls: list[str] = []
    progress_events: list[DownloadProgress] = []
    launched: list[Path] = []
    monkeypatch.setattr("app_desktop.update_controller.UpdateCacheLock", FakeLock)

    def download_installer(asset: InstallerAsset, *, progress_callback=None) -> Path:
        calls.append("download")
        assert progress_callback is not None
        progress = DownloadProgress(asset.size_bytes, asset.size_bytes, 1.0)
        progress_events.append(progress)
        progress_callback(progress)
        return installer

    controller = UpdateController(
        window,
        preferences=prefs,
        check_for_updates=lambda: UpdateCheckResult(
            status="update-available",
            current_version="2.2.0",
            latest_version="2.3.0",
            release=release(),
        ),
        resolve_payload=lambda _release, current_version: payload(),
        download_installer=download_installer,
        launch_installer=lambda path, asset: launched.append(path) or True,
        now=lambda: datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    controller.check_now()
    qtbot.waitUntil(lambda: window.exited, timeout=3000)

    assert calls[0] == "lock-enter"
    assert "download" in calls
    assert calls[-1] == "lock-exit"
    assert progress_events[-1].fraction == 1.0
    assert launched == [installer]
    assert window.warnings == []
    assert prefs.cached
    assert controller.state is UpdateState.LAUNCHING


def test_auto_offline_failure_is_quiet_and_marks_checked() -> None:
    from app_desktop.update_controller import UpdateController

    window = FakeWindow()
    prefs = FakePreferences()
    prefs.enabled = True
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)
    controller = UpdateController(
        window,
        preferences=prefs,
        check_for_updates=lambda: UpdateCheckResult(
            status="unavailable",
            current_version="2.2.0",
            error="offline",
        ),
        now=lambda: now,
    )

    controller.maybe_auto_check()

    assert window.warnings == []
    assert window.questions == []
    assert prefs.checked is True
    assert prefs.checked_at == now


def test_auto_payload_resolution_oserror_is_quiet_and_returns_idle() -> None:
    from app_desktop.update_controller import UpdateController, UpdateState

    window = FakeWindow()
    prefs = FakePreferences()
    prefs.enabled = True
    controller = UpdateController(
        window,
        preferences=prefs,
        check_for_updates=lambda: UpdateCheckResult(
            status="update-available",
            current_version="2.2.0",
            latest_version="2.3.0",
            release=release(),
        ),
        resolve_payload=lambda _release, current_version: (_ for _ in ()).throw(
            OSError("manifest fetch failed")
        ),
        now=lambda: datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    controller.maybe_auto_check()

    assert window.warnings == []
    assert window.questions == []
    assert prefs.checked is True
    assert controller.state is UpdateState.IDLE


def test_manual_update_check_failure_uses_chinese_body() -> None:
    from app_desktop.update_controller import UpdateController
    from shared.update_checker import RELEASES_URL

    window = FakeWindow()
    controller = UpdateController(
        window,
        preferences=FakePreferences(),
        check_for_updates=lambda: UpdateCheckResult(
            status="unavailable",
            current_version="2.2.0",
            error="offline",
        ),
        now=lambda: datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    controller.check_now()

    assert len(window.warnings) == 1
    assert window.warnings[0][0] == "检查更新失败"
    assert window.warnings[0][1] == f"无法检查更新：offline\n\n{RELEASES_URL}"


def test_manual_up_to_date_uses_chinese_body() -> None:
    window = FakeWindow()
    controller = UpdateController(
        window,
        preferences=FakePreferences(),
        check_for_updates=lambda: UpdateCheckResult(
            status="up-to-date",
            current_version="2.3.0",
            latest_version="2.3.0",
        ),
        now=lambda: datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    controller.check_now()

    assert len(window.infos) == 1
    assert window.infos[0] == ("已是最新版本", "版本 2.3.0 已是最新版本。")


def test_manual_payload_resolution_failure_uses_releases_fallback() -> None:
    from app_desktop.update_controller import UpdateController
    from shared.update_checker import RELEASES_URL

    window = FakeWindow()
    controller = UpdateController(
        window,
        preferences=FakePreferences(),
        check_for_updates=lambda: UpdateCheckResult(
            status="update-available",
            current_version="2.2.0",
            latest_version="2.3.0",
            release=release(html_url=""),
        ),
        resolve_payload=lambda _release, current_version: (_ for _ in ()).throw(
            OSError("manifest fetch failed")
        ),
        now=lambda: datetime(2026, 5, 26, tzinfo=timezone.utc),
    )

    controller.check_now()

    assert len(window.warnings) == 1
    assert window.warnings[0][0] == "需要手动更新"
    assert "自动安装不可用：manifest fetch failed" in window.warnings[0][1]
    assert "manifest fetch failed" in window.warnings[0][1]
    assert RELEASES_URL in window.warnings[0][1]
    assert window.questions == []


def test_reentrant_update_check_is_rejected_when_downloading() -> None:
    from app_desktop.update_controller import UpdateController, UpdateState

    window = FakeWindow()
    controller = UpdateController(window, preferences=FakePreferences())
    controller.state = UpdateState.DOWNLOADING

    controller.check_now()

    assert "already in progress" in window.warnings[0][1]


def _controller_for_update_attempt(
    *,
    window: FakeWindow,
    download_installer: Callable[[InstallerAsset], Path],
    launch_installer: Callable[[Path, InstallerAsset], bool],
) -> UpdateController:
    return UpdateController(
        window,
        preferences=FakePreferences(),
        check_for_updates=lambda: UpdateCheckResult(
            status="update-available",
            current_version="2.2.0",
            latest_version="2.3.0",
            release=release(),
        ),
        resolve_payload=lambda _release, current_version: payload(),
        download_installer=download_installer,
        launch_installer=launch_installer,
        now=lambda: datetime(2026, 5, 26, tzinfo=timezone.utc),
    )


def test_download_update_payload_error_warns_and_resets_idle() -> None:
    from app_desktop.update_controller import UpdateState
    from shared.update_payload import UpdatePayloadError

    window = FakeWindow(choice="update")
    controller = _controller_for_update_attempt(
        window=window,
        download_installer=lambda asset: (_ for _ in ()).throw(
            UpdatePayloadError("bad installer metadata")
        ),
        launch_installer=lambda path, asset: True,
    )

    controller.check_now()

    assert window.warnings[0][0] == "更新失败"
    assert "bad installer metadata" in window.warnings[0][1]
    assert controller.state is UpdateState.IDLE
    assert window.exited is False


def test_download_oserror_warns_and_resets_idle() -> None:
    from app_desktop.update_controller import UpdateState

    window = FakeWindow(choice="update")
    controller = _controller_for_update_attempt(
        window=window,
        download_installer=lambda asset: (_ for _ in ()).throw(OSError("disk full")),
        launch_installer=lambda path, asset: True,
    )

    controller.check_now()

    assert "disk full" in window.warnings[0][1]
    assert controller.state is UpdateState.IDLE
    assert window.exited is False


def test_download_runtime_error_warns_and_resets_idle() -> None:
    from app_desktop.update_controller import UpdateState

    window = FakeWindow(choice="update")
    controller = _controller_for_update_attempt(
        window=window,
        download_installer=lambda asset: (_ for _ in ()).throw(RuntimeError("boom")),
        launch_installer=lambda path, asset: True,
    )

    controller.check_now()

    assert "boom" in window.warnings[0][1]
    assert controller.state is UpdateState.IDLE
    assert window.exited is False


def test_launch_failures_warn_and_reset_idle(tmp_path: Path) -> None:
    from app_desktop.update_controller import UpdateState
    from app_desktop.update_installer import InstallerLaunchError

    installer = tmp_path / "DataLab.pkg"
    installer.write_bytes(b"installer")

    for exc in (RuntimeError("launch boom"), InstallerLaunchError("bad launch")):
        def fail_launch(
            path: Path,
            asset: InstallerAsset,
            captured: Exception = exc,
        ) -> bool:
            raise captured

        window = FakeWindow(choice="update")
        controller = _controller_for_update_attempt(
            window=window,
            download_installer=lambda asset: installer,
            launch_installer=fail_launch,
        )

        controller.check_now()

        assert str(exc) in window.warnings[0][1]
        assert controller.state is UpdateState.IDLE
        assert window.exited is False


def test_launch_false_resets_idle_without_exit_or_warning(tmp_path: Path) -> None:
    from app_desktop.update_controller import UpdateState

    installer = tmp_path / "DataLab.pkg"
    installer.write_bytes(b"installer")
    window = FakeWindow(choice="update")
    controller = _controller_for_update_attempt(
        window=window,
        download_installer=lambda asset: installer,
        launch_installer=lambda path, asset: False,
    )

    controller.check_now()

    assert window.warnings == []
    assert controller.state is UpdateState.IDLE
    assert window.exited is False


def test_startup_update_notice_uses_cached_release_notes_once(monkeypatch) -> None:
    from app_desktop import update_controller

    prefs = FakePreferences()
    prefs.cached_notice = CachedReleaseNotes(
        version="2.3.0",
        notes="Cached post-update notes",
        url="https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
        published_at="2026-05-26T00:00:00Z",
    )
    window = FakeWindow(english=True)
    monkeypatch.setattr(update_controller, "current_version", lambda: "2.3.0")
    controller = UpdateController(
        window,
        preferences=prefs,
        check_for_updates=lambda: (_ for _ in ()).throw(AssertionError("network check")),
    )

    controller.maybe_show_startup_update_notice()
    prefs.consume_notice = False
    controller.maybe_show_startup_update_notice()

    assert len(window.infos) == 1
    assert window.infos[0][0] == "Update Complete"
    assert "DataLab has been updated to version 2.3.0" in window.infos[0][1]
    assert "Cached post-update notes" in window.infos[0][1]
    assert prefs.last_seen_versions == ["2.3.0", "2.3.0"]


def test_startup_update_notice_ignores_cache_for_other_version(monkeypatch) -> None:
    from app_desktop import update_controller

    prefs = FakePreferences()
    prefs.cached_notice = CachedReleaseNotes(
        version="2.2.0",
        notes="Old notes",
        url="https://example.invalid/old",
        published_at="2026-05-25T00:00:00Z",
    )
    window = FakeWindow()
    monkeypatch.setattr(update_controller, "current_version", lambda: "2.3.0")
    controller = UpdateController(window, preferences=prefs)

    controller.maybe_show_startup_update_notice()

    assert window.infos == []
    assert prefs.last_seen_versions == []


def test_skipped_version_suppresses_auto_but_manual_prompt_indicates_skipped() -> None:
    from app_desktop.update_controller import UpdateController

    prefs = FakePreferences()
    prefs.enabled = True
    prefs.skipped.add("2.3.0")
    now = datetime(2026, 5, 26, tzinfo=timezone.utc)

    def make_controller(window: FakeWindow) -> UpdateController:
        return UpdateController(
            window,
            preferences=prefs,
            check_for_updates=lambda: UpdateCheckResult(
                status="update-available",
                current_version="2.2.0",
                latest_version="2.3.0",
                release=release(),
            ),
            resolve_payload=lambda _release, current_version: payload(),
            download_installer=lambda asset: Path("/tmp/DataLab.pkg"),
            launch_installer=lambda path, asset: True,
            now=lambda: now,
        )

    auto_window = FakeWindow()
    make_controller(auto_window).maybe_auto_check()

    assert auto_window.questions == []
    assert auto_window.warnings == []
    assert prefs.checked_at == now

    manual_window = FakeWindow(choice="later", english=True)
    make_controller(manual_window).check_now()

    assert manual_window.questions[0][0] == "Update Available"
    assert manual_window.questions[0][2] is True
    assert "previously skipped" in manual_window.questions[0][1]
    assert manual_window.exited is False


def test_build_update_message_contains_release_and_installer_details() -> None:
    from app_desktop.update_dialogs import build_update_message

    message = build_update_message(
        payload(),
        current_version="2.2.0",
        lang="en",
        was_skipped=True,
    )

    assert "Version 2.3.0" in message
    assert "Current version: 2.2.0" in message
    assert "2026-05-26T00:00:00Z" in message
    assert "DataLab.pkg" in message
    assert "10 B" in message
    assert "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0" in message
    assert "Installer updater notes" in message
    assert "DataLab will close" in message
    assert "previously skipped" in message
