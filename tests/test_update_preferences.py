from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from shared.settings_store import SettingsStore
from shared.update_preferences import UpdatePreferences


class FakeSettings:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}
        self.sync_count = 0

    def value(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def setValue(self, key: str, value: object) -> None:  # noqa: N802
        self.values[key] = value

    def remove(self, key: str) -> None:
        self.values.pop(key, None)

    def sync(self) -> None:
        self.sync_count += 1

    def status(self) -> int:
        return 0


def _prefs() -> tuple[UpdatePreferences, FakeSettings]:
    fake = FakeSettings()
    return UpdatePreferences(SettingsStore(store=fake)), fake


def test_default_auto_update_off_should_auto_check_false_until_enabled() -> None:
    prefs, _ = _prefs()
    now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)

    assert prefs.auto_update_enabled() is False
    assert prefs.should_auto_check(now) is False


def test_after_enabling_no_last_check_should_auto_check_true() -> None:
    prefs, _ = _prefs()
    now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)

    prefs.set_auto_update_enabled(True)

    assert prefs.auto_update_enabled() is True
    assert prefs.should_auto_check(now) is True


def test_mark_checked_throttles_until_auto_check_interval_passes() -> None:
    from shared.update_preferences import AUTO_CHECK_INTERVAL

    prefs, _ = _prefs()
    now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
    prefs.set_auto_update_enabled(True)

    prefs.mark_checked(now)

    assert prefs.should_auto_check(now + AUTO_CHECK_INTERVAL - timedelta(seconds=1)) is False
    assert prefs.should_auto_check(now + AUTO_CHECK_INTERVAL) is True


def test_future_clock_skew_more_than_allowance_allows_one_rewrite_check() -> None:
    from shared.update_preferences import FUTURE_CLOCK_SKEW_ALLOWANCE

    prefs, _ = _prefs()
    now = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)
    prefs.set_auto_update_enabled(True)

    prefs.mark_checked(now + FUTURE_CLOCK_SKEW_ALLOWANCE + timedelta(seconds=1))

    assert prefs.should_auto_check(now) is True

    prefs.mark_checked(now)

    assert prefs.should_auto_check(now) is False


def test_skip_version_and_is_skipped() -> None:
    prefs, _ = _prefs()

    prefs.skip_version("v2.1.0")

    assert prefs.is_skipped("2.1.0") is True
    assert prefs.is_skipped("2.1.1") is False


def test_cache_release_notes_roundtrip() -> None:
    prefs, _ = _prefs()

    prefs.cache_release_notes(
        version="2.1.0",
        notes="Release notes",
        url="https://github.com/yilibinbin/DataLab/releases/tag/v2.1.0",
        published_at="2026-05-26T12:00:00Z",
    )

    cached = prefs.cached_release_notes()

    assert cached is not None
    assert cached.version == "2.1.0"
    assert cached.notes == "Release notes"
    assert cached.url == "https://github.com/yilibinbin/DataLab/releases/tag/v2.1.0"
    assert cached.published_at == "2026-05-26T12:00:00Z"


def test_consume_version_changed_notice_true_once_per_new_version() -> None:
    prefs, _ = _prefs()

    assert prefs.consume_version_changed_notice("2.1.0") is True
    assert prefs.consume_version_changed_notice("2.1.0") is False
    assert prefs.consume_version_changed_notice("2.1.1") is True
    assert prefs.consume_version_changed_notice("v2.1.1") is False
