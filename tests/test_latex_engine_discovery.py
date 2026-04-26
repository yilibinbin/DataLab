"""Engine discovery + auto-install for ``shared.latex_engine``.

The desktop GUI needs LaTeX compilation to "just work" out of the box,
but a TeX Live install is multiple gigabytes and not something we can
realistically embed in every PyInstaller bundle. Three tiers cover the
real-world install matrix:

1. **System** — ``pdflatex`` / ``xelatex`` / ``lualatex`` / ``tectonic``
   on PATH. Fastest, no extra disk.
2. **Bundled TinyTeX** — shipped with the .app under
   ``<datalab>/resources/tinytex/``. Populated by the build script
   (opt-in, ~200 MB). Zero network at runtime.
3. **Auto-Tectonic** — ~30 MB single-binary runtime download to
   ``~/.datalab/bin/tectonic`` on first use. Tectonic fetches the
   actual LaTeX packages over the net per-document and caches them in
   ``~/.cache/Tectonic`` (or the OS equivalent).

These tests exercise the pure-Python discovery + path-resolution layer.
The actual download step is mocked so they don't hit the network.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# discover_system_engine — PATH lookup


def test_discover_returns_path_for_existing_engine(tmp_path) -> None:
    from shared.latex_engine import discover_system_engine

    fake_bin = tmp_path / "pdflatex"
    fake_bin.write_text("#!/bin/sh\nexit 0\n")
    fake_bin.chmod(0o755)

    with patch.dict(os.environ, {"PATH": str(tmp_path)}, clear=False):
        path = discover_system_engine("pdflatex")

    assert path is not None
    assert Path(path).resolve() == fake_bin.resolve()


def test_discover_returns_none_when_engine_missing() -> None:
    from shared.latex_engine import discover_system_engine

    # Restrict PATH to a directory guaranteed not to contain it.
    with patch.dict(os.environ, {"PATH": "/nonexistent/datalab/test"}, clear=True):
        path = discover_system_engine("pdflatex-does-not-exist-anywhere")

    assert path is None


# ---------------------------------------------------------------------------
# discover_bundled_engine — embedded TinyTeX in resources/


def test_discover_bundled_engine_finds_tinytex(tmp_path) -> None:
    """``discover_bundled_engine(root, 'pdflatex')`` returns the absolute
    path to the bundled binary when it exists under
    ``<root>/resources/tinytex/bin/<arch>/<engine>``."""
    from shared.latex_engine import discover_bundled_engine

    bin_dir = tmp_path / "resources" / "tinytex" / "bin" / "any-arch"
    bin_dir.mkdir(parents=True)
    fake_engine = bin_dir / "pdflatex"
    fake_engine.write_text("#!/bin/sh\n")
    fake_engine.chmod(0o755)

    found = discover_bundled_engine(tmp_path, "pdflatex")
    assert found is not None
    assert Path(found).resolve() == fake_engine.resolve()


def test_discover_bundled_engine_missing_returns_none(tmp_path) -> None:
    from shared.latex_engine import discover_bundled_engine

    # No resources/tinytex tree at all
    found = discover_bundled_engine(tmp_path, "pdflatex")
    assert found is None


# ---------------------------------------------------------------------------
# tectonic_install_dir / cache layout


def test_tectonic_install_dir_under_user_home(tmp_path, monkeypatch) -> None:
    """The auto-Tectonic binary lives under ``~/.datalab/bin/tectonic``.
    Use a sentinel home so the test doesn't pollute the real one."""
    from shared.latex_engine import tectonic_install_dir

    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Windows
    target = tectonic_install_dir()

    assert target.parts[-2:] == (".datalab", "bin")
    assert target.is_absolute()


def test_tectonic_executable_path_appends_exe_on_windows(monkeypatch) -> None:
    from shared.latex_engine import tectonic_executable_name

    # Pin platform.system to "Windows" — the impl must add ``.exe``.
    monkeypatch.setattr("platform.system", lambda: "Windows")
    assert tectonic_executable_name() == "tectonic.exe"

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    assert tectonic_executable_name() == "tectonic"

    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert tectonic_executable_name() == "tectonic"


# ---------------------------------------------------------------------------
# resolve_engine — the real entry point that all three tiers fall through


def test_resolve_engine_prefers_system_over_bundled(tmp_path, monkeypatch) -> None:
    """If both system and bundled installations exist, system wins
    (faster startup, more likely to be a complete TeX Live)."""
    from shared.latex_engine import resolve_engine

    # System engine on a synthetic PATH
    sys_dir = tmp_path / "sys_path"
    sys_dir.mkdir()
    sys_engine = sys_dir / "pdflatex"
    sys_engine.write_text("#!/bin/sh\n")
    sys_engine.chmod(0o755)

    # Bundled engine under a fake bundle root
    bundle_root = tmp_path / "bundle"
    bin_dir = bundle_root / "resources" / "tinytex" / "bin" / "x"
    bin_dir.mkdir(parents=True)
    bun_engine = bin_dir / "pdflatex"
    bun_engine.write_text("#!/bin/sh\n")
    bun_engine.chmod(0o755)

    monkeypatch.setenv("PATH", str(sys_dir))
    chosen = resolve_engine("pdflatex", bundle_root=bundle_root)
    assert Path(chosen.path).resolve() == sys_engine.resolve()
    assert chosen.source == "system"


def test_resolve_engine_falls_back_to_bundled(tmp_path, monkeypatch) -> None:
    from shared.latex_engine import resolve_engine

    bundle_root = tmp_path / "bundle"
    bin_dir = bundle_root / "resources" / "tinytex" / "bin" / "x"
    bin_dir.mkdir(parents=True)
    bun_engine = bin_dir / "pdflatex"
    bun_engine.write_text("#!/bin/sh\n")
    bun_engine.chmod(0o755)

    monkeypatch.setenv("PATH", "/nonexistent/datalab/test/path")
    chosen = resolve_engine("pdflatex", bundle_root=bundle_root)

    assert chosen is not None
    assert Path(chosen.path).resolve() == bun_engine.resolve()
    assert chosen.source == "bundled"


def test_resolve_engine_returns_none_for_unfindable(monkeypatch, tmp_path) -> None:
    from shared.latex_engine import resolve_engine

    monkeypatch.setenv("PATH", "/nonexistent/datalab/test/path")
    # bundle_root has no resources/tinytex
    chosen = resolve_engine(
        "pdflatex-does-not-exist-anywhere", bundle_root=tmp_path
    )
    assert chosen is None


# ---------------------------------------------------------------------------
# Tectonic-specific URL resolution


def test_tectonic_download_url_for_macos_arm64(monkeypatch) -> None:
    from shared.latex_engine import tectonic_download_url

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("platform.machine", lambda: "arm64")
    url = tectonic_download_url()
    assert url.startswith("https://github.com/tectonic-typesetting/tectonic/releases")
    assert "aarch64-apple-darwin" in url


def test_tectonic_download_url_for_windows_x64(monkeypatch) -> None:
    from shared.latex_engine import tectonic_download_url

    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("platform.machine", lambda: "AMD64")
    url = tectonic_download_url()
    assert "x86_64-pc-windows-msvc" in url
    # Windows release ships as a .zip (not a .tar.gz like the unix
    # builds). The extractor branches on ``url.endswith(".zip")``,
    # so this is a hard contract — not "either zip OR has 'windows'
    # in the URL", which the v1 of this assertion was (a tautology
    # because the Windows triple ``x86_64-pc-windows-msvc`` already
    # contains the substring "windows").
    assert url.endswith(".zip"), f"Windows asset must be a zip; got {url}"


def test_tectonic_download_url_for_linux_x64(monkeypatch) -> None:
    from shared.latex_engine import tectonic_download_url

    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    url = tectonic_download_url()
    assert "x86_64-unknown-linux" in url


def test_tectonic_download_url_unsupported_platform_raises(monkeypatch) -> None:
    from shared.latex_engine import (
        UnsupportedPlatformError,
        tectonic_download_url,
    )

    monkeypatch.setattr("platform.system", lambda: "Plan9")
    monkeypatch.setattr("platform.machine", lambda: "PowerPC")
    with pytest.raises(UnsupportedPlatformError):
        tectonic_download_url()
