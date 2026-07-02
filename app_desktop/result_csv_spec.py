"""Single source of truth for each result kind's CSV base headers + export
filename.

Both the first-render path (the ``_show_*_results`` methods in the
``window_*_mixin`` files) and the reformat path
(``ExtrapolationWindow._refresh_display_format``) read from here, so a
header/filename change is made once and can't drift between the two paths
(audit R3 — the same header literals + filenames were duplicated 2-4x).

Kinds whose CSV headers are computed dynamically are intentionally absent:
- ``error`` appends ``output_unit`` when a unit is present;
- ``statistics`` may append ``value_unit``/``uncertainty_unit`` columns;
- snapshot-based kinds (statistics_matrix/bootstrap/hypothesis/time_series/
  grouped, fitting_comparison) derive their headers from the rendered snapshot.

This is a leaf module (no ``app_desktop`` imports) so both ``window.py`` and the
mixins it composes can import it without a circular dependency.
"""

from __future__ import annotations

_RESULT_CSV_SPEC: dict[str, tuple[tuple[str, ...], str]] = {
    "extrapolation": (("index", "value", "uncertainty", "latex"), "extrapolation_results.csv"),
    "statistics": (("batch", "metric", "value", "uncertainty"), "statistics_results.csv"),
    "fit_single": (
        ("batch", "section", "name", "value", "uncertainty", "stat_error", "sys_error", "note"),
        "fitting_results.csv",
    ),
}


def result_csv_headers(kind: str) -> list[str]:
    """Base CSV headers for a result kind (fresh mutable copy, so callers may
    extend it with dynamic unit columns)."""
    return list(_RESULT_CSV_SPEC[kind][0])


def result_csv_filename(kind: str) -> str:
    """Suggested export filename for a result kind."""
    return _RESULT_CSV_SPEC[kind][1]
