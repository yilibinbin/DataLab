from __future__ import annotations

import ast
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction

from .expression_registry import allowed_constant_names, normalize_expression


class UnitExpressionError(ValueError):
    """Raised when expression dimensional validation fails closed."""


@dataclass(frozen=True)
class UnitDimension:
    factors: tuple[tuple[str, Fraction], ...] = ()

    @classmethod
    def unitless(cls) -> "UnitDimension":
        return cls(())

    @classmethod
    def from_factors(cls, factors: Mapping[str, Fraction]) -> "UnitDimension":
        return cls(tuple(sorted((unit, power) for unit, power in factors.items() if power)))

    def is_unitless(self) -> bool:
        return not self.factors

    def is_exact_unit(self, unit: str) -> bool:
        return self == parse_unit_dimension(unit)

    def multiply(self, other: "UnitDimension") -> "UnitDimension":
        merged = dict(self.factors)
        for unit, power in other.factors:
            merged[unit] = merged.get(unit, Fraction(0)) + power
        return UnitDimension.from_factors(merged)

    def divide(self, other: "UnitDimension") -> "UnitDimension":
        merged = dict(self.factors)
        for unit, power in other.factors:
            merged[unit] = merged.get(unit, Fraction(0)) - power
        return UnitDimension.from_factors(merged)

    def power(self, exponent: Fraction) -> "UnitDimension":
        return UnitDimension.from_factors({unit: power * exponent for unit, power in self.factors})

    def to_text(self) -> str:
        if not self.factors:
            return "1"
        numerator: list[str] = []
        denominator: list[str] = []
        for unit, power in self.factors:
            target = numerator if power > 0 else denominator
            target.append(_unit_power_text(unit, abs(power)))
        numerator_text = "*".join(numerator) if numerator else "1"
        if not denominator:
            return numerator_text
        denominator_text = "*".join(denominator)
        if len(denominator) > 1:
            denominator_text = f"({denominator_text})"
        return f"{numerator_text}/{denominator_text}"


def validate_expression_units(
    expression: str,
    symbol_units: Mapping[str, str | UnitDimension],
    *,
    output_unit: str | UnitDimension | None = None,
) -> UnitDimension:
    """Validate and infer exact units for a DataLab expression."""

    if not isinstance(expression, str) or not expression.strip():
        raise UnitExpressionError("expression must be a non-empty string")
    parsed_symbol_units = {
        str(name): unit if isinstance(unit, UnitDimension) else parse_unit_dimension(str(unit))
        for name, unit in symbol_units.items()
    }
    try:
        tree = ast.parse(normalize_expression(expression), mode="eval")
    except (SyntaxError, RecursionError, MemoryError) as exc:
        raise UnitExpressionError(f"failed to parse expression: {exc}") from exc
    inferred = _infer_node_unit(tree.body, parsed_symbol_units)
    if output_unit is not None:
        expected = output_unit if isinstance(output_unit, UnitDimension) else parse_unit_dimension(str(output_unit))
        if inferred != expected:
            raise UnitExpressionError(
                f"expression unit {inferred.to_text()} does not match declared output unit {expected.to_text()}"
            )
    return inferred


def parse_unit_dimension(unit_text: str | None) -> UnitDimension:
    text = str(unit_text or "").strip()
    if text in {"", "1", "unitless", "dimensionless"}:
        return UnitDimension.unitless()
    parser = _UnitParser(text)
    dimension = parser.parse()
    if parser.has_remaining_tokens():
        raise UnitExpressionError(f"could not parse unit text: {text!r}")
    return dimension


def _infer_node_unit(node: ast.AST, symbol_units: Mapping[str, UnitDimension]) -> UnitDimension:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, int | float):
            raise UnitExpressionError("unsupported expression constant")
        return UnitDimension.unitless()
    if isinstance(node, ast.Name):
        if node.id in allowed_constant_names():
            return UnitDimension.unitless()
        if node.id in symbol_units:
            return symbol_units[node.id]
        raise UnitExpressionError(f"unknown expression symbol: {node.id}")
    if isinstance(node, ast.UnaryOp):
        if not isinstance(node.op, ast.UAdd | ast.USub):
            raise UnitExpressionError("unsupported unary operator")
        return _infer_node_unit(node.operand, symbol_units)
    if isinstance(node, ast.BinOp):
        return _infer_binary_unit(node, symbol_units)
    if isinstance(node, ast.Call):
        return _infer_call_unit(node, symbol_units)
    raise UnitExpressionError(f"unsupported expression syntax: {type(node).__name__}")


def _infer_binary_unit(node: ast.BinOp, symbol_units: Mapping[str, UnitDimension]) -> UnitDimension:
    left = _infer_node_unit(node.left, symbol_units)
    right = _infer_node_unit(node.right, symbol_units)
    if isinstance(node.op, ast.Add | ast.Sub):
        if left != right:
            raise UnitExpressionError(f"add/subtract require identical units: {left.to_text()} vs {right.to_text()}")
        return left
    if isinstance(node.op, ast.Mult):
        return left.multiply(right)
    if isinstance(node.op, ast.Div):
        return left.divide(right)
    if isinstance(node.op, ast.Pow):
        exponent = _literal_numeric_exponent(node.right)
        return left.power(exponent)
    raise UnitExpressionError("unsupported binary operator")


def _infer_call_unit(node: ast.Call, symbol_units: Mapping[str, UnitDimension]) -> UnitDimension:
    if node.keywords:
        raise UnitExpressionError("keyword arguments are not supported")
    if not isinstance(node.func, ast.Name):
        raise UnitExpressionError("unsupported function expression")
    name = node.func.id
    args = [_infer_node_unit(arg, symbol_units) for arg in node.args]
    if name in {"Exp", "Log", "Ln", "Log10"}:
        _require_arg_count(name, args, 1)
        _require_unitless(args[0], name)
        return UnitDimension.unitless()
    if name in {"Sin", "Cos", "Tan"}:
        _require_arg_count(name, args, 1)
        if not (args[0].is_unitless() or args[0].is_exact_unit("rad")):
            raise UnitExpressionError(f"{name} requires unitless or rad input")
        return UnitDimension.unitless()
    if name in {"Asin", "Acos", "Atan"}:
        _require_arg_count(name, args, 1)
        _require_unitless(args[0], name)
        return parse_unit_dimension("rad")
    if name == "Sqrt":
        _require_arg_count(name, args, 1)
        return args[0].power(Fraction(1, 2))
    if name == "Power":
        if len(node.args) != 2:
            raise UnitExpressionError("Power requires exactly two arguments")
        base = _infer_node_unit(node.args[0], symbol_units)
        return base.power(_literal_numeric_exponent(node.args[1]))
    if name == "Abs":
        _require_arg_count(name, args, 1)
        return args[0]
    raise UnitExpressionError(f"unit validation is unavailable for function: {name}")


def _literal_numeric_exponent(node: ast.AST) -> Fraction:
    sign = 1
    value_node = node
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub | ast.UAdd):
        sign = -1 if isinstance(node.op, ast.USub) else 1
        value_node = node.operand
    if not isinstance(value_node, ast.Constant) or isinstance(value_node.value, bool):
        raise UnitExpressionError("power exponents must be literal numeric constants")
    if not isinstance(value_node.value, int | float):
        raise UnitExpressionError("power exponents must be literal numeric constants")
    try:
        return Fraction(str(value_node.value)) * sign
    except (ValueError, OverflowError) as exc:
        raise UnitExpressionError("power exponents must be finite literal numeric constants") from exc


def _require_arg_count(name: str, args: list[UnitDimension], count: int) -> None:
    if len(args) != count:
        raise UnitExpressionError(f"{name} requires exactly {count} argument(s)")


def _require_unitless(unit: UnitDimension, name: str) -> None:
    if not unit.is_unitless():
        raise UnitExpressionError(f"{name} requires exactly unitless input")


def _unit_power_text(unit: str, power: Fraction) -> str:
    if power == 1:
        return unit
    if power.denominator == 1:
        return f"{unit}^{power.numerator}"
    return f"{unit}^({power.numerator}/{power.denominator})"


class _UnitParser:
    def __init__(self, text: str) -> None:
        self._tokens = _tokenize_unit_text(text)
        self._index = 0

    def parse(self) -> UnitDimension:
        if not self._tokens:
            return UnitDimension.unitless()
        return self._parse_product()

    def has_remaining_tokens(self) -> bool:
        return self._index < len(self._tokens)

    def _parse_product(self) -> UnitDimension:
        result = self._parse_factor()
        while self._peek() in {"*", "/"}:
            operator = self._consume()
            factor = self._parse_factor()
            result = result.multiply(factor) if operator == "*" else result.divide(factor)
        return result

    def _parse_factor(self) -> UnitDimension:
        token = self._peek()
        if token is None:
            raise UnitExpressionError("unexpected end of unit text")
        if token == "(":
            self._consume()
            result = self._parse_product()
            if self._consume() != ")":
                raise UnitExpressionError("unbalanced unit parentheses")
        elif token == "1":
            self._consume()
            result = UnitDimension.unitless()
        elif _is_unit_name(token):
            # `token` is already narrowed to a non-None str by _is_unit_name above;
            # _consume() (typed str | None) only advances the cursor past it.
            self._consume()
            result = UnitDimension.from_factors({token: Fraction(1)})
        else:
            raise UnitExpressionError(f"unexpected unit token: {token}")
        if self._peek() == "^":
            self._consume()
            result = result.power(self._parse_exponent())
        return result

    def _parse_exponent(self) -> Fraction:
        if self._peek() == "(":
            self._consume()
            numerator = self._consume()
            next_token = self._consume()
            if numerator is None or next_token is None:
                raise UnitExpressionError("invalid unit exponent")
            if next_token == ")":
                return _parse_unit_exponent(numerator)
            if next_token != "/":
                raise UnitExpressionError("invalid unit exponent")
            denominator = self._consume()
            terminator = self._consume()
            if denominator is None or terminator != ")":
                raise UnitExpressionError("invalid unit exponent")
            return _parse_unit_exponent(f"{numerator}/{denominator}")
        exponent = self._consume()
        if exponent is None:
            raise UnitExpressionError("missing unit exponent")
        return _parse_unit_exponent(exponent)

    def _peek(self) -> str | None:
        if self._index >= len(self._tokens):
            return None
        return self._tokens[self._index]

    def _consume(self) -> str | None:
        token = self._peek()
        if token is not None:
            self._index += 1
        return token


def _tokenize_unit_text(text: str) -> list[str]:
    tokens: list[str] = []
    index = 0
    while index < len(text):
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "*/^()":
            tokens.append(char)
            index += 1
            continue
        start = index
        if char in "+-" or char.isdigit():
            index += 1
            while index < len(text) and (text[index].isdigit() or text[index] == "."):
                index += 1
            tokens.append(text[start:index])
            continue
        if char.isalpha() or char == "_":
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            tokens.append(text[start:index])
            continue
        raise UnitExpressionError(f"unsupported unit character: {char}")
    return tokens


def _is_unit_name(token: str) -> bool:
    return bool(token) and (token[0].isalpha() or token[0] == "_")


def _parse_unit_exponent(token: str) -> Fraction:
    try:
        return Fraction(token)
    except (ValueError, ZeroDivisionError) as exc:
        raise UnitExpressionError(f"invalid unit exponent: {token}") from exc


__all__ = [
    "UnitDimension",
    "UnitExpressionError",
    "parse_unit_dimension",
    "validate_expression_units",
]
