"""Pure functional mathtext PNG rendering primitive."""

import io


def render_mathtext_png(mathtext: str, *, dpi: int, color: str) -> bytes:
    """Render a LaTeX formula string to a PNG image using matplotlib's mathtext."""
    # Import through shared.plotting (lazily, to keep this module's *import*
    # matplotlib-free — see test_render_mathtext_png_does_not_eagerly_import).
    # shared.plotting configures the Agg backend AND the CJK-aware mathtext font
    # set at import, so a formula containing Chinese renders with real glyphs
    # instead of tofu boxes. Fall back to a bare matplotlib import if that
    # centralized module is unavailable for any reason.
    try:
        from shared.plotting import matplotlib
    except Exception:  # noqa: BLE001 - CJK mathtext support is best-effort
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
