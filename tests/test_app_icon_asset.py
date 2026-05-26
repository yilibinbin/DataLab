from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def test_app_icon_has_transparent_rounded_corners() -> None:
    icon = Image.open(ROOT / "DataLab.png").convert("RGBA")

    assert icon.size == (1024, 1024)
    assert icon.getchannel("A").getextrema()[0] == 0
    assert icon.getpixel((0, 0))[3] == 0
    assert icon.getpixel((1023, 0))[3] == 0
    assert icon.getpixel((0, 1023))[3] == 0
    assert icon.getpixel((1023, 1023))[3] == 0
    assert icon.getpixel((512, 512))[3] == 255
