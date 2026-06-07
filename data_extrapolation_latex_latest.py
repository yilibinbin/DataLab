#!/usr/bin/env python3
"""
Backwards-compatible public entrypoint for DataLab's LaTeX/extrapolation core.

The implementation has been moved into the `datalab_latex` package. This module
remains as a thin re-exporting shim to avoid breaking existing imports.
"""

from __future__ import annotations

from datalab_latex import (
    derivatives as _derivatives,
    expression_engine as _expression_engine,
    latex_formatting as _latex_formatting,
    latex_tables as _latex_tables,
    latex_tables_common as _tables_common,
    latex_tables_error_propagation as _tables_error,
    latex_tables_extrapolation as _tables_extrapolation,
)
from datalab_latex.latex_tables_extrapolation import (
    DEFAULT_THREE_POINT_FORMULA as DEFAULT_THREE_POINT_FORMULA,
)

# Re-export everything (including historically-imported private helpers).
#
# Order matters: later modules override earlier names, matching the original
# `datalab_latex.latex_tables` re-export order.
for _module in (
    _tables_common,
    _tables_extrapolation,
    _tables_error,
    _derivatives,
    _expression_engine,
    _latex_formatting,
):
    for _name, _value in _module.__dict__.items():
        if _name.startswith("__"):
            continue
        globals()[_name] = _value

del _module, _name, _value


def main() -> int:
    return int(_latex_tables.main())


if __name__ == "__main__":
    raise SystemExit(main())
