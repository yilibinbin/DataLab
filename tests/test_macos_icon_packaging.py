from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest

from app_desktop import resources
from tools.inspect_macos_bundle_icon import inspect_bundle


ROOT = Path(__file__).resolve().parents[1]


def _write_info_plist(app_path: Path, icon_name: str = "icon") -> None:
    plist_path = app_path / "Contents" / "Info.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(
        plistlib.dumps(
            {
                "CFBundleName": "DataLab",
                "CFBundleIconFile": icon_name,
            }
        )
    )


def _write_bundle_executable(app_path: Path) -> Path:
    executable = app_path / "Contents" / "MacOS" / "DataLab"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_text("#!/bin/sh\n", encoding="utf-8")
    return executable


def test_runtime_icon_policy_keeps_native_icon_for_real_frozen_macos_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_path = tmp_path / "DataLab.app"
    executable = _write_bundle_executable(app_path)
    _write_info_plist(app_path)

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert resources.should_set_runtime_app_icon() is False


def test_runtime_icon_policy_sets_icon_when_frozen_macos_bundle_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _write_bundle_executable(tmp_path / "DataLab.app")

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert resources.should_set_runtime_app_icon() is True


def test_runtime_icon_policy_sets_icon_when_not_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_path = tmp_path / "DataLab.app"
    executable = _write_bundle_executable(app_path)
    _write_info_plist(app_path)

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert resources.should_set_runtime_app_icon() is True


def test_runtime_icon_policy_sets_icon_when_not_macos(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_path = tmp_path / "DataLab.app"
    executable = _write_bundle_executable(app_path)
    _write_info_plist(app_path)

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert resources.should_set_runtime_app_icon() is True


def test_inspect_bundle_accepts_matching_plist_icon_resource(tmp_path: Path) -> None:
    app_path = tmp_path / "DataLab.app"
    _write_info_plist(app_path, icon_name="icon")
    icon_path = app_path / "Contents" / "Resources" / "icon.icns"
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    icon_path.write_bytes(b"icns")

    assert inspect_bundle(app_path) == []


def test_inspect_bundle_reports_missing_icon_resource(tmp_path: Path) -> None:
    app_path = tmp_path / "DataLab.app"
    _write_info_plist(app_path, icon_name="icon")

    assert inspect_bundle(app_path) == ["missing icon resource: Contents/Resources/icon.icns"]


def test_inspect_bundle_reports_missing_icon_metadata(tmp_path: Path) -> None:
    app_path = tmp_path / "DataLab.app"
    plist_path = app_path / "Contents" / "Info.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(plistlib.dumps({"CFBundleName": "DataLab"}))

    assert inspect_bundle(app_path) == ["missing CFBundleIconFile in Contents/Info.plist"]


def test_inspect_bundle_reports_non_dict_plist_root(tmp_path: Path) -> None:
    app_path = tmp_path / "DataLab.app"
    plist_path = app_path / "Contents" / "Info.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_bytes(plistlib.dumps(["CFBundleIconFile", "icon"]))

    assert inspect_bundle(app_path) == ["Info.plist root is not a dictionary"]


def test_build_script_sets_icon_file_from_actual_basename() -> None:
    text = (ROOT / "build_mac_data_gui.sh").read_text()

    assert "MAC_ICON_PLIST_NAME=" in text
    assert "CFBundleIconFile" in text
    assert 'MAC_ICON_PLIST_NAME="$(basename "$MAC_ICON" .icns)"' in text
    assert "CFBundleIconFile $MAC_ICON_PLIST_NAME" in text
