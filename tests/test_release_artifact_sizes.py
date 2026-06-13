from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.record_release_artifact_sizes import build_manifest, discover_artifacts, main
from tools.record_release_artifact_sizes import validate_artifact_size_manifest


def test_discover_artifacts_finds_supported_release_outputs(tmp_path: Path) -> None:
    app_file = tmp_path / "dist" / "DataLab.app" / "Contents" / "MacOS" / "DataLab"
    pkg_file = tmp_path / "dist" / "DataLab.pkg"
    ignored_file = tmp_path / "dist" / "notes.txt"
    app_file.parent.mkdir(parents=True)
    app_file.write_bytes(b"app")
    pkg_file.write_bytes(b"pkg")
    ignored_file.write_text("not an artifact", encoding="utf-8")

    artifacts = {path.relative_to(tmp_path).as_posix() for path in discover_artifacts(tmp_path)}

    assert artifacts == {"dist/DataLab.app", "dist/DataLab.pkg"}


def test_discover_artifacts_ignores_build_intermediates_and_nested_dist_files(tmp_path: Path) -> None:
    python_exe = tmp_path / "build" / "windows_gui_build" / "venv" / "Scripts" / "python.exe"
    component_pkg = tmp_path / "build" / "macos_gui_build" / "DataLab-component.pkg"
    nested_pkg = tmp_path / "dist" / "staging" / "DataLab-component.pkg"
    release_pkg = tmp_path / "dist" / "DataLab.pkg"
    for path in (python_exe, component_pkg, nested_pkg, release_pkg):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

    artifacts = {path.relative_to(tmp_path).as_posix() for path in discover_artifacts(tmp_path)}

    assert artifacts == {"dist/DataLab.pkg"}


def test_build_manifest_records_file_and_directory_sizes(tmp_path: Path) -> None:
    app_file = tmp_path / "dist" / "DataLab.app" / "Contents" / "MacOS" / "DataLab"
    zip_file = tmp_path / "build" / "DataLab.zip"
    app_file.parent.mkdir(parents=True)
    zip_file.parent.mkdir(parents=True)
    app_file.write_bytes(b"abcd")
    zip_file.write_bytes(b"xy")

    manifest = build_manifest(tmp_path, [tmp_path / "dist" / "DataLab.app", zip_file])

    assert manifest["artifact_count"] == 2
    rows = {row["path"]: row for row in manifest["artifacts"]}  # type: ignore[index]
    assert rows["dist/DataLab.app"]["bytes"] == 4
    assert rows["build/DataLab.zip"]["bytes"] == 2


def test_build_manifest_rejects_artifacts_outside_repo_root(tmp_path: Path) -> None:
    artifact = tmp_path.parent / "outside-DataLab.pkg"
    artifact.write_bytes(b"pkg")
    try:
        with pytest.raises(ValueError, match="outside the repository root"):
            build_manifest(tmp_path, [artifact])
    finally:
        artifact.unlink(missing_ok=True)


def test_app_directory_size_counts_symlink_entry_not_external_target(tmp_path: Path) -> None:
    app_root = tmp_path / "dist" / "DataLab.app"
    binary = app_root / "Contents" / "MacOS" / "DataLab"
    external = tmp_path / "outside.bin"
    link = app_root / "Contents" / "Resources" / "outside-link"
    binary.parent.mkdir(parents=True)
    link.parent.mkdir(parents=True)
    binary.write_bytes(b"abcd")
    external.write_bytes(b"x" * 1024)
    link.symlink_to(external)

    manifest = build_manifest(tmp_path, [app_root])
    size = manifest["artifacts"][0]["bytes"]  # type: ignore[index]

    assert size == binary.lstat().st_size + link.lstat().st_size
    assert size < external.stat().st_size


def test_main_writes_json_manifest(tmp_path: Path) -> None:
    artifact = tmp_path / "dist" / "DataLab.pkg"
    artifact.parent.mkdir()
    artifact.write_bytes(b"12345")
    out = tmp_path / "build" / "artifact-sizes.json"

    assert main(["--repo-root", str(tmp_path), "--out", str(out), str(artifact)]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["artifact_count"] == 1
    assert payload["artifacts"][0]["path"] == "dist/DataLab.pkg"
    assert payload["artifacts"][0]["bytes"] == 5


def test_main_rejects_missing_release_artifacts_by_default(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "build" / "artifact-sizes.json"

    assert main(["--repo-root", str(tmp_path), "--out", str(out)]) == 2

    assert not out.exists()
    assert "No release artifacts found" in capsys.readouterr().err


def test_main_allows_empty_manifest_only_for_diagnostics(tmp_path: Path) -> None:
    out = tmp_path / "build" / "artifact-sizes.json"

    assert main(["--repo-root", str(tmp_path), "--out", str(out), "--allow-empty"]) == 0

    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["artifact_count"] == 0
    assert payload["artifacts"] == []


def test_validate_artifact_size_manifest_rejects_private_or_malformed_rows() -> None:
    invalid_payloads = [
        [],
        {"artifact_count": 0, "artifacts": {}},
        {"artifact_count": 0, "artifacts": []},
        {"artifact_count": 2, "artifacts": []},
        {"artifact_count": 1, "artifacts": [{"path": "/Users/fanghao/dist/DataLab.pkg", "bytes": 1, "human_size": "1 B"}]},
        {"artifact_count": 1, "artifacts": [{"path": "file:///tmp/DataLab.pkg", "bytes": 1, "human_size": "1 B"}]},
        {"artifact_count": 1, "artifacts": [{"path": "../DataLab.pkg", "bytes": 1, "human_size": "1 B"}]},
        {"artifact_count": 1, "artifacts": [{"path": "dist\\DataLab.pkg", "bytes": 1, "human_size": "1 B"}]},
        {"artifact_count": 1, "artifacts": [{"path": "dist/DataLab.pkg", "bytes": -1, "human_size": "1 B"}]},
        {"artifact_count": 1, "artifacts": [{"path": "dist/DataLab.pkg", "bytes": 1, "human_size": ""}]},
    ]

    for payload in invalid_payloads:
        with pytest.raises(ValueError):
            validate_artifact_size_manifest(payload)


def test_validate_artifact_size_manifest_accepts_portable_rows() -> None:
    payload = {
        "artifact_count": 2,
        "artifacts": [
            {"path": "dist/DataLab.pkg", "bytes": 123, "human_size": "123 B"},
            {"path": "dist/DataLab-Windows.exe", "bytes": 456, "human_size": "456 B"},
        ],
    }

    rows = validate_artifact_size_manifest(payload)

    assert [row["path"] for row in rows] == ["dist/DataLab.pkg", "dist/DataLab-Windows.exe"]
