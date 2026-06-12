from __future__ import annotations

import ast
import math
import random
import re
from typing import cast

from mpmath import mp

from shared.bilingual import _dual_msg, _split_dual
from shared.derivatives import (
    _get_symbolic_hessian,
    _get_symbolic_partials,
    numerical_partial_derivative,
    numerical_second_partial_derivative,
)
from shared.expression_engine import _mp, _normalize_expression, safe_eval
from shared.uncertainty import UncertainValue


def _normalize_header_to_symbol(header: str, index: int) -> str:
    base = re.sub(r"[^0-9A-Za-z_]", "_", header.strip()) or f"col_{index + 1}"
    if base[0].isdigit():
        base = f"c_{base}"
    return base.strip("_") or f"col_{index + 1}"


def _apply_aliases(formula: str, alias_map: dict[str, str]) -> str:
    result = formula
    for alias in sorted(alias_map.keys(), key=len, reverse=True):
        result = re.sub(r"\b" + re.escape(alias) + r"\b", alias_map[alias], result)
    return result


def _extract_referenced_names(expression: str) -> set[str] | None:
    if expression is None:
        return None
    expr = (expression or "").strip()
    if not expr:
        return set()
    normalized = _normalize_expression(expr)
    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError:
        return None

    class _NameVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.names: set[str] = set()

        def visit_Name(self, node: ast.Name) -> None:
            self.names.add(node.id)

        def visit_Call(self, node: ast.Call) -> None:
            for arg in node.args:
                self.visit(arg)
            for kw in node.keywords:
                if kw.value is not None:
                    self.visit(kw.value)

    visitor = _NameVisitor()
    visitor.visit(tree.body)
    return visitor.names


def detect_used_error_propagation_inputs(
    headers: list[str],
    constants: dict[str, UncertainValue],
    formula_str: str,
) -> tuple[list[str], list[str]]:
    canonical_vars: list[str] = []
    alias_map: dict[str, str] = {}
    seen: set[str] = set()
    for i, header in enumerate(headers):
        symbol = _normalize_header_to_symbol(header, i)
        base = symbol
        counter = 2
        while symbol in seen:
            symbol = f"{base}_{counter}"
            counter += 1
        seen.add(symbol)
        canonical_vars.append(symbol)
        alias_map[f"x{i + 1}"] = symbol

    rewritten_formula = _apply_aliases(formula_str or "", alias_map)
    referenced = _extract_referenced_names(rewritten_formula)
    if referenced is None:
        return list(headers), list(constants.keys())

    used_headers = [headers[i] for i, symbol in enumerate(canonical_vars) if symbol in referenced]
    used_constants = [name for name in constants.keys() if name in referenced]
    return used_headers, used_constants


def apply_formula_to_data(
    headers: list[str],
    parsed_data: list[list[UncertainValue]],
    constants: dict[str, UncertainValue],
    formula_str: str,
    verbose: bool = False,
    warnings: list[str] | None = None,
    return_components: bool = False,
    *,
    propagation_method: str = "taylor",
    propagation_order: int = 1,
    mc_samples: int | None = None,
    mc_seed: int | None = None,
) -> list[UncertainValue]:
    results: list[UncertainValue] = []
    canonical_vars: list[str] = []
    alias_map: dict[str, str] = {}
    seen: set[str] = set()
    for i, header in enumerate(headers):
        symbol = _normalize_header_to_symbol(header, i)
        base = symbol
        counter = 2
        while symbol in seen:
            symbol = f"{base}_{counter}"
            counter += 1
        seen.add(symbol)
        canonical_vars.append(symbol)
        alias_map[f"x{i + 1}"] = symbol

    rewritten_formula = _apply_aliases(formula_str, alias_map)
    if warnings is not None:
        _append_propagation_warnings(
            warnings,
            formula_str=formula_str,
            rewritten_formula=rewritten_formula,
            propagation_method=propagation_method,
            propagation_order=propagation_order,
            mc_samples=mc_samples,
            mc_seed=mc_seed,
        )

    referenced = _extract_referenced_names(rewritten_formula)
    if referenced is None:
        used_header_indices = list(range(len(headers)))
        used_const_names = list(constants.keys())
    else:
        used_header_indices = [i for i, symbol in enumerate(canonical_vars) if symbol in referenced]
        used_const_names = [name for name in constants.keys() if name in referenced]

    canonical_vars_used = [canonical_vars[i] for i in used_header_indices]
    display_labels_used = [headers[i] for i in used_header_indices]
    for const_name in used_const_names:
        canonical_vars_used.append(const_name)
        display_labels_used.append(const_name)
    label_by_canonical = dict(zip(canonical_vars_used, display_labels_used))
    const_values_used = [constants[name].value for name in used_const_names]
    const_uncertainties_used = [constants[name].uncertainty for name in used_const_names]

    first_error: str | None = None
    for row_num, row_data in enumerate(parsed_data):
        row_values = [row_data[idx].value for idx in used_header_indices]
        row_uncertainties = [row_data[idx].uncertainty for idx in used_header_indices]
        row_values.extend(const_values_used)
        row_uncertainties.extend(const_uncertainties_used)
        try:
            components: list[tuple[str, mp.mpf]] | None = None
            if return_components:
                propagated = error_propagation(
                    rewritten_formula,
                    canonical_vars_used,
                    row_values,
                    row_uncertainties,
                    warnings,
                    True,
                    method=propagation_method,
                    order=propagation_order,
                    mc_samples=mc_samples,
                    mc_seed=mc_seed,
                )
                result_value, result_uncertainty, components = cast(
                    tuple[mp.mpf, mp.mpf, list[tuple[str, mp.mpf]]],
                    propagated,
                )
            else:
                propagated = error_propagation(
                    rewritten_formula,
                    canonical_vars_used,
                    row_values,
                    row_uncertainties,
                    warnings,
                    False,
                    method=propagation_method,
                    order=propagation_order,
                    mc_samples=mc_samples,
                    mc_seed=mc_seed,
                )
                result_value, result_uncertainty = cast(
                    tuple[mp.mpf, mp.mpf],
                    propagated,
                )
            contributions_map: dict[str, mp.mpf] | None = None
            if return_components and components:
                contributions_map = {}
                for name, contrib_var in components:
                    label = label_by_canonical.get(name, name)
                    try:
                        contrib_val = _mp(contrib_var)
                    except Exception:
                        contrib_val = contrib_var
                    contributions_map[label] = contributions_map.get(label, mp.mpf("0")) + contrib_val
            results.append(UncertainValue(result_value, result_uncertainty, contributions=contributions_map))
            if verbose:
                print(f"Row {row_num + 1}: {results[-1]}")
        except Exception as exc:
            zh_e, en_e = _split_dual(str(exc))
            message = _dual_msg(
                f"第 {row_num + 1} 行公式计算失败: {zh_e}",
                f"Row {row_num + 1} formula evaluation failed: {en_e}",
            )
            if first_error is None:
                first_error = message
            results.append(UncertainValue(0, 0))
    if first_error:
        raise ValueError(first_error)
    return results


def _append_propagation_warnings(
    warnings: list[str],
    *,
    formula_str: str,
    rewritten_formula: str,
    propagation_method: str,
    propagation_order: int,
    mc_samples: int | None,
    mc_seed: int | None,
) -> None:
    if rewritten_formula != formula_str:
        warnings.append(
            f"公式变量已从旧式 x1/x2 替换为列名/规范名: {rewritten_formula} / "
            f"Formula variables rewritten to canonical names: {rewritten_formula}"
        )
    method_key = (propagation_method or "taylor").strip().lower()
    if method_key in {"mc", "montecarlo", "monte_carlo", "monte-carlo"}:
        method_key = "monte_carlo"
    if method_key == "monte_carlo":
        samples = int(mc_samples) if mc_samples is not None else 5000
        seed_text = str(int(mc_seed)) if mc_seed is not None else "随机"
        seed_text_en = str(int(mc_seed)) if mc_seed is not None else "random"
        warnings.append(
            _dual_msg(
                f"误差传递方法：Monte Carlo（输出为样本均值 ± 标准差；样本数={samples}，种子={seed_text}）。",
                f"Propagation method: Monte Carlo (returns sample mean ± std; samples={samples}, seed={seed_text_en}).",
            )
        )
        return
    try:
        order_val = int(propagation_order or 1)
    except Exception:
        order_val = 1
    if order_val >= 2:
        warnings.append(
            _dual_msg(
                f"误差传递方法：{order_val} 阶 Taylor（输出包含均值修正；包含二阶偏导 Hessian 贡献）。",
                f"Propagation method: Taylor order {order_val} (value includes mean correction; includes Hessian contributions).",
            )
        )


def error_propagation(
    formula_str: str,
    variables: list[str],
    values: list[mp.mpf],
    uncertainties: list[mp.mpf],
    warnings: list[str] | None = None,
    return_components: bool = False,
    *,
    method: str = "taylor",
    order: int = 1,
    mc_samples: int | None = None,
    mc_seed: int | None = None,
) -> tuple[mp.mpf, mp.mpf] | tuple[mp.mpf, mp.mpf, list[tuple[str, mp.mpf]]]:
    method_key = (method or "taylor").strip().lower()
    if method_key in {"mc", "montecarlo", "monte_carlo", "monte-carlo"}:
        method_key = "monte_carlo"
    else:
        method_key = "taylor"
    try:
        order_val = int(order or 1)
    except Exception:
        order_val = 1
    order_val = max(1, order_val)
    if not variables:
        raise ValueError(_dual_msg("误差传递需要至少一个输入变量。", "Error propagation requires at least one input variable."))
    if len(values) != len(variables) or len(uncertainties) != len(variables):
        raise ValueError(_dual_msg("公式输入的变量/数值/不确定度数量不匹配。", "Mismatched variables/values/uncertainties lengths."))
    sigma_vec = [_safe_sigma(sigma) for sigma in uncertainties]
    if method_key == "monte_carlo":
        return _monte_carlo_propagation(
            formula_str,
            variables,
            values,
            sigma_vec,
            warnings,
            return_components,
            samples=mc_samples,
            seed=mc_seed,
        )
    if order_val not in {1, 2}:
        raise ValueError(
            _dual_msg(
                f"当前仅支持 1 或 2 阶误差传递（收到阶数={order_val}）。建议改用 Monte Carlo。",
                f"Currently only order 1 or 2 is supported (got order={order_val}). Please use Monte Carlo.",
            )
        )
    result_value = _evaluate_formula(formula_str, dict(zip(variables, values)))
    total_variance = mp.mpf("0")
    contrib_map: dict[str, mp.mpf] = {}
    symbolic_partials = _get_symbolic_partials(formula_str, list(variables))
    for i, name in enumerate(variables):
        sigma = sigma_vec[i]
        if sigma <= 0:
            continue
        partial_derivative = None
        if symbolic_partials and i < len(symbolic_partials):
            sym_func = symbolic_partials[i]
            if sym_func is not None:
                try:
                    partial_derivative = mp.mpf(sym_func(*values))
                except Exception:
                    partial_derivative = None
        if partial_derivative is None:
            partial_derivative = numerical_partial_derivative(formula_str, variables, values, i, h=None)
        contrib_var = (partial_derivative * sigma) ** 2
        total_variance += contrib_var
        contrib_map[name] = contrib_map.get(name, mp.mpf("0")) + mp.mpf(contrib_var)
    if order_val >= 2:
        result_value, total_variance = _apply_second_order(
            formula_str,
            variables,
            values,
            sigma_vec,
            contrib_map,
            result_value,
            total_variance,
        )
    result_uncertainty = mp.sqrt(total_variance)
    if return_components:
        return result_value, result_uncertainty, [(name, value) for name, value in contrib_map.items() if value != 0]
    return result_value, result_uncertainty


def _safe_sigma(sigma: object) -> mp.mpf:
    try:
        return mp.fabs(mp.mpf(sigma))
    except Exception:
        return mp.mpf("0")


def _evaluate_formula(formula_str: str, scope: dict[str, object]) -> mp.mpf:
    try:
        return mp.mpf(safe_eval(formula_str, scope))
    except Exception as exc:
        zh_e, en_e = _split_dual(str(exc))
        raise ValueError(
            _dual_msg(f"无法计算公式 '{formula_str}': {zh_e}", f"Cannot evaluate formula '{formula_str}': {en_e}")
        ) from exc


def _monte_carlo_propagation(
    formula_str: str,
    variables: list[str],
    values: list[mp.mpf],
    sigma_vec: list[mp.mpf],
    warnings: list[str] | None,
    return_components: bool,
    *,
    samples: int | None,
    seed: int | None,
) -> tuple[mp.mpf, mp.mpf] | tuple[mp.mpf, mp.mpf, list[tuple[str, mp.mpf]]]:
    sample_count = int(samples) if samples is not None else 5000
    if sample_count < 100:
        raise ValueError(_dual_msg("Monte Carlo 样本数至少为 100。", "Monte Carlo sample count must be at least 100."))
    nominal_value = _evaluate_formula(formula_str, {name: mp.mpf(values[idx]) for idx, name in enumerate(variables)})
    if all(sigma <= 0 for sigma in sigma_vec):
        return (nominal_value, mp.mpf("0"), []) if return_components else (nominal_value, mp.mpf("0"))
    rng = random.Random(int(seed) if seed is not None else None)
    mean = mp.mpf("0")
    m2 = mp.mpf("0")
    used = 0
    rejected = 0
    for _ in range(sample_count):
        sample_scope = {}
        for idx, name in enumerate(variables):
            sig = sigma_vec[idx]
            sample_scope[name] = mp.mpf(values[idx]) + sig * mp.mpf(_randn(rng)) if sig > 0 else mp.mpf(values[idx])
        try:
            y = mp.mpf(safe_eval(formula_str, sample_scope))
        except Exception:
            rejected += 1
            continue
        used += 1
        delta = y - mean
        mean += delta / used
        m2 += delta * (y - mean)
    if used < max(10, sample_count // 5):
        raise ValueError(
            _dual_msg(
                f"Monte Carlo 有效样本过少（{used}/{sample_count}），公式可能存在定义域问题。",
                f"Too few valid Monte Carlo samples ({used}/{sample_count}); the formula may have domain issues.",
            )
        )
    if rejected and warnings is not None:
        warnings.append(
            _dual_msg(
                f"Monte Carlo 采样中有 {rejected}/{sample_count} 次公式求值失败（已忽略）。",
                f"{rejected}/{sample_count} Monte Carlo evaluations failed and were skipped.",
            )
        )
    variance = m2 / (used - 1) if used > 1 else mp.mpf("0")
    std = mp.sqrt(variance) if variance >= 0 else mp.nan
    return (mean, std, []) if return_components else (mean, std)


def _randn(rng: random.Random) -> float:
    u1 = rng.random()
    u2 = rng.random()
    if u1 <= 0.0:
        u1 = 1e-300
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _apply_second_order(
    formula_str: str,
    variables: list[str],
    values: list[mp.mpf],
    sigma_vec: list[mp.mpf],
    contrib_map: dict[str, mp.mpf],
    result_value: mp.mpf,
    total_variance: mp.mpf,
) -> tuple[mp.mpf, mp.mpf]:
    mean_shift = mp.mpf("0")
    hessian = _get_symbolic_hessian(formula_str, list(variables))
    half = mp.mpf("0.5")
    for i, name_i in enumerate(variables):
        sigma_i = sigma_vec[i]
        if sigma_i <= 0:
            continue
        for j, _name_j in enumerate(variables):
            sigma_j = sigma_vec[j]
            if sigma_j <= 0:
                continue
            second = None
            if hessian and i < len(hessian) and j < len(hessian[i]):
                func = hessian[i][j]
                if func is not None:
                    try:
                        second = mp.mpf(func(*values))
                    except Exception:
                        second = None
            if second is None:
                second = numerical_second_partial_derivative(
                    formula_str,
                    list(variables),
                    list(values),
                    i,
                    j,
                    hi=None,
                    hj=None,
                )
            if i == j:
                mean_shift += half * second * (sigma_i**2)
            contrib2 = half * (second * sigma_i * sigma_j) ** 2
            total_variance += contrib2
            contrib_map[name_i] = contrib_map.get(name_i, mp.mpf("0")) + mp.mpf(contrib2)
    return mp.mpf(result_value) + mean_shift, total_variance
