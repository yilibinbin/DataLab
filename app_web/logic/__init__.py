#!/usr/bin/env python3
"""Computation and formatting logic for the Flask web UI.

This package is a compatibility facade. Heavy computation lives in submodules:

- `common`: form parsing, formatting, CSV helpers
- `extrapolation`: extrapolation pipeline
- `error_propagation`: error propagation pipeline
- `fitting`: dataset fitting pipeline
- `statistics`: statistical aggregation pipeline
- `plots`: matplotlib render helpers

Route handlers should import from `app_web.logic` to keep `create_app()` small.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable when the module is executed directly.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from .common import (  # noqa: E402,F401
    _encode_b64,
    _extract_data_text,
    _extract_named_text,
    _format_number,
    _format_rows,
    _format_with_precision,
    _generate_csv_from_rows,
    _is_checked,
    _latex_to_plain,
    _norm_token,
    _parse_float,
    _parse_int,
    _split_result,
)
from .error_propagation import (  # noqa: E402,F401
    ErrorPropagationBundle,
    _format_uncertain_value,
    _format_uncertainty_rows,
    _run_error_propagation,
)
from .extrapolation import (  # noqa: E402,F401
    ExtrapolationResultBundle,
    _run_extrapolation,
)
from .fitting import (  # noqa: E402,F401
    FitResultBundle,
    _generate_fitting_latex,
    _parse_fit_data,
    _run_fit,
)
from .plots import (  # noqa: E402,F401
    _render_contribution_plot,
    _render_extrapolation_plot,
    _render_statistics_plot,
)
from .statistics import (  # noqa: E402,F401
    StatsResultBundle,
    _parse_stats_data,
    _run_statistics,
)

__all__ = [
    "ROOT",
    "ErrorPropagationBundle",
    "ExtrapolationResultBundle",
    "FitResultBundle",
    "StatsResultBundle",
    "_encode_b64",
    "_extract_data_text",
    "_extract_named_text",
    "_format_number",
    "_format_rows",
    "_format_uncertain_value",
    "_format_uncertainty_rows",
    "_format_with_precision",
    "_generate_csv_from_rows",
    "_generate_fitting_latex",
    "_is_checked",
    "_latex_to_plain",
    "_norm_token",
    "_parse_fit_data",
    "_parse_float",
    "_parse_int",
    "_parse_stats_data",
    "_render_contribution_plot",
    "_render_extrapolation_plot",
    "_render_statistics_plot",
    "_run_error_propagation",
    "_run_extrapolation",
    "_run_fit",
    "_run_statistics",
    "_split_result",
]

