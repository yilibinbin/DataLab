"""Named preset library for DataLab.

Stores preset dicts (model + parameter defaults + display preferences)
under ``SettingsStore`` using the ``Preferences/presets/<name>`` key
format. Every preset is JSON-encoded so the storage layer sees only
bytes and the complex-Python-types concern stays in this module.

Why presets live here, not in ``SettingsStore``:
- ``SettingsStore`` is deliberately narrow (bytes + ints). Giving it
  a ``save_dict`` method would invite schema drift across callers.
- Presets are the only caller that needs dict/list round-trip. The
  JSON encode/decode + name sanitisation + MAX_PRESET_BYTES cap are
  all preset-specific.

Name sanitisation is load-bearing:
- Preset names flow into the QSettings key via string concatenation
  (``Preferences/presets/<name>``). A user-supplied name containing
  ``/`` could write into a neighbour namespace; a name with control
  characters could corrupt the key index on some backends.
- ``sanitize_preset_name`` rejects both and collapses whitespace.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping, Optional

from shared.settings_store import SettingsStore

__all__ = [
    "MAX_PRESET_BYTES",
    "PRESET_NAMESPACE",
    "delete_preset",
    "list_preset_names",
    "load_preset",
    "sanitize_preset_name",
    "save_preset",
]

_logger = logging.getLogger(__name__)

# Match the SettingsStore allowlist prefix (Preferences/) so writes
# aren't rejected. Keep the sub-namespace explicit so a grep for
# "presets/" in the codebase lands on this module.
PRESET_NAMESPACE = "Preferences/presets/"

# 32 KiB per preset keeps well under the SettingsStore blob cap
# (MAX_BLOB_BYTES = 64 KiB). A realistic preset is <1 KiB — this cap
# is defensive against a caller that stuffs a large history array
# into a preset.
MAX_PRESET_BYTES = 32 * 1024

_NAME_SANITISE_WHITESPACE = re.compile(r"\s+")
# Reject non-whitespace C0/C1 control chars. ASCII whitespace
# (``\t\n\r\f\v``, and space) is handled by _NAME_SANITISE_WHITESPACE
# and must not trigger the control-char reject.
_NAME_CONTROL_CHARS = re.compile(
    r"[\x00-\x08\x0e-\x1f\x7f-\x9f]"
)
# Path separators + traversal markers — reject outright.
_NAME_FORBIDDEN = ("/", "\\", "..")


def sanitize_preset_name(name: str) -> str:
    """Validate + canonicalise a preset name.

    Strips leading/trailing whitespace, collapses inner whitespace to
    a single space. Rejects empty names, control chars, and path
    separators / traversal markers.

    Order matters: control-char check runs FIRST because Python's
    ``\\s+`` regex in Unicode mode treats ``\\x0e``-``\\x1f`` as
    whitespace too, and we don't want a ``\\x1f`` byte to silently
    collapse into a space and then pass the control-char check.
    """
    if not isinstance(name, str):
        raise ValueError(
            f"preset name must be str, got {type(name).__name__}"
        )
    if _NAME_CONTROL_CHARS.search(name):
        raise ValueError("preset name must not contain control characters")
    collapsed = _NAME_SANITISE_WHITESPACE.sub(" ", name).strip()
    if not collapsed:
        raise ValueError("preset name must not be empty or whitespace-only")
    for forbidden in _NAME_FORBIDDEN:
        if forbidden in collapsed:
            raise ValueError(
                f"preset name must not contain {forbidden!r} — would "
                "corrupt the SettingsStore key namespace"
            )
    return collapsed


def _key_for(name: str) -> str:
    return PRESET_NAMESPACE + sanitize_preset_name(name)


def save_preset(
    name: str,
    preset: Mapping[str, Any],
    store: Optional[SettingsStore] = None,
) -> None:
    """Persist a preset under the sanitised name.

    Raises
    ------
    ValueError
        If the name is invalid, the body isn't a dict, the body
        isn't JSON-serialisable, or the serialised size exceeds
        ``MAX_PRESET_BYTES``.
    """
    if not isinstance(preset, Mapping):
        raise ValueError(
            f"preset body must be a dict/mapping, got {type(preset).__name__}"
        )
    try:
        encoded = json.dumps(dict(preset), ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"preset body is not JSON-serialisable: {exc}"
        ) from exc
    blob = encoded.encode("utf-8")
    if len(blob) > MAX_PRESET_BYTES:
        raise ValueError(
            f"preset serialised size {len(blob)} bytes exceeds cap "
            f"{MAX_PRESET_BYTES}; simplify the body"
        )
    (store or SettingsStore()).save_bytes(_key_for(name), blob)


def load_preset(
    name: str,
    store: Optional[SettingsStore] = None,
) -> Optional[dict]:
    """Return a saved preset, or ``None`` if absent / corrupt."""
    try:
        key = _key_for(name)
    except ValueError:
        return None
    blob = (store or SettingsStore()).load_bytes(key)
    if blob is None:
        return None
    try:
        decoded = json.loads(bytes(blob).decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        _logger.warning(
            "preset %r corrupt — decode failed: %s", name, exc
        )
        return None
    if not isinstance(decoded, dict):
        _logger.warning(
            "preset %r has non-dict top-level; ignoring", name
        )
        return None
    return decoded


def delete_preset(
    name: str,
    store: Optional[SettingsStore] = None,
) -> None:
    """Remove a preset. No-op if it doesn't exist."""
    try:
        key = _key_for(name)
    except ValueError:
        return
    (store or SettingsStore()).remove(key)


def list_preset_names(
    store: Optional[SettingsStore] = None,
) -> list[str]:
    """Return all saved preset names, sorted.

    Requires the backing store to expose an ``allKeys`` method — real
    ``QSettings`` does. Fake stores in tests must provide it too.
    Returns an empty list if the store doesn't support enumeration
    (defensive fallback; logs at debug).
    """
    s = store or SettingsStore()
    raw_store = getattr(s, "_store", None)
    all_keys = getattr(raw_store, "allKeys", None)
    if all_keys is None:
        _logger.debug(
            "list_preset_names: store has no allKeys; returning []"
        )
        return []
    try:
        keys = all_keys()
    except Exception as exc:  # noqa: BLE001
        _logger.warning("list_preset_names: allKeys() failed: %s", exc)
        return []
    prefix_len = len(PRESET_NAMESPACE)
    return sorted(
        k[prefix_len:]
        for k in keys
        if isinstance(k, str) and k.startswith(PRESET_NAMESPACE)
    )
