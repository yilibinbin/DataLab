"""Single canonical entry point for DataLab's matplotlib configuration.

Every module that uses matplotlib MUST import ``plt`` from this
module rather than calling ``matplotlib.use(...)`` locally:

    from shared.plotting import plt, rcParams  # RIGHT

    import matplotlib                           # WRONG (do not pattern this)
    matplotlib.use("Agg")

Rationale: ``matplotlib.use`` only works before the first pyplot
import. Scattering ``matplotlib.use`` calls across 8 modules creates
an order-of-import hazard — the first module to import pyplot
wins, and the later ``use`` calls emit a warning and are silently
ignored. Centralising here makes backend + rcParams config a single
source of truth.

Invariants enforced:
- Backend is ``Agg``. Thread-safe + headless + no GUI toolkit
  dependency. DataLab intentionally renders PNG bytes → QPixmap (for
  desktop) or sends raw bytes (for web), so no interactive backend
  is wanted.
- CJK fallback font list is applied at import time — Chinese / Japanese
  / Korean labels in plots render consistently across platforms.
- ``axes.unicode_minus = False`` — plots use ASCII minus so LaTeX
  export and siunitx stay happy.

A regression test (``tests/test_plotting_backend.py``) asserts the
backend is Agg after importing an arbitrary business module, so a
future commit that calls ``matplotlib.use("QtAgg")`` at module
scope fails loudly.
"""

from __future__ import annotations

import matplotlib as _matplotlib

# Lock the backend BEFORE any submodule imports pyplot. The string
# "Agg" is the thread-safe headless raster backend — do not change
# without re-testing the worker threads (Qt + matplotlib interaction
# is notoriously finicky when non-Agg backends are in use).
_matplotlib.use("Agg")

from matplotlib import rcParams  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

__all__ = ["plt", "rcParams", "matplotlib", "assert_agg_backend"]

# Re-export for callers that need access beyond plt/rcParams.
matplotlib = _matplotlib

# CJK fallback font list — applied at import time so every figure
# created anywhere in DataLab inherits it. Order matters: the first
# family present on the host wins.
rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = [
    "Arial Unicode MS",
    "Microsoft YaHei",
    "PingFang SC",
    "Hiragino Sans GB",
    "Heiti TC",
    "SimHei",
    "Noto Sans CJK SC",
    "WenQuanYi Micro Hei",
    "DejaVu Sans",
]
# Axis labels must use ASCII minus so downstream LaTeX export with
# siunitx doesn't see U+2212 and emit a "Missing $ inserted" error.
rcParams["axes.unicode_minus"] = False


def assert_agg_backend() -> None:
    """Verify the current backend is Agg. Called from regression tests
    to make a backend drift visible at test time rather than at user-
    visible crash time (e.g., a headless CI with Qt backend selected
    would succeed locally but fail in CI)."""
    current = _matplotlib.get_backend().lower()
    if current != "agg":
        raise RuntimeError(
            f"matplotlib backend drifted to {current!r}; expected 'agg'. "
            "Check that every module importing pyplot routes through "
            "shared.plotting."
        )
