"""Conservative classification for implicit fitting problems."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

import sympy as sp
from sympy.parsing.sympy_parser import convert_xor, parse_expr, standard_transformations

from .implicit_model import ImplicitModelDefinition

_DATALAB_FUNCTIONS: dict[str, object] = {
    "Abs": sp.Abs,
    "Cos": sp.cos,
    "Exp": sp.exp,
    "Log": sp.log,
    "Sin": sp.sin,
    "Sqrt": sp.sqrt,
    "Tan": sp.tan,
    "abs": sp.Abs,
    "cos": sp.cos,
    "exp": sp.exp,
    "log": sp.log,
    "sin": sp.sin,
    "sqrt": sp.sqrt,
    "tan": sp.tan,
}


class ImplicitStrategy(Enum):
    OBSERVED_LINEAR = "observed_linear"
    OBSERVED_NONLINEAR = "observed_nonlinear"
    GENERAL = "general"


@dataclass(frozen=True)
class ImplicitClassification:
    strategy: ImplicitStrategy
    reason: str


class ImplicitProblemClassifier:
    def classify(self, definition: ImplicitModelDefinition) -> ImplicitClassification:
        if not _is_observed_implicit_variable(definition):
            return ImplicitClassification(
                ImplicitStrategy.GENERAL,
                "Output expression is not the observed implicit variable.",
            )
        linear = self._is_linear_in_parameters(definition)
        if linear is None:
            return ImplicitClassification(
                ImplicitStrategy.GENERAL,
                "Could not parse implicit equation; using conservative uncertain fallback.",
            )
        if linear:
            return ImplicitClassification(
                ImplicitStrategy.OBSERVED_LINEAR,
                "Observed implicit variable equation is linear in all parameters.",
            )
        return ImplicitClassification(
            ImplicitStrategy.OBSERVED_NONLINEAR,
            "Observed implicit variable equation is not linear in all parameters.",
        )

    def _is_linear_in_parameters(self, definition: ImplicitModelDefinition) -> bool | None:
        if not definition.parameters:
            return False
        names = set(definition.parameters) | set(definition.x_variables) | {definition.implicit_variable}
        local_dict = {name: sp.symbols(name) for name in names}
        local_dict.update(_DATALAB_FUNCTIONS)
        try:
            parsed = parse_expr(
                _normalise_datalab_expression(definition.equation),
                local_dict=local_dict,
                transformations=standard_transformations + (convert_xor,),
                evaluate=False,
            )
            numerator, denominator = sp.together(parsed).as_numer_denom()
            parameter_symbols = [local_dict[name] for name in definition.parameters]
            if set(denominator.free_symbols) & set(parameter_symbols):
                return False
            polynomial = sp.Poly(numerator, *parameter_symbols)
        except Exception:
            return None
        return int(polynomial.total_degree()) <= 1


def _is_observed_implicit_variable(definition: ImplicitModelDefinition) -> bool:
    return (
        definition.output_expression.strip() == definition.implicit_variable
        and definition.implicit_variable not in definition.x_variables
    )


def _normalise_datalab_expression(expression: str) -> str:
    normalised = expression
    for _ in range(20):
        updated = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\[", r"\1(", normalised)
        if updated == normalised:
            break
        normalised = updated
    return normalised.replace("]", ")")
