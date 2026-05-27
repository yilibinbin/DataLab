from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _section_lines(text: str, section_name: str) -> list[str]:
    section_header = f"[{section_name}]"
    lines: list[str] = []
    in_section = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            if in_section:
                break
            in_section = line == section_header
            continue
        if in_section and line and not line.startswith(";"):
            lines.append(line)

    return lines


def test_macos_spec_declares_datalab_document_type_for_direct_spec_builds() -> None:
    text = (ROOT / "DataLab.spec").read_text(encoding="utf-8")

    assert "argv_emulation=False" in text
    assert "info_plist=" in text
    assert "CFBundleDocumentTypes" in text
    assert "UTExportedTypeDeclarations" in text
    assert "org.datalab.workspace" in text
    assert '"public.filename-extension": ["datalab"]' in text
    assert '"UTTypeConformsTo": ["public.data"]' in text


def test_mac_build_preserves_existing_pyinstaller_cli_features_and_patches_info_plist() -> None:
    text = (ROOT / "build_mac_data_gui.sh").read_text(encoding="utf-8")

    assert 'pyinstaller "$ENTRY_FILE"' in text
    assert '--name "$APP_NAME"' in text
    assert '"${DOCS_DATA_FLAGS[@]}"' in text
    assert '"${HIDDEN_IMPORT_FLAGS[@]}"' in text
    assert '"${EXCLUDE_FLAGS[@]}"' in text
    assert '"${TARGET_ARCH_FLAG[@]}"' in text
    assert "DATALAB_BUNDLE_TINYTEX" in text
    assert "CFBundleDocumentTypes" in text
    assert "UTExportedTypeDeclarations" in text
    assert "org.datalab.workspace" in text


def test_windows_inno_registers_datalab_file_association() -> None:
    text = (ROOT / "packaging" / "windows" / "DataLab.iss").read_text(encoding="utf-8")
    setup_lines = _section_lines(text, "Setup")
    registry_lines = _section_lines(text, "Registry")

    assert "ChangesAssociations=yes" in setup_lines
    assert (
        'Root: HKCR; Subkey: ".datalab"; ValueType: string; ValueName: ""; '
        'ValueData: "DataLab.Workspace"; Flags: uninsdeletevalue'
    ) in registry_lines
    assert (
        'Root: HKCR; Subkey: ".datalab\\OpenWithProgids"; ValueType: string; '
        'ValueName: "DataLab.Workspace"; ValueData: ""; Flags: uninsdeletevalue'
    ) in registry_lines
    assert (
        'Root: HKCR; Subkey: "DataLab.Workspace"; ValueType: string; '
        'ValueName: ""; ValueData: "DataLab Workspace"; Flags: uninsdeletekey'
    ) in registry_lines
    assert (
        'Root: HKCR; Subkey: "DataLab.Workspace\\DefaultIcon"; ValueType: string; '
        'ValueName: ""; ValueData: "{app}\\DataLab.exe,0"'
    ) in registry_lines
    assert (
        'Root: HKCR; Subkey: "DataLab.Workspace\\shell\\open\\command"; '
        'ValueType: string; ValueName: ""; '
        'ValueData: """{app}\\DataLab.exe"" ""%1"""'
    ) in registry_lines
