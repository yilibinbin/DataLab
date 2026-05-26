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
    assert "PRODUCTBUILD_ARGS=(" in text
    assert 'PRODUCTBUILD_ARGS+=(--sign "$DATALAB_MAC_INSTALLER_IDENTITY")' in text
    assert 'productbuild "${PRODUCTBUILD_ARGS[@]}"' in text

    pkgbuild_section = text[
        text.index("PKGBUILD_ARGS=(") : text.index('pkgbuild "${PKGBUILD_ARGS[@]}"')
    ]
    assert "--sign" not in pkgbuild_section


def test_windows_build_script_has_inno_packaging_hook() -> None:
    text = (ROOT / "build_windows_data_gui.ps1").read_text(encoding="utf-8-sig")
    inno_text = (ROOT / "packaging" / "windows" / "DataLab.iss").read_text(
        encoding="utf-8"
    )

    assert "BuildInnoInstaller" in text
    assert "ISCC.exe" in text
    assert "DataLab-{#AppVersion}-Windows-x64" in inno_text


def test_inno_script_uses_safe_close_behavior() -> None:
    inno_text = (ROOT / "packaging" / "windows" / "DataLab.iss").read_text(
        encoding="utf-8"
    )

    assert "CloseApplications=yes" in inno_text
    assert "RestartApplications=no" in inno_text
    assert "PrivilegesRequired=admin" in inno_text
