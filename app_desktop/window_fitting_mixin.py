"""Phase 7 #19 — thin shim composing the 4 split fitting mixins.

The original ``WindowFittingMixin`` was a 1852-line monolith
covering parameter editing, model dispatch, worker orchestration,
result rendering, residual plotting, and LaTeX output. Phase 7
split it by responsibility into sibling files so each unit fits
in a single editor view (~200-700 lines):

- ``window_fitting_formatters_mixin.py`` — pure(-ish) formatters
  used by every other concern (substituted-expression rendering,
  result text, CSV row builder, LaTeX preamble + table block).
- ``window_fitting_residuals_mixin.py`` — post-compute side:
  worker-result handlers, fit-plot rendering, residual-diff view,
  LaTeX file output, batch-result re-formatting.
- ``window_fitting_models_mixin.py`` — pre-compute / dispatch
  side: every fit-mode execution path (custom, polynomial,
  inverse, Padé, power-limit, self-consistent), worker thread setup, and
  the ``_run_fitting_mode`` dispatcher.

The composition order below pins MRO. Python resolves attribute
lookups left-to-right, so methods defined in earlier mixins
shadow same-named methods in later ones. The order mirrors the
natural call flow (left = "called more often", right = "called by
others"):

  Residuals    (calls Formatters for display)
  Models       (calls Formatters)
  Formatters   (called by both above; rightmost so a future
                  override in either of the above can shadow a formatter
                  cleanly — none do today)

All three mixins live INSIDE this shim's inheritance chain, so
``app_desktop/window.py`` continues to inherit only
``WindowFittingMixin``. This file remains the public entry point;
existing imports
``from app_desktop.window_fitting_mixin import WindowFittingMixin``
keep working unchanged.
"""
from __future__ import annotations

from .window_fitting_formatters_mixin import WindowFittingFormattersMixin
from .window_fitting_models_mixin import WindowFittingModelsMixin
from .window_fitting_residuals_mixin import WindowFittingResidualsMixin

__all__ = ["WindowFittingMixin"]


class WindowFittingMixin(
    WindowFittingResidualsMixin,
    WindowFittingModelsMixin,
    WindowFittingFormattersMixin,
):
    """Composed mixin that delegates every method to one of the
    split files. Defined as an empty subclass so existing
    imports (``from app_desktop.window_fitting_mixin import
    WindowFittingMixin``) keep working without any caller changes.
    """

    def _on_fit_finished(self, payload):
        if super()._on_fit_finished(payload) is False:
            return
        details = getattr(payload.fit_result, "details", {}) or {}
        if details.get("fallback_history"):
            self.statusBar().showMessage(
                self._tr("已回退到高精度求解器。", "Fell back to high-precision solver."),
                8000,
            )
