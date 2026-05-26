from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from shared.update_checker import ReleaseInfo, UpdateCheckResult
from shared.update_payload import InstallerAsset, UpdatePayload


class FakePreferences:
    def __init__(self) -> None:
        self.enabled = False
        self.checked = False
        self.checked_at: datetime | None = None
        self.skipped: set[str] = set()
        self.cached: list[tuple[str, str, str, str]] = []

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
    assert "10 bytes" in message
    assert "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0" in message
    assert "Installer updater notes" in message
    assert "DataLab will close" in message
    assert "previously skipped" in message
