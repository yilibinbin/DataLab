from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtGui import QImage


def test_desktop_gui_screenshot_capture_smoke(tmp_path) -> None:
    from tools.capture_desktop_gui_screens import capture_desktop_gui_screens

    out = tmp_path / "gui-screens"
    report = capture_desktop_gui_screens(out=out, width=1280, height=820)

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
        assert image.width() == 1280
        assert image.height() == 820
        assert item["width"] == 1280
        assert item["height"] == 820
