"""Batch-10 Stage 3 — thin shim composing the two split LaTeX/PDF mixins.

The original ``WindowLatexPdfMixin`` was a 969-line monolith covering two
distinct concerns: driving external LaTeX compilers (write/compile side) and
rendering the resulting PDF into the preview tab (read/display side). Stage 3
split it by responsibility into sibling files so each unit fits in a single
editor view, mirroring the proven ``window_fitting_mixin.py`` shim:

- ``window_latex_compile_mixin.py`` — ``WindowLatexCompileMixin``: open/save/
  reload editor, ``compile_latex_to_pdf`` + worker orchestration, the compile
  outcome handler, opening the compiled PDF, and LaTeX engine resolution /
  Tectonic auto-install.
- ``window_pdf_preview_mixin.py`` — ``WindowPdfPreviewMixin``: PDF zoom, base
  -image generation (pdftoppm/gs), image display, dark-mode inversion, and
  preview-tool discovery.

The composition order below pins MRO. Python resolves attribute lookups
left-to-right, so methods in the earlier mixin shadow same-named methods in the
later one. The two mixins share NO method names, so ordering is not about
shadowing — it encodes the call direction: after a successful compile,
``WindowLatexCompileMixin._on_latex_compile_completed`` calls into
``WindowPdfPreviewMixin._render_pdf_preview``. Compile drives preview, so
compile is leftmost; preview never calls back into compile.

Both mixins live INSIDE this shim's inheritance chain, so
``app_desktop/window.py`` continues to inherit only ``WindowLatexPdfMixin``.
This file remains the public entry point; existing imports
``from app_desktop.window_latex_pdf_mixin import WindowLatexPdfMixin`` keep
working unchanged.

The two LaTeX QThread workers and their helpers (moved to ``workers_qt.py`` in
the prior commit) are re-imported here so that
``from app_desktop.window_latex_pdf_mixin import _LatexCompileWorker,
_looks_like_plain_tex_output`` (test_latex_compile_worker.py) and direct
``window_latex_pdf_mixin._LatexCompileWorker(...)`` construction keep working.
``import subprocess`` is retained so the worker tests that patch
``app_desktop.window_latex_pdf_mixin.subprocess.Popen`` still resolve a
``subprocess`` attribute on this module.
"""

from __future__ import annotations

import subprocess  # noqa: F401 — patched via this module by test_latex_compile_worker.py

from .window_latex_compile_mixin import WindowLatexCompileMixin
from .window_pdf_preview_mixin import WindowPdfPreviewMixin
from .workers_qt import (  # noqa: F401 — re-exported for callers/tests
    _TECTONIC_STAGE_LABELS,
    _LatexCompileOutcome,
    _LatexCompileWorker,
    _LatexEngineRun,
    _TectonicInstallWorker,
    _looks_like_plain_tex_output,
)

__all__ = ["WindowLatexPdfMixin"]


class WindowLatexPdfMixin(WindowLatexCompileMixin, WindowPdfPreviewMixin):
    """Composed mixin delegating every method to one of the two split files.

    Defined as an empty subclass so existing imports
    (``from app_desktop.window_latex_pdf_mixin import WindowLatexPdfMixin``)
    keep working without any caller changes. MRO is pinned as
    (compile, preview): compile drives preview after a successful compile.
    """
