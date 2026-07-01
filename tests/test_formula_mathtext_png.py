import subprocess
import sys

from shared.formula_mathtext_png import render_mathtext_png


def test_render_mathtext_png_does_not_eagerly_import_matplotlib() -> None:
    """Ensure that importing the module does not import matplotlib."""
    code = (
        "import sys\n"
        "from shared.formula_mathtext_png import render_mathtext_png\n"
        "assert 'matplotlib' not in sys.modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"Import purity failed: {result.stderr}"


def test_render_mathtext_png_output_bytes() -> None:
    png_bytes = render_mathtext_png(r"E=mc^2", dpi=100, color="black")
    assert png_bytes.startswith(b"\x89PNG")


def test_render_mathtext_png_renders_cjk_without_missing_glyphs() -> None:
    """A Chinese-named formula (\\text{...}) must render with the CJK font, not
    substitute tofu boxes. matplotlib reports missing glyphs via its *logging*
    (not warnings) and this module builds a bare Figure that does not inherit
    shared.plotting's CJK rcParams, so run in a fresh subprocess (shared.plotting
    NOT preloaded) and assert no "does not have a glyph" appears on stderr.

    CJK support is best-effort: on a host with no CJK-capable font (e.g. a
    minimal CI image) the feature legitimately cannot render Chinese, so skip
    rather than fail — matching the other CJK-dependent tests.
    """
    import pytest

    from shared.plotting import cjk_font_family

    if cjk_font_family() is None:
        pytest.skip("no CJK-capable font available on this host")

    code = (
        "import sys\n"
        "from shared.formula_mathtext_png import render_mathtext_png\n"
        "assert 'shared.plotting' not in sys.modules\n"
        "b = render_mathtext_png(r'$\\text{质量} \\cdot \\text{加速度}$', dpi=100, color='black')\n"
        "assert b.startswith(b'\\x89PNG')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "does not have a glyph" not in result.stderr, result.stderr
