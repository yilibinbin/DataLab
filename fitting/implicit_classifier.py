"""Conservative classification for implicit fitting problems."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import sympy as sp
from sympy.parsing.sympy_parser import convert_xor, parse_expr, standard_transformations

from .implicit_model import ImplicitModelDefinition


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
        if self._is_linear_in_parameters(definition):
            return ImplicitClassification(
                ImplicitStrategy.OBSERVED_LINEAR,
                "Observed implicit variable equation is linear in all parameters.",
            )
        return ImplicitClassification(
            ImplicitStrategy.OBSERVED_NONLINEAR,
            "Observed implicit variable equation is not linear in all parameters.",
        )

    def _is_linear_in_parameters(self, definition: ImplicitModelDefinition) -> bool:
        if not definition.parameters:
            return False
        names = set(definition.parameters) | set(definition.x_variables) | {definition.implicit_variable}
        local_dict = {name: sp.symbols(name) for name in names}
        try:
            parsed = parse_expr(
                definition.equation,
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
            return False
        return int(polynomial.total_degree()) <= 1


def _is_observed_implicit_variable(definition: ImplicitModelDefinition) -> bool:
    return (
        definition.output_expression.strip() == definition.implicit_variable
        and definition.implicit_variable not in definition.x_variables
    )
