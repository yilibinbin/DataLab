from __future__ import annotations

import base64
import io
import re
from typing import Iterable

import mpmath as mp

from .._security_shim import validate_text_size

from data_extrapolation_latex_latest import _dual_msg, format_result_with_uncertainty_latex


def _extract_data_text(form, files, allow_file: bool = True) -> str:
    """Prefer uploaded file content only when allowed; otherwise use textarea text."""
    if allow_file and "data_file" in files and files["data_file"]:
        file = files["data_file"]
        if getattr(file, "filename", ""):
            try:
                content = file.read().decode("utf-8")
                return validate_text_size(content, "上传文件")
            except Exception as exc:
                raise ValueError(
                    _dual_msg(
                        f"上传文件无法读取为 UTF-8 文本: {exc}",
                        f"Uploaded file could not be decoded as UTF-8 text: {exc}",
                    )
                ) from exc
    text = (form.get("data_text") or "").strip()
    return validate_text_size(text, "数据文本")


def _extract_named_text(text_field: str, file_field: str, form, files, allow_file: bool = True) -> str:
    """Generic extractor for either textarea or file upload field."""
    if allow_file and file_field in files and files[file_field]:
        file = files[file_field]
        if getattr(file, "filename", ""):
            try:
                content = file.read().decode("utf-8")
                return validate_text_size(content, f"上传文件 ({file_field})")
            except Exception as exc:
                raise ValueError(
                    _dual_msg(
                        f"上传文件无法读取为 UTF-8 文本: {exc}",
                        f"Uploaded file could not be decoded as UTF-8 text: {exc}",
                    )
                ) from exc
    text = (form.get(text_field) or "").strip()
    return validate_text_size(text, text_field)


def _parse_int(text: str | None) -> int | None:
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    try:
        return int(text)
    except Exception as exc:
        # Be tolerant to inputs like "80.0" or "1e2" coming from browsers.
        try:
            as_float = float(text)
            if as_float.is_integer():
                return int(as_float)
        except Exception:
            pass
        raise ValueError(f"无法解析整数: {text} / Failed to parse integer: {text}") from exc


def _parse_float(text: str | None) -> float | None:
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except Exception as exc:
        raise ValueError(
            _dual_msg(
                f"无法解析浮点数: {text}",
                f"Failed to parse float: {text}",
            )
        ) from exc


def _norm_token(token: str) -> str:
    return (
        token.replace("−", "-")
        .replace("—", "-")
        .replace("–", "-")
        .replace("＋", "+")
    )


def _is_checked(form, name: str, default: bool = False) -> bool:
    """
    Normalize checkbox state:

    - If the checkbox key is present, treat it as checked (unless explicitly false-ish).
    - If the key is absent in a non-empty submitted form, treat it as unchecked.
    - If the form is empty (e.g. initial GET render), fall back to default.
    """
    if form is None:
        return default
    if name in form:
        value = form.get(name)
        if value is None:
            return True
        normalized = str(value).strip().lower()
        if normalized in {"0", "false", "off", "no"}:
            return False
        return True

    # On a real submission, an unchecked checkbox is omitted from the POST body.
    # Honor that instead of "default", otherwise users cannot turn off default-on options.
    try:
        if len(form) > 0:
            return False
    except Exception:
        if bool(form):
            return False
    return default


def _format_number(value, digits: int = 10) -> str:
    try:
        return mp.nstr(value, digits)
    except Exception:
        return str(value)


def _format_with_precision(value, mp_precision: int | None = None) -> str:
    """
    Format number respecting mp.dps precision limit.

    Args:
        value: The mpf value to format
        mp_precision: The mpmath precision (dps), None means use default (16)

    Returns:
        Formatted string with precision not exceeding mp.dps
    """
    try:
        if mp_precision is None:
            mp_precision = 16  # Use default precision
        # Use mp_precision as the max significant digits
        # This ensures we don't show more digits than what mpmath can accurately represent
        result = mp.nstr(value, min(int(mp_precision), 50))  # Cap at 50 for safety
        return str(result) if result else str(value)
    except Exception:
        return str(value)


def _generate_csv_from_rows(formatted_rows: list[dict[str, object]], headers: list[str] | None = None) -> str:
    """
    Generate CSV content from formatted result rows.

    Args:
        formatted_rows: List of dicts with keys like 'index', 'value', 'uncertainty', 'latex'
        headers: Optional custom headers. If None, uses keys from first row.

    Returns:
        CSV formatted string
    """
    if not formatted_rows:
        return ""

    import csv

    output = io.StringIO()

    # Determine headers
    if headers is None:
        # Use keys from first row (maintaining order: index, value, uncertainty, latex)
        first_row = formatted_rows[0]
        if "index" in first_row and "value" in first_row and "uncertainty" in first_row and "latex" in first_row:
            headers = ["index", "value", "uncertainty", "latex"]
        else:
            headers = list(first_row.keys())

    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    writer.writerows(formatted_rows)

    return output.getvalue()


def _latex_to_plain(text: str) -> str:
    text = text.replace(r"\,", "")
    text = re.sub(r"\\text\{([^}]*)\}", r"\1", text)
    return text.replace("\\", "")


def _split_result(result) -> tuple[mp.mpf, mp.mpf]:
    """Normalize result objects/tuples to (value, sigma)."""
    try:
        from data_extrapolation_latex_latest import ExtrapolationResult as _Result
    except Exception:
        _Result = None  # pragma: no cover
    if _Result and isinstance(result, _Result):
        return mp.mpf(result.value), mp.mpf(result.uncertainty)
    if isinstance(result, (tuple, list)) and len(result) >= 2:
        return mp.mpf(result[0]), mp.mpf(result[1])
    return mp.mpf(result), mp.mpf("0")


def _format_rows(
    headers: list[str],  # noqa: ARG001 - kept for backward compatibility
    rows: Iterable[tuple[mp.mpf, ...]],
    results: Iterable,
    digits: int = 10,  # noqa: ARG001 - kept for backward compatibility
    uncertainty_digits: int | None = None,
    mp_precision: int | None = None,
) -> list[dict[str, object]]:
    """
    Format extrapolation results as 3-column format.

    Returns list of dicts with keys:
    - index: row number
    - value: numerical value (limited by mp_precision)
    - uncertainty: numerical uncertainty (limited by mp_precision)
    - latex: LaTeX formatted display with uncertainty
    """
    formatted: list[dict[str, object]] = []
    for idx, (_row, result) in enumerate(zip(rows, results), 1):
        value, sigma = _split_result(result)
        latex = format_result_with_uncertainty_latex(value, sigma, uncertainty_digits)
        formatted.append(
            {
                "index": idx,
                "value": _format_with_precision(value, mp_precision),
                "uncertainty": _format_with_precision(sigma, mp_precision),
                "latex": _latex_to_plain(latex),
            }
        )
    return formatted


def _encode_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")

