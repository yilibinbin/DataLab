"""Pure functional mathtext PNG rendering primitive."""

import io


def render_mathtext_png(mathtext: str, *, dpi: int, color: str) -> bytes:
    """Render a LaTeX formula string to a PNG image using matplotlib's mathtext."""
    import matplotlib

    matplotlib.use("Agg", force=False)
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    figure = Figure(figsize=(0.01, 0.01), dpi=dpi)
    figure.patch.set_alpha(0.0)
    FigureCanvasAgg(figure)
    figure.text(0.0, 0.5, mathtext, fontsize=21, va="center", ha="left", color=color)
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight", pad_inches=0.06)
    return buffer.getvalue()
