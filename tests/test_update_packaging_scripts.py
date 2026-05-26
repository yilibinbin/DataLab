from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_mac_build_script_has_optional_pkg_packaging() -> None:
    text = (ROOT / "build_mac_data_gui.sh").read_text(encoding="utf-8")
    assert "DATALAB_BUILD_PKG" in text
    assert "pkgbuild" in text
    assert "productbuild" in text
    assert "DataLab-${APP_VERSION}-macOS.pkg" in text
    assert "Developer ID Installer" in text
