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
    "MAX_BLOB_BYTES",
    "SettingsStore",
    "ensure_qt_application_identity",
]

_logger = logging.getLogger(__name__)

# Public constants — keep in sync with the packaging metadata. Changing
# either value will orphan existing user settings (QSettings namespaces
# by org+app pair), so treat them as stable once shipped.
SETTINGS_ORG = "DataLab"
SETTINGS_APP = "Desktop"

# Upper bound on any single blob written or read. QSplitter saveState
# for two panes is ~80 bytes; QMainWindow saveState with the current
# docked-widget layout is ~1 KB; the cap is set well above both.
# Applies to BOTH the write path (a bug that tries to persist a huge
# QByteArray fails fast instead of corrupting the prefs store) and the
# read path (an attacker-crafted plist cannot feed arbitrary-sized
# blobs into Qt's restoreState parsers).
MAX_BLOB_BYTES = 64 * 1024  # 64 KiB

# Namespace allowlist. The "no secrets" policy in this module's docstring
# is enforced as a runtime check at every write — a future caller that
# tries ``save_bytes("api/token", ...)`` fails loudly instead of silently
# landing a token in ``~/Library/Preferences/DataLab.Desktop.plist``.
# Extend only after checking whether the proposed key is appropriate
# for plaintext storage.
_ALLOWED_KEY_PREFIXES: tuple[str, ...] = (
    "MainWindow/",  # geometry, state, splitter_state
    "Fitting/",     # last_dpi, preferred_model, etc.
    "Extrapolation/",  # last-used method / parameters
    "Preview/",     # zoom, dark mode, last dpi
    "Preferences/", # generic UI prefs
)


def ensure_qt_application_identity() -> None:
    """Set the QCoreApplication org+app identity if it isn't already set.

    Note: ``SettingsStore`` uses the two-argument ``QSettings(org, app)``
    constructor, which is **immune** to a pre-set wrong org/app. This
    helper only matters for future code using the no-argument
    ``QSettings()`` form (or any Qt API that consults the global
    application identity). We intentionally do NOT override a value
    already set by the parent process — doing so could break embedding
    scenarios where DataLab runs inside another Qt host.
    """
    if not QCoreApplication.organizationName():
        QCoreApplication.setOrganizationName(SETTINGS_ORG)
    if not QCoreApplication.applicationName():
        QCoreApplication.setApplicationName(SETTINGS_APP)


def _validate_key(key: str) -> None:
    """Enforce the namespace allowlist. Called from every write path.

    Raises ``ValueError`` with an explanatory message if the caller is
    trying to write outside the allowed prefixes — callers storing
    secrets should use a platform secret manager (``keyring`` on
    desktop; never ``QSettings``, which is plaintext plist on macOS
    and per-user registry on Windows).
    """
    if not any(key.startswith(p) for p in _ALLOWED_KEY_PREFIXES):
        allowed = ", ".join(_ALLOWED_KEY_PREFIXES)
        raise ValueError(
            f"SettingsStore: key {key!r} is not in the allowed namespace "
            f"({allowed}). Store only non-sensitive UI state here; use a "
            "secret manager (e.g. keyring) for tokens and credentials."
        )


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

        NOT FOR SENSITIVE DATA. Values land in plaintext on every
        supported platform. Use a secret manager (e.g. ``keyring``) for
        anything else. The key-namespace allowlist in ``_validate_key``
        blocks attempts to write outside the UI-state namespace.

        QSettings accepts ``QByteArray`` natively; plain ``bytes`` is
        wrapped first so the platform backends (plist on macOS,
        registry on Windows) get a consistent type. Blobs exceeding
        ``MAX_BLOB_BYTES`` are rejected to prevent a buggy caller (or
        attacker-supplied value) from corrupting the prefs store.
        """
        _validate_key(key)
        try:
            if value is None:
                self._store.remove(key)
            else:
                blob = value if isinstance(value, QByteArray) else QByteArray(bytes(value))
                if blob.size() > MAX_BLOB_BYTES:
                    _logger.warning(
                        "SettingsStore.save_bytes(%s): blob of %d bytes "
                        "exceeds MAX_BLOB_BYTES=%d; not persisted",
                        key,
                        blob.size(),
                        MAX_BLOB_BYTES,
                    )
                    return
                self._store.setValue(key, blob)
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
        absent, empty, corrupted (wrong type), or exceeds
        ``MAX_BLOB_BYTES`` (attacker-planted oversized blob — don't
        hand to Qt's restoreState parsers).

        NOTE: ``key`` must be a compile-time constant — DO NOT embed
        user-supplied data. The key is emitted in warning logs; dynamic
        keys risk information disclosure via log aggregation.
        """
        try:
            raw = self._store.value(key)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.load_bytes(%s) failed: %s", key, exc)
            return None
        if raw is None:
            return None
        if isinstance(raw, QByteArray):
            blob: Optional[QByteArray] = raw if not raw.isEmpty() else None
        elif isinstance(raw, (bytes, bytearray)):
            blob = QByteArray(bytes(raw)) if raw else None
        else:
            # Values written by a foreign process in the wrong type — ignore.
            _logger.debug(
                "SettingsStore.load_bytes(%s): unexpected type %s, ignoring",
                key,
                type(raw).__name__,
            )
            return None
        if blob is not None and blob.size() > MAX_BLOB_BYTES:
            _logger.warning(
                "SettingsStore.load_bytes(%s): oversized blob (%d bytes) "
                "rejected; discarding",
                key,
                blob.size(),
            )
            return None
        return blob

    # ------------------------------------------------------------------
    # Integer helpers (for single-value settings like last-used dpi)
    # ------------------------------------------------------------------

    def save_int(self, key: str, value: int) -> None:
        """Persist an integer. Key-namespace enforced via
        ``_validate_key``."""
        _validate_key(key)
        try:
            self._store.setValue(key, int(value))
            self._store.sync()
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.save_int(%s) failed: %s", key, exc)

    def load_int(
        self,
        key: str,
        default: int = 0,
        min_val: int | None = None,
        max_val: int | None = None,
    ) -> int:
        """Load an integer, optionally clamped to ``[min_val, max_val]``.

        The clamp defends against a hand-edited or attacker-replaced
        prefs file (e.g. ``last_dpi=2147483647``) reaching code that
        allocates buffers proportional to the value. Callers with a
        known safe range SHOULD pass both bounds; callers using the
        default (0, no clamps) should clamp at the use site.
        """
        try:
            raw = self._store.value(key)
        except Exception as exc:  # noqa: BLE001
            _logger.warning("SettingsStore.load_int(%s) failed: %s", key, exc)
            return default
        if raw is None:
            return default
        try:
            value = int(raw)
        except (TypeError, ValueError):
            return default
        if min_val is not None:
            value = max(min_val, value)
        if max_val is not None:
            value = min(max_val, value)
        return value

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
