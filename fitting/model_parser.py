"""Custom fitting expression parsing.

IMPORTANT: This module MUST reuse the same expression parser/registry that is
used by:
- extrapolation custom formula
- error propagation formula

Those implementations now live in `shared.expression_engine` and are the
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

# The fit hot path evaluates the model expression via ``compile_expression``,
# which parses/validates once and returns a fast evaluator (P1-1). To patch the
# evaluator in tests, patch ``fitting.model_parser.compile_expression`` — the
# ``from … import`` above creates a fresh local binding here.
from shared.derivatives import numerical_partial_derivative
from shared.expression_engine import (
    _ALLOWED_CONSTANTS,
    _ALLOWED_FUNCTIONS,
    compile_expression,
)
from shared.bilingual import _dual_msg
from shared.uncertainty import parse_numeric_value

# Signature of the inner per-model evaluator: takes a positional
# variable-tuple and parameter-tuple of mp.mpf values and returns
# the model's mp.mpf output. Used by every fit-execution path
# (custom, polynomial, inverse, Padé, linear-named, auto).
MpfCallable = Callable[
    [tuple[mp.mpf, ...], tuple[mp.mpf, ...]], mp.mpf
]


def reserved_expression_names() -> set[str]:
    """Return expression-engine names that user variables/constants must not shadow."""
    return {name.lower() for name in _ALLOWED_FUNCTIONS} | {
        name.lower() for name in _ALLOWED_CONSTANTS
    }


def is_reserved_expression_name(name: str) -> bool:
    return name.lower() in reserved_expression_names()


@dataclass
class ModelSpecification:
    """Container that stores callable evaluation hooks."""

    expression: str
    variables: list[str]
    parameters: list[str]
    constants: dict[str, str]
    evaluate_func: MpfCallable
    gradient_funcs: dict[str, MpfCallable]

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


def infer_parameter_names(
    expression: str,
    variable_names: Sequence[str] | None = None,
    config_keys: Sequence[str] | None = None,
    *,
    variables: Sequence[str] | None = None,
    known_parameters: Sequence[str] | None = None,
    constants: Sequence[str] | None = None,
) -> list[str]:
    """Infer fitting parameter names from a custom expression.

    This helper is used by the desktop GUI to auto-fill missing parameter names.
    It must exclude safe-eval function/constant identifiers so that typing `Ln`,
    `Gamma`, etc. won't be misclassified as a fit parameter.
    """

    if variable_names is None:
        if variables is None:
            raise TypeError("infer_parameter_names() missing required argument: 'variable_names'")
        variable_names = variables
    if config_keys is None:
        config_keys = known_parameters

    variable_list = list(variable_names)
    constant_list = list(constants or [])
    reserved = {name.lower() for name in variable_list}
    reserved |= {name.lower() for name in constant_list}
    reserved |= reserved_expression_names()

    ordered: list[str] = []
    for name in config_keys or []:
        if name.lower() not in reserved and name not in ordered:
            ordered.append(name)
    if not expression:
        return ordered

    candidates = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression)

    for token in candidates:
        token_lower = token.lower()
        if token_lower in reserved:
            continue
        if token not in ordered:
            ordered.append(token)

    return ordered if ordered else variable_list


def _constant_values(constants: dict[str, str]) -> dict[str, mp.mpf]:
    return {name: parse_numeric_value(value) for name, value in constants.items()}


def _build_safe_eval_callable(
    expression: str,
    variable_names: list[str],
    parameter_names: list[str],
    constants: dict[str, str],
) -> MpfCallable:
    all_names = list(variable_names) + list(parameter_names)
    var_count = len(variable_names)
    param_count = len(parameter_names)
    constant_scope = _constant_values(constants)
    # Parse/validate the model expression once; the fit loop evaluates it per
    # data point per LM iteration, so hoisting the parse out is the P1-1 win.
    evaluate = compile_expression(expression)

    def _call(
        var_tuple: tuple[mp.mpf, ...], param_tuple: tuple[mp.mpf, ...]
    ) -> mp.mpf:
        if len(var_tuple) != var_count or len(param_tuple) != param_count:
            raise ValueError(
                _dual_msg(
                    "模型求值参数数量不匹配。",
                    "Model evaluation received mismatched argument counts.",
                )
            )
        values = tuple(var_tuple) + tuple(param_tuple)
        scope = {name: value for name, value in zip(all_names, values)}
        scope.update(constant_scope)
        return mp.mpf(evaluate(scope))

    return _call


def _build_numeric_gradient_callable(
    expression: str,
    variable_names: list[str],
    parameter_names: list[str],
    *,
    parameter_index: int,
    constants: dict[str, str],
) -> MpfCallable:
    constant_names = list(constants)
    all_names = list(variable_names) + constant_names + list(parameter_names)
    var_count = len(variable_names)
    constant_count = len(constant_names)
    param_count = len(parameter_names)
    constant_values = [parse_numeric_value(constants[name]) for name in constant_names]
    deriv_index = var_count + constant_count + int(parameter_index)

    def _call(
        var_tuple: tuple[mp.mpf, ...], param_tuple: tuple[mp.mpf, ...]
    ) -> mp.mpf:
        if len(var_tuple) != var_count or len(param_tuple) != param_count:
            raise ValueError(
                _dual_msg(
                    "模型偏导参数数量不匹配。",
                    "Model derivative received mismatched argument counts.",
                )
            )
        values = list(tuple(var_tuple) + tuple(constant_values) + tuple(param_tuple))
        return mp.mpf(numerical_partial_derivative(expression, all_names, values, deriv_index))

    return _call


def build_model_specification(
    expression: str,
    variable_names: Sequence[str],
    parameter_names: Sequence[str],
    constants: dict[str, str] | None = None,
) -> ModelSpecification:
    """Build mp-ready callables for a custom model expression.

    NOTE: Parsing and allowed function/constant registry MUST match
    extrapolation/error-propagation (safe_eval).
    """

    clean_expr = expression.strip()
    if not clean_expr:
        raise ValueError(_dual_msg("未提供模型表达式。", "Model expression not provided."))

    var_names = list(variable_names)
    param_names = list(parameter_names)
    constant_map = dict(constants or {})
    if not param_names:
        raise ValueError(_dual_msg("至少需要一个参数以执行拟合。", "Need at least one parameter to fit."))

    all_names = var_names + param_names + list(constant_map)
    duplicates = sorted({name for name in all_names if all_names.count(name) > 1})
    if duplicates:
        joined = ", ".join(duplicates)
        raise ValueError(
            _dual_msg(
                f"变量名/参数名存在重复: {joined}",
                f"Duplicate variable/parameter names: {joined}",
            )
        )
    reserved_constants = sorted(name for name in constant_map if is_reserved_expression_name(name))
    if reserved_constants:
        joined = ", ".join(reserved_constants)
        raise ValueError(
            _dual_msg(
                f"常数名称不能使用表达式保留名: {joined}",
                f"Reserved expression names cannot be used as constants: {joined}",
            )
        )

    evaluate_func = _build_safe_eval_callable(clean_expr, var_names, param_names, constant_map)

    gradient_funcs: dict[str, MpfCallable] = {}
    for idx, name in enumerate(param_names):
        gradient_funcs[name] = _build_numeric_gradient_callable(
            clean_expr,
            var_names,
            param_names,
            parameter_index=idx,
            constants=constant_map,
        )

    return ModelSpecification(
        expression=clean_expr,
        variables=var_names,
        parameters=param_names,
        constants=constant_map,
        evaluate_func=evaluate_func,
        gradient_funcs=gradient_funcs,
    )
