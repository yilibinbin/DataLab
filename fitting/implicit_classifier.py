"""Conservative classification for implicit fitting problems."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import Enum

from .implicit_model import ImplicitModelDefinition

_SAFE_FUNCTION_NAMES = {
    "Abs",
    "Cos",
    "Exp",
    "Log",
    "Sin",
    "Sqrt",
    "Tan",
    "abs",
    "cos",
    "exp",
    "log",
    "sin",
    "sqrt",
    "tan",
}
_SAFE_CONSTANT_NAMES = {"E", "Pi", "pi"}
_NONLINEAR_DEGREE = 2


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
        expression = _normalise_datalab_expression(definition.equation)
        try:
            parsed = ast.parse(expression, mode="eval")
        except SyntaxError:
            return None
        allowed_non_parameters = (
            set(definition.x_variables)
            | {definition.implicit_variable}
            | set(definition.constants)
            | _SAFE_CONSTANT_NAMES
        )
        degree = _parameter_degree(parsed.body, set(definition.parameters), allowed_non_parameters)
        if degree is None:
            return None
        return degree <= 1


def _parameter_degree(
    node: ast.AST,
    parameters: set[str],
    allowed_non_parameters: set[str],
) -> int | None:
    if isinstance(node, ast.Constant):
        return 0 if isinstance(node.value, int | float) else None
    if isinstance(node, ast.Name):
        if node.id in parameters:
            return 1
        if node.id in allowed_non_parameters:
            return 0
        return None
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        return _parameter_degree(node.operand, parameters, allowed_non_parameters)
    if isinstance(node, ast.BinOp):
        return _binary_parameter_degree(node, parameters, allowed_non_parameters)
    if isinstance(node, ast.Call):
        return _call_parameter_degree(node, parameters, allowed_non_parameters)
    return None


def _binary_parameter_degree(
    node: ast.BinOp,
    parameters: set[str],
    allowed_non_parameters: set[str],
) -> int | None:
    left = _parameter_degree(node.left, parameters, allowed_non_parameters)
    right = _parameter_degree(node.right, parameters, allowed_non_parameters)
    if left is None or right is None:
        return None
    if isinstance(node.op, ast.Add | ast.Sub):
        return max(left, right)
    if isinstance(node.op, ast.Mult):
        return min(left + right, _NONLINEAR_DEGREE)
    if isinstance(node.op, ast.Div):
        if right != 0:
            return _NONLINEAR_DEGREE
        return left
    if isinstance(node.op, ast.Pow):
        return _power_parameter_degree(node, left, right)
    return None


def _power_parameter_degree(node: ast.BinOp, base_degree: int, exponent_degree: int) -> int | None:
    if exponent_degree != 0:
        return _NONLINEAR_DEGREE
    if base_degree == 0:
        return 0
    exponent = _numeric_literal(node.right)
    if exponent is None:
        return _NONLINEAR_DEGREE
    if exponent == 0:
        return 0
    if exponent == 1:
        return base_degree
    return _NONLINEAR_DEGREE


def _call_parameter_degree(
    node: ast.Call,
    parameters: set[str],
    allowed_non_parameters: set[str],
) -> int | None:
    if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCTION_NAMES:
        return None
    if node.keywords:
        return None
    for arg in node.args:
        degree = _parameter_degree(arg, parameters, allowed_non_parameters)
        if degree is None:
            return None
        if degree != 0:
            return _NONLINEAR_DEGREE
    return 0


def _numeric_literal(node: ast.AST) -> int | float | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.UAdd | ast.USub):
        value = _numeric_literal(node.operand)
        if value is None:
            return None
        return value if isinstance(node.op, ast.UAdd) else -value
    return None


def _is_observed_implicit_variable(definition: ImplicitModelDefinition) -> bool:
    return (
        definition.output_expression.strip() == definition.implicit_variable
        and definition.implicit_variable not in definition.x_variables
    )


def _normalise_datalab_expression(expression: str) -> str:
    normalised = expression.replace("^", "**")
    function_names = "|".join(re.escape(name) for name in sorted(_SAFE_FUNCTION_NAMES, key=len, reverse=True))
    for _ in range(20):
        updated = re.sub(rf"\b({function_names})\s*\[", r"\1(", normalised)
        if updated == normalised:
            break
        normalised = updated
    return normalised.replace("]", ")")
