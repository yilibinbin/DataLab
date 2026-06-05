"""Pin the TinyTeX install script's existence + key contracts.

The actual download is too heavy for unit tests (the TinyTeX archive
is ~200 MB), so this test only checks the script's structural
invariants:

- ``tools/install_tinytex.sh`` is present and executable.
- It writes its output to ``<repo>/resources/tinytex/`` (which is
  exactly where ``shared.latex_engine.discover_bundled_engine`` looks).
- The mac build script accepts a ``DATALAB_BUNDLE_TINYTEX=1`` env var
  that triggers the install script before PyInstaller runs.
- The Windows build script has the equivalent flag (``-BundleTinyTeX``).

If you're touching the install script, do bump the version pin —
TinyTeX's bootstrap URL is the contract that's most likely to drift.
"""

from __future__ import annotations

import stat
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_install_tinytex_script_exists() -> None:
    path = REPO_ROOT / "tools" / "install_tinytex.sh"
    assert path.is_file(), f"missing installer: {path}"


def test_install_tinytex_script_is_executable() -> None:
    path = REPO_ROOT / "tools" / "install_tinytex.sh"
    mode = path.stat().st_mode
    assert mode & stat.S_IXUSR, f"{path} must be chmod +x"


def test_install_tinytex_targets_resources_tinytex() -> None:
    """The runtime discovery layer (``shared.latex_engine``) looks
    under ``resources/tinytex/bin/<arch>``. The install script must
    write there or the bundled-engine path is silently broken."""
    text = _read("tools/install_tinytex.sh")
    assert "resources/tinytex" in text


def test_mac_build_flag_documented() -> None:
    text = _read("build_mac_data_gui.sh")
    assert "DATALAB_BUNDLE_TINYTEX" in text, (
        "build_mac_data_gui.sh must accept DATALAB_BUNDLE_TINYTEX env "
        "var to opt into bundling TinyTeX"
    )


def test_windows_build_flag_documented() -> None:
    text = _read("build_windows_data_gui.ps1")
    assert "BundleTinyTeX" in text, (
        "build_windows_data_gui.ps1 must support a -BundleTinyTeX "
        "switch parameter for parity with mac"
    )


def test_resources_dir_added_to_pyinstaller_when_tinytex_bundled() -> None:
    """The tinytex tree must be added via --add-data so PyInstaller
    actually copies it into the frozen .app's resources/ tree."""
    text = _read("build_mac_data_gui.sh")
    assert "resources/tinytex" in text
    # The flag needs to appear inside the if-bundling-enabled block.
    # Spot-check that --add-data and resources/tinytex are both
    # present in the same script.
    assert "--add-data" in text
