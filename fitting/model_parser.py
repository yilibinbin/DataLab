"""Custom fitting expression parsing.

IMPORTANT: This module MUST reuse the same expression parser/registry that is
used by:
- extrapolation custom formula
- error propagation formula

Those implementations live in `data_extrapolation_latex_latest.py` and are the
single source of truth for:
- allowed functions/constants
- parser behavior (Mathematica-style function names, [] -> (), ^ -> **)
- safety rules (no attribute access, no kwargs, etc.)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Sequence

from mpmath import mp

from data_extrapolation_latex_latest import (
    _ALLOWED_CONSTANTS,
    _ALLOWED_FUNCTIONS,
    _dual_msg,
    numerical_partial_derivative,
    safe_eval,
)


@dataclass
class ModelSpecification:
    """Container that stores callable evaluation hooks."""

    expression: str
    variables: list[str]
    parameters: list[str]
    evaluate_func: Callable[[tuple, tuple], mp.mpf]
    gradient_funcs: dict[str, Callable[[tuple, tuple], mp.mpf]]

    def evaluate(self, variable_values: dict[str, mp.mpf], parameter_values: dict[str, mp.mpf]) -> mp.mpf:
        var_tuple = tuple(variable_values[name] for name in self.variables)
        param_tuple = tuple(parameter_values[name] for name in self.parameters)
        return mp.mpf(self.evaluate_func(var_tuple, param_tuple))

    def partial(self, parameter: str, variable_values: dict[str, mp.mpf], parameter_values: dict[str, mp.mpf]) -> mp.mpf:
        grad = self.gradient_funcs.get(parameter)
        if grad is None:
            return mp.mpf("0")
        var_tuple = tuple(variable_values[name] for name in self.variables)
        param_tuple = tuple(parameter_values[name] for name in self.parameters)
        return mp.mpf(grad(var_tuple, param_tuple))


def infer_parameter_names(expression: str, variable_names: Sequence[str], config_keys: Sequence[str] | None = None) -> list[str]:
    """Infer fitting parameter names from a custom expression.

    This helper is used by the desktop GUI to auto-fill missing parameter names.
    It must exclude safe-eval function/constant identifiers so that typing `Ln`,
    `Gamma`, etc. won't be misclassified as a fit parameter.
    """

    ordered = list(config_keys or [])
    if not expression:
        return ordered

    candidates = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression)
    reserved = {name.lower() for name in variable_names}
    reserved |= {name.lower() for name in _ALLOWED_FUNCTIONS}
    reserved |= {name.lower() for name in _ALLOWED_CONSTANTS}

    for token in candidates:
        token_lower = token.lower()
        if token_lower in reserved:
            continue
        if token in variable_names:
            continue
        if token not in ordered:
            ordered.append(token)

    return ordered if ordered else list(variable_names)


def _build_safe_eval_callable(expression: str, variable_names: list[str], parameter_names: list[str]):
    all_names = list(variable_names) + list(parameter_names)
    var_count = len(variable_names)
    param_count = len(parameter_names)

    def _call(var_tuple: tuple, param_tuple: tuple):
        if len(var_tuple) != var_count or len(param_tuple) != param_count:
            raise ValueError(
                _dual_msg(
                    "模型求值参数数量不匹配。",
                    "Model evaluation received mismatched argument counts.",
                )
            )
        values = tuple(var_tuple) + tuple(param_tuple)
        scope = {name: value for name, value in zip(all_names, values)}
        return mp.mpf(safe_eval(expression, scope))

    return _call


def _build_numeric_gradient_callable(
    expression: str, variable_names: list[str], parameter_names: list[str], *, parameter_index: int
):
    all_names = list(variable_names) + list(parameter_names)
    var_count = len(variable_names)
    param_count = len(parameter_names)
    deriv_index = var_count + int(parameter_index)

    def _call(var_tuple: tuple, param_tuple: tuple):
        if len(var_tuple) != var_count or len(param_tuple) != param_count:
            raise ValueError(
                _dual_msg(
                    "模型偏导参数数量不匹配。",
                    "Model derivative received mismatched argument counts.",
                )
            )
        values = list(tuple(var_tuple) + tuple(param_tuple))
        return mp.mpf(numerical_partial_derivative(expression, all_names, values, deriv_index))

    return _call


def build_model_specification(expression: str, variable_names: Sequence[str], parameter_names: Sequence[str]) -> ModelSpecification:
    """Build mp-ready callables for a custom model expression.

    NOTE: Parsing and allowed function/constant registry MUST match
    extrapolation/error-propagation (safe_eval).
    """

    clean_expr = expression.strip()
    if not clean_expr:
        raise ValueError(_dual_msg("未提供模型表达式。", "Model expression not provided."))

    var_names = list(variable_names)
    param_names = list(parameter_names)
    if not param_names:
        raise ValueError(_dual_msg("至少需要一个参数以执行拟合。", "Need at least one parameter to fit."))

    all_names = var_names + param_names
    duplicates = sorted({name for name in all_names if all_names.count(name) > 1})
    if duplicates:
        joined = ", ".join(duplicates)
        raise ValueError(
            _dual_msg(
                f"变量名/参数名存在重复: {joined}",
                f"Duplicate variable/parameter names: {joined}",
            )
        )

    evaluate_func = _build_safe_eval_callable(clean_expr, var_names, param_names)

    gradient_funcs: dict[str, Callable[[tuple, tuple], mp.mpf]] = {}
    for idx, name in enumerate(param_names):
        gradient_funcs[name] = _build_numeric_gradient_callable(
            clean_expr, var_names, param_names, parameter_index=idx
        )

    return ModelSpecification(
        expression=clean_expr,
        variables=var_names,
        parameters=param_names,
        evaluate_func=evaluate_func,
        gradient_funcs=gradient_funcs,
    )
