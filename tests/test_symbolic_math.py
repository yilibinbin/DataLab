from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest
import sympy as sp

from shared.symbolic_math import build_sympy_local_dict, parse_symbolic_expression


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
