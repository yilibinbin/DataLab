"""Auto-installer for Tectonic + helpers around the installer.

The download itself is mocked — these tests run offline. We're pinning:
- The installer creates the right directory tree.
- It writes the binary to the expected location.
- It chmod's the binary executable on POSIX.
- It does NOT re-download when the binary is already present (idempotent).
- It returns a callable ``EngineChoice`` after install.

A separate (network-gated) integration test could fetch the real
binary, but we don't run it on CI by default.
"""

from __future__ import annotations

import io
import os
import stat
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _build_fake_tar_with_tectonic(tmp_path: Path) -> bytes:
    """Synthesize a tar.gz that mirrors Tectonic's release archive."""
    binary_payload = b"#!/bin/sh\necho fake-tectonic\n"
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="tectonic")
        info.size = len(binary_payload)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(binary_payload))
    return buf.getvalue()


def _build_fake_zip_with_tectonic() -> bytes:
    """Synthesize the Windows zip release."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("tectonic.exe", b"MZfake-tectonic-windows\n")
    return buf.getvalue()


def test_ensure_tectonic_installed_downloads_and_extracts(
    tmp_path, monkeypatch
) -> None:
    from shared import latex_engine

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")

    fake_archive = _build_fake_tar_with_tectonic(tmp_path)
    fake_response = MagicMock()
    fake_response.read.return_value = fake_archive
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)

    with patch.object(
        latex_engine, "_open_url", return_value=fake_response
    ) as mock_open:
        choice = latex_engine.ensure_tectonic_installed()

    assert mock_open.called, "must hit the network on first install"
    assert choice is not None
    assert choice.source == "auto-tectonic"
    binary = Path(choice.path)
    assert binary.is_file()
    # POSIX: chmod +x landed
    assert binary.stat().st_mode & stat.S_IXUSR


def test_ensure_tectonic_installed_is_idempotent(tmp_path, monkeypatch) -> None:
    """Second call must return the existing binary without downloading."""
    from shared import latex_engine

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")

    install_dir = tmp_path / ".datalab" / "bin"
    install_dir.mkdir(parents=True)
    fake_binary = install_dir / "tectonic"
    fake_binary.write_bytes(b"#!/bin/sh\nexit 0\n")
    fake_binary.chmod(0o755)

    with patch.object(latex_engine, "_open_url") as mock_open:
        choice = latex_engine.ensure_tectonic_installed()

    assert not mock_open.called, "must NOT download when binary already exists"
    assert choice is not None
    assert choice.source == "auto-tectonic"
    assert Path(choice.path).resolve() == fake_binary.resolve()


def test_ensure_tectonic_installed_windows_zip(tmp_path, monkeypatch) -> None:
    """Windows release ships as a zip; the installer must unpack the
    .exe rather than expecting a tarball."""
    from shared import latex_engine

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("platform.machine", lambda: "AMD64")

    fake_archive = _build_fake_zip_with_tectonic()
    fake_response = MagicMock()
    fake_response.read.return_value = fake_archive
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)

    with patch.object(latex_engine, "_open_url", return_value=fake_response):
        choice = latex_engine.ensure_tectonic_installed()

    assert choice is not None
    binary = Path(choice.path)
    assert binary.is_file()
    assert binary.name == "tectonic.exe"


def test_ensure_tectonic_installed_unsupported_platform_raises(
    tmp_path, monkeypatch
) -> None:
    from shared import latex_engine

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("platform.system", lambda: "Plan9")
    monkeypatch.setattr("platform.machine", lambda: "PowerPC")

    with pytest.raises(latex_engine.UnsupportedPlatformError):
        latex_engine.ensure_tectonic_installed()


# ---------------------------------------------------------------------------
# Tectonic compile-mode wrapper
# ---------------------------------------------------------------------------


def test_tectonic_compile_command_uses_keep_logs_flag(tmp_path) -> None:
    """When the user picks Tectonic the compile command shape is
    different from pdflatex/xelatex (no -interaction flag, etc.). The
    helper that builds the argv list must use Tectonic's flags so the
    GUI's pdf preview round-trip still produces a .pdf next to the .tex.
    """
    from shared.latex_engine import tectonic_compile_argv

    tex_path = tmp_path / "demo.tex"
    tex_path.write_text("\\documentclass{article}\\begin{document}hi\\end{document}")
    argv = tectonic_compile_argv("/usr/local/bin/tectonic", tex_path)

    assert argv[0] == "/usr/local/bin/tectonic"
    # Tectonic v2 syntax: ``tectonic -X compile`` chooses the compile
    # subcommand. ``--keep-logs`` mirrors the GUI's existing log
    # display contract.
    assert "--keep-logs" in argv
    assert str(tex_path) in argv


def test_tectonic_compile_argv_uses_pdf_format(tmp_path) -> None:
    """We always want a PDF out (no DVI / postscript paths)."""
    from shared.latex_engine import tectonic_compile_argv

    tex = tmp_path / "x.tex"
    tex.write_text("")
    argv = tectonic_compile_argv("/bin/tectonic", tex)
    # Either -F pdf or --outfmt pdf is acceptable depending on the
    # Tectonic version; pin that one of them is there.
    flat = " ".join(argv)
    assert "pdf" in flat
