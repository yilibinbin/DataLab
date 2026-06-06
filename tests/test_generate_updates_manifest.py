from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

TEST_SIGNING_KEY_ID = "test-key"
TEST_PRIVATE_KEY_B64 = "arq5WLNRcnCZW5b+LGSYraZ0boKTF5oCDOo8Wn6jwf4="
TEST_PUBLIC_KEY_B64 = "CSrQ+417vi16q+8rxYk7X6x58RDmkQH0WVq168r2ArU="


def test_generate_updates_manifest_writes_size_and_sha(tmp_path: Path) -> None:
    from tools.generate_updates_manifest import generate_manifest
    from shared.update_signing import verify_manifest_signature

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
        signing_private_key_b64=TEST_PRIVATE_KEY_B64,
        signing_key_id=TEST_SIGNING_KEY_ID,
    )

    assert manifest["schema_version"] == 1
    assert manifest["version"] == "2.3.0"
    assert manifest["release_url"] == "https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0"
    assert manifest["assets"]["macos"]["sha256"] == hashlib.sha256(b"mac").hexdigest()
    assert manifest["assets"]["macos"]["size_bytes"] == 3
    assert manifest["assets"]["windows-x64"]["sha256"] == hashlib.sha256(b"win").hexdigest()
    assert manifest["assets"]["windows-x64"]["size_bytes"] == 3
    assert manifest["signature"]["algorithm"] == "ed25519"
    verify_manifest_signature(
        manifest,
        public_keys={TEST_SIGNING_KEY_ID: TEST_PUBLIC_KEY_B64},
    )
    assert "install_args" not in manifest["assets"]["windows-x64"]


def test_generate_updates_manifest_requires_signature_for_assets(tmp_path: Path) -> None:
    from tools.generate_updates_manifest import generate_manifest

    mac = tmp_path / "DataLab-2.3.0-macOS.pkg"
    mac.write_bytes(b"mac")

    with pytest.raises(ValueError, match="must be signed"):
        generate_manifest(
            version="2.3.0",
            release_url="https://github.com/yilibinbin/DataLab/releases/tag/v2.3.0",
            notes="Release notes",
            macos_pkg=mac,
            windows_exe=None,
            published_at="2026-05-26T00:00:00Z",
            min_client_version="2.2.0",
        )


def test_generate_updates_manifest_cli_writes_json_without_install_args(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.generate_updates_manifest import main
    from shared.update_signing import verify_manifest_signature

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
            "--signing-private-key-b64",
            TEST_PRIVATE_KEY_B64,
            "--signing-key-id",
            TEST_SIGNING_KEY_ID,
            "--output",
            str(output),
        ],
    )

    assert main() == 0

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert output.read_text(encoding="utf-8").endswith("\n")
    assert manifest["assets"]["macos"]["name"] == mac.name
    verify_manifest_signature(
        manifest,
        public_keys={TEST_SIGNING_KEY_ID: TEST_PUBLIC_KEY_B64},
    )
    assert "windows-x64" not in manifest["assets"]
    assert "install_args" not in json.dumps(manifest)


def test_generate_updates_manifest_cli_reads_signing_key_id_from_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.generate_updates_manifest import main
    from shared.update_signing import verify_manifest_signature

    mac = tmp_path / "DataLab-2.8.0-macOS.pkg"
    notes = tmp_path / "notes.md"
    output = tmp_path / "updates.json"
    mac.write_bytes(b"mac")
    notes.write_text("Release notes\n", encoding="utf-8")

    monkeypatch.setenv("DATALAB_UPDATE_SIGNING_PRIVATE_KEY_B64", TEST_PRIVATE_KEY_B64)
    monkeypatch.setenv("DATALAB_UPDATE_SIGNING_KEY_ID", TEST_SIGNING_KEY_ID)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_updates_manifest.py",
            "--version",
            "2.8.0",
            "--release-url",
            "https://github.com/yilibinbin/DataLab/releases/tag/v2.8.0",
            "--notes-file",
            str(notes),
            "--published-at",
            "2026-06-06T00:00:00Z",
            "--min-client-version",
            "2.7.6",
            "--macos-pkg",
            str(mac),
            "--output",
            str(output),
        ],
    )

    assert main() == 0

    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["signature"]["key_id"] == TEST_SIGNING_KEY_ID
    verify_manifest_signature(
        manifest,
        public_keys={TEST_SIGNING_KEY_ID: TEST_PUBLIC_KEY_B64},
    )
