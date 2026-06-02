from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from mpmath import mp
import sympy as sp

from datalab_latex.expression_engine import safe_eval
from root_solving.models import RootProblem
from shared.computation_inputs import SymbolCategories, classify_expression_symbols, validate_symbol_classification
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard
from shared.symbolic_math import normalize_symbolic_expression, parse_symbolic_expression
from shared.uncertainty import parse_numeric_value


@dataclass(frozen=True)
class RootExpressionSystem:
    expressions: tuple[str, ...]
    symbolic_expressions: tuple[sp.Expr, ...]
    symbol_map: Mapping[str, sp.Symbol]
    unknown_names: tuple[str, ...]
    input_names: tuple[str, ...]
    nominal_inputs: Mapping[str, mp.mpf]
    precision: int

    def evaluate(self, unknown_values: Mapping[str, object], equation_index: int = 0) -> mp.mpf:
        expression = self._expression(equation_index)
        values = self._numeric_scope(unknown_values)
        try:
            with precision_guard(self.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
                return _finite_mpf(safe_eval(expression, dict(values)), f"equation {equation_index} result")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Failed to evaluate equation {equation_index}: {exc}") from exc

    def residuals(self, unknown_values: Mapping[str, object]) -> tuple[mp.mpf, ...]:
        return tuple(self.evaluate(unknown_values, index) for index in range(len(self.expressions)))

    def derivative_unknown(
        self,
        name: str,
        unknown_values: Mapping[str, object],
        equation_index: int = 0,
    ) -> mp.mpf:
        if name not in self.unknown_names:
            raise ValueError(f"Unknown value is not part of this root problem: {name}")
        return self._derivative(name, unknown_values, equation_index)

    def derivative_input(
        self,
        name: str,
        unknown_values: Mapping[str, object],
        equation_index: int = 0,
    ) -> mp.mpf:
        if name not in self.input_names:
            raise ValueError(f"Input value is not part of this root problem: {name}")
        return self._derivative(name, unknown_values, equation_index)

    def polynomial_coefficients(self) -> tuple[mp.mpf, ...] | None:
        if len(self.symbolic_expressions) != 1 or len(self.unknown_names) != 1:
            return None

        unknown_symbol = self.symbol_map[self.unknown_names[0]]
        substitutions = {
            self.symbol_map[name]: _sympy_numeric(value, self.precision)
            for name, value in self.nominal_inputs.items()
            if name in self.symbol_map
        }
        expression = self.symbolic_expressions[0].subs(substitutions)
        try:
            polynomial = sp.Poly(expression, unknown_symbol)
        except sp.PolynomialError:
            return None
        if not polynomial.is_univariate:
            return None
        return tuple(_mp_from_sympy(coefficient, self.precision) for coefficient in polynomial.all_coeffs())

    def _derivative(
        self,
        name: str,
        unknown_values: Mapping[str, object],
        equation_index: int,
    ) -> mp.mpf:
        symbol = self.symbol_map[name]
        try:
            derivative = sp.diff(self._symbolic_expression(equation_index), symbol)
            substitutions = self._sympy_scope(unknown_values)
            return _mp_from_sympy(derivative.subs(substitutions), self.precision)
        except Exception:
            return self._finite_difference_derivative(name, unknown_values, equation_index)

    def _finite_difference_derivative(
        self,
        name: str,
        unknown_values: Mapping[str, object],
        equation_index: int,
    ) -> mp.mpf:
        values = self._numeric_scope(unknown_values)
        center = values[name]
        step = mp.sqrt(mp.eps) * max(mp.mpf("1"), abs(center))
        if step == 0:
            step = mp.sqrt(mp.eps)

        plus = dict(unknown_values)
        minus = dict(unknown_values)
        if name in self.unknown_names:
            plus[name] = center + step
            minus[name] = center - step
            return (self.evaluate(plus, equation_index) - self.evaluate(minus, equation_index)) / (2 * step)

        plus_inputs = dict(self.nominal_inputs)
        minus_inputs = dict(self.nominal_inputs)
        plus_inputs[name] = center + step
        minus_inputs[name] = center - step
        return (
            self._evaluate_with_inputs(unknown_values, plus_inputs, equation_index)
            - self._evaluate_with_inputs(unknown_values, minus_inputs, equation_index)
        ) / (2 * step)

    def _evaluate_with_inputs(
        self,
        unknown_values: Mapping[str, object],
        nominal_inputs: Mapping[str, mp.mpf],
        equation_index: int,
    ) -> mp.mpf:
        values = _coerce_unknown_values(unknown_values, self.unknown_names)
        values.update(nominal_inputs)
        try:
            with precision_guard(self.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
                return _finite_mpf(
                    safe_eval(self._expression(equation_index), dict(values)),
                    f"equation {equation_index} result",
                )
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Failed to evaluate equation {equation_index}: {exc}") from exc

    def _numeric_scope(self, unknown_values: Mapping[str, object]) -> dict[str, mp.mpf]:
        values = _coerce_unknown_values(unknown_values, self.unknown_names)
        values.update(self.nominal_inputs)
        return values

    def _sympy_scope(self, unknown_values: Mapping[str, object]) -> dict[sp.Symbol, Any]:
        values = self._numeric_scope(unknown_values)
        return {self.symbol_map[name]: _sympy_numeric(value, self.precision) for name, value in values.items()}

    def _expression(self, equation_index: int) -> str:
        try:
            return self.expressions[equation_index]
        except IndexError as exc:
            raise ValueError(f"Equation index out of range: {equation_index}") from exc

    def _symbolic_expression(self, equation_index: int) -> sp.Expr:
        try:
            return self.symbolic_expressions[equation_index]
        except IndexError as exc:
            raise ValueError(f"Equation index out of range: {equation_index}") from exc


def build_root_expression_system(problem: RootProblem) -> RootExpressionSystem:
    unknown_names = tuple(unknown.name for unknown in problem.unknowns)
    row_names = tuple(problem.row_values)
    known_names = () if row_names else tuple(known.name for known in problem.known_values)
    constant_names = tuple(problem.constants)
    input_names = row_names or known_names
    _validate_scope_names(
        unknown_names=unknown_names,
        input_names=input_names,
        constant_names=constant_names,
    )
    variables = (*unknown_names, *input_names, *constant_names)
    with precision_guard(problem.precision, clamp_min=MIN_MPMATH_DPS, clamp_max=MAX_MPMATH_DPS):
        nominal_inputs = _nominal_inputs(problem)
    expressions = tuple(normalize_symbolic_expression(equation) for equation in problem.equations)

    symbolic_expressions: list[sp.Expr] = []
    symbol_map: dict[str, sp.Symbol] | None = None
    for index, expression in enumerate(expressions):
        try:
            parsed, parsed_symbols = parse_symbolic_expression(expression, variables=variables, normalize=False)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Failed to parse equation {index}: {exc}") from exc
        _validate_expression_scope(parsed, parsed_symbols, expression)
        symbolic_expressions.append(parsed)
        if symbol_map is None:
            symbol_map = parsed_symbols

    return RootExpressionSystem(
        expressions=expressions,
        symbolic_expressions=tuple(symbolic_expressions),
        symbol_map=symbol_map or {},
        unknown_names=unknown_names,
        input_names=(*input_names, *constant_names),
        nominal_inputs=nominal_inputs,
        precision=problem.precision,
    )


def _nominal_inputs(problem: RootProblem) -> dict[str, mp.mpf]:
    values: dict[str, mp.mpf] = {}
    if problem.row_values:
        for name, value in problem.row_values.items():
            values[name] = _parse_nominal(value, f"data column {name}")
    else:
        for known in problem.known_values:
            values[known.name] = _parse_nominal(known.value, f"known value {known.name}")
    for name, value in problem.constants.items():
        values[name] = _parse_nominal(value, f"constant {name}")
    return values


def _parse_nominal(value: object, label: str) -> mp.mpf:
    try:
        return _finite_mpf(parse_numeric_value(value), label)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Invalid numeric value for {label}.") from exc


def _coerce_unknown_values(values: Mapping[str, object], names: Sequence[str]) -> dict[str, mp.mpf]:
    numeric: dict[str, mp.mpf] = {}
    for name in names:
        if name not in values:
            raise ValueError(f"Missing value for unknown {name}.")
        try:
            numeric[name] = _finite_mpf(values[name], f"unknown {name}")
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Invalid finite value for unknown {name}.") from exc
    return numeric


def _validate_scope_names(
    *,
    unknown_names: Sequence[str],
    input_names: Sequence[str],
    constant_names: Sequence[str],
) -> None:
    classification = classify_expression_symbols(
        (),
        SymbolCategories(
            unknowns=tuple(unknown_names),
            data_columns=tuple(input_names),
            constants=tuple(constant_names),
        ),
    )
    validate_symbol_classification(classification)


def _validate_expression_scope(
    expression: sp.Expr,
    symbol_map: Mapping[str, sp.Symbol],
    source: str,
) -> None:
    allowed_symbols = set(symbol_map.values())
    missing = sorted(str(symbol) for symbol in expression.free_symbols if symbol not in allowed_symbols)
    if missing:
        names = ", ".join(missing)
        raise ValueError(f"Expression references names outside the root scope: {names}. Expression: {source}")


def _finite_mpf(value: object, label: str) -> mp.mpf:
    numeric = mp.mpf(value)
    if not mp.isfinite(numeric):
        raise ValueError(f"{label} must be finite.")
    return numeric


def _sympy_numeric(value: object, precision: int) -> sp.Float:
    return sp.Float(str(_finite_mpf(value, "symbolic numeric value")), precision)


def _mp_from_sympy(value: Any, precision: int) -> mp.mpf:
    evaluated = sp.N(value, precision)
    if not evaluated.is_real:
        raise ValueError(f"Expression did not evaluate to a real number: {value}")
    return _finite_mpf(str(evaluated), "symbolic expression result")
