from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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
