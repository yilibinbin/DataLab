"""Persistent update preferences for DataLab.

This module intentionally stores only non-sensitive strings and booleans in
``SettingsStore``. It is Qt-free apart from the injected settings backend, so
startup update policy can be tested without a QApplication.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from shared.settings_store import (
    KEY_UPDATE_AUTO_ENABLED,
    KEY_UPDATE_CACHE_NOTES,
    KEY_UPDATE_CACHE_PUBLISHED_AT,
    KEY_UPDATE_CACHE_URL,
    KEY_UPDATE_CACHE_VERSION,
    KEY_UPDATE_LAST_CHECKED_AT,
    KEY_UPDATE_LAST_SEEN_VERSION,
    KEY_UPDATE_SKIPPED_VERSION,
    SettingsStore,
)
from shared.update_checker import normalize_version_tag


AUTO_CHECK_INTERVAL = timedelta(hours=24)
FUTURE_CLOCK_SKEW_ALLOWANCE = timedelta(minutes=10)


@dataclass(frozen=True)
class CachedReleaseNotes:
    version: str
    notes: str
    url: str
    published_at: str


class UpdatePreferences:
    def __init__(self, store: SettingsStore | None = None) -> None:
        self._store = store or SettingsStore()

    def auto_update_enabled(self) -> bool:
        return self._store.load_bool(KEY_UPDATE_AUTO_ENABLED, default=False)

    def set_auto_update_enabled(self, enabled: bool) -> None:
        self._store.save_bool(KEY_UPDATE_AUTO_ENABLED, enabled)

    def should_auto_check(self, now: datetime | None = None) -> bool:
        if not self.auto_update_enabled():
            return False
        checked_at = self._last_checked_at()
        if checked_at is None:
            return True
        current_time = _coerce_utc(now)
        if checked_at - current_time > FUTURE_CLOCK_SKEW_ALLOWANCE:
            return True
        return current_time - checked_at >= AUTO_CHECK_INTERVAL

    def mark_checked(self, when: datetime | None = None) -> None:
        self._store.save_string(KEY_UPDATE_LAST_CHECKED_AT, _format_datetime(when))

    def skip_version(self, version: str) -> None:
        self._store.save_string(KEY_UPDATE_SKIPPED_VERSION, normalize_version_tag(version))

    def is_skipped(self, version: str) -> bool:
        skipped = self._store.load_string(KEY_UPDATE_SKIPPED_VERSION, default="").strip()
        return bool(skipped) and skipped == normalize_version_tag(version)

    def cache_release_notes(
        self,
        *,
        version: str,
        notes: str,
        url: str,
        published_at: str,
    ) -> None:
        self._store.save_string(KEY_UPDATE_CACHE_VERSION, normalize_version_tag(version))
        self._store.save_string(KEY_UPDATE_CACHE_NOTES, notes)
        self._store.save_string(KEY_UPDATE_CACHE_URL, url)
        self._store.save_string(KEY_UPDATE_CACHE_PUBLISHED_AT, published_at)

    def cached_release_notes(self) -> CachedReleaseNotes | None:
        version = self._store.load_string(KEY_UPDATE_CACHE_VERSION, default="").strip()
        if not version:
            return None
        return CachedReleaseNotes(
            version=version,
            notes=self._store.load_string(KEY_UPDATE_CACHE_NOTES, default=""),
            url=self._store.load_string(KEY_UPDATE_CACHE_URL, default=""),
            published_at=self._store.load_string(
                KEY_UPDATE_CACHE_PUBLISHED_AT, default=""
            ),
        )

    def consume_version_changed_notice(self, current_version: str) -> bool:
        normalized = normalize_version_tag(current_version)
        if not normalized:
            return False
        last_seen = self._store.load_string(KEY_UPDATE_LAST_SEEN_VERSION, default="")
        if normalize_version_tag(last_seen) == normalized:
            return False
        self._store.save_string(KEY_UPDATE_LAST_SEEN_VERSION, normalized)
        return True

    def _last_checked_at(self) -> datetime | None:
        raw = self._store.load_string(KEY_UPDATE_LAST_CHECKED_AT, default="").strip()
        if not raw:
            return None
        return _parse_datetime(raw)


def _coerce_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _format_datetime(value: datetime | None) -> str:
    return _coerce_utc(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _coerce_utc(parsed)
