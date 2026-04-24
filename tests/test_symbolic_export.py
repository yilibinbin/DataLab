"""Symbolic expression export (Phase 3 #13) — regression tests.

Allows users to "Copy as SymPy" or "Copy as Mathematica" from a
fitted formula, so they can continue the computation in their
preferred CAS. Uses DataLab's Mathematica-style input syntax
(``Sin[x]``, ``Exp[x]``) as the source and emits:

- SymPy: ``sin(x)`` / ``exp(x)`` (Python-valid, can be ``eval``'d after
  ``from sympy import *``)
- Mathematica: ``Sin[x]`` / ``Exp[x]`` (the input form is already
  Mathematica-ish; we emit a round-trip-verified canonical string)

Contract:
- Every function in DataLab's expression-engine allowlist has a known
  SymPy / Mathematica rendering. Adding a function to the allowlist
  without adding the render table entry is a test failure.
- Exports preserve semantic structure (no lossy reformatting).
- Constants ``Pi`` / ``E`` map to SymPy's ``pi`` / ``E`` and
  Mathematica's ``Pi`` / ``E``.
- Unknown identifiers raise ``ValueError`` (no silent pass-through).
"""

from __future__ import annotations

import pytest


def test_to_sympy_linear_expression():
    from fitting.symbolic_export import to_sympy

    assert to_sympy("b0 + b1*x") == "b0 + b1*x"


def test_to_sympy_with_builtin_functions():
    from fitting.symbolic_export import to_sympy

    assert to_sympy("Sin[x] + Cos[x]") == "sin(x) + cos(x)"
    assert to_sympy("Exp[x] * Log[x]") == "exp(x)*log(x)"
    assert to_sympy("Sqrt[x^2 + 1]") == "sqrt(x**2 + 1)"


def test_to_sympy_constants():
    from fitting.symbolic_export import to_sympy

    assert to_sympy("Pi*x") == "pi*x"
    assert to_sympy("E^x") == "E**x"


def test_to_sympy_nested_functions():
    from fitting.symbolic_export import to_sympy

    assert to_sympy("Sin[Cos[x]]") == "sin(cos(x))"


def test_to_sympy_rejects_unknown_identifier():
    from fitting.symbolic_export import to_sympy

    with pytest.raises(ValueError, match="Unknown"):
        to_sympy("Frobnicate[x]")


def test_to_sympy_rejects_malformed_expression():
    from fitting.symbolic_export import to_sympy

    with pytest.raises(ValueError):
        to_sympy("Sin[")  # unbalanced


def test_to_mathematica_linear():
    from fitting.symbolic_export import to_mathematica

    assert to_mathematica("b0 + b1*x") == "b0 + b1*x"


def test_to_mathematica_with_builtin_functions():
    from fitting.symbolic_export import to_mathematica

    # Input already in Mathematica form — output should round-trip
    assert to_mathematica("Sin[x] + Cos[x]") == "Sin[x] + Cos[x]"
    assert to_mathematica("Exp[x] * Log[x]") == "Exp[x]*Log[x]"


def test_to_mathematica_python_power_becomes_caret():
    """Our input accepts x^2 style; Mathematica output must use ^."""
    from fitting.symbolic_export import to_mathematica

    assert to_mathematica("x^2 + x^3") == "x^2 + x^3"


def test_to_mathematica_rejects_unknown_identifier():
    from fitting.symbolic_export import to_mathematica

    with pytest.raises(ValueError, match="Unknown"):
        to_mathematica("Frobnicate[x]")


def test_allowlist_coverage_sympy():
    """Every function in the expression engine's allowlist must have
    a SymPy rendering registered. Adding to the allowlist without
    adding the render table is a hard failure so the export
    contract stays complete."""
    from datalab_latex.expression_engine import list_allowed_functions
    from fitting.symbolic_export import SYMPY_FUNCTION_MAP

    engine_funcs = set(list_allowed_functions()["functions"])
    mapped_funcs = set(SYMPY_FUNCTION_MAP.keys())
    missing = engine_funcs - mapped_funcs
    assert not missing, (
        f"Allowlist functions missing SymPy mapping: {missing}. "
        "Add entries to fitting/symbolic_export.SYMPY_FUNCTION_MAP."
    )


def test_allowlist_coverage_mathematica():
    """Every function must be Mathematica-exportable too. Since input
    uses the same notation, the map is near-identity — but it's
    still explicit so a future lowercased function name can be
    detected and rejected."""
    from datalab_latex.expression_engine import list_allowed_functions
    from fitting.symbolic_export import MATHEMATICA_FUNCTION_MAP

    engine_funcs = set(list_allowed_functions()["functions"])
    mapped_funcs = set(MATHEMATICA_FUNCTION_MAP.keys())
    assert not (engine_funcs - mapped_funcs), (
        "Allowlist functions missing Mathematica mapping: "
        f"{engine_funcs - mapped_funcs}"
    )


def test_sympy_roundtrip_via_sympify():
    """SymPy output must actually parse via ``sympify``. Skips if
    sympy isn't installed; sympy is a gui_requirements.txt dependency
    so the CI should have it."""
    sympy = pytest.importorskip("sympy")

    from fitting.symbolic_export import to_sympy

    exprs = [
        "b0 + b1*x",
        "a*Sin[x] + b*Cos[x]",
        "Exp[x]/Sqrt[1 + x^2]",
        "Pi*x + E^x",
    ]
    for expr in exprs:
        sympy_src = to_sympy(expr)
        # Should not raise
        parsed = sympy.sympify(sympy_src)
        assert parsed is not None


def test_substituted_parameters_render():
    """When the caller has concrete parameter values (post-fit), the
    expression engine substitutes them in. Export must handle the
    resulting numeric literals cleanly."""
    from fitting.symbolic_export import to_sympy

    assert "1.5" in to_sympy("1.5*x + 2.3")
    assert "x**2" in to_sympy("x^2")


def test_empty_expression_raises():
    from fitting.symbolic_export import to_sympy

    with pytest.raises(ValueError):
        to_sympy("")
    with pytest.raises(ValueError):
        to_sympy("   ")


def test_expression_with_unicode_minus():
    """EU locale exports sometimes use U+2212 MINUS SIGN. Export must
    normalize to ASCII minus."""
    from fitting.symbolic_export import to_sympy

    assert to_sympy("x \u2212 1") == "x - 1"
