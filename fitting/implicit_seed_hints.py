"""Conservative seed hints for implicit output root solving."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import sympy as sp
from mpmath import mp

from shared.symbolic_math import parse_symbolic_expression

if TYPE_CHECKING:
    from .implicit_model import ImplicitModelDefinition


@dataclass(frozen=True)
class ImplicitSeedHint:
    reason: str
    candidates: Callable[[dict[str, mp.mpf], mp.mpf], tuple[mp.mpf, ...]]


def detect_seed_hint(
    definition: ImplicitModelDefinition,
    *,
    precision: int | None = None,
) -> ImplicitSeedHint | None:
    """Detect inverse-square output forms and return root seed candidates."""

    if len(definition.x_variables) != 1:
        return None
    dps = precision or mp.dps
    try:
        offset, coefficient = _inverse_square_terms(definition, precision=dps)
    except (TypeError, ValueError, SyntaxError):
        return None

    if not mp.isfinite(offset) or not mp.isfinite(coefficient) or coefficient == 0:
        return None

    x_name = definition.x_variables[0]

    def _candidates(variables: dict[str, mp.mpf], target: mp.mpf) -> tuple[mp.mpf, ...]:
        with mp.workdps(dps):
            effective_target = mp.mpf(target) - offset
            if effective_target == 0:
                return ()
            ratio = coefficient / effective_target
            if ratio <= 0 or not mp.isfinite(ratio):
                return ()
            x_value = mp.mpf(variables[x_name])
            root = mp.sqrt(ratio)
            accepted: list[mp.mpf] = []
            for candidate in (x_value - root, x_value + root):
                reconstructed = offset + coefficient / (x_value - candidate) ** 2
                scale = max(mp.mpf("1"), mp.fabs(target), mp.fabs(reconstructed))
                if mp.fabs(reconstructed - target) <= max(mp.mpf("1e-30"), mp.eps * scale * 32):
                    accepted.append(candidate)
            return tuple(accepted)

    return ImplicitSeedHint(reason="validated inverse-square output seed", candidates=_candidates)


def _inverse_square_terms(definition: ImplicitModelDefinition, *, precision: int) -> tuple[mp.mpf, mp.mpf]:
    x_name = definition.x_variables[0]
    u_name = definition.implicit_variable
    names = [x_name, u_name, *definition.constants]
    expr, symbols = parse_symbolic_expression(definition.output_expression, variables=names)

    free_names = {str(symbol) for symbol in expr.free_symbols}
    if free_names.intersection(definition.parameters):
        raise ValueError("Seed hint output depends on free parameters.")
    allowed = {x_name, u_name, *definition.constants}
    if free_names.difference(allowed):
        raise ValueError("Seed hint output contains unknown symbols.")

    x_symbol = symbols[x_name]
    u_symbol = symbols[u_name]
    offset_expr = sp.simplify(sp.limit(expr, u_symbol, sp.oo))
    coefficient_expr = sp.simplify((expr - offset_expr) * (x_symbol - u_symbol) ** 2)
    if (
        offset_expr.has(x_symbol)
        or offset_expr.has(u_symbol)
        or coefficient_expr.has(x_symbol)
        or coefficient_expr.has(u_symbol)
    ):
        raise ValueError("Output is not a constant-offset inverse-square expression.")

    substitutions = {
        symbols[name]: sp.Float(str(definition.constants[name]), precision)
        for name in definition.constants
    }
    offset = _finite_mpf(sp.simplify(offset_expr.subs(substitutions)), precision=precision)
    coefficient = _finite_mpf(sp.simplify(coefficient_expr.subs(substitutions)), precision=precision)
    if offset is None or coefficient is None:
        raise ValueError("Seed hint terms must be finite real values.")
    return offset, coefficient


def _finite_mpf(value: object, *, precision: int) -> mp.mpf | None:
    evaluated = sp.N(value, precision)
    if getattr(evaluated, "is_real", None) is False:
        return None
    try:
        result = mp.mpf(str(evaluated))
    except (TypeError, ValueError):
        return None
    return result if mp.isfinite(result) else None
