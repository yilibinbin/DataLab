from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

import mpmath as mp

from .._security_shim import compile_latex_safe, mpmath_synchronized, validate_latex_engine
from datalab_core.results import ResultStatus
from datalab_core.service_factory import create_core_session_service
from datalab_core.statistics import (
    build_statistics_requests,
    statistics_csv_rows_from_result,
    statistics_payload_to_compute_result,
)

from data_extrapolation_latex_latest import (
    _dual_msg,
    _precision_guard,
    format_result_with_uncertainty_latex,
)
from statistics_utils import generate_statistics_latex

from .common import (
    _core_failure_message,
    _encode_b64,
    _format_number,
    _format_with_precision,
    _generate_csv_from_rows,
    _is_checked,
    _latex_to_plain,
    _merged_core_warnings,
    _norm_token,
    _parse_int,
)
from .plots import _render_statistics_plot, _render_statistics_plots
from shared.uncertainty import has_explicit_uncertainty, parse_uncertainty_format


@dataclass
class StatsResultBundle:
    headers: list[str]
    rows: list[tuple[mp.mpf, ...]]
    sigmas: list[tuple[mp.mpf | None, ...]]
    result: dict
    latex_text: str
    pdf_b64: str | None
    plot_b64: str | None
    plot_b64_list: list[str] | None
    csv_data: str | None
    raw_csv_data: str | None
    warnings: list[str]
    stats_mode: str
    mp_precision: int | None


def _parse_stats_data(text: str):
    """
    Parse statistics data in format:
    - Single column: value (can have parentheses uncertainty like 1.23(4))
    - Two columns: value sigma

    Matches desktop GUI's _parse_generic_table behavior.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError(
            _dual_msg(
                "统计数据至少需要表头和一行数据。",
                "Statistics data requires a header and at least one data row.",
            )
        )
    raw_headers = lines[0].split()
    if len(raw_headers) < 1:
        raise ValueError(_dual_msg("表头至少需要一列。", "Table header must contain at least one column."))
    headers = [raw_headers[0]]

    values: list[mp.mpf] = []
    sigmas: list[mp.mpf | None] = []
    data_rows: list[tuple[mp.mpf, ...]] = []
    sigma_rows: list[tuple[mp.mpf | None, ...]] = []

    for line_num, line in enumerate(lines[1:], 2):
        parts = line.split()
        if not parts:
            continue

        # Handle different formats:
        # 1. Single column with parentheses: "1152842742.723(12)"
        # 2. Two columns: "2.1 0.05"
        # 3. Single column plain number: "2.1"

        if len(parts) == 1:
            token = _norm_token(parts[0])
            try:
                uv = parse_uncertainty_format(token, lang="zh")
                val = mp.mpf(uv.value)
                sigma_val = (
                    mp.mpf(uv.uncertainty)
                    if has_explicit_uncertainty(token)
                    else None
                )
            except Exception as exc:
                raise ValueError(
                    _dual_msg(
                        f"第 {line_num} 行无法解析数字: {parts[0]} ({exc})",
                        f"Could not parse number on line {line_num}: {parts[0]} ({exc})",
                    )
                ) from exc

            values.append(val)
            sigmas.append(sigma_val)
            data_rows.append((val,))
            sigma_rows.append((sigma_val,))

        elif len(parts) >= 2:
            try:
                token1 = _norm_token(parts[0])
                try:
                    uv1 = parse_uncertainty_format(token1, lang="zh")
                    val = mp.mpf(uv1.value)
                except Exception:
                    val = mp.mpf(token1)

                token2 = _norm_token(parts[1])
                try:
                    uv2 = parse_uncertainty_format(token2, lang="zh")
                    sigma_val = mp.mpf(uv2.value)
                except Exception:
                    sigma_val = mp.mpf(token2)
                if not mp.isfinite(sigma_val):
                    raise ValueError(
                        _dual_msg(
                            f"第 {line_num} 行的不确定度不是有限数: {parts[1]}",
                            f"Uncertainty on line {line_num} is not finite: {parts[1]}",
                        )
                    )

            except Exception as exc:
                raise ValueError(
                    _dual_msg(
                        f"第 {line_num} 行无法解析为数字: {line} ({exc})",
                        f"Could not parse line {line_num} as numbers: {line} ({exc})",
                    )
                ) from exc

            values.append(val)
            sigmas.append(sigma_val)
            data_rows.append((val,))
            sigma_rows.append((sigma_val,))

    return headers, values, sigmas, data_rows, sigma_rows


def _format_statistics_rows(stats_result: dict, row_count: int, mp_precision: int | None = None) -> list[dict[str, object]]:
    """Compatibility wrapper around the shared semantic statistics CSV serializer."""

    return statistics_csv_rows_from_result(
        stats_result,
        row_count=row_count,
        include_batch=False,
        precision_digits=mp_precision,
    )


@mpmath_synchronized
def _run_statistics(data_text: str, form, lang: str = "zh") -> StatsResultBundle:
    mp_precision = _parse_int(form.get("stats_mp_precision"))
    latex_precision = _parse_int(form.get("stats_digits")) or 12
    latex_group_size = _parse_int(form.get("stats_latex_group_size"))
    if latex_group_size is None:
        latex_group_size = 3
    result_digits = _parse_int(form.get("stats_uncertainty_digits"))
    if result_digits is None:
        result_digits = 1
    use_dcolumn = _is_checked(form, "stats_use_dcolumn", default=True)
    compile_pdf = _is_checked(form, "stats_compile_pdf", default=False)
    generate_plots = _is_checked(form, "stats_generate_plots", default=False)
    latex_engine = (form.get("stats_latex_engine") or "xelatex").strip() or "xelatex"
    caption_text = (form.get("stats_caption") or "").strip()
    use_caption = _is_checked(form, "stats_use_caption", default=False) if "stats_use_caption" in form else bool(caption_text)
    caption = (caption_text or None) if use_caption else None
    stats_mode = (form.get("stats_mode") or "mean_sample").strip()
    use_sample = _is_checked(form, "stats_use_sample", default=False)
    use_weighted_variance = _is_checked(form, "stats_use_weighted_variance", default=False)
    trim_fraction = form.get("stats_trim_fraction")

    warnings: list[str] = []
    with _precision_guard(mp_precision) as applied_precision:
        headers, values, sigmas, data_rows, sigma_rows = _parse_stats_data(data_text)
        value_col = headers[0] if headers else "value"
        try:
            core_batches = build_statistics_requests(
                headers=(value_col,),
                rows=data_rows,
                sigma_rows=sigma_rows,
                value_col=value_col,
                stats_mode=stats_mode,
                use_sample=use_sample,
                use_weighted_variance=use_weighted_variance,
                trim_fraction=trim_fraction,
                precision_digits=applied_precision,
                uncertainty_digits=result_digits,
                request_id_prefix="web-statistics",
            )
        except Exception as exc:  # noqa: BLE001 - preserve the web form error boundary.
            raise ValueError(str(exc)) from exc
        try:
            core_result = create_core_session_service().submit(core_batches[0].request)
        except Exception as exc:  # noqa: BLE001 - preserve the web form error boundary.
            raise ValueError(str(exc)) from exc
        if core_result.status is not ResultStatus.SUCCEEDED:
            raise ValueError(_core_failure_message(core_result.payload, "Statistics failed."))
        stats_result = statistics_payload_to_compute_result(
            core_result.payload,
            core_result.warnings,
        )
        warnings.extend(_merged_core_warnings(core_result.payload, core_result.warnings))
        with tempfile.TemporaryDirectory() as tmpdir:
            tex_path = Path(tmpdir) / "stats.tex"
            generate_statistics_latex(
                headers[0] if headers else "value",
                data_rows,
                sigma_rows,
                stats_result,
                digits=latex_precision,
                tex_path=str(tex_path),
                use_dcolumn=use_dcolumn,
                uncertainty_digits=result_digits,
                caption=caption,
                latex_group_size=latex_group_size,
            )
            latex_text = tex_path.read_text(encoding="utf-8")

    with _precision_guard(applied_precision):
        mean_latex = ""
        try:
            mean_val = stats_result.get("mean")
            std_mean = stats_result.get("std_mean")
            if mean_val is not None and std_mean is not None:
                latex = format_result_with_uncertainty_latex(mean_val, std_mean, result_digits)
                mean_latex = _latex_to_plain(latex) if latex else ""
        except Exception:
            mean_latex = ""

        display_result: dict[str, object] = {}
        for key, val in stats_result.items():
            if isinstance(val, mp.mpf):
                display_result[key] = _format_number(val, 12)
            else:
                display_result[key] = val
        display_result["mean_latex"] = mean_latex

        plot_b64 = None
        plot_b64_list = None
        if generate_plots and values:
            plot_bytes_list = _render_statistics_plots(values, sigmas, stats_result, lang=lang)
            if plot_bytes_list:
                plot_b64_list = [_encode_b64(plot_bytes) for plot_bytes in plot_bytes_list]
                plot_b64 = plot_b64_list[0]
            else:
                plot_bytes = _render_statistics_plot(values, sigmas, stats_result, lang=lang)
                if plot_bytes:
                    plot_b64 = _encode_b64(plot_bytes)
                    plot_b64_list = [plot_b64]

        csv_data = None
        stats_rows = _format_statistics_rows(stats_result, len(values), mp_precision)
        if stats_rows:
            csv_headers = ["metric", "value", "uncertainty"]
            csv_data = _generate_csv_from_rows(stats_rows, headers=csv_headers)

        raw_csv_data = None
        if data_rows and headers:
            raw_rows = []
            has_sigma = sigmas and any(sigma_row and any(s is not None for s in sigma_row) for sigma_row in sigma_rows)

            for idx, row in enumerate(data_rows, 1):
                csv_row: dict[str, object] = {"index": idx}
                for h_idx, header in enumerate(headers):
                    if h_idx < len(row):
                        csv_row[header] = _format_with_precision(row[h_idx], mp_precision)
                if has_sigma and idx <= len(sigma_rows):
                    sigma_row = sigma_rows[idx - 1]
                    for h_idx, header in enumerate(headers):
                        if sigma_row and h_idx < len(sigma_row) and sigma_row[h_idx] is not None:
                            csv_row[f"{header}_sigma"] = _format_with_precision(sigma_row[h_idx], mp_precision)
                raw_rows.append(csv_row)

            if raw_rows:
                raw_headers = ["index"] + list(headers)
                if has_sigma:
                    raw_headers += [f"{h}_sigma" for h in headers]
                raw_csv_data = _generate_csv_from_rows(raw_rows, headers=raw_headers)

    pdf_b64 = None
    if compile_pdf:
        validated_engine = validate_latex_engine(latex_engine)
        pdf_bytes = compile_latex_safe(latex_text, validated_engine, warnings, "stats")
        if pdf_bytes:
            pdf_b64 = _encode_b64(pdf_bytes)

    if stats_result.get("dropped"):
        dropped = stats_result.get("dropped")
        warnings.append(
            f"有 {dropped} 条数据因缺少 σ 或格式被忽略。 / {dropped} data points were ignored due to missing σ or invalid format."
        )
    return StatsResultBundle(
        headers=headers,
        rows=data_rows,
        sigmas=sigma_rows,
        result=display_result,
        latex_text=latex_text,
        pdf_b64=pdf_b64,
        plot_b64=plot_b64,
        plot_b64_list=plot_b64_list,
        csv_data=csv_data,
        raw_csv_data=raw_csv_data,
        warnings=warnings,
        stats_mode=stats_mode,
        mp_precision=mp_precision,
    )
