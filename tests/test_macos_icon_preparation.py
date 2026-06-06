from __future__ import annotations

from pathlib import Path

from PIL import Image

from tools.prepare_macos_icon import prepare_master_icon, write_iconset


ROOT = Path(__file__).resolve().parents[1]


def test_prepare_master_icon_removes_large_transparent_margin_and_cleans_rgb() -> None:
    master = prepare_master_icon(ROOT / "DataLab.png")
    alpha = master.getchannel("A")
    bbox = alpha.getbbox()

    assert master.size == (1024, 1024)
    assert bbox is not None
    assert bbox[0] <= 32
    assert bbox[1] <= 32
    assert bbox[2] >= 992
    assert bbox[3] >= 992

    for red, green, blue, alpha_value in master.getdata():
        if alpha_value == 0:
            assert (red, green, blue) == (0, 0, 0)


def test_write_iconset_generates_alpha_clean_sizes(tmp_path: Path) -> None:
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

    small = Image.open(iconset / "icon_64x64.png").convert("RGBA")
    for red, green, blue, alpha_value in small.getdata():
        if alpha_value == 0:
            assert (red, green, blue) == (0, 0, 0)


def test_macos_build_uses_alpha_aware_icon_preparation() -> None:
    text = (ROOT / "build_mac_data_gui.sh").read_text(encoding="utf-8")

    assert "tools/prepare_macos_icon.py" in text
    assert "sips -z" not in text
