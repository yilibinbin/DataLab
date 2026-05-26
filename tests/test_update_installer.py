from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import pytest


def _write_installer(path: Path, data: bytes = b"DataLab installer") -> tuple[str, int]:
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest(), len(data)


def test_windows_installer_command_is_constructed_in_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_desktop import update_installer

    path = tmp_path / "DataLab.exe"
    sha256, size = _write_installer(path)
    captured: list[list[str]] = []
    module = cast(Any, update_installer)

    def fake_popen(argv: list[str]) -> object:
        captured.append(argv)
        return object()

    monkeypatch.setattr(module.platform, "system", lambda: "Windows")
    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)

    result = update_installer.launch_installer(
        path,
        platform_key="windows-x64",
        expected_sha256=sha256,
        expected_size=size,
    )

    assert result.launched is True
    assert result.argv == (str(path), "/VERYSILENT", "/NORESTART")
    assert captured == [[str(path), "/VERYSILENT", "/NORESTART"]]


def test_macos_installer_command_is_constructed_in_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_desktop import update_installer

    path = tmp_path / "DataLab.pkg"
    sha256, size = _write_installer(path)
    captured: list[list[str]] = []
    module = cast(Any, update_installer)

    def fake_popen(argv: list[str]) -> object:
        captured.append(argv)
        return object()

    monkeypatch.setattr(module.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)

    result = update_installer.launch_installer(
        path,
        platform_key="macos",
        expected_sha256=sha256,
        expected_size=size,
    )

    assert result.launched is True
    assert result.argv == ("/usr/sbin/installer", "-pkg", str(path), "-target", "/")
    assert captured == [["/usr/sbin/installer", "-pkg", str(path), "-target", "/"]]


def test_windows_launcher_rejects_wrong_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_desktop import update_installer

    path = tmp_path / "DataLab.txt"
    sha256, size = _write_installer(path)
    module = cast(Any, update_installer)
    monkeypatch.setattr(module.platform, "system", lambda: "Windows")

    with pytest.raises(update_installer.InstallerLaunchError, match="extension"):
        update_installer.launch_installer(
            path,
            platform_key="windows-x64",
            expected_sha256=sha256,
            expected_size=size,
        )


def test_launcher_rejects_bad_sha256(tmp_path: Path) -> None:
    from app_desktop import update_installer

    path = tmp_path / "DataLab.exe"
    _, size = _write_installer(path)

    with pytest.raises(update_installer.InstallerLaunchError, match="sha256"):
        update_installer.launch_installer(
            path,
            platform_key="windows-x64",
            expected_sha256="0" * 64,
            expected_size=size,
        )


def test_launch_installer_does_not_accept_caller_provided_argv(tmp_path: Path) -> None:
    from app_desktop import update_installer

    path = tmp_path / "DataLab.exe"
    sha256, size = _write_installer(path)

    with pytest.raises(TypeError):
        cast(Any, update_installer.launch_installer)(
            path,
            platform_key="windows-x64",
            expected_sha256=sha256,
            expected_size=size,
            argv=("malicious",),
        )
