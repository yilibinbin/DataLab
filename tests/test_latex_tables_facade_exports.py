from __future__ import annotations

import datalab_latex.latex_tables as latex_tables
import datalab_latex.latex_tables_error_propagation as _err_mod
import datalab_latex.latex_tables_extrapolation as _extrap_mod

import data_extrapolation_latex_latest as shim


def test_latex_tables_facade_exports_are_restricted():
    assert not hasattr(latex_tables, "_normalize_input_lines")
    assert hasattr(latex_tables, "generate_latex_table")
    assert hasattr(latex_tables, "generate_error_propagation_table")
    assert hasattr(latex_tables, "__all__")
    assert all(not name.startswith("_") for name in latex_tables.__all__)


def test_latex_tables_facade_reexports_match_canonical_modules() -> None:
    """Phase 7 #23 batch 4 replaced the dynamic ``_reexport_public()``
    helper with ``from … import *``. Verify every name in the
    submodules' ``__all__`` is present on the façade AND points to
    the SAME function object (not a stale copy or wrapper).
    """
    for name in _extrap_mod.__all__:
        assert hasattr(latex_tables, name), (
            f"latex_tables missing re-exported name {name!r} from "
            "latex_tables_extrapolation"
        )
        assert getattr(latex_tables, name) is getattr(_extrap_mod, name), (
            f"latex_tables.{name} is not the same object as "
            f"latex_tables_extrapolation.{name} — re-export is stale"
        )

    for name in _err_mod.__all__:
        assert hasattr(latex_tables, name), (
            f"latex_tables missing re-exported name {name!r} from "
            "latex_tables_error_propagation"
        )
        assert getattr(latex_tables, name) is getattr(_err_mod, name), (
            f"latex_tables.{name} is not the same object as "
            f"latex_tables_error_propagation.{name} — re-export is stale"
        )


def test_latex_tables_facade_all_aggregates_both_submodules() -> None:
    """``latex_tables.__all__`` must be the union of both submodules'
    ``__all__`` lists, in source order (extrapolation first, error
    propagation second). Pins the aggregation logic so a refactor
    that drops one source silently won't pass."""
    expected = list(_extrap_mod.__all__) + list(_err_mod.__all__)
    assert list(latex_tables.__all__) == expected


def test_latex_latest_shim_keeps_private_helpers():
    assert hasattr(shim, "_dual_msg")
    assert hasattr(shim, "_precision_guard")
    assert hasattr(shim, "_expand_scientific_brackets_to_fixed")
