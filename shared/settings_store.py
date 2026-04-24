"""Persistent settings store for DataLab desktop.

Thin wrapper over ``PySide6.QtCore.QSettings`` that centralises all
configuration keys so they're discoverable in one place, type-checked
at the boundary, and bilingual-ready for the preferences UI later.

Design goals:
- **No QtWidgets import**: only ``QtCore`` so the store can be imported
  from headless contexts (CLI, tests) without a QApplication. The store
  does not know or care about the widgets it persists state for.
- **Binary-safe values**: splitter geometry, window geometry, and tab
  positions are ``QByteArray`` blobs from ``QMainWindow.saveState`` /
  ``QSplitter.saveState``. QSettings round-trips these transparently
  on all platforms when stored at a single key.
- **No schema evolution**: each key is a dumb blob; on a version
  mismatch the widget's ``restoreState`` returns False and the UI
  falls back to defaults. We do NOT try to migrate stale blobs — the
  cost of a stale restore (mildly off-centred panel) is dwarfed by the
  correctness cost of guessing at binary layout changes.
- **No secrets**: QSettings on macOS writes to ``~/Library/Preferences``
  (plaintext plist); on Windows, the registry. Neither is suitable for
  tokens or credentials. Callers storing anything other than UI state
  must use a secret manager instead.

Organisation-level keys (not per-user):
  DataLab / Desktop / MainWindow / geometry
  DataLab / Desktop / MainWindow / state
  DataLab / Desktop / MainWindow / main_splitter_state
  DataLab / Desktop / Fitting / last_dpi  (example for future use)

The organisation + application name pair is set once at module import
time via ``QCoreApplication.setOrganizationName`` /
``setApplicationName`` if the caller hasn't already done so. That lets
QSettings pick the right default scope (per-user, per-app).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PySide6.QtCore import QByteArray, QCoreApplication, QSettings

__all__ = [
    "SETTINGS_ORG",
    "SETTINGS_APP",
    "SettingsStore",
    "ensure_qt_application_identity",
]

_logger = logging.getLogger(__name__)

# Public constants — keep in sync with the packaging metadata. Changing
# either value will orphan existing user settings (QSettings namespaces
# by org+app pair), so treat them as stable once shipped.
SETTINGS_ORG = "DataLab"
SETTINGS_APP = "Desktop"


def ensure_qt_application_identity() -> None:
    """Set the QCoreApplication org+app identity if it isn't already set.

    QSettings with the ``(org, app)`` constructor — the one we use — does
    not need this, but QSettings() with the default constructor does.
    Call this at process startup to make both flavours work
    interchangeably and to make the desktop's settings visible to any
    future Qt-backed tool (e.g. a diagnostics CLI)."""
    if not QCoreApplication.organizationName():
        QCoreApplication.setOrganizationName(SETTINGS_ORG)
    if not QCoreApplication.applicationName():
        QCoreApplication.setApplicationName(SETTINGS_APP)


class SettingsStore:
    """Typed accessor over QSettings.

    Instantiate once and share the instance across a process; QSettings
    is cheap to construct but the explicit seam makes the surface
    greppable and trivial to mock in tests (``SettingsStore(store=...)``
    injection takes a stand-in implementing ``value`` / ``setValue`` /
    ``remove`` / ``sync``).
    """

    def __init__(self, store: Optional[Any] = None) -> None:
        if store is None:
            ensure_qt_application_identity()
            store = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self._store = store

    # ------------------------------------------------------------------
    # Binary blob helpers (splitter / window state)
    # ------------------------------------------------------------------

    def save_bytes(self, key: str, value: QByteArray | bytes | None) -> None:
        """Persist a binary blob. ``None`` clears the key.

        QSettings accepts ``QByteArray`` natively; plain ``bytes`` is
        wrapped first so the platform backends (plist on macOS,
        registry on Windows) get a consistent type.
        """
        try:
            if value is None:
                self._store.remove(key)
            elif isinstance(value, QByteArray):
                self._store.setValue(key, value)
            else:
                self._store.setValue(key, QByteArray(bytes(value)))
            self._store.sync()
        except Exception as exc:  # noqa: BLE001
            # A failed write is non-fatal — worst case is the next start
            # falls back to defaults. Log at warning so sysadmins on a
            # read-only ~/Library can see the problem.
            _logger.warning(
                "SettingsStore.save_bytes(%s) failed: %s", key, exc
            )

    def load_bytes(self, key: str) -> Optional[QByteArray]:
        """Retrieve a binary blob. Returns ``None`` when the key is
        absent or corrupted (non-bytes value)."""
        try:
            raw = self._store.value(key)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.load_bytes(%s) failed: %s", key, exc)
            return None
        if raw is None:
            return None
        if isinstance(raw, QByteArray):
            return raw if not raw.isEmpty() else None
        if isinstance(raw, (bytes, bytearray)):
            return QByteArray(bytes(raw)) if raw else None
        # Values written by a foreign process in the wrong type — ignore.
        _logger.debug(
            "SettingsStore.load_bytes(%s): unexpected type %s, ignoring",
            key,
            type(raw).__name__,
        )
        return None

    # ------------------------------------------------------------------
    # Integer helpers (for single-value settings like last-used dpi)
    # ------------------------------------------------------------------

    def save_int(self, key: str, value: int) -> None:
        try:
            self._store.setValue(key, int(value))
            self._store.sync()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.save_int(%s) failed: %s", key, exc)

    def load_int(self, key: str, default: int = 0) -> int:
        try:
            raw = self._store.value(key)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.load_int(%s) failed: %s", key, exc)
            return default
        if raw is None:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    # ------------------------------------------------------------------
    # Bookkeeping
    # ------------------------------------------------------------------

    def remove(self, key: str) -> None:
        """Forget the given key. No error if it was already absent."""
        try:
            self._store.remove(key)
            self._store.sync()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.remove(%s) failed: %s", key, exc)

    def clear_all(self) -> None:
        """Wipe every key under this ``(org, app)`` namespace. Mainly
        for tests and for a user-facing "reset preferences" action."""
        try:
            self._store.clear()
            self._store.sync()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.clear_all failed: %s", exc)


# Pre-declared key constants. Consumers should import these rather than
# re-typing strings, so a rename is one grep away.
KEY_MAIN_WINDOW_GEOMETRY = "MainWindow/geometry"
KEY_MAIN_WINDOW_STATE = "MainWindow/state"
KEY_MAIN_SPLITTER_STATE = "MainWindow/main_splitter_state"
