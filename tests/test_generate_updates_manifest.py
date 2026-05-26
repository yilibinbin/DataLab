from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest


def test_generate_updates_manifest_writes_size_and_sha(tmp_path: Path) -> None:
    from tools.generate_updates_manifest import generate_manifest

    mac = tmp_path / "DataLab-2.3.0-macOS.pkg"
    win = tmp_path / "DataLab-2.3.0-Windows-x64.exe"
    mac.write_bytes(b"mac")
    win.write_bytes(b"win")

    manifest = generate_manifest(
        version="2.3.0",
        release_url="https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
        notes="Release notes",
        macos_pkg=mac,
        windows_exe=win,
        published_at="2026-05-26T00:00:00Z",
        min_client_version="2.2.0",
    )

    assert manifest["schema_version"] == 1
    assert manifest["version"] == "2.3.0"
    assert manifest["release_url"] == "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0"
    assert manifest["assets"]["macos"]["sha256"] == hashlib.sha256(b"mac").hexdigest()
    assert manifest["assets"]["macos"]["size_bytes"] == 3
    assert manifest["assets"]["windows-x64"]["sha256"] == hashlib.sha256(b"win").hexdigest()
    assert manifest["assets"]["windows-x64"]["size_bytes"] == 3
    assert "install_args" not in manifest["assets"]["windows-x64"]


def test_generate_updates_manifest_cli_writes_json_without_install_args(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.generate_updates_manifest import main

    mac = tmp_path / "DataLab-2.3.0-macOS.pkg"
    notes = tmp_path / "notes.md"
    output = tmp_path / "updates.json"
    mac.write_bytes(b"mac")
    notes.write_text("Release notes\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_updates_manifest.py",
            "--version",
            "2.3.0",
            "--release-url",
            "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
            "--notes-file",
            str(notes),
            "--published-at",
            "2026-05-26T00:00:00Z",
            "--min-client-version",
            "2.2.0",
            "--macos-pkg",
            str(mac),
            "--output",
            str(output),
        ],
    )

    assert main() == 0

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert output.read_text(encoding="utf-8").endswith("\n")
    assert manifest["assets"]["macos"]["name"] == mac.name
    assert "windows-x64" not in manifest["assets"]
    assert "install_args" not in json.dumps(manifest)
