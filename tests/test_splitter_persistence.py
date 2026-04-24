"""Splitter-state persistence — end-to-end regression test.

Pins the Phase 2 Task 2.1 contract:
- the main splitter exposes itself as ``self._main_splitter``
- ``closeEvent`` saves ``splitter.saveState()`` to
  ``KEY_MAIN_SPLITTER_STATE`` via ``SettingsStore``
- ``build_ui`` loads the blob back and calls ``restoreState`` on it

Uses pytest-qt to construct a real ``ExtrapolationWindow``, drag the
splitter, close, and confirm the next instance opens with the same
dimensions. QSettings is monkey-patched with an in-memory fake so the
test never touches the real user scope.
"""

from __future__ import annotations

import os
from typing import Any, Dict

import pytest

# Desktop tests require a Qt offscreen platform. If that isn't set this
# module's import of ``ExtrapolationWindow`` will try to open an X
# display and fail.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from shared.settings_store import (  # noqa: E402
    KEY_MAIN_SPLITTER_STATE,
    SettingsStore,
)


@pytest.fixture
def _fake_settings(monkeypatch):
    """Replace the QSettings factory with an in-memory dict so the test
    is hermetic. Must patch at the SettingsStore-constructor level so
    both the load path (build_ui) and the save path (closeEvent) use
    the same fake."""

    class _FakeQSettings:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            # Share storage across every instance — the app creates
            # fresh ones in build_ui and closeEvent.
            pass

        def value(self, key: str, default: Any = None) -> Any:
            return _shared_storage.get(key, default)

        def setValue(self, key: str, value: Any) -> None:  # noqa: N802
            _shared_storage[key] = value

        def remove(self, key: str) -> None:
            _shared_storage.pop(key, None)

        def sync(self) -> None:
            pass

        def clear(self) -> None:
            _shared_storage.clear()

    _shared_storage: Dict[str, Any] = {}
    monkeypatch.setattr(
        "shared.settings_store.QSettings", _FakeQSettings
    )
    yield _shared_storage


def test_splitter_state_round_trips_across_window_lifetimes(qtbot, _fake_settings):
    """Construct a window, mutate the splitter, close, reopen — the
    second instance must start with the saved sizes."""
    from app_desktop.window import ExtrapolationWindow

    # Ensure we have a QApplication. pytest-qt normally handles this,
    # but we also call it here for belt-and-braces (e.g., if the test
    # is run ad-hoc).
    app = QApplication.instance() or QApplication([])  # noqa: F841

    win1 = ExtrapolationWindow()
    qtbot.addWidget(win1)
    splitter = getattr(win1, "_main_splitter", None)
    assert splitter is not None, (
        "build_ui must expose the splitter as self._main_splitter"
    )
    # Mutate the splitter to a distinctive state so we can tell a
    # successful restore from default-on-reopen.
    splitter.setSizes([300, 1040])
    expected_state = QByteArray(splitter.saveState())
    assert not expected_state.isEmpty()

    # Close → saves state → tear down.
    win1.close()
    saved = _fake_settings.get(KEY_MAIN_SPLITTER_STATE)
    assert saved is not None, "closeEvent must save splitter state"
    assert isinstance(saved, QByteArray) and not saved.isEmpty()

    # Open a fresh instance — build_ui loads the state and applies it.
    win2 = ExtrapolationWindow()
    qtbot.addWidget(win2)
    restored = win2._main_splitter.saveState()
    assert bytes(restored) == bytes(expected_state), (
        "new window must restore the previously-saved splitter state"
    )
    win2.close()


def test_corrupted_splitter_state_blob_is_discarded(qtbot, _fake_settings):
    """A stale/corrupt blob from an older app version (e.g., after a
    layout refactor) must be silently discarded, not crash startup."""
    from app_desktop.window import ExtrapolationWindow

    _fake_settings[KEY_MAIN_SPLITTER_STATE] = QByteArray(
        b"\x00corrupted-blob-wrong-length\xff"
    )

    app = QApplication.instance() or QApplication([])  # noqa: F841
    # Must not raise
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    assert getattr(win, "_main_splitter", None) is not None
    # The restore failed silently — our build_ui wrapper clears the
    # bad blob. Confirm it was removed so we don't keep retrying.
    assert _fake_settings.get(KEY_MAIN_SPLITTER_STATE) is None
    win.close()
