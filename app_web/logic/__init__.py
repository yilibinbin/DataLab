#!/usr/bin/env python3
"""Computation and formatting logic for the Flask web UI.

This package was originally a single 2 000+ line ``_legacy_impl.py``
monolith. Phase 7 finished the split and removed the dead snapshot;
the modular structure below is now the only source of truth:

- ``common``           form parsing, formatting, CSV helpers
- ``extrapolation``    extrapolation pipeline
- ``error_propagation`` error propagation pipeline
- ``fitting``          dataset fitting pipeline
- ``statistics``       statistical aggregation pipeline
- ``plots``            matplotlib render helpers

Route handlers should import from ``app_web.logic`` (this facade)
to keep ``create_app()`` small.
"""

from __future__ import annotations

from importlib import import_module
import sys
from pathlib import Path

# Ensure project root is importable when the module is executed directly.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_EXPORT_MODULES = {
    "ErrorPropagationBundle": "error_propagation",
    "ExtrapolationResultBundle": "extrapolation",
    "FitResultBundle": "fitting",
    "StatsResultBundle": "statistics",
    "_encode_b64": "common",
    "_extract_data_text": "common",
    "_extract_named_text": "common",
    "_format_number": "common",
    "_format_rows": "common",
    "_format_uncertain_value": "error_propagation",
    "_format_uncertainty_rows": "error_propagation",
    "_format_with_precision": "common",
    "_generate_csv_from_rows": "common",
    "_generate_fitting_latex": "fitting",
    "_is_checked": "common",
    "_latex_to_plain": "common",
    "_norm_token": "common",
    "_parse_fit_data": "fitting",
    "_parse_float": "common",
    "_parse_int": "common",
    "_parse_stats_data": "statistics",
    "_render_contribution_plot": "plots",
    "_render_extrapolation_plot": "plots",
    "_render_statistics_plot": "plots",
    "_run_error_propagation": "error_propagation",
    "_run_extrapolation": "extrapolation",
    "_run_fit": "fitting",
    "_run_statistics": "statistics",
    "_split_result": "common",
}

__all__ = list(_EXPORT_MODULES)


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
