"""Platform installer launcher for DataLab desktop updates."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path

from shared.update_payload import sha256_file


class InstallerLaunchError(RuntimeError):
    """Raised when an installer cannot be verified or launched."""


@dataclass(frozen=True)
class InstallerLaunchResult:
    launched: bool
    argv: tuple[str, ...]


def _verify(path: Path, expected_sha256: str, expected_size: int) -> None:
    if not path.is_file():
        raise InstallerLaunchError(f"installer not found: {path}")

    actual_size = path.stat().st_size
    if actual_size != expected_size:
        raise InstallerLaunchError(f"size mismatch: expected {expected_size}, got {actual_size}")

    actual_sha256 = sha256_file(path).lower()
    if actual_sha256 != expected_sha256.lower():
        raise InstallerLaunchError("sha256 mismatch")


def _argv(path: Path, platform_key: str) -> list[str]:
    system = platform.system()
    suffix = path.suffix.lower()

    if platform_key == "windows-x64":
        if suffix != ".exe":
            raise InstallerLaunchError("installer extension must be .exe for windows-x64")
        if system != "Windows":
            raise InstallerLaunchError("platform mismatch: windows-x64 requires Windows")
        return [str(path), "/VERYSILENT", "/NORESTART"]

    if platform_key == "macos":
        if suffix != ".pkg":
            raise InstallerLaunchError("installer extension must be .pkg for macos")
        if system != "Darwin":
            raise InstallerLaunchError("platform mismatch: macos requires Darwin")
        return ["/usr/sbin/installer", "-pkg", str(path), "-target", "/"]

    raise InstallerLaunchError(f"unsupported platform: {platform_key}")


def launch_installer(
    path: Path,
    *,
    platform_key: str,
    expected_sha256: str,
    expected_size: int,
) -> InstallerLaunchResult:
    _verify(path, expected_sha256, expected_size)
    argv = _argv(path, platform_key)
    try:
        subprocess.Popen(argv)  # noqa: S603
    except OSError as exc:
        raise InstallerLaunchError(f"failed to launch installer: {exc}") from exc
    return InstallerLaunchResult(launched=True, argv=tuple(argv))
