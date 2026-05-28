from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]


def test_app_icon_has_transparent_rounded_corners() -> None:
    icon = Image.open(ROOT / "DataLab.png").convert("RGBA")
    alpha = icon.getchannel("A")

    assert icon.size == (1024, 1024)
    assert alpha.getextrema()[0] == 0

    transparent = 0
    for x in range(0, 24):
        for y in range(0, 24):
            if alpha.getpixel((x, y)) == 0:
                transparent += 1
    assert transparent >= 200

    assert icon.getpixel((512, 512))[3] == 255
