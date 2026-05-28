from __future__ import annotations

from typing import Any

from app_desktop.update_progress_dialog import UpdateProgressDialog
from shared.update_payload import InstallerAsset


def _asset() -> InstallerAsset:
    return InstallerAsset(
        platform_key="macos",
        name="DataLab-test.pkg",
        url="https://example.invalid/DataLab-test.pkg",
        sha256="0" * 64,
        size_bytes=100,
    )


def test_progress_dialog_cannot_be_dismissed_during_download(qtbot: Any) -> None:
    dialog = UpdateProgressDialog(_asset(), "en")
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.reject()
    assert dialog.isVisible()

    assert dialog.close() is False
    assert dialog.isVisible()
