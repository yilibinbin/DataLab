"""``shared.settings_store`` — regression tests.

Pins the wrapper's contract so a future refactor can't silently drop
the persistence of main-window geometry or the splitter state. Uses
an in-memory fake QSettings so we don't pollute the real user scope
during CI runs (QSettings on macOS writes to ~/Library/Preferences).
"""

from __future__ import annotations

from typing import Any, Dict

import pytest
from PySide6.QtCore import QByteArray

from shared.settings_store import (
    KEY_MAIN_SPLITTER_STATE,
    KEY_MAIN_WINDOW_GEOMETRY,
    KEY_MAIN_WINDOW_STATE,
    SETTINGS_APP,
    SETTINGS_ORG,
    SettingsStore,
    ensure_qt_application_identity,
)


class _FakeQSettings:
    """Minimal stand-in for ``QSettings``. Implements only the methods
    ``SettingsStore`` uses so test isolation is trivially verifiable."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self.sync_count = 0

    def value(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def setValue(self, key: str, value: Any) -> None:  # noqa: N802
        self._data[key] = value

    def remove(self, key: str) -> None:
        self._data.pop(key, None)

    def sync(self) -> None:
        self.sync_count += 1

    def clear(self) -> None:
        self._data.clear()


@pytest.fixture
def _store() -> tuple[SettingsStore, _FakeQSettings]:
    fake = _FakeQSettings()
    return SettingsStore(store=fake), fake


def test_save_and_load_bytes_roundtrip(_store):
    store, fake = _store
    payload = QByteArray(b"\x01\x02\x03splitter-state\xff")
    store.save_bytes(KEY_MAIN_SPLITTER_STATE, payload)
    assert fake.sync_count >= 1, "save_bytes must flush via sync()"
    loaded = store.load_bytes(KEY_MAIN_SPLITTER_STATE)
    assert loaded is not None
    assert bytes(loaded) == bytes(payload)


def test_load_bytes_returns_none_for_missing_key(_store):
    store, _ = _store
    assert store.load_bytes("nonexistent/key") is None


def test_save_bytes_none_clears_key(_store):
    store, fake = _store
    store.save_bytes(KEY_MAIN_WINDOW_GEOMETRY, QByteArray(b"junk"))
    assert KEY_MAIN_WINDOW_GEOMETRY in fake._data
    store.save_bytes(KEY_MAIN_WINDOW_GEOMETRY, None)
    assert KEY_MAIN_WINDOW_GEOMETRY not in fake._data


def test_save_bytes_accepts_plain_bytes(_store):
    store, _ = _store
    store.save_bytes(KEY_MAIN_WINDOW_STATE, b"raw-python-bytes")
    loaded = store.load_bytes(KEY_MAIN_WINDOW_STATE)
    assert loaded is not None
    assert bytes(loaded) == b"raw-python-bytes"


def test_load_bytes_treats_empty_bytearray_as_absent(_store):
    """An explicitly-empty QByteArray is indistinguishable from a stale
    blob; treat as "no value" so the caller's default path runs."""
    store, fake = _store
    fake._data[KEY_MAIN_SPLITTER_STATE] = QByteArray(b"")
    assert store.load_bytes(KEY_MAIN_SPLITTER_STATE) is None


def test_load_bytes_ignores_wrong_type(_store):
    """Some other tool / older version might have written a string at
    this key. Ignore rather than raise."""
    store, fake = _store
    fake._data[KEY_MAIN_WINDOW_GEOMETRY] = "not-bytes"
    assert store.load_bytes(KEY_MAIN_WINDOW_GEOMETRY) is None


def test_save_and_load_int_roundtrip(_store):
    store, _ = _store
    store.save_int("Fitting/last_dpi", 350)
    assert store.load_int("Fitting/last_dpi") == 350


def test_load_int_returns_default_for_missing(_store):
    store, _ = _store
    assert store.load_int("Fitting/nonexistent", default=42) == 42


def test_load_int_returns_default_for_garbage(_store):
    store, fake = _store
    fake._data["Fitting/last_dpi"] = "not-an-int"
    assert store.load_int("Fitting/last_dpi", default=200) == 200


def test_load_int_range_clamp_enforces_bounds(_store):
    """Defends against hand-edited or attacker-replaced plist values —
    a stored ``last_dpi=2147483647`` must clamp down to the supplied
    ceiling rather than reach the renderer unchanged."""
    store, fake = _store
    fake._data["Fitting/last_dpi"] = 2_147_483_647
    assert (
        store.load_int("Fitting/last_dpi", default=150, min_val=50, max_val=600)
        == 600
    )
    fake._data["Fitting/last_dpi"] = -999
    assert (
        store.load_int("Fitting/last_dpi", default=150, min_val=50, max_val=600)
        == 50
    )


def test_remove_deletes_key(_store):
    store, fake = _store
    store.save_int("Fitting/dpi", 350)
    store.remove("Fitting/dpi")
    assert "Fitting/dpi" not in fake._data


def test_clear_all_wipes_everything(_store):
    store, fake = _store
    store.save_int("Fitting/a", 1)
    store.save_bytes("MainWindow/b", b"x")
    store.clear_all()
    assert not fake._data


def test_save_bytes_rejects_key_outside_allowlist(_store):
    """The 'no secrets' policy in the docstring is enforced at runtime —
    a future caller trying to land a token in the plist fails loudly."""
    store, _ = _store
    with pytest.raises(ValueError, match="allowed namespace"):
        store.save_bytes("api/token", b"secret")


def test_save_int_rejects_key_outside_allowlist(_store):
    store, _ = _store
    with pytest.raises(ValueError, match="allowed namespace"):
        store.save_int("users/uid", 1001)


def test_save_bytes_rejects_oversized_blob(_store):
    """A buggy caller or attacker-supplied value cannot bloat the
    prefs store beyond MAX_BLOB_BYTES."""
    from shared.settings_store import MAX_BLOB_BYTES

    store, fake = _store
    oversized = QByteArray(b"x" * (MAX_BLOB_BYTES + 1))
    store.save_bytes("MainWindow/state", oversized)
    # Not persisted — the warning-logged rejection leaves the key absent.
    assert "MainWindow/state" not in fake._data


def test_load_bytes_rejects_oversized_blob(_store):
    """An attacker who replaces the plist with a giant blob cannot
    feed it into Qt's restoreState parsers."""
    from shared.settings_store import MAX_BLOB_BYTES

    store, fake = _store
    fake._data["MainWindow/state"] = QByteArray(b"x" * (MAX_BLOB_BYTES + 1))
    assert store.load_bytes("MainWindow/state") is None


def test_save_bytes_swallows_errors_does_not_raise(monkeypatch):
    """A full disk / read-only prefs dir must not crash the app."""
    class _RaisingFake(_FakeQSettings):
        def setValue(self, key, value):  # noqa: N802
            raise OSError("disk full")

    store = SettingsStore(store=_RaisingFake())
    # Must not raise
    store.save_bytes(KEY_MAIN_SPLITTER_STATE, QByteArray(b"x"))


def test_load_bytes_swallows_errors_returns_none(monkeypatch):
    class _RaisingFake(_FakeQSettings):
        def value(self, key, default=None):
            raise OSError("io error")

    store = SettingsStore(store=_RaisingFake())
    assert store.load_bytes("any") is None


def test_ensure_qt_application_identity_is_idempotent():
    """Calling twice is safe and doesn't clobber existing values."""
    from PySide6.QtCore import QCoreApplication

    # Whether the testing environment already set these or not, the
    # function must leave them non-empty.
    ensure_qt_application_identity()
    org = QCoreApplication.organizationName()
    app = QCoreApplication.applicationName()
    ensure_qt_application_identity()
    assert QCoreApplication.organizationName() == org
    assert QCoreApplication.applicationName() == app
    # And the values must match our constants (or pre-set by the env).
    assert org and app


def test_constants_are_strings():
    """Paranoid guard: if someone ever changes these to enums we want
    to force an explicit code review across the persistence layer."""
    assert isinstance(SETTINGS_ORG, str) and SETTINGS_ORG
    assert isinstance(SETTINGS_APP, str) and SETTINGS_APP
    assert isinstance(KEY_MAIN_WINDOW_GEOMETRY, str)
    assert isinstance(KEY_MAIN_WINDOW_STATE, str)
    assert isinstance(KEY_MAIN_SPLITTER_STATE, str)
