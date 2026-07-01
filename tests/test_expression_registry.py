from __future__ import annotations

import subprocess
import sys


def test_expression_registry_and_names_import_stay_lightweight() -> None:
    script = r"""
import sys

import shared.expression_registry
import shared.expression_names

forbidden_prefixes = (
    "PySide6",
    "matplotlib",
    "data_extrapolation_latex_latest",
    "datalab_latex",
    "fitting",
    "mpmath",
    "sympy",
)
forbidden = sorted(
    name
    for name in sys.modules
    if any(name == prefix or name.startswith(prefix + ".") for prefix in forbidden_prefixes)
)
if forbidden:
    raise SystemExit("forbidden imports: " + ", ".join(forbidden))
print("ok")
"""

    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )

    assert completed.stdout.strip() == "ok"


def test_expression_registry_names_match_all_consumers() -> None:
    from datalab_latex.expression_engine import list_allowed_functions as latex_allowed
    from fitting import model_parser
    from fitting import symbolic_export
    from shared import expression_names
    from shared.expression_engine import list_allowed_functions as shared_allowed
    from shared.expression_registry import (
        allowed_constant_names,
        allowed_function_names,
        reserved_expression_names,
    )

    functions = list(allowed_function_names())
    constants = list(allowed_constant_names())
    expected_reserved = {name.lower() for name in (*functions, *constants)}

    assert functions[:3] == ["Sin", "Cos", "Tan"]
    assert constants == ["Pi", "E"]
    assert set(shared_allowed()["functions"]) == set(functions)
    assert set(latex_allowed()["functions"]) == set(functions)
    assert set(shared_allowed()["constants"]) == set(constants)
    assert set(latex_allowed()["constants"]) == set(constants)
    assert shared_allowed() == latex_allowed()
    assert expression_names.reserved_expression_names() == expected_reserved
    assert model_parser.reserved_expression_names() == expected_reserved
    assert set(symbolic_export.SYMPY_FUNCTION_MAP) == set(functions)
    assert set(symbolic_export.MATHEMATICA_FUNCTION_MAP) == set(functions)
    assert set(symbolic_export.allowed_export_names()) == set(functions) | set(constants)
    assert reserved_expression_names() == expected_reserved


def test_expression_registry_normalization_matches_consumers() -> None:
    from datalab_latex.expression_engine import _normalize_expression as latex_normalize
    from fitting.symbolic_export import _normalize_for_parse, to_sympy
    from shared.expression_engine import _normalize_expression as shared_normalize
    from shared.expression_registry import normalize_expression
    from shared.formula_latex_export import expression_to_latex, normalize_expression as latex_export_normalize

    source = "Sin[x]^2 + Sqrt[A]"
    expected = "Sin(x)**2 + Sqrt(A)"

    assert normalize_expression(source) == expected
    assert shared_normalize(source) == expected
    assert latex_normalize(source) == expected
    assert _normalize_for_parse(source) == expected
    assert latex_export_normalize(source) == expected
    assert to_sympy(source) == "sin(x)**2 + sqrt(A)"
    assert expression_to_latex(source) == r"\sin\left(x\right)^{2} + \sqrt{A}"


def test_latex_engine_is_a_shim_over_the_shared_engine() -> None:
    # P0-3: the two safe-eval engines were collapsed to one. The LaTeX-facing
    # module must now re-export the *same objects* from shared.expression_engine
    # (not a copy), so an allowlist change can never drift between the two.
    import datalab_latex.expression_engine as latex_engine
    import shared.expression_engine as shared_engine

    for name in (
        "safe_eval",
        "list_allowed_functions",
        "_ALLOWED_FUNCTIONS",
        "_ALLOWED_CONSTANTS",
        "_normalize_expression",
        "_ast_metrics",
        "_detect_lowercase_allowed_function_calls",
        "MAX_AST_DEPTH",
        "MAX_AST_NODES",
    ):
        assert getattr(latex_engine, name) is getattr(shared_engine, name), name

    # The one deliberate difference: LaTeX rendering routes through the render
    # service, while the shared engine stays LaTeX-independent (passthrough).
    assert latex_engine.format_latex_formula is not shared_engine.format_latex_formula
    assert latex_engine.format_latex_formula("sin(x)+a*x^2").strip()
    assert shared_engine.format_latex_formula("sin(x)+a*x^2") == "sin(x)+a*x^2"


def test_lowercase_allowed_function_call_detection_matches_engines() -> None:
    from datalab_latex.expression_engine import _detect_lowercase_allowed_function_calls as latex_detect
    from shared.expression_engine import _detect_lowercase_allowed_function_calls as shared_detect
    from shared.expression_registry import detect_lowercase_allowed_function_calls

    source = "sin[x] + cos(x) + custom(x) + Log[x]"
    expected = {"sin", "cos"}

    assert detect_lowercase_allowed_function_calls(source) == expected
    assert shared_detect(source) == expected
    assert latex_detect(source) == expected
