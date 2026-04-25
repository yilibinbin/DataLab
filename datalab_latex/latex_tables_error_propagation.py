from __future__ import annotations

import ast
import math
import random
import re
from typing import Literal, overload

from mpmath import mp

from shared.bilingual import _dual_msg, _split_dual

from .derivatives import (
    _get_symbolic_hessian,
    _get_symbolic_partials,
    numerical_partial_derivative,
    numerical_second_partial_derivative,
)
from .expression_engine import _mp, _normalize_expression, format_latex_formula, safe_eval
from .latex_formatting import _format_value_for_latex_file, _siunitx_column_spec, calculate_dcolumn_format_for_column
from .latex_tables_common import (
    _apply_aliases,
    _build_standalone_preamble,
    _estimate_page_geometry,
    _needs_cjk_support,
    _normalize_header_to_symbol,
    _normalize_input_lines,
    _normalize_numeric_token,
    _normalize_table_segments,
    _string_length_hint,
)


class UncertainValue:
    """Class to represent a value with uncertainty."""

    # ``_mp()`` (datalab_latex.expression_engine) accepts mp.mpf, int, float,
    # or any value whose ``str()`` produces a number string. We name the
    # union so the public surface stops looking like ``object`` while still
    # matching what the body actually requires.
    def __init__(
        self,
        value: mp.mpf | int | float | str,
        uncertainty: mp.mpf | int | float | str,
        uncertainty_digits: int | None = None,
        contributions: dict[str, mp.mpf] | None = None,
    ) -> None:
        self.value: mp.mpf = _mp(value)
        self.uncertainty: mp.mpf = _mp(uncertainty)
        # Keep the significant digits of the uncertainty as provided by the user
        self.uncertainty_digits: int | None = uncertainty_digits
        # Optional variance contributions per variable/constant name
        self.contributions: dict[str, mp.mpf] | None = contributions or None

    def __str__(self) -> str:
        return f"{self.value} ± {self.uncertainty}"

    def __repr__(self) -> str:
        return f"UncertainValue({self.value}, {self.uncertainty}, digits={self.uncertainty_digits})"


def parse_uncertainty_format(number_str: str, lang: str = "en") -> UncertainValue:
    """Parse a number in format 1.23(1)[-2] to value and uncertainty."""
    number_str = number_str.strip()

    # Normalize special Unicode minus signs to standard hyphen
    number_str = number_str.replace("−", "-")  # U+2212 MINUS SIGN to U+002D HYPHEN-MINUS

    pattern = (
        r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
        r"(?:\([+-]?(?:\d+(?:\.\d*)?|\.\d+)\))?"
        r"(?:[eE][+-]?\d+)?"
        r"(?:\[[+-]?\d+\])?$"
    )

    def _err(msg_en: str, msg_zh: str) -> str:
        return msg_zh if lang == "zh" else msg_en

    if not re.fullmatch(pattern, number_str):
        raise ValueError(
            _err(
                f"Unrecognized uncertainty format: {number_str}",
                f"无法识别的不确定度格式: {number_str}",
            )
        )

    exponent = 0
    if "[" in number_str and "]" in number_str:
        bracket_match = re.search(r"\[([+-]?\d+)\]", number_str)
        if bracket_match:
            exponent = int(bracket_match.group(1))
            number_str = number_str[: bracket_match.start()] + number_str[bracket_match.end() :]

    uncertainty_digits: int | None = None

    def _sig_digits_from_text(text: str) -> int:
        raw = (text or "").strip()
        if not raw:
            return 1
        if raw.startswith(("+", "-")):
            raw = raw[1:]
        if "e" in raw.lower():
            mantissa, _exp = raw.lower().split("e", 1)
        else:
            mantissa = raw
        mantissa = mantissa.replace(".", "").lstrip("0")
        return max(1, len(mantissa))

    uncertainty = mp.mpf("0")
    if "(" in number_str and ")" in number_str:
        paren_match = re.search(r"\(([+-]?(?:\d+(?:\.\d*)?|\.\d+))\)", number_str)
        if paren_match:
            paren_text = paren_match.group(1)
            uncertainty_digits = _sig_digits_from_text(paren_text)
            mantissa_str = number_str[: paren_match.start()]
            suffix = number_str[paren_match.end() :]

            if "." in paren_text or "e" in paren_text.lower():
                uncertainty = _mp(paren_text)
            else:
                unc_value = _mp(paren_text)
                if "." in mantissa_str:
                    decimal_pos = mantissa_str.find(".")
                    digits_after_decimal = len(mantissa_str) - decimal_pos - 1
                    uncertainty = unc_value * mp.power(10, -digits_after_decimal)
                else:
                    uncertainty = unc_value

            number_str = mantissa_str + suffix

    value = _mp(number_str)

    if exponent != 0:
        factor = mp.power(10, exponent)
        value *= factor
        uncertainty *= factor

    return UncertainValue(value, uncertainty, uncertainty_digits=uncertainty_digits)


def _process_uncertainty_lines(
    lines: list[str], verbose: bool = False
) -> tuple[list[str], list[list[UncertainValue]]]:
    lines = _normalize_input_lines(lines)
    if len(lines) < 2:
        raise ValueError("Input must contain at least a header and one data row")

    header_line = lines[0].strip()
    headers = header_line.split()

    if verbose:
        print("Found headers: {0}".format(headers))
        print("Processing {0} data rows...".format(len(lines) - 1))

    parsed_data: list[list[UncertainValue]] = []

    for line_num, raw_line in enumerate(lines[1:], 2):
        line = raw_line.strip()
        if not line:
            continue

        values = [_normalize_numeric_token(part) for part in line.split()]
        row_data: list[UncertainValue] = []
        for value_str in values:
            try:
                if "(" in value_str or "[" in value_str:
                    uncertain_value = parse_uncertainty_format(value_str)
                else:
                    uncertain_value = UncertainValue(float(value_str), 0.0)
                row_data.append(uncertain_value)
            except Exception as e:
                message = f"Cannot parse value '{value_str}' on line {line_num}: {e}"
                if verbose:
                    print(f"Warning: {message}")
                raise ValueError(message) from e

        if row_data:
            parsed_data.append(row_data)
            if verbose:
                print(f"Row {line_num - 1}: Parsed {len(row_data)} values")

    if verbose:
        print("Successfully processed {0} data rows".format(len(parsed_data)))

    return headers, parsed_data


def process_uncertainty_data_file(
    filename: str, verbose: bool = False
) -> tuple[list[str], list[list[UncertainValue]]]:
    """Process a data file containing values with uncertainties in the format 1.23(1)[-2]."""
    with open(filename, "r") as f:
        lines = f.readlines()
    return _process_uncertainty_lines(lines, verbose)


def process_uncertainty_string(
    content: str, verbose: bool = False
) -> tuple[list[str], list[list[UncertainValue]]]:
    """Process an in-memory string that follows the same format as the uncertainty data file."""
    if not content or not content.strip():
        raise ValueError("输入数据为空，无法解析。")
    return _process_uncertainty_lines(content.splitlines(), verbose)


def _process_constants_lines(
    lines: list[str], verbose: bool = False
) -> dict[str, UncertainValue]:
    constants: dict[str, UncertainValue] = {}
    for line_num, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split(None, 1)
        if len(parts) != 2:
            if verbose:
                print(f"Warning: Invalid format on line {line_num}: {line}")
            continue

        const_name, value_str = parts
        try:
            uncertain_value = parse_uncertainty_format(value_str)
            constants[const_name] = uncertain_value
            if verbose:
                print(f"Loaded constant {const_name}: {uncertain_value}")
        except Exception as e:
            if verbose:
                print(f"Warning: Cannot parse constant '{const_name}' on line {line_num}: {e}")
            continue
    return constants


def process_constants_file(filename: str, verbose: bool = False) -> dict[str, UncertainValue]:
    """Process a constants file containing constant values with uncertainties."""
    try:
        with open(filename, "r") as f:
            lines = f.readlines()
    except FileNotFoundError:
        if verbose:
            print(f"Constants file '{filename}' not found, proceeding without constants")
        return {}
    return _process_constants_lines(lines, verbose)


def process_constants_string(content: str, verbose: bool = False) -> dict[str, UncertainValue]:
    """Process constants supplied via a string buffer."""
    if not content or not content.strip():
        return {}
    return _process_constants_lines(content.splitlines(), verbose)


def _extract_referenced_names(expression: str) -> set[str] | None:
    """
    Return a set of referenced identifier names in the expression (excluding called function names).

    Returns None if the expression cannot be parsed.
    """
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
    """Detect referenced input symbols (data columns + constants) for error propagation."""
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
        alias_map[f"x{i+1}"] = symbol

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
    """Apply a formula to each row of data with error propagation."""
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
        alias_map[f"x{i+1}"] = symbol  # backwards compatibility

    rewritten_formula = _apply_aliases(formula_str, alias_map)
    if warnings is not None:
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
        else:
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
    label_by_canonical = {canon: label for canon, label in zip(canonical_vars_used, display_labels_used)}

    const_values_used = [constants[name].value for name in used_const_names]
    const_uncertainties_used = [constants[name].uncertainty for name in used_const_names]

    if verbose:
        print(f"Variables: {canonical_vars_used}")
        print(f"Constants: {used_const_names}")
        print(f"Formula: {rewritten_formula}")

    first_error: str | None = None
    for row_num, row_data in enumerate(parsed_data):
        row_values = []
        row_uncertainties = []

        for idx in used_header_indices:
            uncertain_value = row_data[idx]
            row_values.append(uncertain_value.value)
            row_uncertainties.append(uncertain_value.uncertainty)

        row_values.extend(const_values_used)
        row_uncertainties.extend(const_uncertainties_used)

        try:
            # Mypy --strict can't narrow on a runtime bool, so dispatch
            # each overload explicitly. ``components`` stays None on the
            # False branch.
            components: list[tuple[str, mp.mpf]] | None = None
            if return_components:
                result_value, result_uncertainty, components = error_propagation(
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
            else:
                result_value, result_uncertainty = error_propagation(
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

            result = UncertainValue(result_value, result_uncertainty, contributions=contributions_map)
            results.append(result)

            if verbose:
                print(f"Row {row_num + 1}: {result}")

        except Exception as e:
            zh_e, en_e = _split_dual(str(e))
            message = _dual_msg(
                f"第 {row_num + 1} 行公式计算失败: {zh_e}",
                f"Row {row_num + 1} formula evaluation failed: {en_e}",
            )
            if verbose:
                print(message)
            if first_error is None:
                first_error = message
            results.append(UncertainValue(0.0, 0.0))  # Add placeholder

    if first_error:
        raise ValueError(first_error)
    return results


@overload
def error_propagation(
    formula_str: str,
    variables: list[str],
    values: list[mp.mpf],
    uncertainties: list[mp.mpf],
    warnings: list[str] | None = ...,
    return_components: Literal[False] = ...,
    *,
    method: str = ...,
    order: int = ...,
    mc_samples: int | None = ...,
    mc_seed: int | None = ...,
) -> tuple[mp.mpf, mp.mpf]: ...


@overload
def error_propagation(
    formula_str: str,
    variables: list[str],
    values: list[mp.mpf],
    uncertainties: list[mp.mpf],
    warnings: list[str] | None,
    return_components: Literal[True],
    *,
    method: str = ...,
    order: int = ...,
    mc_samples: int | None = ...,
    mc_seed: int | None = ...,
) -> tuple[mp.mpf, mp.mpf, list[tuple[str, mp.mpf]]]: ...


# Keyword-form of the components overload — supports the typical
# ``error_propagation(..., return_components=True)`` site without
# forcing the caller to spell out ``warnings`` positionally first.
@overload
def error_propagation(
    formula_str: str,
    variables: list[str],
    values: list[mp.mpf],
    uncertainties: list[mp.mpf],
    warnings: list[str] | None = ...,
    *,
    return_components: Literal[True],
    method: str = ...,
    order: int = ...,
    mc_samples: int | None = ...,
    mc_seed: int | None = ...,
) -> tuple[mp.mpf, mp.mpf, list[tuple[str, mp.mpf]]]: ...


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
    """Propagate uncertainties through a formula (Taylor or Monte Carlo)."""
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

    sigma_vec: list[mp.mpf] = []
    for sigma in uncertainties:
        try:
            sigma_vec.append(mp.fabs(mp.mpf(sigma)))
        except Exception:
            sigma_vec.append(mp.mpf("0"))

    if method_key == "monte_carlo":
        samples = int(mc_samples) if mc_samples is not None else 5000
        if samples < 100:
            raise ValueError(_dual_msg("Monte Carlo 样本数至少为 100。", "Monte Carlo sample count must be at least 100."))

        rng = random.Random(int(mc_seed) if mc_seed is not None else None)

        nominal_scope = {name: mp.mpf(values[idx]) for idx, name in enumerate(variables)}
        try:
            nominal_value = mp.mpf(safe_eval(formula_str, nominal_scope))
        except Exception as exc:
            zh_e, en_e = _split_dual(str(exc))
            raise ValueError(
                _dual_msg(f"无法计算公式 '{formula_str}': {zh_e}", f"Cannot evaluate formula '{formula_str}': {en_e}")
            ) from exc

        if all(sigma <= 0 for sigma in sigma_vec):
            if return_components:
                return nominal_value, mp.mpf("0"), []
            return nominal_value, mp.mpf("0")

        def _randn() -> float:
            u1 = rng.random()
            u2 = rng.random()
            if u1 <= 0.0:
                u1 = 1e-300
            return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

        mean = mp.mpf("0")
        m2 = mp.mpf("0")
        used = 0
        rejected = 0
        for _ in range(samples):
            sample_scope: dict[str, object] = {}
            for idx, name in enumerate(variables):
                mu = values[idx]
                sig = sigma_vec[idx]
                if sig > 0:
                    sample_scope[name] = mp.mpf(mu) + sig * mp.mpf(_randn())
                else:
                    sample_scope[name] = mp.mpf(mu)
            try:
                y = mp.mpf(safe_eval(formula_str, sample_scope))
            except Exception:
                rejected += 1
                continue
            used += 1
            delta = y - mean
            mean += delta / used
            m2 += delta * (y - mean)

        if used < max(10, samples // 5):
            raise ValueError(
                _dual_msg(
                    f"Monte Carlo 有效样本过少（{used}/{samples}），公式可能存在定义域问题。",
                    f"Too few valid Monte Carlo samples ({used}/{samples}); the formula may have domain issues.",
                )
            )
        if rejected and warnings is not None:
            warnings.append(
                _dual_msg(
                    f"Monte Carlo 采样中有 {rejected}/{samples} 次公式求值失败（已忽略）。",
                    f"{rejected}/{samples} Monte Carlo evaluations failed and were skipped.",
                )
            )
        variance = m2 / (used - 1) if used > 1 else mp.mpf("0")
        std = mp.sqrt(variance) if variance >= 0 else mp.nan
        if return_components:
            return mean, std, []
        return mean, std

    if order_val not in {1, 2}:
        raise ValueError(
            _dual_msg(
                f"当前仅支持 1 或 2 阶误差传递（收到阶数={order_val}）。建议改用 Monte Carlo。",
                f"Currently only order 1 or 2 is supported (got order={order_val}). Please use Monte Carlo.",
            )
        )

    var_dict = dict(zip(variables, values))
    try:
        result_value = safe_eval(formula_str, var_dict)
    except Exception as exc:
        zh_e, en_e = _split_dual(str(exc))
        raise ValueError(
            _dual_msg(f"无法计算公式 '{formula_str}': {zh_e}", f"Cannot evaluate formula '{formula_str}': {en_e}")
        ) from exc

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

        try:
            result_value = mp.mpf(result_value) + mean_shift
        except Exception:
            result_value = result_value + mean_shift

    result_uncertainty = mp.sqrt(total_variance)
    if return_components:
        contributions: list[tuple[str, mp.mpf]] = []
        for name in variables:
            value = contrib_map.get(name)
            if value is None:
                continue
            if value != 0:
                contributions.append((name, value))
        return result_value, result_uncertainty, contributions
    return result_value, result_uncertainty


def _error_table_row_strings(
    headers: list[str],  # noqa: ARG001 - retained for backward compatibility
    formatted_columns: list[list[str]],
    formatted_result_column: list[str],
    start_row: int,
    end_row: int,
) -> list[str]:
    num_cols = len(formatted_columns)
    rows = []
    for local_index, row_index in enumerate(range(start_row, end_row), 1):
        cells = [str(local_index)]
        for col_idx in range(num_cols):
            cells.append(formatted_columns[col_idx][row_index])
        cells.append(formatted_result_column[row_index])
        rows.append("\t\t\t" + " & ".join(cells) + " \\\\")
    return rows


def generate_error_propagation_table(
    headers: list[str],
    parsed_data: list[list[UncertainValue]],
    results: list[UncertainValue],
    constants: dict[str, UncertainValue],
    formula_str: str,
    output_filename: str,
    caption: str | None = None,
    verbose: bool = False,
    use_dcolumn: bool = False,
    table_segments: list[tuple[int, int]] | None = None,
    precision: int | None = None,
    result_uncertainty_digits: int | None = None,
    used_columns: list[str] | None = None,
    latex_group_size: int = 3,
) -> None:
    """Generate a LaTeX table for error propagation results."""
    if used_columns is None:
        header_indices = list(range(len(headers)))
    else:
        used_set = {name.lower().strip() for name in used_columns if name}
        header_indices = [idx for idx, name in enumerate(headers) if name.lower().strip() in used_set]
        if not header_indices and used_set:
            header_indices = list(range(len(headers)))

    column_lengths = [len(str(max(1, len(parsed_data)))) + 1]
    for idx in header_indices:
        header = headers[idx]
        column_lengths.append(max(4, _string_length_hint(header)))
    column_lengths.append(6)
    formatted_columns: list[list[str]] = [[] for _ in header_indices]
    formatted_result_column: list[str] = []
    for _, (row_data, result) in enumerate(zip(parsed_data, results), 1):
        for out_idx, src_idx in enumerate(header_indices):
            uncertain_value = row_data[src_idx]
            unc_digits = getattr(uncertain_value, "uncertainty_digits", None)
            formatted_value = _format_value_for_latex_file(
                value=uncertain_value.value,
                sigma=uncertain_value.uncertainty,
                use_dcolumn=use_dcolumn,
                latex_input_decimals=precision if precision is not None else None,
                is_input=True,
                latex_group_size=latex_group_size,
                uncertainty_digits=unc_digits,
            )
            formatted_columns[out_idx].append(formatted_value)
            column_lengths[1 + out_idx] = max(column_lengths[1 + out_idx], _string_length_hint(formatted_value))
        result_formatted = _format_value_for_latex_file(
            value=result.value,
            sigma=result.uncertainty,
            use_dcolumn=use_dcolumn,
            latex_input_decimals=precision if precision is not None else None,
            is_input=False,
            latex_group_size=latex_group_size,
            uncertainty_digits=result_uncertainty_digits,
        )
        formatted_result_column.append(result_formatted)
        column_lengths[-1] = max(column_lengths[-1], _string_length_hint(result_formatted))
    page_w, _ = _estimate_page_geometry(column_lengths, len(parsed_data) + 6)
    cjk_segments = [caption if caption else "", " ".join(headers), formula_str or ""]
    if constants:
        cjk_segments.append(" ".join(constants.keys()))
    needs_cjk = _needs_cjk_support(*cjk_segments)
    latex_content = _build_standalone_preamble(
        page_w,
        include_dcolumn=use_dcolumn,
        needs_cjk=needs_cjk,
        latex_group_size=latex_group_size,
    )

    header_cols = ["$n$"]
    for src_idx in header_indices:
        h = headers[src_idx]
        clean_header = h.replace("$", "")
        header_cols.append(f"\\multicolumn{{1}}{{c}}{{{clean_header}}}")
    header_cols.append("\\multicolumn{1}{c}{Result}")
    header_row = "\t\t\t" + " & ".join(header_cols) + " \\\\"

    segments = _normalize_table_segments(len(parsed_data), table_segments)
    for block_index, (start_row, end_row) in enumerate(segments, 1):
        if use_dcolumn:
            data_formats = [
                calculate_dcolumn_format_for_column(
                    col_data[start_row:end_row],
                    f"data_col_{i}",
                )
                for i, col_data in enumerate(formatted_columns)
            ]
            result_format = calculate_dcolumn_format_for_column(
                formatted_result_column[start_row:end_row],
                "result_col",
            )
            table_format = "c " + " ".join(data_formats) + " " + result_format
        else:
            data_formats = [_siunitx_column_spec(col_data[start_row:end_row]) for col_data in formatted_columns]
            result_format = _siunitx_column_spec(formatted_result_column[start_row:end_row])
            table_format = "c " + " ".join(data_formats) + " " + result_format
        if verbose:
            print(f"LaTeX table formats (block {block_index}/{len(segments)}): {table_format}")

        latex_content.extend(
            [
                "\\begin{table}[!ht]",
                "\t\\centering",
                "\t\\caption{{{0}}}\\label{{tab:error_propagation_{1}}}".format(
                    caption
                    if caption
                    else "Error propagation results using formula: $" + format_latex_formula(formula_str) + "$",
                    block_index,
                ),
                "\t\\begin{threeparttable}",
                "\t\t\\begin{{tabular}}{{{0}}}".format(table_format),
                "\t\t\t\\toprule",
                header_row,
                "\t\t\t\\midrule",
            ]
        )

        latex_content.extend(
            _error_table_row_strings(
                headers,
                formatted_columns,
                formatted_result_column,
                start_row,
                end_row,
            )
        )

        latex_content.extend(
            [
                "\t\t\t\\bottomrule",
                "\t\t\\end{tabular}",
                "\t\t\\begin{tablenotes}",
                "\t\t\t\\footnotesize",
                "\t\t\t\\item Formula used: $" + format_latex_formula(formula_str) + "$",
            ]
        )

        if constants:
            latex_content.append("\t\t\t\\item Constants used:")
            for const_name, const_value in constants.items():
                const_unc_digits = getattr(const_value, "uncertainty_digits", None)
                const_formatted = _format_value_for_latex_file(
                    value=const_value.value,
                    sigma=const_value.uncertainty,
                    use_dcolumn=use_dcolumn,
                    latex_input_decimals=precision if precision is not None else None,
                    is_input=True,
                    latex_group_size=latex_group_size,
                    uncertainty_digits=const_unc_digits,
                )
                latex_content.append(f"\t\t\t\\item ${const_name} = {const_formatted}$")

        latex_content.extend(
            [
                "\t\t\\end{tablenotes}",
                "\t\\end{threeparttable}",
                "\\end{table}",
                "",
            ]
        )

    latex_content.append("\\end{document}")

    with open(output_filename, "w") as f:
        f.write("\n".join(latex_content))

    if verbose:
        format_type = "dcolumn format with number spacing" if use_dcolumn else "regular format with spacing"
        print("Error propagation LaTeX table ({0}) written to: {1}".format(format_type, output_filename))
        print("Total rows: {0}".format(len(parsed_data)))


__all__ = [
    "UncertainValue",
    "apply_formula_to_data",
    "detect_used_error_propagation_inputs",
    "error_propagation",
    "generate_error_propagation_table",
    "parse_uncertainty_format",
    "process_constants_file",
    "process_constants_string",
    "process_uncertainty_data_file",
    "process_uncertainty_string",
]
