"""show_bounded_critical keeps the OK button on-screen for long error bodies."""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QMessageBox

from app_desktop.message_dialogs import show_bounded_critical


def _capture(monkeypatch: Any) -> list[QMessageBox]:
    QApplication.instance() or QApplication([])
    boxes: list[QMessageBox] = []

    def fake_exec(self: QMessageBox) -> int:
        boxes.append(self)
        return QMessageBox.StandardButton.Ok

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    return boxes


def test_long_body_goes_to_scrollable_detail_not_inline(monkeypatch: Any) -> None:
    boxes = _capture(monkeypatch)
    long_log = "\n".join(f"error line {i}: something went wrong" for i in range(200))
    show_bounded_critical(None, "Compilation Failed", long_log, summary="Compile failed.")

    box = boxes[-1]
    # The long log must NOT be inline (that grows the dialog past the screen); it lives in the
    # scrollable Show-Details pane, with only the short summary inline.
    assert box.text() == "Compile failed."
    assert box.detailedText() == long_log
    assert box.icon() == QMessageBox.Icon.Critical


def test_short_body_stays_inline(monkeypatch: Any) -> None:
    boxes = _capture(monkeypatch)
    show_bounded_critical(None, "Error", "Something small failed.")

    box = boxes[-1]
    assert box.text() == "Something small failed."
    assert box.detailedText() == ""  # short → no detail pane
