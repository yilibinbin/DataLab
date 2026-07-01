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
