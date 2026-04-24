"""
Raster backend implementation for PDF preview.
Integrates with existing PDF-to-image conversion pipeline.
"""

import logging
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Tuple, List
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)


def find_pdf_conversion_tool() -> Optional[Tuple[str, str]]:
    """
    Find available PDF conversion tool.
    Returns: (tool_name, tool_path) or None

    Priority: pdftoppm > gs (ghostscript)
    """
    # Try pdftoppm first (fastest, best quality)
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm:
        return ("pdftoppm", pdftoppm)

    # Try ghostscript
    for gs_cmd in ["gs", "gswin64c", "gswin32c"]:  # Windows variants
        gs_path = shutil.which(gs_cmd)
        if gs_path:
            return ("gs", gs_path)

    return None


def convert_pdf_to_images(
    pdf_path: Path,
    dpi: int = 200,
    max_pages: Optional[int] = None,
    tool: Optional[Tuple[str, str]] = None,
) -> List[Image.Image]:
    """
    Convert PDF pages to PIL images using available tool.

    Args:
        pdf_path: Path to PDF file
        dpi: Render DPI
        max_pages: Limit number of pages to convert
        tool: (tool_name, tool_path) tuple

    Returns:
        List of PIL Image objects (RGBA)
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Find tool if not provided
    if not tool:
        tool = find_pdf_conversion_tool()
        if not tool:
            raise RuntimeError("No PDF conversion tool found (pdftoppm or ghostscript)")

    tool_name, tool_path = tool
    images = []

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        try:
            if tool_name == "pdftoppm":
                images = _convert_pdftoppm(pdf_path, tmp_path, dpi, max_pages, tool_path)
            elif tool_name == "gs":
                images = _convert_ghostscript(pdf_path, tmp_path, dpi, max_pages, tool_path)
            else:
                raise RuntimeError(f"Unknown tool: {tool_name}")

            logger.info(f"[pdf] Converted {len(images)} pages using {tool_name}")
            return images

        except Exception as e:
            logger.error(f"[pdf] Conversion error: {e}")
            raise


def _convert_pdftoppm(
    pdf_path: Path,
    tmpdir: Path,
    dpi: int,
    max_pages: Optional[int],
    pdftoppm_path: str,
) -> List[Image.Image]:
    """Convert using pdftoppm (preferred)."""
    output_prefix = str(tmpdir / "page")

    cmd = [
        pdftoppm_path,
        "-png",
        "-r", str(dpi),
        str(pdf_path),
        output_prefix,
    ]

    if max_pages:
        cmd.extend(["-l", str(max_pages)])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            text=False,
            check=False
        )

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"pdftoppm failed: {stderr}")

        prefix_name = Path(output_prefix).name
        candidates = list(tmpdir.glob(f"{prefix_name}-*.png"))

        def _page_key(path: Path) -> int:
            stem = path.stem
            if "-" in stem:
                suffix = stem.rsplit("-", 1)[1]
                if suffix.isdigit():
                    return int(suffix)
            return 0

        candidates.sort(key=_page_key)
        if not candidates:
            single = Path(f"{output_prefix}.png")
            if single.exists():
                candidates = [single]

        images: List[Image.Image] = []
        for img_path in candidates:
            img = Image.open(img_path).convert("RGBA")
            images.append(img)
        return images

    except subprocess.TimeoutExpired:
        raise RuntimeError("pdftoppm conversion timeout")
    except Exception as e:
        raise RuntimeError(f"pdftoppm error: {e}")


def _convert_ghostscript(
    pdf_path: Path,
    tmpdir: Path,
    dpi: int,
    max_pages: Optional[int],
    gs_path: str,
) -> List[Image.Image]:
    """Convert using ghostscript (fallback)."""
    output_pattern = str(tmpdir / "page-%d.png")

    cmd = [
        gs_path,
        "-q",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",
        "-sDEVICE=png16m",
        f"-r{dpi}x{dpi}",
        "-dGraphicsAlphaBits=4",
        f"-sOutputFile={output_pattern}",
        str(pdf_path),
    ]

    if max_pages:
        cmd.insert(4, f"-dLastPage={max_pages}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
            text=False,
            check=False
        )

        if result.returncode != 0:
            stderr = result.stderr.decode("utf-8", errors="replace")
            raise RuntimeError(f"ghostscript failed: {stderr}")

        # Load converted images
        images = []
        page_num = 1
        while True:
            img_path = Path(f"{tmpdir / 'page'}-{page_num}.png")
            if not img_path.exists():
                break

            img = Image.open(img_path).convert("RGBA")
            images.append(img)
            page_num += 1

        return images

    except subprocess.TimeoutExpired:
        raise RuntimeError("ghostscript conversion timeout")
    except Exception as e:
        raise RuntimeError(f"ghostscript error: {e}")


def apply_zoom_to_image(image: Image.Image, zoom: float) -> Image.Image:
    """
    Apply zoom to image with high-quality resampling.

    Args:
        image: PIL Image
        zoom: Zoom factor (1.0 = 100%)

    Returns:
        Zoomed PIL Image
    """
    if zoom == 1.0:
        return image

    new_width = int(image.width * zoom)
    new_height = int(image.height * zoom)

    # Use high-quality resampling
    return image.resize((new_width, new_height), Image.Resampling.LANCZOS)


def apply_dark_mode_to_image(image: Image.Image) -> Image.Image:
    """
    Apply dark mode (color inversion) to image while preserving alpha.
    """
    if image.mode == "RGBA":
        # Invert RGB, preserve alpha
        rgb = image.convert("RGB")
        inverted = ImageOps.invert(rgb)
        inverted.putalpha(image.split()[3])  # Restore alpha channel
        return inverted
    elif image.mode == "RGB":
        return ImageOps.invert(image)
    elif image.mode == "L":
        return ImageOps.invert(image)
    else:
        # Try to convert and invert
        try:
            rgb = image.convert("RGB")
            return ImageOps.invert(rgb)
        except Exception:
            return image


def pil_to_qpixmap(image: Image.Image) -> 'QPixmap':
    """
    Convert PIL Image to Qt QPixmap.
    """
    from PySide6.QtGui import QImage, QPixmap

    if image.mode not in ("RGBA", "BGRA"):
        image = image.convert("RGBA")

    data = image.tobytes("raw", "RGBA")
    qimage = QImage(data, image.width, image.height, QImage.Format_RGBA8888)
    return QPixmap.fromImage(qimage)
