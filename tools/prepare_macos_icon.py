from __future__ import annotations

import argparse
from pathlib import Path

try:
    from PIL import Image
except Exception as exc:  # pragma: no cover - exercised by build script failures
    raise SystemExit(f"Pillow is required to prepare macOS icons: {exc}") from exc

ICONSET_SIZES = (16, 32, 64, 128, 256, 512)
CANVAS_SIZE = 1024
DEFAULT_VISIBLE_FRACTION = 0.96


def _sanitize_transparent_rgb(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = []
    for red, green, blue, alpha in rgba.getdata():
        if alpha == 0:
            pixels.append((0, 0, 0, 0))
        else:
            pixels.append((red, green, blue, alpha))
    rgba.putdata(pixels)
    return rgba


def prepare_master_icon(
    source: Path,
    *,
    canvas_size: int = CANVAS_SIZE,
    visible_fraction: float = DEFAULT_VISIBLE_FRACTION,
) -> Image.Image:
    """Return a macOS icon master with tight content and clean alpha edges."""

    if not 0.5 <= visible_fraction <= 1.0:
        raise ValueError("visible_fraction must be between 0.5 and 1.0")
    image = _sanitize_transparent_rgb(Image.open(source))
    alpha_bbox = image.getchannel("A").getbbox()
    if alpha_bbox is None:
        raise ValueError(f"{source} does not contain visible pixels")
    cropped = image.crop(alpha_bbox)
    target_size = max(1, int(round(canvas_size * visible_fraction)))
    scale = min(target_size / cropped.width, target_size / cropped.height)
    resized_size = (
        max(1, int(round(cropped.width * scale))),
        max(1, int(round(cropped.height * scale))),
    )
    cropped = cropped.resize(resized_size, Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    x = (canvas_size - cropped.width) // 2
    y = (canvas_size - cropped.height) // 2
    canvas.alpha_composite(cropped, (x, y))
    return _sanitize_transparent_rgb(canvas)


def _resize_icon(image: Image.Image, size: int) -> Image.Image:
    resized = image.resize((size, size), Image.Resampling.LANCZOS)
    return _sanitize_transparent_rgb(resized)


def write_iconset(source: Path, iconset_dir: Path, *, visible_fraction: float = DEFAULT_VISIBLE_FRACTION) -> None:
    master = prepare_master_icon(source, visible_fraction=visible_fraction)
    iconset_dir.mkdir(parents=True, exist_ok=True)
    for size in ICONSET_SIZES:
        _resize_icon(master, size).save(iconset_dir / f"icon_{size}x{size}.png", dpi=(72, 72))
        _resize_icon(master, size * 2).save(iconset_dir / f"icon_{size}x{size}@2x.png", dpi=(72, 72))


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare alpha-clean macOS .iconset PNGs for DataLab.")
    parser.add_argument("source", type=Path)
    parser.add_argument("iconset_dir", type=Path)
    parser.add_argument("--visible-fraction", type=float, default=DEFAULT_VISIBLE_FRACTION)
    args = parser.parse_args()
    write_iconset(args.source, args.iconset_dir, visible_fraction=args.visible_fraction)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
