"""Analytic implicit derivatives for self-consistent fitting models."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import TYPE_CHECKING

import sympy as sp
from mpmath import mp

from shared.symbolic_math import parse_symbolic_expression

if TYPE_CHECKING:
    from .implicit_model import ImplicitModelDefinition


_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImplicitDerivativeEvaluator:
    implicit_variable: str
    ordered_names: tuple[str, ...]
    partial_functions: dict[str, Callable[..., object]]
    residual_u_function: Callable[..., object]

    def partial(
        self,
        parameter: str,
        variables: dict[str, mp.mpf],
        params: dict[str, mp.mpf],
        constants: dict[str, mp.mpf],
        implicit_value: mp.mpf,
        *,
        min_abs_residual_u: mp.mpf | None = None,
    ) -> mp.mpf:
        ordered = _ordered_scope_values(
            self.ordered_names,
            variables,
            params,
            constants,
            self.implicit_variable,
            implicit_value,
        )
        residual_u = mp.mpf(self.residual_u_function(*ordered))
        if not mp.isfinite(residual_u):
            raise ValueError("Analytic implicit derivative has non-finite F_u.")
        if min_abs_residual_u is not None and mp.fabs(residual_u) <= min_abs_residual_u:
            raise ValueError("Analytic implicit derivative is near-singular because F_u is too small.")
        fn = self.partial_functions[parameter]
        value = mp.mpf(fn(*ordered))
        if not mp.isfinite(value):
            raise ValueError(f"Analytic implicit derivative for {parameter!r} is not finite.")
        return value


def build_implicit_derivative_evaluator(
    definition: ImplicitModelDefinition,
) -> ImplicitDerivativeEvaluator | None:
    """Build derivative callables for independent model parameters.

    Callers that expose dependent parameter expressions must either apply the
    free-parameter chain rule themselves or keep this analytic path disabled.
    """

    names = [*definition.x_variables, definition.implicit_variable, *definition.parameters, *definition.constants]
    try:
        equation, symbols = parse_symbolic_expression(definition.equation, variables=names)
        output, _ = parse_symbolic_expression(definition.output_expression, variables=names)
    except Exception:
        return None

    allowed = set(names)
    if {str(symbol) for symbol in equation.free_symbols}.difference(allowed):
        return None
    if {str(symbol) for symbol in output.free_symbols}.difference(allowed):
        return None

    u_symbol = symbols[definition.implicit_variable]
    implicit_residual = u_symbol - equation
    residual_u = sp.simplify(sp.diff(implicit_residual, u_symbol))
    if residual_u == 0:
        return None

    ordered_names = tuple(names)
    ordered_symbols = [symbols[name] for name in ordered_names]
    partial_functions: dict[str, Callable[..., object]] = {}
    try:
        residual_u_function = _harden_lambdify_callable(sp.lambdify(
            ordered_symbols,
            residual_u,
            "mpmath",
        ))
    except (TypeError, ValueError, SyntaxError):
        return None
    for parameter in definition.parameters:
        parameter_symbol = symbols[parameter]
        residual_parameter = sp.diff(implicit_residual, parameter_symbol)
        implicit_partial = -residual_parameter / residual_u
        output_partial = sp.diff(output, parameter_symbol) + sp.diff(output, u_symbol) * implicit_partial
        try:
            partial_functions[parameter] = _harden_lambdify_callable(sp.lambdify(
                ordered_symbols,
                sp.simplify(output_partial),
                "mpmath",
            ))
        except Exception:
            return None

    return ImplicitDerivativeEvaluator(
        implicit_variable=definition.implicit_variable,
        ordered_names=ordered_names,
        partial_functions=partial_functions,
        residual_u_function=residual_u_function,
    )


def _harden_lambdify_callable(fn: Callable[..., object]) -> Callable[..., object]:
    try:
        fn.__globals__["__builtins__"] = {}
    except Exception:
        _logger.debug(
            "Could not strip __builtins__ from implicit derivative lambdify callable; "
            "parser-level whitelist remains primary defense.",
            exc_info=True,
        )
    return fn


def _ordered_scope_values(
    ordered_names: tuple[str, ...],
    variables: dict[str, mp.mpf],
    params: dict[str, mp.mpf],
    constants: dict[str, mp.mpf],
    implicit_variable: str,
    implicit_value: mp.mpf,
) -> list[mp.mpf]:
    values: list[mp.mpf] = []
    for name in ordered_names:
        if name in variables:
            values.append(mp.mpf(variables[name]))
        elif name in params:
            values.append(mp.mpf(params[name]))
        elif name in constants:
            values.append(mp.mpf(constants[name]))
        elif name == implicit_variable:
            values.append(mp.mpf(implicit_value))
        else:
            raise KeyError(f"No numeric value is available for symbol {name!r}.")
    return values
