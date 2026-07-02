from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeAlias

from mpmath import mp

from extrapolation_methods import (
    PowerLawComputationError,
    PowerLawConfig,
    SequenceAcceleratorConfig,
    SequenceAccelerationError,
    apply_sequence_accelerator,
    extrapolate_power_law,
)
from shared.bilingual import _dual_msg, _split_dual
from shared.expression_engine import _mp, _normalize_expression, safe_eval
from shared.formula_defaults import DEFAULT_THREE_POINT_FORMULA
from shared.precision import precision_guard

_MpInput: TypeAlias = "mp.mpf | int | float | str"


@dataclass
class ExtrapolationResult:
    """Wrapper for extrapolated values with optional metadata."""

    value: mp.mpf
    uncertainty: mp.mpf
    method: str = "quadratic"
    details: dict[str, mp.mpf | str] = field(default_factory=dict)


@dataclass
class ExtrapolationOptions:
    """Runtime controls for extrapolation."""

    method: str = "quadratic"
    power_law_config: PowerLawConfig | None = None
    uncertainty_column: str | None = None
    mp_precision: int | None = None
    levin_variant: str = "u"
    custom_formula: str | None = None
    warnings: list[str] = field(default_factory=list)
    uncertainty_digits: int | None = None


def compute_extrapolation(A: float, B: float, C: float) -> tuple[float, float]:
    """
    Compute extrapolated value V and uncertainty U using three data points.

    This follows the MATLAB function:
    V = ((C - B)^2) / (B - A) + C
    U = max([abs(V - A), abs(V - B), abs(V - C)])
    """
    if abs(B - A) < 1e-15:
        V = C
        U = max(abs(V - A), abs(V - B), abs(V - C))
        return V, U

    V = ((C - B) ** 2) / (B - A) + C
    U = max(abs(V - A), abs(V - B), abs(V - C))
    return V, U


def compute_extrapolation_decimal(A: _MpInput, B: _MpInput, C: _MpInput) -> tuple[mp.mpf, mp.mpf]:
    """High-precision extrapolation mirroring the MATLAB formula using mpmath."""
    a_mp = _mp(A)
    b_mp = _mp(B)
    c_mp = _mp(C)
    if mp.fabs(b_mp - a_mp) < mp.mpf("1e-50"):
        V = c_mp
        U = max(mp.fabs(V - a_mp), mp.fabs(V - b_mp), mp.fabs(V - c_mp))
        return V, U
    diff_CB = c_mp - b_mp
    diff_BA = b_mp - a_mp
    V = (diff_CB * diff_CB) / diff_BA + c_mp
    U = max(mp.fabs(V - a_mp), mp.fabs(V - b_mp), mp.fabs(V - c_mp))
    return V, U


DEFAULT_REFERENCE_INDEX = 2
AUTO_REFERENCE_MAX_DIFF_KEY = "auto_max_diff"
ACCELERATOR_METHODS = {"richardson", "shanks", "wynn_epsilon", "levin_u"}
THREE_POINT_METHODS = {"quadratic", "power_law"}

_METHOD_DISPLAY_NAMES_ZH = {
    "quadratic": "默认三点公式",
    "power_law": "幂律外推",
    "richardson": "Richardson 序列加速",
    "custom": "自定义公式",
}

_METHOD_DISPLAY_NAMES_EN = {
    "quadratic": "Default three-point formula",
    "power_law": "Power-law extrapolation",
    "richardson": "Richardson acceleration",
    "custom": "Custom formula",
}

_UNICODE_MINUS_SIGNS = {
    "\u2212",
    "\u2013",
    "\u2014",
    "\uFF0D",
    "\u2010",
    "\uFE58",
    "\uFE63",
    "\u2012",
}
_UNICODE_PLUS_SIGNS = {"\uFF0B", "\uFE62"}


def process_data_file(
    filename: str,
    verbose: bool = False,
    options: ExtrapolationOptions | None = None,
) -> tuple[list[str], list[tuple[mp.mpf, ...]], list[ExtrapolationResult]]:
    """Process a data file and perform extrapolation on each row."""
    return process_data_lines(Path(filename).read_text().splitlines(), verbose, options=options)


def process_data_string(
    content: str,
    verbose: bool = False,
    options: ExtrapolationOptions | None = None,
) -> tuple[list[str], list[tuple[mp.mpf, ...]], list[ExtrapolationResult]]:
    """Process an in-memory string and perform extrapolation on each row."""
    if not content or not content.strip():
        raise ValueError("输入数据为空，无法解析。")
    return process_data_lines(content.splitlines(), verbose, options=options)


def process_data_lines(
    lines: list[str],
    verbose: bool = False,
    options: ExtrapolationOptions | None = None,
) -> tuple[list[str], list[tuple[mp.mpf, ...]], list[ExtrapolationResult]]:
    """Parse text rows and perform extrapolation through the shared compute engine."""
    headers, rows = parse_extrapolation_lines(lines, verbose=verbose, options=options)
    processed_rows, results = process_extrapolation_rows(headers, rows, verbose=verbose, options=options)
    return headers, processed_rows, results


def parse_extrapolation_string(
    content: str,
    verbose: bool = False,
    options: ExtrapolationOptions | None = None,
) -> tuple[list[str], list[tuple[mp.mpf, ...]]]:
    """Parse an extrapolation text block without computing results."""
    if not content or not content.strip():
        raise ValueError("输入数据为空，无法解析。")
    return parse_extrapolation_lines(content.splitlines(), verbose=verbose, options=options)


def parse_extrapolation_lines(
    lines: list[str],
    verbose: bool = False,
    options: ExtrapolationOptions | None = None,
) -> tuple[list[str], list[tuple[mp.mpf, ...]]]:
    """Parse extrapolation rows with the same trimming policy as legacy processing."""
    opts = _ensure_options(options)
    method = _normalize_method_name(opts.method)
    with precision_guard(opts.mp_precision):
        normalized_lines = _normalize_input_lines(lines)
        if len(normalized_lines) < 2:
            raise ValueError("Input must contain at least a header and one data row")

        headers = normalized_lines[0].strip().split()
        if len(headers) < 3:
            raise ValueError("Header must contain at least 3 column names")

        _maybe_warn_three_point_limit(opts, headers, method, verbose)
        if method in THREE_POINT_METHODS and len(headers) > 3:
            headers = headers[:3]
        column_count = len(headers)

        if verbose:
            print("Found headers: {0}".format(headers))
            print("Processing {0} data rows...".format(len(normalized_lines) - 1))

        data_rows: list[tuple[mp.mpf, ...]] = []
        for line_num, line in enumerate(normalized_lines[1:], 2):
            line = line.strip()
            if not line:
                continue
            values = [_normalize_numeric_token(part) for part in line.split()]
            if len(values) < column_count:
                if verbose:
                    print(
                        "Warning: Line {0} has fewer than {1} values, skipping".format(
                            line_num,
                            column_count,
                        )
                    )
                continue
            try:
                data_rows.append(tuple(_mp(token) for token in values[:column_count]))
            except ValueError as exc:
                if verbose:
                    print("Warning: Cannot parse line {0}: {1}".format(line_num, str(exc)))
                continue

        return headers, data_rows


def process_extrapolation_rows(
    headers: Sequence[str],
    rows: Sequence[Sequence[object]],
    verbose: bool = False,
    options: ExtrapolationOptions | None = None,
) -> tuple[list[tuple[mp.mpf, ...]], list[ExtrapolationResult]]:
    """Compute extrapolation results from already-normalized table rows."""
    opts = _ensure_options(options)
    method = _normalize_method_name(opts.method)
    normalized_headers = [str(header) for header in headers]
    if len(normalized_headers) < 3:
        raise ValueError("Header must contain at least 3 column names")

    with precision_guard(opts.mp_precision):
        if method in THREE_POINT_METHODS and len(normalized_headers) > 3:
            normalized_headers = normalized_headers[:3]
        column_count = len(normalized_headers)
        desired_reference = (opts.uncertainty_column or "").strip()
        use_auto_max_diff = desired_reference.lower() == AUTO_REFERENCE_MAX_DIFF_KEY
        reference_index = _resolve_reference_index(
            normalized_headers,
            None if use_auto_max_diff else desired_reference,
        )
        fallback_reference_index = min(DEFAULT_REFERENCE_INDEX, len(normalized_headers) - 1)
        accelerator_precision = opts.mp_precision
        levin_variant = opts.levin_variant or "u"
        data_rows: list[tuple[mp.mpf, ...]] = []
        extrapolated_results: list[ExtrapolationResult] = []

        for row_number, row in enumerate(rows, 1):
            row_tuple = tuple(_mp(value) for value in row[:column_count])
            if len(row_tuple) < column_count:
                if verbose:
                    print(
                        "Warning: Line {0} does not have enough values for the selected method".format(
                            row_number
                        )
                    )
                continue
            method_values = row_tuple[:3] if method in THREE_POINT_METHODS else row_tuple
            if len(method_values) < 3:
                if verbose:
                    print(
                        "Warning: Line {0} does not have enough values for the selected method".format(
                            row_number
                        )
                    )
                continue

            try:
                result_entry = _compute_row_result(
                    method=method,
                    method_values=method_values,
                    row_tuple=row_tuple,
                    headers=normalized_headers,
                    options=opts,
                    reference_index=reference_index,
                    fallback_reference_index=fallback_reference_index,
                    use_auto_max_diff=use_auto_max_diff,
                    accelerator_precision=accelerator_precision,
                    levin_variant=levin_variant,
                    verbose=verbose,
                )
            except (PowerLawComputationError, SequenceAccelerationError) as exc:
                if verbose:
                    print("Warning: Cannot extrapolate line {0}: {1}".format(row_number, exc))
                continue

            data_rows.append(row_tuple)
            extrapolated_results.append(result_entry)
            if verbose:
                _print_row_result(row_number, method, normalized_headers, row_tuple, result_entry)

        if verbose:
            print("Successfully processed {0} data rows".format(len(data_rows)))
        return data_rows, extrapolated_results


def _compute_row_result(
    *,
    method: str,
    method_values: tuple[mp.mpf, ...],
    row_tuple: tuple[mp.mpf, ...],
    headers: list[str],
    options: ExtrapolationOptions,
    reference_index: int,
    fallback_reference_index: int,
    use_auto_max_diff: bool,
    accelerator_precision: int | None,
    levin_variant: str,
    verbose: bool,
) -> ExtrapolationResult:
    if method == "power_law":
        if not options.power_law_config:
            raise PowerLawComputationError("未提供幂律参数（x1/x2/x3 等），无法计算。")
        power_result = extrapolate_power_law(options.power_law_config, method_values[:3])
        ref_idx = _reference_index_for_result(
            headers,
            row_tuple,
            power_result.value,
            reference_index,
            fallback_reference_index,
            use_auto_max_diff,
            options,
            verbose,
        )
        reference_value = row_tuple[ref_idx]
        return ExtrapolationResult(
            value=power_result.value,
            uncertainty=abs(power_result.value - reference_value),
            method="power_law",
            details={
                "reference_column": _reference_label(headers, ref_idx),
                "exponent": power_result.exponent,
                "amplitude": power_result.amplitude,
            },
        )
    if method in ACCELERATOR_METHODS:
        precision = accelerator_precision
        if not precision:
            raise SequenceAccelerationError("请设置多精度位数以执行该序列加速方法。")
        accel_result = apply_sequence_accelerator(
            method,
            method_values,
            SequenceAcceleratorConfig(precision=precision, levin_variant=levin_variant),
        )
        ref_idx = _reference_index_for_result(
            headers,
            row_tuple,
            accel_result.value,
            reference_index,
            fallback_reference_index,
            use_auto_max_diff,
            options,
            verbose,
        )
        reference_value = row_tuple[ref_idx]
        return ExtrapolationResult(
            value=accel_result.value,
            uncertainty=abs(accel_result.value - reference_value),
            method=method,
            details={
                "reference_column": _reference_label(headers, ref_idx),
                **accel_result.metadata,
            },
        )
    if method == "custom":
        formula = (options.custom_formula or "").strip()
        if not formula:
            raise ValueError("未提供自定义公式。")
        value = _evaluate_custom_formula(formula, headers, row_tuple, warnings=options.warnings)
        V = _mp(value)
        ref_idx = _reference_index_for_result(
            headers,
            row_tuple,
            V,
            reference_index,
            fallback_reference_index,
            use_auto_max_diff,
            options,
            verbose,
        )
        reference_value = row_tuple[ref_idx]
        return ExtrapolationResult(
            value=V,
            uncertainty=mp.fabs(V - reference_value),
            method="custom",
            details={"reference_column": _reference_label(headers, ref_idx), "formula": formula},
        )
    a_val, b_val, c_val = method_values[:3]
    V, U = compute_extrapolation_decimal(a_val, b_val, c_val)
    return ExtrapolationResult(value=V, uncertainty=U, method="quadratic")


def _reference_index_for_result(
    headers: list[str],
    row_tuple: tuple[mp.mpf, ...],
    extrapolated_value: mp.mpf,
    reference_index: int,
    fallback_reference_index: int,
    use_auto_max_diff: bool,
    options: ExtrapolationOptions,
    verbose: bool,
) -> int:
    ref_idx = min(reference_index, len(row_tuple) - 1)
    if not use_auto_max_diff:
        return ref_idx
    chosen = _auto_reference_index_max_diff(row_tuple, extrapolated_value)
    if chosen is None:
        _append_option_warning(
            options,
            _dual_msg(
                "最大差异列：无法自动选择参考列，已回退到默认参考列。",
                "Max-diff column: unable to auto-select a reference column; fell back to the default reference column.",
            ),
            verbose,
        )
        return min(fallback_reference_index, len(row_tuple) - 1)
    return chosen


def _print_row_result(
    row_number: int,
    method: str,
    headers: list[str],
    row_tuple: tuple[mp.mpf, ...],
    result_entry: ExtrapolationResult,
) -> None:
    column_states = ", ".join(
        f"{_reference_label(headers, idx)}={row_tuple[idx]}" for idx in range(len(row_tuple))
    )
    if method == "power_law":
        print(
            "Row {0}: {1} -> E_inf={2}, Δ={3}, p={4}".format(
                row_number,
                column_states,
                result_entry.value,
                result_entry.uncertainty,
                result_entry.details.get("exponent"),
            )
        )
    elif method in ACCELERATOR_METHODS:
        print(
            "Row {0}: {1} -> {2} limit={3}, Δ={4}".format(
                row_number,
                column_states,
                method,
                result_entry.value,
                result_entry.uncertainty,
            )
        )
    else:
        print(
            "Row {0}: {1} -> V={2}, U={3}".format(
                row_number,
                column_states,
                result_entry.value,
                result_entry.uncertainty,
            )
        )


def _normalize_method_name(name: str | None) -> str:
    method = (name or "quadratic").strip().lower()
    known = {"quadratic", "power_law", "richardson", "shanks", "wynn_epsilon", "levin_u", "custom"}
    return method if method in known else "quadratic"


def _resolve_reference_index(headers: list[str], desired: str | None) -> int:
    if not headers:
        return 0
    fallback = min(DEFAULT_REFERENCE_INDEX, len(headers) - 1)
    if not desired:
        return fallback
    normalized = desired.strip().lower()
    if not normalized or normalized == AUTO_REFERENCE_MAX_DIFF_KEY:
        return fallback
    lookup = {header.lower(): idx for idx, header in enumerate(headers)}
    if normalized in lookup:
        return lookup[normalized]
    aliases = {chr(ord("a") + idx): idx for idx in range(min(len(headers), 26))}
    if normalized in aliases:
        return aliases[normalized]
    if normalized.isdigit():
        return min(max(0, int(normalized) - 1), len(headers) - 1)
    return fallback


def _auto_reference_index_max_diff(row_tuple: tuple[mp.mpf, ...], extrapolated_value: mp.mpf) -> int | None:
    """Choose the column index with the largest |extrapolated_value - ref_i|."""
    if not row_tuple:
        return None
    try:
        V = _mp(extrapolated_value)
    except Exception:
        return None
    try:
        if not mp.isfinite(V):
            return None
    except Exception:
        pass
    best_idx: int | None = None
    best_diff: mp.mpf | None = None
    for idx, ref_val in enumerate(row_tuple):
        try:
            if not mp.isfinite(ref_val):
                continue
            diff = mp.fabs(V - ref_val)
            if not mp.isfinite(diff):
                continue
        except Exception:
            continue
        if best_idx is None or (best_diff is not None and diff > best_diff):
            best_idx = idx
            best_diff = diff
    return best_idx


def _reference_label(headers: list[str], index: int) -> str:
    if headers and 0 <= index < len(headers):
        return headers[index]
    return f"列{index + 1}"


def _method_display_name(method: str, lang: str = "zh") -> str:
    if lang == "en":
        return _METHOD_DISPLAY_NAMES_EN.get(method, method)
    return _METHOD_DISPLAY_NAMES_ZH.get(method, method)


def _append_option_warning(options: ExtrapolationOptions, message: str, verbose: bool) -> None:
    if not message:
        return
    if message not in options.warnings:
        options.warnings.append(message)
        if verbose:
            print(f"Warning: {message}")


def _maybe_warn_three_point_limit(
    options: ExtrapolationOptions,
    headers: list[str],
    method: str,
    verbose: bool,
) -> None:
    if method not in THREE_POINT_METHODS or len(headers) <= 3:
        return
    extra = len(headers) - 3
    zh_name = _method_display_name(method, "zh")
    en_name = _method_display_name(method, "en")
    message_zh = f"{zh_name} 仅支持三点外推，已忽略多余 {extra} 列。"
    message_en = f"{en_name} only supports three-point extrapolation; ignored {extra} extra column(s)."
    _append_option_warning(options, f"{message_zh} / {message_en}", verbose)


def _evaluate_custom_formula(
    formula: str,
    headers: list[str],
    row_values: tuple[mp.mpf, ...],
    warnings: list[str] | None = None,
) -> mp.mpf:
    """Evaluate the custom extrapolation formula using the shared safe parser."""
    normalized_formula = _normalize_expression(formula)
    if not normalized_formula.strip():
        raise ValueError("未提供自定义公式。")

    variables: dict[str, object] = {}
    alias_map: dict[str, str] = {}
    seen: set[str] = set()
    for idx, header in enumerate(headers):
        canonical = _normalize_header_to_symbol(header, idx)
        base = canonical
        counter = 2
        while canonical in seen:
            canonical = f"{base}_{counter}"
            counter += 1
        seen.add(canonical)
        variables[canonical] = row_values[idx]
        alias_map[f"x{idx + 1}"] = canonical

    variable_keys = list(variables.keys())
    for alias, pos in (("A", 0), ("B", 1), ("C", 2)):
        if pos < len(headers):
            alias_map[alias] = variable_keys[pos]

    rewritten = _apply_aliases(normalized_formula, alias_map)
    if warnings is not None and rewritten != normalized_formula:
        warnings.append(
            f"自定义公式已重写为使用列名/规范名: {rewritten} / "
            f"Custom formula rewritten to canonical variable names: {rewritten}"
        )
    try:
        return _mp(safe_eval(rewritten, variables))
    except Exception as exc:  # noqa: BLE001
        zh_e, en_e = _split_dual(str(exc))
        raise ValueError(
            _dual_msg(
                f"自定义公式求值失败: {zh_e}",
                f"Failed to evaluate custom formula: {en_e}",
            )
        ) from exc


def _ensure_options(options: ExtrapolationOptions | None) -> ExtrapolationOptions:
    if isinstance(options, ExtrapolationOptions):
        return options
    return ExtrapolationOptions()


def _normalize_input_lines(lines: list[str]) -> list[str]:
    trimmed = [line.rstrip() for line in lines]
    start = 0
    while start < len(trimmed) and not trimmed[start].strip():
        start += 1
    return trimmed[start:]


def _normalize_numeric_token(token: str) -> str:
    result = token.strip()
    for ch in _UNICODE_MINUS_SIGNS:
        result = result.replace(ch, "-")
    for ch in _UNICODE_PLUS_SIGNS:
        result = result.replace(ch, "+")
    return result


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


__all__ = [
    "ACCELERATOR_METHODS",
    "AUTO_REFERENCE_MAX_DIFF_KEY",
    "DEFAULT_REFERENCE_INDEX",
    "DEFAULT_THREE_POINT_FORMULA",
    "ExtrapolationOptions",
    "ExtrapolationResult",
    "THREE_POINT_METHODS",
    "compute_extrapolation",
    "compute_extrapolation_decimal",
    "parse_extrapolation_lines",
    "parse_extrapolation_string",
    "process_data_file",
    "process_data_lines",
    "process_data_string",
    "process_extrapolation_rows",
]
