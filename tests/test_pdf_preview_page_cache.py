"""PDF preview raster cache — regression tests.

``shared.pdf_preview_raster.convert_pdf_to_images`` shells out to
``pdftoppm`` or ``gs`` for every call. When a user flips between pages
or toggles zoom / dark-mode, the LaTeX preview pane re-invokes the
function with the same ``(pdf_path, dpi)``. Each shell-out costs
~200–800 ms and is the dominant lag in the preview UX.

This test pins the cache contract:

- repeat calls with identical ``(pdf, dpi)`` skip the subprocess and
  return cached images
- a changed file (mtime or size) invalidates the cache — users who
  re-export the PDF must see the new version, not a stale cached one
- changed ``dpi`` misses the cache (different raster)
- a non-existent PDF still raises (caching must not mask the error)
- cache-clear helper resets the store
- cache is bounded (won't OOM after hundreds of previews)
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from PIL import Image


pytestmark = pytest.mark.skipif(
    shutil.which("pdftoppm") is None and shutil.which("gs") is None,
    reason="Requires pdftoppm or ghostscript on PATH",
)


@pytest.fixture
def _minimal_pdf(tmp_path: Path) -> Path:
    """Generate a 1-page 'minimal' PDF using matplotlib (which every
    DataLab test env has). Keeps the fixture self-contained — no
    binary blobs checked into git."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(4, 3), dpi=72)
    fig.text(0.5, 0.5, "cache test", ha="center", va="center")
    pdf_path = tmp_path / "sample.pdf"
    fig.savefig(str(pdf_path), format="pdf")
    plt.close(fig)
    assert pdf_path.exists() and pdf_path.stat().st_size > 0
    return pdf_path


@pytest.fixture(autouse=True)
def _reset_raster_cache():
    from shared.pdf_preview_raster import clear_pdf_raster_cache

    clear_pdf_raster_cache()
    yield
    clear_pdf_raster_cache()


def test_second_call_uses_cache(_minimal_pdf: Path, monkeypatch):
    """The second call for the same ``(pdf, dpi)`` must not shell out."""
    from shared import pdf_preview_raster as raster

    call_count = {"n": 0}
    real_run = subprocess.run

    def _counting_run(*args, **kwargs):
        call_count["n"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr("shared.pdf_preview_raster.subprocess.run", _counting_run)

    raster.convert_pdf_to_images(_minimal_pdf, dpi=72)
    first_count = call_count["n"]
    assert first_count >= 1, "first call must actually shell out"

    raster.convert_pdf_to_images(_minimal_pdf, dpi=72)
    assert call_count["n"] == first_count, (
        "second call with same args must use cached output — no new subprocess"
    )

    info = raster.pdf_raster_cache_info()
    assert info.hits >= 1


def test_different_dpi_misses(_minimal_pdf: Path, monkeypatch):
    from shared import pdf_preview_raster as raster

    call_count = {"n": 0}
    real_run = subprocess.run

    def _counting_run(*args, **kwargs):
        call_count["n"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr("shared.pdf_preview_raster.subprocess.run", _counting_run)

    raster.convert_pdf_to_images(_minimal_pdf, dpi=72)
    raster.convert_pdf_to_images(_minimal_pdf, dpi=150)
    assert call_count["n"] >= 2, "different dpi must shell out anew"


def test_changed_pdf_invalidates_cache(_minimal_pdf: Path, monkeypatch):
    """Rewriting the PDF must invalidate the cache — a user who
    re-exports must see the new content."""
    from shared import pdf_preview_raster as raster

    call_count = {"n": 0}
    real_run = subprocess.run

    def _counting_run(*args, **kwargs):
        call_count["n"] += 1
        return real_run(*args, **kwargs)

    monkeypatch.setattr("shared.pdf_preview_raster.subprocess.run", _counting_run)

    raster.convert_pdf_to_images(_minimal_pdf, dpi=72)
    first_count = call_count["n"]

    # Overwrite the PDF with a freshly generated one (different content).
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(4, 3), dpi=72)
    fig.text(0.5, 0.5, "REWRITTEN", ha="center", va="center")
    fig.savefig(str(_minimal_pdf), format="pdf")
    plt.close(fig)

    raster.convert_pdf_to_images(_minimal_pdf, dpi=72)
    assert call_count["n"] > first_count, (
        "changed PDF file (new size/mtime) must invalidate the cache and re-shell"
    )


def test_missing_pdf_raises(tmp_path: Path):
    """The cache must not mask a missing-file error."""
    from shared import pdf_preview_raster as raster

    with pytest.raises(FileNotFoundError):
        raster.convert_pdf_to_images(tmp_path / "nonexistent.pdf", dpi=72)


def test_clear_cache_drops_entries(_minimal_pdf: Path):
    from shared import pdf_preview_raster as raster

    raster.convert_pdf_to_images(_minimal_pdf, dpi=72)
    info = raster.pdf_raster_cache_info()
    assert info.currsize >= 1

    raster.clear_pdf_raster_cache()
    info_after = raster.pdf_raster_cache_info()
    assert info_after.currsize == 0
    assert info_after.hits == 0
    assert info_after.misses == 0


def test_cache_bounded_size():
    """A long preview session must not grow cache unbounded."""
    from shared.pdf_preview_raster import _PDF_RASTER_CACHE_MAXSIZE

    # Bounded — but large enough for typical editing sessions
    # (every preview is up to ~10 MB per page at 200 dpi; we care more
    # about the entry count than raw bytes here).
    assert 8 <= _PDF_RASTER_CACHE_MAXSIZE <= 64


def test_cache_returns_equivalent_image_sequence(_minimal_pdf: Path):
    """Cached output must be equivalent (not merely truthy) — this
    protects against a bug where the cache returns stale PIL handles
    that have been closed."""
    from shared import pdf_preview_raster as raster

    first = raster.convert_pdf_to_images(_minimal_pdf, dpi=72)
    second = raster.convert_pdf_to_images(_minimal_pdf, dpi=72)
    assert len(first) == len(second) >= 1
    for a, b in zip(first, second):
        assert isinstance(a, Image.Image) and isinstance(b, Image.Image)
        assert a.size == b.size
        assert a.mode == b.mode
        # Byte-compare the image data — matplotlib+pdftoppm is deterministic
        assert a.tobytes() == b.tobytes()


def test_dpi_zero_raises(_minimal_pdf: Path):
    """dpi=0 would produce a zero-size raster / pdftoppm failure — reject
    at the guard rather than let the subprocess misbehave."""
    from shared.pdf_preview_raster import convert_pdf_to_images

    with pytest.raises(ValueError, match="dpi"):
        convert_pdf_to_images(_minimal_pdf, dpi=0)


def test_dpi_negative_raises(_minimal_pdf: Path):
    from shared.pdf_preview_raster import convert_pdf_to_images

    with pytest.raises(ValueError, match="dpi"):
        convert_pdf_to_images(_minimal_pdf, dpi=-10)


def test_dpi_too_high_raises(_minimal_pdf: Path):
    """dpi=100000 on an A4 page would ask for ~35 GB of PIL memory —
    reject at the guard."""
    from shared.pdf_preview_raster import convert_pdf_to_images

    with pytest.raises(ValueError, match="dpi"):
        convert_pdf_to_images(_minimal_pdf, dpi=100_000)


def test_max_pages_nonpositive_raises(_minimal_pdf: Path):
    """max_pages=0 or negative is a programming error — fail fast."""
    from shared.pdf_preview_raster import convert_pdf_to_images

    with pytest.raises(ValueError, match="max_pages"):
        convert_pdf_to_images(_minimal_pdf, dpi=72, max_pages=0)
    with pytest.raises(ValueError, match="max_pages"):
        convert_pdf_to_images(_minimal_pdf, dpi=72, max_pages=-5)


def test_max_pages_clamped_to_absolute_ceiling(_minimal_pdf: Path):
    """A caller asking for 10 000 pages gets clamped to
    ``_ABSOLUTE_MAX_PAGES``. The test fixture is a 1-page PDF so we
    can't verify the clamp caps actual output — but we verify no
    exception is raised and the call returns normally."""
    from shared.pdf_preview_raster import (
        _ABSOLUTE_MAX_PAGES,
        convert_pdf_to_images,
    )

    assert _ABSOLUTE_MAX_PAGES <= 50, (
        "absolute page ceiling must stay tight to bound memory"
    )
    result = convert_pdf_to_images(_minimal_pdf, dpi=72, max_pages=10_000)
    assert len(result) >= 1


def test_concurrent_miss_returns_valid_images(_minimal_pdf: Path):
    """Two threads racing on the same cache miss must both get valid
    images. Documents that we deliberately don't hold the lock across
    the subprocess — duplicate work is idempotent and bounded, while
    holding the lock for up to 800 ms would stall all other cache ops."""
    import threading

    from shared import pdf_preview_raster as raster

    raster.clear_pdf_raster_cache()
    results: list[list[Image.Image]] = []
    errors: list[BaseException] = []
    barrier = threading.Barrier(2)

    def worker() -> None:
        try:
            barrier.wait(timeout=5)
            imgs = raster.convert_pdf_to_images(_minimal_pdf, dpi=72)
            results.append(imgs)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, f"worker raised: {errors}"
    assert len(results) == 2, "both workers must complete"
    for imgs in results:
        assert imgs and all(isinstance(img, Image.Image) for img in imgs)
        assert imgs[0].mode == "RGBA"


def test_resolve_canonicalises_symlink(_minimal_pdf: Path, tmp_path: Path):
    """A symlink to a PDF must hit the same cache entry as the target —
    the key uses ``Path.resolve()``."""
    from shared import pdf_preview_raster as raster

    link = tmp_path / "alias.pdf"
    try:
        link.symlink_to(_minimal_pdf)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported on this filesystem")

    raster.clear_pdf_raster_cache()
    raster.convert_pdf_to_images(_minimal_pdf, dpi=72)
    miss_before = raster.pdf_raster_cache_info().misses
    raster.convert_pdf_to_images(link, dpi=72)
    info = raster.pdf_raster_cache_info()
    assert info.misses == miss_before, (
        "symlink alias must hit the cache entry for its target"
    )
    assert info.hits >= 1
