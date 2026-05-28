from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_icon_policy_checks_real_app_bundle_path() -> None:
    text = (ROOT / "app_desktop" / "resources.py").read_text()

    assert "def _is_running_inside_macos_app_bundle" in text
    assert "def should_set_runtime_app_icon" in text
    assert "Contents" in text
    assert "MacOS" in text
    assert ".app" in text


def test_build_script_sets_icon_file_from_actual_basename() -> None:
    text = (ROOT / "build_mac_data_gui.sh").read_text()

    assert "CFBundleIconFile" in text
    assert 'basename "$MAC_ICON" .icns' in text
    assert "app_icon" not in text or 'basename "$MAC_ICON" .icns' in text


def test_bundle_icon_inspector_exists() -> None:
    text = (ROOT / "tools" / "inspect_macos_bundle_icon.py").read_text()

    assert "CFBundleIconFile" in text
    assert "Contents/Resources" in text
