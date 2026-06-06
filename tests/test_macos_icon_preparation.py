from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image

from tools.prepare_macos_icon import prepare_master_icon, write_iconset


ROOT = Path(__file__).resolve().parents[1]


def test_prepare_master_icon_outputs_native_opaque_square() -> None:
    master = prepare_master_icon(ROOT / "DataLab.png")
    alpha = master.getchannel("A")
    bbox = alpha.getbbox()

    assert master.size == (1024, 1024)
    assert bbox == (0, 0, 1024, 1024)

    assert all(alpha_value == 255 for alpha_value in alpha.getdata())
    for point in [(0, 0), (0, 512), (512, 0), (1023, 512), (512, 1023), (1023, 1023)]:
        assert master.getpixel(point)[3] == 255


def test_write_iconset_generates_native_opaque_sizes(tmp_path: Path) -> None:
    iconset = tmp_path / "app_icon.iconset"

    write_iconset(ROOT / "DataLab.png", iconset)

    expected = {
        "icon_16x16.png",
        "icon_16x16@2x.png",
        "icon_32x32.png",
        "icon_32x32@2x.png",
        "icon_64x64.png",
        "icon_64x64@2x.png",
        "icon_128x128.png",
        "icon_128x128@2x.png",
        "icon_256x256.png",
        "icon_256x256@2x.png",
        "icon_512x512.png",
        "icon_512x512@2x.png",
    }
    assert {path.name for path in iconset.glob("*.png")} == expected

    for path in iconset.glob("*.png"):
        image = Image.open(path).convert("RGBA")
        assert image.getchannel("A").getbbox() == (0, 0, image.width, image.height)
        assert all(alpha_value == 255 for alpha_value in image.getchannel("A").getdata())


def test_prepare_master_icon_avoids_poisoned_transparent_rgb_halo(tmp_path: Path) -> None:
    source = Image.new("RGBA", (64, 64), (255, 0, 0, 0))
    pixels = source.load()
    for y in range(8, 56):
        for x in range(8, 56):
            pixels[x, y] = (0, 120, 220, 255)
    for y in range(6, 58):
        for x in range(6, 58):
            if pixels[x, y][3] == 0:
                pixels[x, y] = (0, 120, 220, 96)
    source_path = tmp_path / "poisoned.png"
    source.save(source_path)

    master = prepare_master_icon(source_path, canvas_size=128, visible_fraction=1.0)

    assert master.getchannel("A").getextrema() == (255, 255)
    edge_pixels = [
        master.getpixel((0, 64)),
        master.getpixel((127, 64)),
        master.getpixel((64, 0)),
        master.getpixel((64, 127)),
    ]
    for red, green, blue, alpha in edge_pixels:
        assert alpha == 255
        assert blue > red
        assert green > red


@pytest.mark.skipif(shutil.which("iconutil") is None, reason="macOS iconutil is unavailable")
def test_iconutil_roundtrip_preserves_native_opaque_icon(tmp_path: Path) -> None:
    iconset = tmp_path / "app_icon.iconset"
    icns = tmp_path / "app_icon.icns"
    roundtrip = tmp_path / "roundtrip.iconset"

    write_iconset(ROOT / "DataLab.png", iconset)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)], check=True)
    subprocess.run(["iconutil", "-c", "iconset", str(icns), "-o", str(roundtrip)], check=True)

    large = Image.open(roundtrip / "icon_512x512@2x.png").convert("RGBA")
    alpha = large.getchannel("A")
    assert large.size == (1024, 1024)
    assert alpha.getbbox() == (0, 0, 1024, 1024)
    assert alpha.getextrema() == (255, 255)


def test_macos_build_uses_alpha_aware_icon_preparation() -> None:
    text = (ROOT / "build_mac_data_gui.sh").read_text(encoding="utf-8")

    assert "tools/prepare_macos_icon.py" in text
    assert "sips -z" not in text
