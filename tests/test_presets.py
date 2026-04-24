"""Preset library (Phase 3 #15) — regression tests.

Users save named presets (fit model + parameter defaults + display
preferences) and load them later. Presets are persisted via the
existing ``shared.settings_store``, so the persistence layer is
already tested — this module pins the higher-level preset
dictionary / JSON schema.

Contract:
- ``save_preset(name, preset)`` and ``load_preset(name)`` round-trip
  via the SettingsStore injected as a test double.
- Preset names are sanitised: whitespace collapsed, leading/trailing
  punctuation stripped. Empty / control-only names rejected.
- Values must be JSON-serialisable (dicts/lists/strings/numbers).
- Oversized presets (exceeding MAX_PRESET_BYTES) are rejected at save
  time to protect the SettingsStore's MAX_BLOB_BYTES cap.
- ``list_preset_names()`` returns all saved presets, sorted.
- ``delete_preset(name)`` removes it; a later load returns None.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from typing import Any, Dict  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtCore import QByteArray  # noqa: E402

from shared.presets import (  # noqa: E402
    MAX_PRESET_BYTES,
    PRESET_NAMESPACE,
    delete_preset,
    list_preset_names,
    load_preset,
    save_preset,
    sanitize_preset_name,
)
from shared.settings_store import SettingsStore  # noqa: E402


class _FakeQSettings:
    def __init__(self, *_args: Any, **_kwargs: Any) -> None:
        self._data: Dict[str, Any] = {}

    def value(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def setValue(self, key: str, value: Any) -> None:  # noqa: N802
        self._data[key] = value

    def remove(self, key: str) -> None:
        self._data.pop(key, None)

    def sync(self) -> None:
        pass

    def clear(self) -> None:
        self._data.clear()

    def status(self):
        from PySide6.QtCore import QSettings

        return QSettings.Status.NoError

    def allKeys(self):  # noqa: N802
        return list(self._data.keys())


@pytest.fixture
def _store():
    return SettingsStore(store=_FakeQSettings())


def test_save_and_load_preset_roundtrip(_store):
    preset = {
        "model": "linear",
        "precision": 50,
        "log_scale": "x",
        "dpi": 300,
    }
    save_preset("my-lab", preset, store=_store)
    loaded = load_preset("my-lab", store=_store)
    assert loaded == preset


def test_load_nonexistent_preset_returns_none(_store):
    assert load_preset("no-such-preset", store=_store) is None


def test_save_preset_rejects_empty_name(_store):
    with pytest.raises(ValueError, match="name"):
        save_preset("", {"a": 1}, store=_store)
    with pytest.raises(ValueError, match="name"):
        save_preset("   ", {"a": 1}, store=_store)


def test_save_preset_rejects_non_dict_body(_store):
    with pytest.raises(ValueError, match="dict|mapping"):
        save_preset("x", "not-a-dict", store=_store)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="dict|mapping"):
        save_preset("x", [1, 2, 3], store=_store)  # type: ignore[arg-type]


def test_save_preset_rejects_non_json_serializable(_store):
    class _NotJsonable:
        pass

    with pytest.raises(ValueError, match="serial"):
        save_preset("x", {"foo": _NotJsonable()}, store=_store)


def test_save_preset_rejects_oversized_body(_store):
    giant = {"blob": "x" * (MAX_PRESET_BYTES + 1)}
    with pytest.raises(ValueError, match="size|large"):
        save_preset("x", giant, store=_store)


def test_list_preset_names_returns_sorted(_store):
    save_preset("zeta", {"a": 1}, store=_store)
    save_preset("alpha", {"a": 1}, store=_store)
    save_preset("beta", {"a": 1}, store=_store)
    assert list_preset_names(store=_store) == ["alpha", "beta", "zeta"]


def test_delete_preset_removes_it(_store):
    save_preset("temp", {"a": 1}, store=_store)
    assert load_preset("temp", store=_store) == {"a": 1}
    delete_preset("temp", store=_store)
    assert load_preset("temp", store=_store) is None


def test_delete_nonexistent_preset_is_noop(_store):
    # Must not raise
    delete_preset("nothing-here", store=_store)


def test_sanitize_preset_name_strips_whitespace():
    assert sanitize_preset_name("  hello  ") == "hello"
    assert sanitize_preset_name("foo\tbar") == "foo bar"


def test_sanitize_preset_name_collapses_inner_whitespace():
    assert sanitize_preset_name("a   b") == "a b"


def test_sanitize_preset_name_rejects_empty():
    with pytest.raises(ValueError):
        sanitize_preset_name("")
    with pytest.raises(ValueError):
        sanitize_preset_name("\t\n  ")


def test_sanitize_preset_name_rejects_path_traversal():
    """A preset name must not contain path separators — otherwise a
    hand-crafted name could end up writing to a neighbour's
    namespace via the SettingsStore's key composition."""
    with pytest.raises(ValueError):
        sanitize_preset_name("a/b")
    with pytest.raises(ValueError):
        sanitize_preset_name("c\\d")
    with pytest.raises(ValueError):
        sanitize_preset_name("..")


def test_sanitize_preset_name_rejects_control_chars():
    with pytest.raises(ValueError):
        sanitize_preset_name("hello\x00world")
    with pytest.raises(ValueError):
        sanitize_preset_name("a\x1fb")


def test_preset_namespace_constant_is_allowlisted():
    """Sanity: PRESET_NAMESPACE must be allowlisted in SettingsStore's
    _ALLOWED_KEY_PREFIXES so save_bytes doesn't reject preset writes."""
    from shared.settings_store import _ALLOWED_KEY_PREFIXES

    assert any(
        PRESET_NAMESPACE.startswith(prefix.rstrip("/"))
        for prefix in _ALLOWED_KEY_PREFIXES
    )


def test_save_and_load_unicode_preset_name(_store):
    """Unicode names (Chinese, Japanese, Cyrillic) must round-trip."""
    save_preset("我的预设", {"value": 1}, store=_store)
    assert load_preset("我的预设", store=_store) == {"value": 1}


def test_preset_values_preserve_numeric_precision(_store):
    """A preset with high-precision floats must round-trip without
    silent precision loss."""
    preset = {"coef": 1.23456789012345, "scale": 1e-8}
    save_preset("precision", preset, store=_store)
    loaded = load_preset("precision", store=_store)
    assert loaded["coef"] == 1.23456789012345
    assert loaded["scale"] == 1e-8


def test_preset_nested_dicts_and_lists(_store):
    preset = {
        "model": "linear",
        "bounds": {"low": 0.0, "high": 10.0},
        "tags": ["lab", "published"],
    }
    save_preset("nested", preset, store=_store)
    loaded = load_preset("nested", store=_store)
    assert loaded == preset
