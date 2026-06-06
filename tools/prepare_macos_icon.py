from __future__ import annotations

import argparse
from pathlib import Path

try:
    from PIL import Image, ImageChops
except Exception as exc:  # pragma: no cover - exercised by build script failures
    raise SystemExit(f"Pillow is required to prepare macOS icons: {exc}") from exc

ICONSET_SIZES = (16, 32, 64, 128, 256, 512)
CANVAS_SIZE = 1024
DEFAULT_VISIBLE_FRACTION = 1.0


def _sanitize_transparent_rgb(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    for y in range(rgba.height):
        for x in range(rgba.width):
            red, green, blue, alpha = pixels[x, y]
            if alpha == 0:
                pixels[x, y] = (0, 0, 0, 0)
    return rgba


def _resize_rgba_premultiplied(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize RGBA data without pulling transparent RGB into edge pixels."""

    rgba = image.convert("RGBA")
    red, green, blue, alpha = rgba.split()
    premultiplied = Image.merge(
        "RGBA",
        (
            ImageChops.multiply(red, alpha),
            ImageChops.multiply(green, alpha),
            ImageChops.multiply(blue, alpha),
            alpha,
        ),
    )
    resized = premultiplied.resize(size, Image.Resampling.LANCZOS)
    red, green, blue, alpha = resized.split()
    red_px = red.load()
    green_px = green.load()
    blue_px = blue.load()
    alpha_px = alpha.load()
    for y in range(size[1]):
        for x in range(size[0]):
            alpha_value = alpha_px[x, y]
            if alpha_value:
                red_px[x, y] = min(255, round(red_px[x, y] * 255 / alpha_value))
                green_px[x, y] = min(255, round(green_px[x, y] * 255 / alpha_value))
                blue_px[x, y] = min(255, round(blue_px[x, y] * 255 / alpha_value))
    return Image.merge("RGBA", (red, green, blue, alpha))


def _row_edge_backgrounds(image: Image.Image) -> list[tuple[tuple[int, int, int], tuple[int, int, int]]]:
    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    colors: list[tuple[tuple[int, int, int], tuple[int, int, int]] | None] = []
    for y in range(height):
        row_colors = [
            (x, pixels[x, y][:3])
            for x in range(width)
            if pixels[x, y][3] > 192 and pixels[x, y][2] - pixels[x, y][0] > 20
        ]
        if row_colors:
            colors.append((row_colors[0][1], row_colors[-1][1]))
        else:
            colors.append(None)

    nearest: tuple[tuple[int, int, int], tuple[int, int, int]] | None = None
    for idx, color in enumerate(colors):
        if color is None and nearest is not None:
            colors[idx] = nearest
        elif color is not None:
            nearest = color
    nearest = None
    for idx in range(len(colors) - 1, -1, -1):
        color = colors[idx]
        if color is None and nearest is not None:
            colors[idx] = nearest
        elif color is not None:
            nearest = color
    fallback = ((0, 120, 220), (0, 92, 180))
    return _smooth_edge_backgrounds([color or fallback for color in colors])


def _smooth_edge_backgrounds(
    colors: list[tuple[tuple[int, int, int], tuple[int, int, int]]],
    *,
    radius: int = 24,
) -> list[tuple[tuple[int, int, int], tuple[int, int, int]]]:
    smoothed: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []
    for idx in range(len(colors)):
        start = max(0, idx - radius)
        end = min(len(colors), idx + radius + 1)
        window = colors[start:end]
        sides = []
        for side in range(2):
            sides.append(
                tuple(
                    round(sum(color[side][channel] for color in window) / len(window))
                    for channel in range(3)
                )
            )
        smoothed.append((sides[0], sides[1]))
    return smoothed


def _flatten_to_native_macos_square(image: Image.Image) -> Image.Image:
    """Return an opaque square so macOS applies the native app icon mask."""

    rgba = image.convert("RGBA")
    pixels = rgba.load()
    width, height = rgba.size
    row_backgrounds = _row_edge_backgrounds(rgba)
    flattened = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
    out = flattened.load()
    for y in range(height):
        left_bg, right_bg = row_backgrounds[y]
        for x in range(width):
            red, green, blue, alpha = pixels[x, y]
            if alpha >= 255:
                out[x, y] = (red, green, blue, 255)
            else:
                bg_red, bg_green, bg_blue = left_bg if x < width // 2 else right_bg
                inv_alpha = 255 - alpha
                out[x, y] = (
                    round((red * alpha + bg_red * inv_alpha) / 255),
                    round((green * alpha + bg_green * inv_alpha) / 255),
                    round((blue * alpha + bg_blue * inv_alpha) / 255),
                    255,
                )
    return flattened


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
    cropped = _resize_rgba_premultiplied(cropped, resized_size)

    canvas = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    x = (canvas_size - cropped.width) // 2
    y = (canvas_size - cropped.height) // 2
    canvas.alpha_composite(cropped, (x, y))
    return _flatten_to_native_macos_square(canvas)


def _resize_icon(image: Image.Image, size: int) -> Image.Image:
    resized = _resize_rgba_premultiplied(image, (size, size))
    return _flatten_to_native_macos_square(resized)


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
