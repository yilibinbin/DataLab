"""
Raster backend implementation for PDF preview.
Integrates with existing PDF-to-image conversion pipeline.
"""

import logging
import os
import subprocess
import tempfile
import shutil
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, NamedTuple, Optional, Tuple, List, TYPE_CHECKING, TypeAlias
from PIL import Image, ImageOps

if TYPE_CHECKING:
    # ``QPixmap`` is referenced as a forward annotation on the
    # ``pil_to_qpixmap`` return type. The PySide6 import lives inside
    # the function body so unit tests don't need a Qt event loop, so
    # the type-checker needs an explicit TYPE_CHECKING import.
    from PySide6.QtGui import QPixmap

# Cache-key tuple shape:
# ``(resolved_abs_path: str, mtime_ns: int, size: int, dpi: int,
#    max_pages: int, tool_name: str)``.
# All six elements are hashable, so the tuple is a valid dict key.
_PdfCacheKey: TypeAlias = tuple[str, int, int, int, int, str]

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Per-call LRU cache for ``convert_pdf_to_images`` (#10)
# ----------------------------------------------------------------------------
#
# Every PDF preview frame — page navigation, zoom change, dark-mode toggle —
# calls ``convert_pdf_to_images`` with the same ``(pdf_path, dpi)``. Each
# invocation spawns a pdftoppm / gs subprocess (~200-800 ms) and re-decodes
# every page. For an editing session where the user hammers next-page a few
# dozen times, that dominates the preview latency.
#
# We cache on ``(pdf_abspath, pdf_mtime_ns, pdf_size, dpi, max_pages, tool_name)``.
# mtime+size together catch the "user re-exported the PDF" case without
# a full hash — both values change on every meaningful rewrite, and the
# filesystem supplies them in O(1) from ``stat()``. The ``tool_name``
# suffix distinguishes pdftoppm and ghostscript outputs (pixel-identical
# most of the time, but not guaranteed — separate cache entries keep the
# byte-identity invariant on each tool).
#
# Values are the already-RGBA'd PIL images in memory. PIL's lazy-load is
# forced by the ``.convert("RGBA")`` inside the converters, so the images
# survive the ``TemporaryDirectory`` cleanup on the source files.

# Worst-case memory at the enforced ceilings: 16 entries × 50 pages × ~140 MB
# per A4 page at 600 dpi RGBA ≈ 112 GB. At typical desktop use (DPI=200,
# ~5 pages, A4) it's ~800 MB. The hard caps on DPI and page count (below)
# are load-bearing for this calculation — callers that bypass those caps
# could blow past the memory budget. **DO NOT expose this function to a
# web route with user-controlled dpi or max_pages.** It is desktop-only
# today (grep across app_web/ confirms no blueprint calls it). Any web
# exposure must add an explicit allow-list + rate limit.
_PDF_RASTER_CACHE_MAXSIZE = 16
_pdf_raster_cache: "OrderedDict[_PdfCacheKey, List[Image.Image]]" = OrderedDict()
_pdf_raster_cache_lock = threading.Lock()
_pdf_raster_cache_stats = {"hits": 0, "misses": 0}

# DPI bounds. 36 is pdftoppm's practical lower bound (below that pages
# come out illegibly small); 600 matches the desktop's
# ``window_latex_pdf_mixin._clamp_dpi`` ceiling. Enforced before any
# subprocess / cache work so an untrusted caller can't request a
# memory-exhausting raster.
_DPI_MIN_RASTER = 36
_DPI_MAX_RASTER = 600

# Hard ceiling on pages rasterised per call — defuses the "PDF bomb"
# attack where a 10 000-page PDF (legitimate edge case or adversarial
# input) would explode memory. Callers passing ``max_pages=None``
# (no explicit cap) implicitly opt into this ceiling; callers passing
# a lower value get their requested cap.
_ABSOLUTE_MAX_PAGES = 50


def _clamp_dpi_raster(dpi: Any) -> int:
    """Validate+clamp the raster DPI. Raises ValueError on non-integer
    input so programming errors aren't silently swallowed."""
    try:
        value = int(dpi)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"dpi must be an integer, got {dpi!r}") from exc
    if value < _DPI_MIN_RASTER or value > _DPI_MAX_RASTER:
        raise ValueError(
            f"dpi={value} is outside the safe range "
            f"[{_DPI_MIN_RASTER}, {_DPI_MAX_RASTER}] — "
            "rasterisation at this resolution would risk memory exhaustion"
        )
    return value


def _resolve_max_pages(max_pages: Optional[int]) -> int:
    """Apply the ``_ABSOLUTE_MAX_PAGES`` ceiling. ``None`` (no cap from
    caller) maps to the absolute ceiling; an explicit value is clamped
    down to it."""
    if max_pages is None:
        return _ABSOLUTE_MAX_PAGES
    try:
        value = int(max_pages)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"max_pages must be an integer or None, got {max_pages!r}"
        ) from exc
    if value <= 0:
        raise ValueError(f"max_pages must be positive, got {value}")
    return min(value, _ABSOLUTE_MAX_PAGES)


class _PdfRasterCacheInfo(NamedTuple):
    """Hit/miss counters plus current LRU occupancy.

    Field order matches ``functools._CacheInfo``
    (``hits, misses, maxsize, currsize``) so a caller unpacking
    positionally against either flavour gets the same values. Do **not**
    reorder — the compat contract is part of the shared diagnostic
    surface with the mpmath sampling cache and the render cache.
    """

    hits: int
    misses: int
    maxsize: int
    currsize: int


def _pdf_cache_key(
    pdf_path: Path,
    dpi: int,
    max_pages: int,
    tool_name: str,
) -> _PdfCacheKey:
    """Build a cache key that invalidates when the file changes.

    Uses ``(resolved_abs_path, mtime_ns, size, dpi, max_pages, tool_name)``.

    Uses ``Path.resolve()`` (not ``os.path.abspath``) so symlinks are
    canonicalised to their target. Two callers passing different symlink
    paths that resolve to the same file share a cache entry (correct —
    they're rendering the same bytes). ``resolve()`` can raise
    ``OSError`` (missing target, broken symlink chain) — the caller
    catches this and bypasses the cache.

    Both mtime and size are required: a same-size-same-time overwrite is
    extraordinarily rare but possible (e.g., an atomic replace followed
    by a backdate); using both makes accidental stale hits near-impossible.
    """
    resolved = pdf_path.resolve(strict=True)
    st = resolved.stat()
    return (
        str(resolved),
        st.st_mtime_ns,
        st.st_size,
        int(dpi),
        max_pages,
        tool_name,
    )


def clear_pdf_raster_cache() -> None:
    """Drop all cached pages. Call on PDF-export completion to ensure the
    user sees a fresh render even if mtime resolution fooled the cache."""
    with _pdf_raster_cache_lock:
        _pdf_raster_cache.clear()
        _pdf_raster_cache_stats["hits"] = 0
        _pdf_raster_cache_stats["misses"] = 0


def pdf_raster_cache_info() -> _PdfRasterCacheInfo:
    """Snapshot of the raster LRU state.

    Constructed with keyword args so the ``functools._CacheInfo``-matching
    field order stays locked — don't rely on argument position here.
    """
    with _pdf_raster_cache_lock:
        return _PdfRasterCacheInfo(
            hits=_pdf_raster_cache_stats["hits"],
            misses=_pdf_raster_cache_stats["misses"],
            maxsize=_PDF_RASTER_CACHE_MAXSIZE,
            currsize=len(_pdf_raster_cache),
        )


def _cache_get(key: _PdfCacheKey) -> Optional[List[Image.Image]]:
    """LRU-aware fetch: moves the entry to the end on hit. Returns a
    copy of the image list (so a caller mutating the list — e.g., zoom
    in place — doesn't poison the cache for the next caller)."""
    with _pdf_raster_cache_lock:
        entry = _pdf_raster_cache.get(key)
        if entry is None:
            _pdf_raster_cache_stats["misses"] += 1
            return None
        _pdf_raster_cache.move_to_end(key)
        _pdf_raster_cache_stats["hits"] += 1
        # Shallow-copy the list; individual PIL images are reused (safe —
        # they're treated as immutable by every caller in DataLab).
        return list(entry)


def _cache_put(key: _PdfCacheKey, value: List[Image.Image]) -> None:
    """Store and evict to ``_PDF_RASTER_CACHE_MAXSIZE`` LRU entries."""
    with _pdf_raster_cache_lock:
        _pdf_raster_cache[key] = list(value)
        _pdf_raster_cache.move_to_end(key)
        while len(_pdf_raster_cache) > _PDF_RASTER_CACHE_MAXSIZE:
            _pdf_raster_cache.popitem(last=False)


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
        dpi: Render DPI. Clamped to ``[_DPI_MIN_RASTER, _DPI_MAX_RASTER]``
          — values outside that range raise ``ValueError`` rather than
          silently requesting a multi-gigabyte raster.
        max_pages: Limit number of pages to convert. ``None`` applies
          the ``_ABSOLUTE_MAX_PAGES`` hard cap; an explicit value is
          clamped down to that cap. Non-positive values raise.
        tool: (tool_name, tool_path) tuple

    Returns:
        List of PIL Image objects (RGBA)

    LRU-cached by ``(resolved_abs_path, mtime_ns, size, dpi,
    effective_max_pages, tool)`` so repeat previews of an unchanged PDF
    skip the subprocess entirely. A rewritten PDF (new mtime or size)
    invalidates its entry. Cache misses preserve the original (uncached)
    behaviour exactly, so ``FileNotFoundError`` on a missing PDF still
    propagates.
    """
    # Validate BEFORE anything expensive. A dpi=0 or dpi=100000 must fail
    # fast with a clear error, not get far enough to exhaust memory.
    safe_dpi = _clamp_dpi_raster(dpi)
    effective_max_pages = _resolve_max_pages(max_pages)

    # Raise cleanly **before** touching the cache — a stale cached entry
    # must never mask a deleted file.
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Find tool if not provided
    if not tool:
        tool = find_pdf_conversion_tool()
        if not tool:
            raise RuntimeError("No PDF conversion tool found (pdftoppm or ghostscript)")

    tool_name, tool_path = tool

    # Cache lookup: build the key from stat() (cheap), then either
    # return the cached images or fall through to the converter.
    try:
        cache_key = _pdf_cache_key(
            pdf_path, safe_dpi, effective_max_pages, tool_name
        )
    except OSError as exc:
        # stat()/resolve() failed between the exists() check and now.
        # Log at WARNING so repeated races (e.g. an attacker cycling a
        # symlink target) surface in production monitoring — silently
        # bypassing the cache at DEBUG level would hide the signal.
        logger.warning(
            "[pdf] stat/resolve failed after exists(), bypassing cache "
            "(possible race or broken symlink): %s",
            exc,
        )
        cache_key = None

    if cache_key is not None:
        cached = _cache_get(cache_key)
        if cached is not None:
            logger.debug(
                f"[pdf] cache hit: {pdf_path.name} @ {safe_dpi} dpi ({len(cached)} pages)"
            )
            return cached

    images: List[Image.Image] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        try:
            if tool_name == "pdftoppm":
                images = _convert_pdftoppm(
                    pdf_path, tmp_path, safe_dpi, effective_max_pages, tool_path
                )
            elif tool_name == "gs":
                images = _convert_ghostscript(
                    pdf_path, tmp_path, safe_dpi, effective_max_pages, tool_path
                )
            else:
                raise RuntimeError(f"Unknown tool: {tool_name}")

            logger.info(f"[pdf] Converted {len(images)} pages using {tool_name}")
            # Force the PIL lazy-loader to actually read bytes before the
            # TemporaryDirectory vanishes. ``convert("RGBA")`` in
            # ``_convert_pdftoppm`` / ``_convert_ghostscript`` already
            # triggers load, but belt-and-braces here prevents silent
            # read-after-close bugs if either converter is refactored.
            for img in images:
                img.load()

            if cache_key is not None and images:
                _cache_put(cache_key, images)

            return images

        except Exception as e:
            logger.error(f"[pdf] Conversion error: {e}")
            raise


def _convert_pdftoppm(
    pdf_path: Path,
    tmpdir: Path,
    dpi: int,
    max_pages: int,
    pdftoppm_path: str,
) -> List[Image.Image]:
    """Convert using pdftoppm (preferred).

    ``max_pages`` is a resolved positive integer (see
    ``_resolve_max_pages`` — callers that passed ``None`` have already
    been mapped to ``_ABSOLUTE_MAX_PAGES``). The ``-l`` flag is emitted
    unconditionally to make the page cap explicit at the subprocess
    boundary — this is the load-bearing defence against PDF-bomb inputs
    and must NOT be made conditional even if the resolver changes.
    """
    output_prefix = str(tmpdir / "page")

    cmd = [
        pdftoppm_path,
        "-png",
        "-r", str(dpi),
        "-l", str(max_pages),
        str(pdf_path),
        output_prefix,
    ]

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
    max_pages: int,
    gs_path: str,
) -> List[Image.Image]:
    """Convert using ghostscript (fallback).

    ``max_pages`` is a resolved positive integer (see
    ``_resolve_max_pages``). The ``-dLastPage`` flag is emitted
    unconditionally as the load-bearing PDF-bomb defence — do NOT
    make it conditional.
    """
    output_pattern = str(tmpdir / "page-%d.png")

    cmd = [
        gs_path,
        "-q",
        "-dNOPAUSE",
        "-dBATCH",
        "-dSAFER",
        f"-dLastPage={max_pages}",
        "-sDEVICE=png16m",
        f"-r{dpi}x{dpi}",
        "-dGraphicsAlphaBits=4",
        f"-sOutputFile={output_pattern}",
        str(pdf_path),
    ]

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
    qimage = QImage(
        data, image.width, image.height, QImage.Format.Format_RGBA8888
    )
    return QPixmap.fromImage(qimage)
