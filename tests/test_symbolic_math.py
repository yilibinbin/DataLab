from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
import sympy as sp

from datalab_latex.expression_engine import list_allowed_functions, safe_eval
from shared.symbolic_math import SYMPY_CONSTANTS, SYMPY_FUNCTIONS, build_sympy_local_dict, parse_symbolic_expression


def test_parse_symbolic_expression_supports_numeric_literals_and_xor() -> None:
    expr, symbols = parse_symbolic_expression("2^3 + 1/2 + 0.25", variables=())

    assert expr == sp.Pow(2, 3) + sp.Rational(1, 2) + sp.Float("0.25")
    assert symbols == {}


def test_parse_symbolic_expression_returns_all_declared_symbols() -> None:
    x = sp.Symbol("x")
    y = sp.Symbol("y")

    expr, symbols = parse_symbolic_expression("x + 1", variables=("x", "y"))

    assert expr == x + 1
    assert symbols == {"x": x, "y": y}


def test_parse_symbolic_expression_supports_mathematica_functions() -> None:
    x = sp.Symbol("x")

    expr, symbols = parse_symbolic_expression("Sin[x] + Ln[x] + Log10[x]", variables=("x",))

    assert expr == sp.sin(x) + sp.log(x) + sp.log(x, 10)
    assert symbols == {"x": x}


def test_parse_symbolic_expression_supports_runtime_formula_constants() -> None:
    x = sp.Symbol("x")

    expr, symbols = parse_symbolic_expression("Pi + E + Sin[x]", variables=("x",))

    assert expr == sp.pi + sp.E + sp.sin(x)
    assert symbols == {"x": x}


def test_parse_symbolic_expression_rejects_lowercase_runtime_function_aliases() -> None:
    with pytest.raises(ValueError, match="Unsupported symbolic function call"):
        parse_symbolic_expression("sin[x]", variables=("x",))


def test_parse_symbolic_expression_rejects_unknown_function_names() -> None:
    with pytest.raises(ValueError, match="Unsupported symbolic function call"):
        parse_symbolic_expression("Known + UnknownName[1]", variables=("Known",))


def test_parse_symbolic_expression_rejects_python_attribute_access() -> None:
    with pytest.raises(ValueError, match="Unsupported symbolic expression syntax"):
        parse_symbolic_expression("().__class__.__base__.__subclasses__()", variables=())


def test_parse_symbolic_expression_rejects_subscript_access() -> None:
    with pytest.raises(ValueError, match="Unsupported symbolic function call"):
        parse_symbolic_expression("x[0]", variables=("x",))


def test_parse_symbolic_expression_rejects_keyword_arguments() -> None:
    with pytest.raises(ValueError, match="Keyword arguments"):
        parse_symbolic_expression("Sin(x=1)", variables=("x",))


def test_parse_symbolic_expression_rejects_non_name_call_target() -> None:
    with pytest.raises(ValueError, match="Unsupported symbolic expression syntax"):
        parse_symbolic_expression("Sin(1)(2)", variables=())


def test_parse_symbolic_expression_rejects_dunder_names() -> None:
    with pytest.raises(ValueError, match="Unsupported symbolic expression name"):
        parse_symbolic_expression("__import__ + x", variables=("x",))


def test_parse_symbolic_expression_rejects_non_expression_literals() -> None:
    with pytest.raises(ValueError, match="Unsupported symbolic expression syntax"):
        parse_symbolic_expression("(1, 2)", variables=())


def test_parse_symbolic_expression_preserves_unknown_bare_symbols_for_derivative_compatibility() -> None:
    x = sp.Symbol("x")

    expr, symbols = parse_symbolic_expression("x + c", variables=("x",))

    assert expr == x + sp.Symbol("c")
    assert symbols == {"x": x}


def test_build_sympy_local_dict_uses_exact_parser_registry() -> None:
    symbols, local_dict = build_sympy_local_dict(["x", "Pi"])

    assert symbols == [sp.Symbol("x"), sp.Symbol("Pi")]
    assert local_dict["x"] == sp.Symbol("x")
    assert local_dict["Pi"] == sp.Symbol("Pi")
    assert local_dict["Sin"] is sp.sin
    assert local_dict["Ln"] is sp.log
    log10 = cast(Callable[[object], object], local_dict["Log10"])
    assert callable(log10)
    assert str(log10("x")) == "log(x)/log(10)"


def test_symbolic_registry_tracks_runtime_safe_eval_allowlist_names() -> None:
    runtime = list_allowed_functions()

    assert set(SYMPY_FUNCTIONS) == set(runtime["functions"])
    assert set(SYMPY_CONSTANTS) == set(runtime["constants"])


@pytest.mark.parametrize(
    "expression",
    [
        "Sin[x] + Pi + E",
        "Sqrt[x^2] + Log10[100]",
    ],
)
def test_symbolic_parser_and_safe_eval_accept_same_capitalized_formula_contract(expression: str) -> None:
    parse_symbolic_expression(expression, variables=("x",))
    safe_eval(expression, {"x": 2})


@pytest.mark.parametrize("expression", ["sin[x]", "cos[x]", "sqrt[x]"])
def test_symbolic_parser_and_safe_eval_reject_same_lowercase_function_contract(expression: str) -> None:
    with pytest.raises(ValueError):
        parse_symbolic_expression(expression, variables=("x",))
    with pytest.raises(ValueError):
        safe_eval(expression, {"x": 2})


def test_implicit_detectors_use_shared_symbolic_parser_boundary() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    detector_paths = [
        repo_root / "fitting" / "implicit_transforms.py",
        repo_root / "fitting" / "implicit_seed_hints.py",
        repo_root / "fitting" / "implicit_derivatives.py",
    ]
    forbidden_imports = {
        "sympy.parsing.sympy_parser",
        "shared.symbolic_math.SYMPY_FUNCTIONS",
        "shared.symbolic_math.SYMPY_CONSTANTS",
        "shared.symbolic_math.build_sympy_local_dict",
    }
    for path in detector_paths:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_shared_parser = False
        sympy_aliases: set[str] = {"sympy"}
        for node in ast.walk(module):
            if isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                imported = {alias.name for alias in node.names}
                assert module_name not in forbidden_imports
                if module_name == "sympy" and imported.intersection({"parse_expr", "sympify"}):
                    raise AssertionError(f"{path.name} must not import SymPy parser helpers directly")
                if module_name == "shared.symbolic_math":
                    assert imported == {"parse_symbolic_expression"}
                if module_name == "shared" and "symbolic_math" in imported:
                    raise AssertionError(f"{path.name} must not import shared.symbolic_math as a module alias")
                assert not {f"{module_name}.{name}" for name in imported}.intersection(forbidden_imports)
                if module_name == "shared.symbolic_math" and "parse_symbolic_expression" in imported:
                    imported_shared_parser = True
            elif isinstance(node, ast.Import):
                imported_modules = {alias.name for alias in node.names}
                if {"shared", "shared.symbolic_math"}.intersection(imported_modules):
                    raise AssertionError(f"{path.name} must not import shared or shared.symbolic_math as a module alias")
                sympy_aliases.update(alias.asname or alias.name for alias in node.names if alias.name == "sympy")
                assert not imported_modules.intersection(forbidden_imports)
            elif isinstance(node, ast.Attribute):
                dotted = _attribute_name(node)
                if dotted in {
                    "shared.symbolic_math.SYMPY_FUNCTIONS",
                    "shared.symbolic_math.SYMPY_CONSTANTS",
                    "shared.symbolic_math.build_sympy_local_dict",
                }:
                    raise AssertionError(f"{path.name} must not access shared symbolic registry attributes directly")
                if _is_sympy_parser_attribute(dotted, sympy_aliases):
                    raise AssertionError(f"{path.name} must not bypass shared symbolic parsing with {dotted}")
        assert imported_shared_parser, f"{path.name} must parse formulas through shared.symbolic_math"


def _attribute_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _is_sympy_parser_attribute(dotted: str | None, aliases: set[str]) -> bool:
    if dotted is None:
        return False
    return any(
        dotted
        in {
            f"{alias}.parse_expr",
            f"{alias}.sympify",
            f"{alias}.parsing.sympy_parser.parse_expr",
            f"{alias}.parsing.sympy_parser.sympify",
        }
        for alias in aliases
    )
