from __future__ import annotations

import io
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import mpmath as mp

from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard

from data_extrapolation_latex_latest import (
    _dual_msg,
    ExtrapolationOptions,
    ExtrapolationResult,
    apply_formula_to_data,
    detect_used_error_propagation_inputs,
    generate_error_propagation_table,
    generate_latex_table,
    process_constants_file,
    process_constants_string,
    process_data_string,
    process_uncertainty_string,
)

from statistics_utils import compute_statistics, generate_statistics_latex_batches

from fitting import (
    auto_fit_dataset,
    build_model_specification,
    build_parameter_state,
    fit_custom_model,
)
from fitting.auto_models import (
    AUTO_MODELS,
    AutoModelDefinition,
    build_inverse_series_definition,
    build_polynomial_definition,
    fit_linear_model,
)
from fitting.hp_fitter import FitResult


@contextmanager
def _mp_precision_guard(dps: int | None):
    """Delegate to ``shared.precision.precision_guard`` with worker-side bounds.

    Kept as a thin wrapper so existing worker call-sites do not need to be
    refactored. ``mp.dps`` is process-global — concurrent workers must share
    a single canonical guard to avoid precision corruption.

    Applies the worker's [MIN_MPMATH_DPS, MAX_MPMATH_DPS] envelope to the
    shared guard so programmatic callers (tests, batch runners, corrupted
    configs) cannot push ``mp.dps`` outside the range the widget spinner
    would normally enforce. Interactive callers are already clamped upstream
    by the Qt spinner; this is the defense-in-depth layer.
    """
    if dps is None:
        yield mp.mp.dps
        return
    with precision_guard(
        dps,
        clamp_min=MIN_MPMATH_DPS,
        clamp_max=MAX_MPMATH_DPS,
    ) as effective_dps:
        yield effective_dps


def _safe_resolve_path(text: str) -> Path:
    """Expand and resolve a user-supplied path without raising on missing files."""
    candidate = Path(text).expanduser()
    try:
        return candidate.resolve()
    except Exception:
        return candidate


def _safe_read_text(path: Path) -> str:
    """Read UTF-8 text with a helpful error message."""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            _dual_msg(
                f"无法以 UTF-8 读取文件 {path}: {exc}",
                f"Failed to decode file as UTF-8: {path} ({exc})",
            )
        ) from exc
    except OSError as exc:
        raise ValueError(
            _dual_msg(
                f"读取文件失败 {path}: {exc}",
                f"Failed to read file: {path} ({exc})",
            )
        ) from exc


def split_extrapolation_result(result):
    """Normalize extrapolation result to (value, sigma, original object)."""
    if isinstance(result, ExtrapolationResult):
        return result.value, result.uncertainty, result
    try:
        value, sigma = result
        return value, sigma, None
    except Exception:
        return result, mp.mpf("0"), None


def _render_extrapolation_plot_bytes(
    row_values: tuple[mp.mpf, ...],
    value: mp.mpf,
    sigma: mp.mpf,
    idx: int,
    *,
    is_en: bool,
) -> bytes | None:
    """Render a per-row extrapolation plot as PNG bytes."""
    if not row_values:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    try:
        y_vals = [float(mp.mpf(v)) for v in row_values]
        x_vals = list(range(1, len(y_vals) + 1))
        x_extrap = x_vals[-1] + 1
        y_extrap = float(value)
        yerr = abs(float(sigma))
        data_label = "Data" if is_en else "数据"
        extrap_label = f"Extrapolated ±σ (row {idx})" if is_en else f"外推值±σ (行 {idx})"
        xlabel = "Point index" if is_en else "点序号"
        ylabel = "Value" if is_en else "数值"
        title = f"Extrapolation trend: row {idx}" if is_en else f"外推趋势：行 {idx}"

        fig, ax = plt.subplots(figsize=(6, 4), dpi=180)
        ax.plot(x_vals, y_vals, marker="o", linestyle="-", color="#1f77b4", label=data_label)
        ax.plot([x_vals[-1], x_extrap], [y_vals[-1], y_extrap], linestyle="--", color="#d62728", alpha=0.7)
        ax.errorbar(
            x_extrap,
            y_extrap,
            yerr=yerr,
            fmt="o",
            color="#d62728",
            ecolor="#555555",
            capsize=4,
            label=extrap_label,
        )
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        ax.legend(frameon=False)
        buf = io.BytesIO()
        fig.tight_layout()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        return None


@dataclass
class AutoFitJob:
    headers: list[str]
    data_rows: list[tuple[mp.mpf, ...]]
    sigma_rows: list[tuple[mp.mpf | None, ...]]
    x_series: list[mp.mpf]
    y_series: list[mp.mpf]
    sigma_series: list[mp.mpf | None]
    weights: list[mp.mpf] | None
    precision: int
    custom_entries: list[tuple[str, Any, Any]]
    extra_models: list[AutoModelDefinition]
    verbose: bool = False
    render_plots: bool = True
    # Phase 3 #12 — when True, run MCMC posterior refinement on the
    # best-AIC candidate after least-squares completes. Opt-in because
    # emcee typically takes 10–60 s on modest problems. Silently
    # skipped if emcee isn't installed (mcmc_fitter.HAS_EMCEE=False).
    refine_with_mcmc: bool = False


def _execute_auto_fit_job(job: AutoFitJob):
    with _mp_precision_guard(job.precision):
        return auto_fit_dataset(
            job.x_series,
            job.y_series,
            precision=job.precision,
            custom_entries=job.custom_entries or None,
            extra_models=job.extra_models,
            weights=job.weights,
            data_sigmas=job.sigma_series,
        )


@dataclass
class CalcJob:
    mode: str
    data_path: Path | None
    manual_content: str
    manual_constants: str
    constants_file_path: str | None
    options: ExtrapolationOptions
    caption: str | None
    generate_latex: bool
    output_path: str
    use_dcolumn: bool
    verbose: bool
    render_plots: bool = False
    constants_enabled: bool = False
    use_constants_file: bool = False
    formula: str | None = None
    error_propagation_method: str = "taylor"
    error_propagation_order: int = 1
    error_mc_samples: int | None = None
    error_mc_seed: int | None = None
    lang: str = "en"
    stats_value_col: str | None = None
    stats_sigma_col: str | None = None
    stats_mode: str | None = None
    stats_sample: bool = True
    stats_weighted_variance: bool = True
    dataset: tuple[list[str], list[tuple[mp.mpf, ...]], list[tuple[mp.mpf | None, ...]]] | None = None
    latex_digits: int = 16
    latex_group_size: int = 3
    segments: list[tuple[int, int]] | None = None
    uncertainty_digits: int = 3


@dataclass
class CalcResult:
    mode: str
    logs: list[str]
    warnings: list[str]
    payload: dict[str, object]
    latex_path: str | None = None


def _build_contribution_summary(contrib_map: dict[str, mp.mpf]) -> list[dict[str, object]]:
    if not contrib_map:
        return []
    total_var = sum(contrib_map.values())
    if total_var <= 0:
        total_var = mp.mpf("0")
    summary: list[dict[str, object]] = []
    for name, var in contrib_map.items():
        sigma = mp.sqrt(var) if var >= 0 else mp.mpf("0")
        percent = float(var / total_var * 100) if total_var != 0 else 0.0
        summary.append({"name": name, "variance": var, "sigma": sigma, "percent": percent})
    summary.sort(key=lambda item: item.get("variance", mp.mpf("0")), reverse=True)
    return summary


def _render_contribution_plot(
    summary: list[dict[str, object]],
    lang: str,
    *,
    title_suffix: str | None = None,
) -> bytes | None:
    if not summary:
        return None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None
    try:
        labels = [entry["name"] for entry in summary]
        percents = [float(entry.get("percent", 0.0)) for entry in summary]
        fig, ax = plt.subplots(figsize=(6.0, 0.45 * len(summary) + 1.2), dpi=180)
        y_pos = list(range(len(labels)))
        bars = ax.barh(y_pos, percents, color="#4f6bed")
        ax.invert_yaxis()
        xlabel = "Uncertainty contribution (%)" if lang == "en" else "不确定度贡献 (%)"
        ax.set_xlabel(xlabel)
        ax.set_xlim(0, max(100.0, (max(percents) if percents else 0) * 1.1))
        ax.set_yticks(y_pos, labels)
        for bar, pct in zip(bars, percents):
            ax.text(bar.get_width() + 1.5, bar.get_y() + bar.get_height() / 2, f"{pct:.2f}%", va="center")
        ax.grid(axis="x", alpha=0.3, linestyle="--")
        base_title = "Uncertainty breakdown" if lang == "en" else "不确定度贡献分解"
        if title_suffix:
            base_title = f"{base_title} - {title_suffix}"
        ax.set_title(base_title)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        return None


def _aggregate_error_contributions(
    results: list[object],
    lang: str,
    *,
    render_plot: bool = True,
) -> tuple[list[dict[str, object]], bytes | None]:
    contrib_sum: dict[str, mp.mpf] = {}
    for entry in results:
        contribs = getattr(entry, "contributions", None)
        if not contribs:
            continue
        for name, value in contribs.items():
            try:
                contrib_sum[name] = contrib_sum.get(name, mp.mpf("0")) + mp.mpf(value)
            except Exception:
                continue
    if not contrib_sum:
        return [], None
    summary = _build_contribution_summary(contrib_sum)
    plot_bytes: bytes | None = None
    if render_plot:
        try:
            plot_bytes = _render_contribution_plot(summary, lang)
        except Exception:
            plot_bytes = None
    return summary, plot_bytes


def _execute_calc_job(
    job: CalcJob,
    *,
    stop_checker=None,
    emit_log=None,
) -> CalcResult:
    logs: list[str] = []
    options = job.options
    lang = job.lang

    def _check_cancelled():
        if stop_checker:
            stop_checker()

    def _v(message: str):
        if job.verbose:
            logs.append(message)
            if emit_log:
                try:
                    emit_log(message)
                except Exception:
                    pass

    def _loc(zh: str, en: str) -> str:
        return en if lang == "en" else zh

    def _segment_lengths_from_text(text: str, expected_rows: int) -> list[int]:
        if not text or not text.strip():
            return []
        lengths: list[int] = []
        header_seen = False
        current = 0
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                if header_seen and current > 0:
                    lengths.append(current)
                    current = 0
                continue
            if not header_seen:
                header_seen = True
                continue
            current += 1
        if header_seen and current > 0:
            lengths.append(current)
        total = sum(lengths)
        if expected_rows <= 0:
            return lengths
        if not lengths:
            return [expected_rows]
        if total == expected_rows:
            return lengths
        adjusted: list[int] = []
        used = 0
        for seg_len in lengths:
            if used >= expected_rows:
                break
            remaining = expected_rows - used
            clipped = min(max(seg_len, 0), remaining)
            if clipped > 0:
                adjusted.append(clipped)
                used += clipped
        if used < expected_rows:
            adjusted.append(expected_rows - used)
        return adjusted

    def _table_segments_from_lengths(total_rows: int, lengths: list[int]) -> list[tuple[int, int]]:
        if total_rows <= 0:
            return []
        segments: list[tuple[int, int]] = []
        start = 0
        for length in lengths:
            if length <= 0:
                continue
            end = start + length
            segments.append((start, min(end, total_rows)))
            start = end
        if not segments or segments[-1][1] != total_rows:
            return [(0, total_rows)]
        normalized: list[tuple[int, int]] = []
        last_end = 0
        for segment_start, segment_end in segments:
            if segment_start != last_end:
                return [(0, total_rows)]
            normalized.append((segment_start, segment_end))
            last_end = segment_end
        return normalized

    headers: list[str] | None = None
    latex_path: str | None = None
    payload: dict[str, object] = {}

    _check_cancelled()
    with _mp_precision_guard(options.mp_precision) as applied_precision:
        if job.mode == "extrapolation":
            data_rows: list[tuple[mp.mpf, ...]] = []
            results: list[object] = []
            plot_bytes_list: list[bytes | None] = []
            seg_lengths: list[int] = []
            if job.data_path:
                _check_cancelled()
                text = _safe_read_text(job.data_path)
                h, rows, res = process_data_string(text, job.verbose, options=options)
                headers = h
                data_rows.extend(rows)
                results.extend(res)
                seg_lengths.extend(_segment_lengths_from_text(text, len(rows)))
                logs.append(f"Loaded file data: {job.data_path}")
            if job.manual_content:
                _check_cancelled()
                h, rows, res = process_data_string(job.manual_content, job.verbose, options=options)
                if headers is None:
                    headers = h
                elif headers != h:
                    raise ValueError(
                        _dual_msg(
                            "文件与手动输入的表头不一致。",
                            "File headers do not match the manual header.",
                        )
                    )
                data_rows.extend(rows)
                results.extend(res)
                seg_lengths.extend(_segment_lengths_from_text(job.manual_content, len(rows)))
                logs.append("Manual input data used.")
            if not headers or not data_rows:
                raise ValueError(
                    _dual_msg(
                        "没有可用于外推的有效数据。",
                        "No valid data available for extrapolation.",
                    )
                )
            _v(f"[extrapolation] rows={len(data_rows)} headers={headers}")
            table_segments = _table_segments_from_lengths(len(data_rows), seg_lengths)
            if job.generate_latex:
                _check_cancelled()
                generate_latex_table(
                    headers,
                    data_rows,
                    results,
                    job.output_path,
                    caption=job.caption,
                    precision=job.latex_digits,
                    verbose=job.verbose,
                    use_dcolumn=job.use_dcolumn,
                    table_segments=table_segments,
                    result_uncertainty_digits=job.uncertainty_digits,
                    latex_group_size=job.latex_group_size,
                )
                latex_path = job.output_path
                logs.append(f"LaTeX written: {job.output_path}")
            if job.render_plots:
                is_en = job.lang == "en"
                for idx, (row, res) in enumerate(zip(data_rows, results), 1):
                    _check_cancelled()
                    value, sigma, _ = split_extrapolation_result(res)
                    plot_bytes = _render_extrapolation_plot_bytes(row, value, sigma, idx, is_en=is_en)
                    plot_bytes_list.append(plot_bytes)
            payload = {
                "headers": headers,
                "data_rows": data_rows,
                "results": results,
                "table_segments": table_segments,
                "precision_used": applied_precision,
                "render_plots": job.render_plots,
            }
            if plot_bytes_list:
                payload["plots"] = plot_bytes_list
        elif job.mode == "error":
            _check_cancelled()
            if not job.formula:
                raise ValueError(
                    _dual_msg(
                        "误差传递需要填写公式。",
                        "Error propagation requires a formula.",
                    )
                )
            constants: dict[str, object] = {}
            if job.options and job.options.warnings is None:
                job.options.warnings = []
            if job.constants_enabled:
                if job.use_constants_file:
                    const_path_text = job.constants_file_path or ""
                    if not const_path_text:
                        raise ValueError(
                            _loc(
                                "已启用常数，但未提供常数文件。",
                                "Constants enabled but no constants file provided.",
                            )
                        )
                    path = _safe_resolve_path(const_path_text)
                    if not path.exists():
                        raise ValueError(_loc("常数文件不存在。", "Constants file not found."))
                    constants = process_constants_file(str(path), job.verbose)
                    logs.append(f"Loaded constants file: {path}")
                else:
                    if job.manual_constants:
                        constants = process_constants_string(job.manual_constants, job.verbose)
                        if constants:
                            logs.append("Manual constants appended.")
                        else:
                            raise ValueError(
                                _loc(
                                    "未能解析手动常数，请检查格式。",
                                    "Failed to parse manual constants, please check the format.",
                                )
                            )
                    else:
                        raise ValueError(
                            _loc(
                                "已启用常数，但未提供手动常数。",
                                "Constants enabled but no manual constants provided.",
                            )
                        )

            parsed_data = []
            seg_lengths: list[int] = []
            if job.data_path:
                text = _safe_read_text(job.data_path)
                h, rows = process_uncertainty_string(text, job.verbose)
                headers = h
                parsed_data.extend(rows)
                seg_lengths.extend(_segment_lengths_from_text(text, len(rows)))
                logs.append(f"Loaded file data: {job.data_path}")
            if job.manual_content:
                h, rows = process_uncertainty_string(job.manual_content, job.verbose)
                if headers is None:
                    headers = h
                elif headers != h:
                    raise ValueError(
                        _dual_msg(
                            "文件与手动输入的表头不一致。",
                            "File headers do not match the manual header.",
                        )
                    )
                parsed_data.extend(rows)
                seg_lengths.extend(_segment_lengths_from_text(job.manual_content, len(rows)))
                logs.append("Manual data used.")
            if not headers or not parsed_data:
                raise ValueError(
                    _dual_msg(
                        "未能解析出任何误差传递数据。",
                        "No error-propagation data could be parsed.",
                    )
                )
            _v(f"[error] rows={len(parsed_data)} headers={headers} formula={job.formula}")
            table_segments = _table_segments_from_lengths(len(parsed_data), seg_lengths)
            used_headers, used_constants = detect_used_error_propagation_inputs(headers, constants, job.formula or "")
            constants_used = {name: constants[name] for name in used_constants if name in constants}
            _check_cancelled()
            results = apply_formula_to_data(
                headers,
                parsed_data,
                constants_used,
                job.formula,
                job.verbose,
                warnings=options.warnings,
                return_components=True,
                propagation_method=job.error_propagation_method,
                propagation_order=job.error_propagation_order,
                mc_samples=job.error_mc_samples,
                mc_seed=job.error_mc_seed,
            )
            row_plot_bytes: list[bytes | None] = []
            if job.render_plots:
                for idx_row, res in enumerate(results, 1):
                    contrib_map = getattr(res, "contributions", None)
                    if not contrib_map:
                        row_plot_bytes.append(None)
                        continue
                    summary = _build_contribution_summary({k: mp.mpf(v) for k, v in contrib_map.items() if v is not None})
                    if not summary:
                        row_plot_bytes.append(None)
                        continue
                    try:
                        plot_bytes = _render_contribution_plot(summary, lang, title_suffix=f"row {idx_row}")
                    except Exception:
                        plot_bytes = None
                    row_plot_bytes.append(plot_bytes)
            contrib_summary, contrib_plot = _aggregate_error_contributions(results, lang, render_plot=job.render_plots)
            if contrib_summary:
                title = "[error] uncertainty breakdown" if lang == "en" else "[误差] 不确定度贡献分解"
                logs.append(title)
                for entry in contrib_summary:
                    name = entry["name"]
                    percent = entry["percent"]
                    sigma_txt = mp.nstr(entry["sigma"], 8)
                    logs.append(f" - {name}: {percent:.2f}% (σ_contrib={sigma_txt})")
            payload = {
                "headers": headers,
                "parsed_data": parsed_data,
                "results": results,
                "table_segments": table_segments,
                "constants": constants_used,
                "formula": job.formula or "",
                "precision_used": applied_precision,
            }
            has_row_plots = any(plot for plot in row_plot_bytes)
            if contrib_summary:
                payload["contribution_breakdown"] = contrib_summary
            if job.render_plots and contrib_plot:
                payload["contribution_plot"] = contrib_plot
            if job.render_plots and has_row_plots:
                payload["row_contribution_plots"] = row_plot_bytes
            if job.generate_latex:
                generate_error_propagation_table(
                    headers,
                    parsed_data,
                    results,
                    constants_used,
                    job.formula,
                    job.output_path,
                    caption=job.caption,
                    verbose=job.verbose,
                    use_dcolumn=job.use_dcolumn,
                    table_segments=table_segments,
                    precision=job.latex_digits,
                    result_uncertainty_digits=job.uncertainty_digits,
                    used_columns=used_headers,
                    latex_group_size=job.latex_group_size,
                )
                latex_path = job.output_path
                logs.append(f"Error propagation LaTeX written: {job.output_path}")
        elif job.mode == "statistics":
            _check_cancelled()
            if not job.dataset:
                raise ValueError(
                    _dual_msg(
                        "统计数据缺失，无法计算。",
                        "Statistics data is missing; cannot compute.",
                    )
                )
            headers, rows, sigma_rows = job.dataset
            value_col = job.stats_value_col or ""
            if not value_col:
                raise ValueError(
                    _dual_msg(
                        "请在统计设置中指定数值列。",
                        "Please select the value column in statistics settings.",
                    )
                )
            if value_col not in headers:
                raise ValueError(
                    _dual_msg(
                        f"未找到列 {value_col}。",
                        f"Column not found: {value_col}.",
                    )
                )
            val_idx = headers.index(value_col)
            sigma_col = (job.stats_sigma_col or "").strip()
            sigma_idx = None
            if sigma_col:
                if sigma_col not in headers:
                    raise ValueError(
                        _dual_msg(
                            f"未找到列 {sigma_col}。",
                            f"Column not found: {sigma_col}.",
                        )
                    )
                sigma_idx = headers.index(sigma_col)
            segments = job.segments or [(0, len(rows))]
            batches: list[dict[str, object]] = []
            normalized_segments = segments if segments else [(0, len(rows))]
            _v(f"[statistics] rows={len(rows)} value_col={value_col} batches={len(normalized_segments)}")
            if job.verbose:
                print(
                    "[statistics] mode="
                    f"{job.stats_mode or 'mean'} use_sample={job.stats_sample} "
                    f"use_weighted_variance={job.stats_weighted_variance}"
                )
                print(
                    f"[statistics] value_col={value_col} sigma_cols={'yes' if sigma_rows else 'no'} "
                    f"total_rows={len(rows)} batches={len(normalized_segments)}"
                )
            for batch_idx, (start, end) in enumerate(normalized_segments, 1):
                _check_cancelled()
                start = max(0, start)
                end = min(len(rows), max(start, end))
                batch_rows = rows[start:end]
                if not batch_rows:
                    continue
                batch_sigmas = sigma_rows[start:end] if sigma_rows else []
                values = [row[val_idx] for row in batch_rows]
                sigmas: list[mp.mpf | None] = []
                if sigma_idx is not None:
                    for row in batch_rows:
                        entry_val = None
                        if sigma_idx < len(row):
                            try:
                                entry_val = mp.mpf(row[sigma_idx])
                            except Exception:
                                entry_val = None
                        sigmas.append(mp.fabs(entry_val) if entry_val is not None else None)
                else:
                    for sigma_row in batch_sigmas:
                        entry = sigma_row[val_idx] if val_idx < len(sigma_row) else None
                        if entry is None:
                            sigmas.append(None)
                            continue
                        if hasattr(entry, "uncertainty"):
                            entry_val = getattr(entry, "uncertainty", None)
                        else:
                            entry_val = entry
                        try:
                            sigmas.append(mp.mpf(entry_val) if entry_val is not None else None)
                        except Exception:
                            sigmas.append(None)
                if job.verbose:
                    print(
                        f"[statistics] batch {batch_idx} size={len(values)} use_sample={job.stats_sample} use_weighted_variance={job.stats_weighted_variance}"
                    )
                    for i, (v, s) in enumerate(zip(values, sigmas), 1):
                        print(f"[statistics] batch {batch_idx} point {i}: value={v} sigma={s}")
                try:
                    result = compute_statistics(
                        values,
                        sigmas,
                        job.stats_mode or "mean",
                        use_sample=job.stats_sample,
                        use_weighted_variance=job.stats_weighted_variance,
                    )
                except Exception as exc:  # noqa: BLE001
                    message = _loc(f"批次 {batch_idx} 统计失败: {exc}", f"Batch {batch_idx} failed: {exc}")
                    raise ValueError(message) from exc
                if job.verbose:
                    print(
                        f"[statistics] batch {batch_idx} mean={result.get('mean')} "
                        f"std={result.get('std')} std_mean={result.get('std_mean')} "
                        f"v_min={result.get('v_min')} v_max={result.get('v_max')} "
                        f"n_eff={result.get('effective_n')}"
                    )
                batches.append(
                    {
                        "index": batch_idx,
                        "headers": headers,
                        "value_col": value_col,
                        "rows": batch_rows,
                        "sigma_rows": batch_sigmas,
                        "values": values,
                        "sigmas": sigmas,
                        "result": result,
                        "row_count": len(batch_rows),
                    }
                )
            if not batches:
                raise ValueError(
                    _dual_msg(
                        "统计列中没有数据。",
                        "No data in the statistics column.",
                    )
                )
            if job.generate_latex:
                generate_statistics_latex_batches(
                    value_col,
                    batches,
                    job.latex_digits,
                    job.output_path,
                    job.use_dcolumn,
                    caption=job.caption,
                    uncertainty_digits=job.uncertainty_digits,
                    latex_group_size=job.latex_group_size,
                )
                latex_path = job.output_path
                logs.append(f"统计平均 LaTeX 已写入: {job.output_path}")
            payload = {
                "batches": batches,
                "value_col": value_col,
                "row_count": len(rows),
                "headers": headers,
                "values": batches[0]["values"] if len(batches) == 1 else None,
                "sigmas": batches[0]["sigmas"] if len(batches) == 1 else None,
                "render_plots": job.render_plots,
                "precision_used": applied_precision,
            }
        else:
            raise ValueError(f"Unsupported mode for async calculation: {job.mode}")

    warnings = list(options.warnings) if getattr(options, "warnings", None) else []
    return CalcResult(mode=job.mode, logs=logs, warnings=warnings, payload=payload, latex_path=latex_path)



@dataclass
class FitJob:
    model_type: str
    headers: list[str]
    data_rows: list[tuple[mp.mpf, ...]]
    sigma_rows: list[tuple[mp.mpf | None, ...]]
    x_series: list[mp.mpf]
    y_series: list[mp.mpf]
    sigma_series: list[mp.mpf | None]
    weights: list[mp.mpf] | None
    variable_map: dict[str, str]
    variable_data: dict[str, list[mp.mpf]]
    target_series: list[mp.mpf]
    target_column: str
    model_expr: str
    parameter_config: dict
    parameter_names: list[str]
    template_expr: str | None = None
    template_params: dict | None = None
    poly_degree: int = 0
    inverse_min: int = 1
    inverse_max: int = 3
    pade_m: int = 1
    pade_n: int = 1
    auto_identifier: str | None = None
    precision: int = 80
    generate_latex: bool = False
    output_path: str = ""
    use_dcolumn: bool = True
    caption: str | None = None
    verbose: bool = False
    render_plots: bool = True
    latex_digits: int = 16
    weighted: bool = False
    label: str = ""
    is_multidim: bool = False


@dataclass
class FitResultPayload:
    job: FitJob
    fit_result: FitResult
    expression: str
    logs: list[str]
    warnings: list[str]


@dataclass
class FitBatchTask:
    index: int
    fit_job: FitJob | None = None
    auto_job: AutoFitJob | None = None


@dataclass
class FitBatchResultEntry:
    index: int
    kind: str  # "fit", "auto", or "error"
    fit_payload: FitResultPayload | None = None
    auto_payload: tuple | None = None  # (summary, job)
    error: str | None = None
    captured_log: str = ""


@dataclass
class AutoFitRenderResult:
    text: str
    plot_bytes: bytes | None
    fit_result: FitResult | None
    expression: str | None
    substituted: str | None


def _execute_fit_job_payload(job: FitJob) -> FitResultPayload:
    logs: list[str] = []
    warnings: list[str] = []
    with _mp_precision_guard(job.precision):
        if job.verbose:
            try:
                print(
                    f"[fit] model={job.model_type} label={job.label} "
                    f"target={job.target_column} vars={list(job.variable_map.keys()) or ['x']} "
                    f"n={len(job.x_series)} precision={job.precision} weighted={job.weighted}"
                )
                if job.model_expr:
                    print(f"[fit] expression={job.model_expr}")
                if job.parameter_config:
                    print(f"[fit] initial_params={job.parameter_config}")
            except Exception:
                pass
        model_type = job.model_type
        fit_result: FitResult | None = None
        expression = job.model_expr
        if model_type in {"poly", "inverse", "log_poly", "exp_combo"}:
            if model_type == "poly":
                definition = build_polynomial_definition(job.poly_degree)
            elif model_type == "inverse":
                definition = build_inverse_series_definition(job.inverse_min, job.inverse_max)
            else:
                identifier = job.auto_identifier or ("M4B" if model_type == "log_poly" else "M7B")
                definition = next((d for d in AUTO_MODELS if d.identifier == identifier), None)
                if definition is None:
                    raise ValueError(_dual_msg(f"未找到模型 {identifier}", f"Model not found: {identifier}"))
            fit_result = fit_linear_model(
                definition,
                job.x_series,
                job.y_series,
                precision=job.precision,
                weights=job.weights,
                data_sigmas=job.sigma_series,
            )
            expression = fit_result.details.get("expression", expression)
            logs.append(f"{definition.label} 完成。")
        elif model_type in {"power_limit", "pade", "custom"}:
            expr = job.template_expr if model_type in {"power_limit", "pade"} else job.model_expr
            params = job.template_params if model_type in {"power_limit", "pade"} else job.parameter_config
            var_names = list(job.variable_map.keys()) or ["x"]
            param_keys = list(params.keys()) if params else []
            parameter_names: list[str] = []
            seen: set[str] = set()
            for name in param_keys + list(job.parameter_names):
                if name in seen:
                    continue
                parameter_names.append(name)
                seen.add(name)
            if not parameter_names:
                parameter_names = param_keys
            spec = build_model_specification(expr, var_names, parameter_names)
            state = build_parameter_state(params or {}, parameter_names)
            fit_result = fit_custom_model(
                spec,
                state,
                job.variable_data,
                job.target_series,
                precision=job.precision,
                weights=job.weights,
                data_sigmas=job.sigma_series,
            )
            expression = expr
            logs.append(f"{model_type} 拟合完成。")
        else:
            raise ValueError(
                _dual_msg(
                    f"不支持的拟合模型: {model_type}",
                    f"Unsupported fit model: {model_type}",
                )
            )
        if job.verbose and fit_result is not None:
            try:
                print(f"[fit] params={fit_result.params}")
                print(
                    f"[fit] chi2={fit_result.chi2} reduced_chi2={fit_result.reduced_chi2} "
                    f"r2={fit_result.r2} rmse={fit_result.rmse}"
                )
                if fit_result.param_errors_total:
                    print(f"[fit] param_errors_total={fit_result.param_errors_total}")
            except Exception:
                pass
    return FitResultPayload(job=job, fit_result=fit_result, expression=expression, logs=logs, warnings=warnings)


__all__ = [
    "AutoFitJob",
    "AutoFitRenderResult",
    "CalcJob",
    "CalcResult",
    "FitBatchResultEntry",
    "FitBatchTask",
    "FitJob",
    "FitResultPayload",
    "split_extrapolation_result",
]
