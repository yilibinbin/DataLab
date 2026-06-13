from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtGui import QImage

from app_desktop.workbench_visual_contract import SUPPORTED_VISUAL_HEIGHT, SUPPORTED_VISUAL_WIDTH


def test_desktop_gui_screenshot_capture_smoke(tmp_path) -> None:
    from tools.capture_desktop_gui_screens import capture_desktop_gui_screens

    out = tmp_path / "gui-screens"
    report = capture_desktop_gui_screens(
        out=out,
        width=SUPPORTED_VISUAL_WIDTH,
        height=SUPPORTED_VISUAL_HEIGHT,
    )

    assert report["count"] >= 10
    assert (out / "manifest.json").is_file()
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["count"] == report["count"]

    for item in report["screenshots"]:
        path = out / os.path.basename(item["path"])
        assert path.is_file()
        assert path.stat().st_size > 0
        image = QImage(str(path))
        assert not image.isNull(), path
        assert image.width() == SUPPORTED_VISUAL_WIDTH
        assert image.height() == SUPPORTED_VISUAL_HEIGHT
        assert item["width"] == SUPPORTED_VISUAL_WIDTH
        assert item["height"] == SUPPORTED_VISUAL_HEIGHT
