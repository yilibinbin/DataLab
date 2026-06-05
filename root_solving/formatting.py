"""Formatting helpers for root-solving results."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from mpmath import mp

from datalab_latex.latex_formatting import format_result_with_uncertainty_latex
from root_solving.messages import localize_root_message
from root_solving.models import RootBatchResult, RootBatchRowResult, RootResult

CSV_HEADERS = ["name", "value", "uncertainty", "display_value", "backend", "mode", "residual_norm"]
BATCH_CSV_HEADERS = [
    "input_row_index",
    "root_index",
    "name",
    "value",
    "uncertainty",
    "display_value",
    "backend",
    "mode",
    "residual_norm",
    "failure",
]
_BATCH_RESULT_COLUMNS = frozenset(BATCH_CSV_HEADERS)


def render_root_result(
    result: RootResult,
    *,
    display_digits: int = 10,
    uncertainty_digits: int = 1,
    language: str = "en",
) -> tuple[str, list[dict[str, str]], list[str]]:
    """Render a root-solving result for desktop markdown and CSV plumbing."""
    digits = max(1, int(display_digits))
    residual_norm = _format_optional_real(result.residual_norm, digits)
    csv_rows = [
        {
            "name": root.name,
            "value": "" if root.value is None else _format_root_value(root.value, digits),
            "uncertainty": _format_optional_real(root.uncertainty, digits),
            "display_value": _format_root_display_value(root, digits, uncertainty_digits),
            "backend": result.backend,
            "mode": result.mode,
            "residual_norm": residual_norm,
        }
        for root in result.roots
    ]
    return _render_markdown(csv_rows, result.warnings, details=result.details, language=language), csv_rows, list(CSV_HEADERS)


def render_root_batch_result(
    batch: RootBatchResult,
    *,
    display_digits: int = 10,
    uncertainty_digits: int = 1,
    language: str = "en",
) -> tuple[str, list[dict[str, str]], list[str]]:
    """Render a root batch result as a flat table for desktop result plumbing."""
    digits = max(1, int(display_digits))
    source_headers = list(batch.headers)
    source_output_headers = _source_output_headers(source_headers)
    headers = [
        "input_row_index",
        "root_index",
        *source_output_headers,
        "name",
        "value",
        "uncertainty",
        "display_value",
        "backend",
        "mode",
        "residual_norm",
        "failure",
    ]
    rows: list[dict[str, str]] = []
    warnings: list[str] = [warning for warning in batch.warnings if warning]
    detail_values: dict[str, object] = {}
    for batch_row in batch.rows:
        warnings.extend(warning for warning in batch_row.warnings if warning)
        if batch_row.failure:
            rows.append(_batch_failure_row(batch_row, source_headers, source_output_headers, failure=batch_row.failure))
            continue
        if batch_row.result is None:
            rows.append(_batch_failure_row(batch_row, source_headers, source_output_headers, failure="missing result"))
            continue
        warnings.extend(warning for warning in batch_row.result.warnings if warning)
        _merge_root_details(detail_values, batch_row.result.details)
        residual_norm = _format_optional_real(batch_row.result.residual_norm, digits)
        if not batch_row.result.roots:
            rows.append(_batch_failure_row(batch_row, source_headers, source_output_headers, failure="no roots"))
            continue
        for root_index, root in enumerate(batch_row.result.roots):
            rows.append(
                {
                    "input_row_index": _format_row_index(batch_row),
                    "root_index": str(root_index),
                    **_source_values_for_output(batch_row, source_headers, source_output_headers),
                    "name": root.name,
                    "value": _format_root_value(root.value, digits),
                    "uncertainty": _format_optional_real(root.uncertainty, digits),
                    "display_value": _format_root_display_value(root, digits, uncertainty_digits),
                    "backend": batch_row.result.backend,
                    "mode": batch_row.result.mode,
                    "residual_norm": residual_norm,
                    "failure": "",
                }
            )
    return _render_markdown_with_headers(rows, headers, _deduplicate_strings(warnings), details=detail_values, language=language), rows, headers


def _batch_failure_row(
    row: RootBatchRowResult,
    source_headers: list[str],
    source_output_headers: list[str],
    *,
    failure: str,
) -> dict[str, str]:
    return {
        "input_row_index": _format_row_index(row),
        "root_index": "",
        **_source_values_for_output(row, source_headers, source_output_headers),
        "name": "",
        "value": "",
        "uncertainty": "",
        "display_value": "",
        "backend": "",
        "mode": "",
        "residual_norm": "",
        "failure": failure,
    }


def _source_output_headers(source_headers: list[str]) -> list[str]:
    output: list[str] = []
    used = set(_BATCH_RESULT_COLUMNS)
    for header in source_headers:
        candidate = f"input_{header}" if header in _BATCH_RESULT_COLUMNS else header
        while candidate in used or candidate in output:
            candidate = f"input_{candidate}"
        output.append(candidate)
        used.add(candidate)
    return output


def _source_values_for_output(
    row: RootBatchRowResult,
    source_headers: list[str],
    source_output_headers: list[str],
) -> dict[str, str]:
    return {
        output_header: row.source_values.get(source_header, "")
        for source_header, output_header in zip(source_headers, source_output_headers, strict=True)
    }


def _format_row_index(row: RootBatchRowResult) -> str:
    return "" if row.row_index is None else str(row.row_index)


def _render_markdown(
    rows: list[dict[str, str]],
    warnings: Iterable[str],
    *,
    details: Mapping[str, object] | None = None,
    language: str = "en",
) -> str:
    return _render_markdown_with_headers(rows, list(CSV_HEADERS), warnings, details=details, language=language)


def _render_markdown_with_headers(
    rows: list[dict[str, str]],
    headers: list[str],
    warnings: Iterable[str],
    *,
    details: Mapping[str, object] | None = None,
    language: str = "en",
) -> str:
    markdown_headers = _markdown_headers(headers)
    display_headers = [_display_header(header, language=language) for header in markdown_headers]
    lines = [
        "| " + " | ".join(display_headers) + " |",
        "| " + " | ".join("---" for _ in display_headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                _escape_markdown_cell(_display_cell(header, row.get(header, ""), language=language))
                for header in markdown_headers
            )
            + " |"
        )
    detail_lines = _root_detail_lines(details or {}, language=language)
    if detail_lines:
        lines.extend(["", _details_label(language)])
        lines.extend(f"- {line}" for line in detail_lines)
    warning_lines = [warning for warning in warnings if warning]
    if warning_lines:
        lines.extend(["", _warning_label(language)])
        lines.extend(f"- {_escape_markdown_warning(localize_root_message(warning, language=language))}" for warning in warning_lines)
    return "\n".join(lines)


_ZH_HEADERS = {
    "input_row_index": "输入行",
    "root_index": "根序号",
    "name": "名称",
    "value": "值",
    "display_value": "值",
    "uncertainty": "不确定度",
    "backend": "后端",
    "mode": "模式",
    "residual_norm": "残差范数",
    "failure": "失败原因",
}


def _markdown_headers(headers: list[str]) -> list[str]:
    if "display_value" not in headers:
        return headers
    return [header for header in headers if header not in {"value", "uncertainty"}]


def _display_header(header: str, *, language: str) -> str:
    if header == "display_value" and language != "zh":
        return "value"
    if language != "zh":
        return header
    if header.startswith("input_") and header not in _ZH_HEADERS:
        return f"输入 {header.removeprefix('input_')}"
    return _ZH_HEADERS.get(header, header)


def _warning_label(language: str) -> str:
    return "警告:" if language == "zh" else "Warnings:"


def _details_label(language: str) -> str:
    return "详情:" if language == "zh" else "Details:"


def _display_cell(header: str, value: str, *, language: str) -> str:
    if header == "failure":
        return str(localize_root_message(value, language=language))
    return value


def _root_detail_lines(details: Mapping[str, object], *, language: str) -> list[str]:
    keys = (
        "uncertainty_method",
        "uncertainty_requested_method",
        "monte_carlo_samples",
        "monte_carlo_failures",
        "monte_carlo_valid_samples",
        "monte_carlo_first_failure",
        "uncertainty_bias",
    )
    lines: list[str] = []
    for key in keys:
        value = details.get(key)
        if value is None or value == "":
            continue
        label = _detail_label(key, language=language)
        lines.append(f"{label}: {_escape_markdown_warning(_detail_value(key, value, language=language))}")
    return lines


def _detail_label(key: str, *, language: str) -> str:
    if language != "zh":
        return key.replace("_", " ")
    labels = {
        "uncertainty_method": "不确定度方法",
        "uncertainty_requested_method": "请求的不确定度方法",
        "monte_carlo_samples": "蒙特卡洛样本数",
        "monte_carlo_failures": "蒙特卡洛失败数",
        "monte_carlo_valid_samples": "蒙特卡洛有效样本数",
        "monte_carlo_first_failure": "蒙特卡洛首个失败",
        "uncertainty_bias": "不确定度均值偏移",
    }
    return labels.get(key, key)


def _detail_value(key: str, value: object, *, language: str) -> str:
    text = str(value)
    if language != "zh":
        return text
    if key not in {"uncertainty_method", "uncertainty_requested_method"}:
        return text
    values = {
        "taylor": "泰勒",
        "linear": "线性",
        "monte_carlo": "蒙特卡洛",
        "off": "关闭",
        "skipped": "跳过",
        "mixed": "混合",
    }
    return values.get(text, text)


def _merge_root_details(target: dict[str, object], source: Mapping[str, object]) -> None:
    _merge_same_or_mixed(target, source, "uncertainty_method")
    _merge_same_or_mixed(target, source, "uncertainty_requested_method")
    _merge_sum(target, source, "monte_carlo_failures")
    _merge_sum(target, source, "monte_carlo_valid_samples")
    _merge_first(target, source, "monte_carlo_first_failure")
    _merge_same_or_mixed(target, source, "monte_carlo_samples")
    _merge_same_or_mixed(target, source, "uncertainty_bias")


def _merge_same_or_mixed(target: dict[str, object], source: Mapping[str, object], key: str) -> None:
    value = source.get(key)
    if value is None or value == "":
        return
    if key in target and target[key] != value:
        target[key] = "mixed"
        return
    target[key] = value


def _merge_sum(target: dict[str, object], source: Mapping[str, object], key: str) -> None:
    value = source.get(key)
    if value is None or value == "":
        return
    numeric = _detail_int(value, default=None)
    if numeric is None:
        _merge_same_or_mixed(target, source, key)
        return
    current = _detail_int(target.get(key), default=0)
    if current is None:
        current = 0
    target[key] = current + numeric


def _detail_int(value: object, *, default: int | None) -> int | None:
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return default
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _merge_first(target: dict[str, object], source: Mapping[str, object], key: str) -> None:
    value = source.get(key)
    if value is None or value == "" or key in target:
        return
    target[key] = value


def _deduplicate_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _format_root_value(value: mp.mpf | mp.mpc | complex, digits: int) -> str:
    if isinstance(value, (mp.mpc, complex)):
        real = _format_real(mp.re(value), digits)
        imaginary = mp.mpf(mp.im(value))
        sign = "+" if imaginary >= 0 else "-"
        magnitude = _format_real(mp.fabs(imaginary), digits)
        return f"{real} {sign} {magnitude} i"
    return _format_real(value, digits)


def _format_optional_real(value: mp.mpf | None, digits: int) -> str:
    if value is None:
        return ""
    return _format_real(value, digits)


def _format_root_display_value(root: object, digits: int, uncertainty_digits: int) -> str:
    value = getattr(root, "value", None)
    uncertainty = getattr(root, "uncertainty", None)
    if value is None:
        return ""
    if uncertainty is None:
        return _format_root_value(value, digits)
    if isinstance(value, (mp.mpc, complex)):
        return _format_root_value(value, digits)
    try:
        formatted = format_result_with_uncertainty_latex(value, uncertainty, max(1, int(uncertainty_digits)))
    except (ValueError, TypeError, ArithmeticError):
        return _format_root_value(value, digits)
    return _latex_to_plain_uncertainty(formatted)


def _latex_to_plain_uncertainty(value: str) -> str:
    text = value.replace(r"\,", "")
    text = re.sub(r"\[\\text\{([+-]?\d+)\}\]", r"e\1", text)
    text = re.sub(r"\\text\{([^{}]*)\}", r"\1", text)
    return text.replace("\\", "")


def _format_real(value: mp.mpf, digits: int) -> str:
    return str(mp.nstr(value, n=digits))


def _escape_markdown_cell(value: str) -> str:
    return value.replace("\\", "\\\\").replace("|", "\\|")


def _escape_markdown_warning(value: str) -> str:
    return value.replace("\\", "\\\\")
