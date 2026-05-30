"""Output-transform detection for implicit fitting.

Detect only exact affine output maps that preserve least-squares residual
semantics for the observed implicit-variable path.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import sympy as sp
from mpmath import mp

from shared.symbolic_math import parse_symbolic_expression

from .implicit_model import ImplicitModelDefinition


@dataclass(frozen=True)
class OutputTransform:
    transformed_targets: Callable[[dict[str, Sequence[mp.mpf]], Sequence[mp.mpf]], list[mp.mpf]]
    transformed_sigmas: Callable[
        [dict[str, Sequence[mp.mpf]], Sequence[mp.mpf | None] | None],
        list[mp.mpf | None] | None,
    ]
    transformed_weights: Callable[[dict[str, Sequence[mp.mpf]], list[mp.mpf] | None], list[mp.mpf] | None]
    forward_values: Callable[[dict[str, Sequence[mp.mpf]], Sequence[mp.mpf]], list[mp.mpf]]
    expression: str
    reason: str


def detect_output_transform(
    definition: ImplicitModelDefinition,
    *,
    precision: int | None = None,
) -> OutputTransform | None:
    """Detect finite constant-affine output expressions `a*u + b`."""

    if definition.output_expression.strip() == definition.implicit_variable:
        return None
    names = [*definition.x_variables, definition.implicit_variable, *definition.constants]
    dps = precision or mp.dps
    try:
        expr, symbols = parse_symbolic_expression(definition.output_expression, variables=names)
        with mp.workdps(dps):
            constants = _constant_values(definition.constants)
    except (TypeError, ValueError, SyntaxError):
        return None

    free_names = {str(symbol) for symbol in expr.free_symbols}
    if free_names.intersection(definition.parameters):
        return None
    allowed = {definition.implicit_variable, *definition.x_variables, *definition.constants}
    if free_names.difference(allowed):
        return None

    u_symbol = symbols[definition.implicit_variable]
    slope_expr = sp.simplify(sp.diff(expr, u_symbol))
    intercept_expr = sp.simplify(expr - slope_expr * u_symbol)
    if slope_expr == 0 or slope_expr.has(u_symbol) or intercept_expr.has(u_symbol):
        return None

    substitutions = {symbols[name]: sp.Float(str(definition.constants[name]), dps) for name in constants}
    slope_eval = sp.simplify(slope_expr.subs(substitutions))
    intercept_eval = sp.simplify(intercept_expr.subs(substitutions))
    x_symbols = [symbols[name] for name in definition.x_variables]
    if any(slope_eval.has(symbol) or intercept_eval.has(symbol) for symbol in x_symbols):
        return None

    with mp.workdps(dps):
        slope = _finite_mpf(slope_eval, precision=dps)
        intercept = _finite_mpf(intercept_eval, precision=dps)
    if slope is None or intercept is None or mp.fabs(slope) <= mp.mpf("1e-50"):
        return None
    return _build_affine_transform(definition, slope=slope, intercept=intercept)


def _build_affine_transform(
    definition: ImplicitModelDefinition,
    *,
    slope: mp.mpf,
    intercept: mp.mpf,
) -> OutputTransform | None:
    if not mp.isfinite(slope) or not mp.isfinite(intercept) or mp.fabs(slope) <= mp.mpf("1e-50"):
        return None

    def _targets(
        variable_data: dict[str, Sequence[mp.mpf]],
        targets: Sequence[mp.mpf],
    ) -> list[mp.mpf]:
        return [(mp.mpf(target) - intercept) / slope for target in targets]

    def _sigmas(
        variable_data: dict[str, Sequence[mp.mpf]],
        data_sigmas: Sequence[mp.mpf | None] | None,
    ) -> list[mp.mpf | None] | None:
        if data_sigmas is None:
            return None
        scale = mp.fabs(slope)
        return [None if sigma is None else mp.mpf(sigma) / scale for sigma in data_sigmas]

    def _weights(
        variable_data: dict[str, Sequence[mp.mpf]],
        weights: list[mp.mpf] | None,
    ) -> list[mp.mpf] | None:
        if weights is None:
            return None
        scale = mp.fabs(slope)
        return [mp.mpf(weight) * scale * scale for weight in weights]

    def _forward(
        variable_data: dict[str, Sequence[mp.mpf]],
        implicit_values: Sequence[mp.mpf],
    ) -> list[mp.mpf]:
        return [slope * mp.mpf(value) + intercept for value in implicit_values]

    return OutputTransform(
        transformed_targets=_targets,
        transformed_sigmas=_sigmas,
        transformed_weights=_weights,
        forward_values=_forward,
        expression=definition.output_expression,
        reason="exact affine output transform",
    )


def _constant_values(constants: dict[str, str]) -> dict[str, mp.mpf]:
    values = {name: mp.mpf(value) for name, value in constants.items()}
    if any(not mp.isfinite(value) for value in values.values()):
        raise ValueError("Affine output constants must be finite real values.")
    return values


def _finite_mpf(value: object, *, precision: int) -> mp.mpf | None:
    evaluated = sp.N(value, precision)
    if getattr(evaluated, "is_real", None) is False:
        return None
    try:
        result = mp.mpf(str(evaluated))
    except (TypeError, ValueError):
        return None
    return result if mp.isfinite(result) else None
