from __future__ import annotations

import io
import inspect
import logging
import math
import multiprocessing
import queue
import time
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, cast

import mpmath as mp

from shared.parallel_backend import KillableProcessTaskRunner
from shared.precision import MAX_MPMATH_DPS, MIN_MPMATH_DPS, precision_guard
from shared.parallel_config import NestedParallelPolicy, ParallelConfig, ParallelMode
from shared.uncertainty import UncertainValue, parse_uncertainty_format

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
    ImplicitModelDefinition,
    ImplicitSolveOptions,
    build_implicit_model_specification,
    build_model_specification,
    build_parameter_state,
    FitRunner,
    ModelProblem,
    fit_custom_model,
)
from fitting import implicit_model as _implicit_model
from fitting.auto_models import (
    build_inverse_series_definition,
    build_polynomial_definition,
    fit_linear_model,
)
from fitting.hp_fitter import FitResult
from root_solving.batch import solve_root_batch
from root_solving.formatting import render_root_batch_result
from root_solving.models import RootUnknown
from root_solving.normalization import normalize_root_uncertainty_options
from shared.input_normalization import normalize_constants_state
# Private-by-convention logger name — matches the rest of DataLab
# (_logger in sse.py, collaborate.py, mcmc_fitter.py, etc.). The
# leading underscore prevents ``from app_desktop.workers_core import
# logger`` from accidentally exposing the handle as a public API.
_logger = logging.getLogger(__name__)

can_fit_observed_implicit_variable = getattr(
    _implicit_model,
    "can_fit_observed_implicit_variable",
    lambda _definition: False,
)
fit_observed_implicit_variable_linear_model = getattr(
    _implicit_model,
    "fit_observed_implicit_variable_linear_model",
    None,
)
_ORIGINAL_BUILD_IMPLICIT_MODEL_SPECIFICATION = build_implicit_model_specification
_ORIGINAL_CAN_FIT_OBSERVED_IMPLICIT_VARIABLE = can_fit_observed_implicit_variable
_ORIGINAL_FIT_OBSERVED_IMPLICIT_VARIABLE_LINEAR_MODEL = fit_observed_implicit_variable_linear_model
_ORIGINAL_FIT_CUSTOM_MODEL = fit_custom_model


def _attach_mcmc_refinement(summary: Any, job: Any) -> None:
    """Attach MCMC diagnostics to the current best fit when available."""

    from fitting.mcmc_fitter import HAS_EMCEE, render_corner_plot, run_mcmc

    if not HAS_EMCEE:
        _logger.info("refine_with_mcmc=True but emcee not installed; skipping")
        return
    best = summary.best() if getattr(summary, "best_model", None) is not None else None
    if best is None or getattr(best, "fit_result", None) is None:
        _logger.info("refine_with_mcmc=True but no best candidate; skipping")
        return

    best_fit = best.fit_result
    param_names = _mcmc_free_parameter_names(best_fit, job)
    if not param_names:
        _logger.info("best candidate has no parameters; skipping MCMC")
        return
    initial_guess = [float(best_fit.params[name]) for name in param_names]
    base_params = {name: mp.mpf(value) for name, value in (best_fit.params or {}).items()}
    parameter_state = _mcmc_parameter_state(job)
    observations, targets = _mcmc_observations(job)
    likelihood_weights = _mcmc_likelihood_weights(job, len(targets))
    rmse = _estimate_rmse(targets, best_fit)
    evaluator = best_fit.details.get("evaluator") if best_fit.details else None
    if evaluator is None:
        _logger.info("MCMC refinement skipped: best fit did not provide an evaluator")
        return

    def _log_probability(theta: Sequence[object]) -> float:
        if not param_names or rmse <= 0:
            return float("-inf")
        try:
            new_params = _mcmc_params_from_theta(
                theta,
                param_names,
                base_params,
                parameter_state,
            )
            residuals_sq = 0.0
            for index, (observation, target) in enumerate(zip(observations, targets)):
                _set_mcmc_evaluator_point_index(evaluator, index)
                pred = float(_evaluate_mcmc_prediction(evaluator, new_params, observation))
                if not math.isfinite(pred):
                    return float("-inf")
                residual = float(target) - pred
                weight = float(likelihood_weights[index]) if likelihood_weights is not None else 1.0
                residuals_sq += weight * (residual**2)
                if not math.isfinite(residuals_sq):
                    return float("-inf")
            return -0.5 * residuals_sq / (rmse**2)
        except (TypeError, ValueError, ArithmeticError, OverflowError, KeyError):
            return float("-inf")

    import math as _math_pre

    proposal_scale = max(1e-4, rmse * 1e-2)
    pre_flight_lps = [_log_probability(initial_guess)]
    for sign in (-1, 1):
        perturbed = [value + sign * proposal_scale for value in initial_guess]
        pre_flight_lps.append(_log_probability(perturbed))
    if not any(_math_pre.isfinite(lp) for lp in pre_flight_lps):
        _logger.info(
            "MCMC pre-flight: all %d sample log-probabilities were -inf; skipping MCMC refinement.",
            len(pre_flight_lps),
        )
        if best_fit.details is None:
            best_fit.details = {}
        best_fit.details["mcmc_warning"] = (
            "MCMC 跳过：初始 log-probability 全部 -inf（数据过于病态）。 / "
            "MCMC skipped: all initial log-probabilities are -inf "
            "(data is too ill-conditioned for Gaussian sampling)."
        )
        return

    try:
        mcmc_result = run_mcmc(
            _log_probability,
            initial_guess,
            param_names,
            n_walkers=max(32, 2 * len(param_names) + 2),
            n_steps=800,
            n_burn_in=200,
            proposal_scale=proposal_scale,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("MCMC run failed: %s", exc)
        if best_fit.details is None:
            best_fit.details = {}
        best_fit.details["mcmc_warning"] = (
            f"MCMC 运行失败：{exc}。仅使用最小二乘结果。 / "
            f"MCMC run failed: {exc}. Using LSQ-only result."
        )
        return

    acc = mcmc_result.acceptance_fraction
    chain_warning: str | None = None
    if not _math_pre.isfinite(acc) or acc < 0.05:
        chain_warning = (
            f"MCMC 接受率 {acc:.2f} 过低（<0.05），结果可能不可靠。 / "
            f"MCMC acceptance fraction {acc:.2f} is very low (<0.05); "
            "credible intervals may be unreliable."
        )
    elif acc > 0.85:
        chain_warning = (
            f"MCMC 接受率 {acc:.2f} 过高（>0.85），proposal_scale 可能太小。 / "
            f"MCMC acceptance fraction {acc:.2f} is very high (>0.85); "
            "proposal_scale may be too small."
        )

    corner_png = b""
    try:
        corner_png = render_corner_plot(mcmc_result)
    except Exception as exc:  # noqa: BLE001
        _logger.warning("corner plot render failed: %s", exc)

    if best_fit.details is None:
        best_fit.details = {}
    best_fit.details["mcmc_refinement"] = {
        "medians": mcmc_result.medians,
        "lo_ci": mcmc_result.lo_ci,
        "hi_ci": mcmc_result.hi_ci,
        "acceptance_fraction": mcmc_result.acceptance_fraction,
    }
    if chain_warning:
        best_fit.details["mcmc_warning"] = chain_warning
    if corner_png:
        best_fit.details["mcmc_corner_png"] = corner_png


def _mcmc_free_parameter_names(best_fit: Any, job: Any) -> list[str]:
    params = getattr(best_fit, "params", {}) or {}
    configured_names = list(getattr(job, "parameter_names", []) or [])
    if configured_names:
        return [name for name in configured_names if name in params and not _mcmc_parameter_is_fixed(job, name)]
    return [name for name in params if not _mcmc_parameter_is_fixed(job, name)]


def _mcmc_parameter_is_fixed(job: Any, name: str) -> bool:
    config = getattr(job, "parameter_config", {}) or {}
    entry = config.get(name, {}) if isinstance(config, dict) else {}
    return isinstance(entry, dict) and (bool(entry.get("fixed")) or bool(entry.get("expr")))


def _mcmc_parameter_state(job: Any) -> Any | None:
    parameter_names = list(getattr(job, "parameter_names", []) or [])
    parameter_config = getattr(job, "parameter_config", {}) or {}
    if not parameter_names or not isinstance(parameter_config, dict):
        return None
    try:
        return build_parameter_state(parameter_config, parameter_names)
    except Exception:  # noqa: BLE001 - MCMC must not fail the completed LSQ fit.
        return None


def _mcmc_params_from_theta(
    theta: Sequence[object],
    param_names: Sequence[str],
    base_params: Mapping[str, mp.mpf],
    parameter_state: Any | None,
) -> dict[str, mp.mpf]:
    theta_values = [mp.mpf(value) for value in theta]
    theta_by_name = dict(zip(param_names, theta_values))
    if parameter_state is not None:
        free_vector = tuple(
            theta_by_name.get(name, base_params.get(name, mp.mpf("0")))
            for name in parameter_state.free_params
        )
        return cast(dict[str, mp.mpf], parameter_state.compose(free_vector))
    params = dict(base_params)
    params.update(theta_by_name)
    return params


def _mcmc_observations(job: Any) -> tuple[list[object], list[mp.mpf]]:
    variable_data = getattr(job, "variable_data", None)
    targets = getattr(job, "target_series", None)
    if isinstance(variable_data, dict) and targets is not None:
        names = list(variable_data)
        row_count = len(targets)
        observations: list[object] = []
        for index in range(row_count):
            observations.append({name: mp.mpf(variable_data[name][index]) for name in names})
        return observations, [mp.mpf(value) for value in targets]
    x_series = list(getattr(job, "x_series", []) or [])
    y_series = list(getattr(job, "y_series", []) or [])
    return [mp.mpf(value) for value in x_series], [mp.mpf(value) for value in y_series]


def _mcmc_likelihood_weights(job: Any, target_count: int) -> list[mp.mpf] | None:
    weights = getattr(job, "weights", None)
    if weights is not None and len(weights) == target_count:
        return [mp.mpf(value) for value in weights]
    sigmas = getattr(job, "sigma_series", None)
    if sigmas is None or len(sigmas) != target_count:
        return None
    parsed: list[mp.mpf] = []
    for sigma in sigmas:
        if sigma is None:
            return None
        value = mp.mpf(sigma)
        if value <= 0:
            return None
        parsed.append(1 / (value * value))
    return parsed


def _set_mcmc_evaluator_point_index(evaluator: Any, index: int) -> None:
    setter = getattr(evaluator, "set_implicit_point_index", None)
    if callable(setter):
        setter(index)


def _evaluate_mcmc_prediction(evaluator: Any, params: Mapping[str, mp.mpf], observation: object) -> Any:
    scalar_observation = None
    if isinstance(observation, Mapping) and len(observation) == 1:
        scalar_observation = next(iter(observation.values()))
    candidates: list[tuple[object, ...]] = [(params, observation)]
    if scalar_observation is not None:
        candidates.append((params, scalar_observation))
        candidates.append((scalar_observation,))
    candidates.append((observation,))
    for args in candidates:
        if _callable_accepts_args(evaluator, args):
            return evaluator(*args)
    raise TypeError("MCMC evaluator does not accept supported argument shapes")


def _callable_accepts_args(evaluator: Any, args: Sequence[object]) -> bool:
    try:
        signature = inspect.signature(evaluator)
    except (TypeError, ValueError):
        return True
    try:
        signature.bind(*args)
    except TypeError:
        return False
    return True


def _estimate_rmse(y_series: Any, best_fit: Any) -> float:
    """Estimate a strictly positive RMSE for MCMC proposal scaling."""

    residuals = best_fit.details.get("residuals") if best_fit.details else None
    if residuals:
        try:
            count = len(residuals)
            ss = sum(float(residual) ** 2 for residual in residuals)
            return max(1e-8, (ss / max(1, count)) ** 0.5)
        except Exception:  # noqa: BLE001
            pass
    try:
        values = [float(value) for value in y_series]
        if len(values) < 2:
            return 1.0
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        return max(1e-8, variance**0.5)
    except Exception:  # noqa: BLE001
        return 1.0


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


_READ_FALLBACK_ENCODINGS: tuple[str, ...] = (
    "utf-8",       # de-facto standard for new content
    "utf-8-sig",   # some Windows editors emit a BOM
    "gbk",         # zh-CN Windows default; ``cp936`` is just an
                   # alias on CPython so we don't list it twice
    "latin-1",     # terminator: never raises on byte input
)


def _safe_read_text(path: Path) -> str:
    """Read text with multi-encoding fallback.

    A real LaTeX user reported ``UnicodeDecodeError: 'utf-8' codec
    can't decode byte 0xcd`` opening a .tex saved as GBK on a
    zh-CN Windows box. The fallback chain (see
    ``_READ_FALLBACK_ENCODINGS``) ends with Latin-1, which never
    raises on byte input — mojibake from a wrong-encoding decode
    is recoverable (the user can re-save in UTF-8), a fatal dialog
    is not.

    Raises ``ValueError`` only on actual filesystem errors (missing
    file, permission denied, etc.).
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(
            _dual_msg(
                f"读取文件失败 {path}: {exc}",
                f"Failed to read file: {path} ({exc})",
            )
        ) from exc

    for encoding in _READ_FALLBACK_ENCODINGS[:-1]:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode(_READ_FALLBACK_ENCODINGS[-1])


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
        # Centralised backend init (backend=Agg + CJK fonts +
        # unicode-minus handling). Using this in every site keeps
        # backend drift from a local matplotlib.use() call impossible.
        from shared.plotting import plt
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
    sigma_rows: list[tuple[mp.mpf | UncertainValue | None, ...]]
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
    implicit_definition: ImplicitModelDefinition | None = None
    timeout_seconds: float | None = None
    custom_constants: dict[str, str] | None = None
    parallel_config: ParallelConfig = field(default_factory=ParallelConfig)


@dataclass(frozen=True)
class RootSolvingJob:
    equations: tuple[str, ...]
    unknown_rows: tuple[dict[str, str], ...]
    data_headers: tuple[str, ...]
    data_rows: tuple[tuple[str, ...], ...]
    constants_enabled: bool
    constants_rows: tuple[dict[str, str], ...]
    constants_view: str
    constants_text: str
    mode: str
    scan_config: dict[str, str | int | float | bool]
    precision: int
    display_digits: int
    uncertainty_options: dict[str, object] = field(default_factory=lambda: {"method": "taylor", "taylor_order": 1})


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


@dataclass
class FitBatchResultEntry:
    index: int
    kind: str  # "fit" or "error"
    fit_payload: FitResultPayload | None = None
    error: str | None = None
    captured_log: str = ""


_FIT_SUBPROCESS_POLL_INTERVAL = 0.05
_FIT_SUBPROCESS_TIMEOUT_SLACK = 0.05


_ROOT_CSV_HEADERS = ["name", "value", "uncertainty", "backend", "mode", "residual_norm"]
ROOT_SOLVING_SUBPROCESS_TIMEOUT_SECONDS = 300.0


def _serialize_root_solving_job(job: RootSolvingJob) -> dict[str, Any]:
    uncertainty_options = _normalize_root_uncertainty_payload(job.uncertainty_options)
    return {
        "equations": tuple(str(value) for value in job.equations),
        "unknown_rows": tuple(
            _string_row(row, ("name", "initial", "lower", "upper"), optional_keys=("source",))
            for row in job.unknown_rows
        ),
        "data_headers": tuple(str(value) for value in job.data_headers),
        "data_rows": tuple(tuple(str(cell) for cell in row) for row in job.data_rows),
        "constants_enabled": bool(job.constants_enabled),
        "constants_rows": tuple(_string_row(row, ("name", "value")) for row in job.constants_rows),
        "constants_view": str(job.constants_view),
        "constants_text": str(job.constants_text),
        "mode": str(job.mode),
        "scan_config": dict(job.scan_config),
        "uncertainty_options": uncertainty_options,
        "precision": int(job.precision),
        "display_digits": int(job.display_digits),
    }


def _string_row(
    row: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    optional_keys: tuple[str, ...] = (),
) -> dict[str, str]:
    clean = {key: "" if row.get(key) is None else str(row.get(key)) for key in keys}
    for key in optional_keys:
        if key in row:
            clean[key] = "" if row.get(key) is None else str(row.get(key))
    return clean


def _deserialize_root_solving_job(payload: Mapping[str, Any]) -> RootSolvingJob:
    data_headers = tuple(str(value) for value in payload.get("data_headers", ()))
    data_rows = _data_row_sequence(payload.get("data_rows", ()))
    if not data_headers and "known_rows" in payload:
        data_headers, data_rows = _legacy_known_rows_to_data(payload)
    return RootSolvingJob(
        equations=tuple(str(value) for value in payload.get("equations", ())),
        unknown_rows=tuple(
            _string_row(
                _dict_string_row(row),
                ("name", "initial", "lower", "upper"),
                optional_keys=("source",),
            )
            for row in _row_sequence(payload.get("unknown_rows", ()))
        ),
        data_headers=data_headers,
        data_rows=data_rows,
        constants_enabled=bool(payload.get("constants_enabled", False)),
        constants_rows=tuple(_dict_string_row(row) for row in _row_sequence(payload.get("constants_rows", ()))),
        constants_view=str(payload.get("constants_view", "table")),
        constants_text=str(payload.get("constants_text", "")),
        mode=str(payload.get("mode", "auto")),
        scan_config=_deserialize_scan_config(payload.get("scan_config", {})),
        uncertainty_options=_normalize_root_uncertainty_payload(payload.get("uncertainty_options", {})),
        precision=int(payload.get("precision", 16)),
        display_digits=int(payload.get("display_digits", 10)),
    )


def _normalize_root_uncertainty_payload(value: Any) -> dict[str, object]:
    try:
        normalized = normalize_root_uncertainty_options(value if isinstance(value, Mapping) else {})
    except ValueError:
        fallback = dict(value) if isinstance(value, Mapping) else {}
        fallback["monte_carlo_samples"] = 2000
        try:
            normalized = normalize_root_uncertainty_options(fallback)
        except ValueError:
            normalized = normalize_root_uncertainty_options({})
    return {
        "method": normalized.method,
        "taylor_order": normalized.taylor_order,
        "monte_carlo_samples": normalized.monte_carlo_samples,
        "monte_carlo_seed": normalized.monte_carlo_seed,
    }


def _legacy_known_rows_to_data(
    payload: Mapping[str, Any],
) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]]:
    known_rows = tuple(_dict_string_row(row) for row in _row_sequence(payload.get("known_rows", ())))
    headers = tuple(row.get("name", "").strip() for row in known_rows if row.get("name", "").strip())
    values = tuple(row.get("value", "") for row in known_rows if row.get("name", "").strip())
    if not headers:
        return (), ()
    return headers, (values,)


def _row_sequence(value: Any) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError("root-solving rows must be a tuple/list of objects")
    rows: list[Mapping[str, Any]] = []
    for row in value:
        if not isinstance(row, Mapping):
            raise ValueError("root-solving row must be an object")
        rows.append(row)
    return tuple(rows)


def _data_row_sequence(value: Any) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, (tuple, list)):
        raise ValueError("root-solving data rows must be a tuple/list of rows")
    rows: list[tuple[str, ...]] = []
    for row in value:
        if not isinstance(row, (tuple, list)):
            raise ValueError("root-solving data row must be a tuple/list")
        rows.append(tuple(str(cell) for cell in row))
    return tuple(rows)


def _deserialize_scan_config(value: Any) -> dict[str, str | int | float | bool]:
    if not isinstance(value, Mapping):
        raise ValueError("root-solving scan_config must be an object")
    clean: dict[str, str | int | float | bool] = {}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)):
            clean[str(key)] = item
    return clean


def _dict_string_row(row: Mapping[str, Any]) -> dict[str, str]:
    return {str(key): "" if value is None else str(value) for key, value in row.items()}


def _execute_root_solving_job_payload(job: RootSolvingJob) -> dict[str, object]:
    constants_state = normalize_constants_state(
        enabled=job.constants_enabled,
        rows=job.constants_rows,
        view=job.constants_view,
        text=job.constants_text,
        numeric_mode="uncertainty",
    )
    data_rows = tuple(
        tuple(parse_uncertainty_format(cell) for cell in row)
        for row in job.data_rows
    )
    unknowns = tuple(RootUnknown(**row) for row in job.unknown_rows if row.get("name", "").strip())
    batch = solve_root_batch(
        equations=job.equations,
        unknowns=unknowns,
        data_headers=job.data_headers,
        data_rows=data_rows,
        constants_state=constants_state,
        mode=job.mode,
        precision=job.precision,
        scan_config=job.scan_config,
        data_text_rows=job.data_rows,
        uncertainty_options=job.uncertainty_options,
    )
    markdown, csv_rows, csv_headers = render_root_batch_result(batch, display_digits=job.display_digits)
    headers = csv_headers or list(_ROOT_CSV_HEADERS)
    roots_count = sum(len(row.result.roots) for row in batch.rows if row.result is not None)
    warnings = list(batch.warnings)
    for row in batch.rows:
        warnings.extend(row.warnings)
        if row.result is not None:
            warnings.extend(row.result.warnings)
    warnings = _deduplicate_strings(warnings)
    return {
        "kind": "root_solving",
        "markdown": markdown,
        "csv_rows": csv_rows,
        "csv_headers": headers,
        "log": (
            f"root solving completed: mode={job.mode} rows={len(batch.rows)} "
            f"roots={roots_count} precision={job.precision}"
        ),
        "warnings": warnings,
    }


def _deduplicate_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _root_solving_job_entry(job_payload: dict[str, Any]) -> dict[str, object]:
    job = _deserialize_root_solving_job(job_payload)
    return _execute_root_solving_job_payload(job)


def _execute_root_solving_job_payload_subprocess(
    job: RootSolvingJob,
    *,
    timeout_seconds: float | None = ROOT_SOLVING_SUBPROCESS_TIMEOUT_SECONDS,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, object]:
    job_payload = _serialize_root_solving_job(job)
    runner = KillableProcessTaskRunner(config=ParallelConfig())
    try:
        return cast(
            dict[str, object],
            runner.run_killable(
                _root_solving_job_entry,
                job_payload,
                timeout_seconds=timeout_seconds,
                should_cancel=should_cancel,
            ),
        )
    except InterruptedError as exc:
        raise InterruptedError("Root solving cancelled") from exc


def _fit_job_requires_process_boundary(job: FitJob) -> bool:
    return job.model_type == "self_consistent"


def _serialize_parallel_config(config: ParallelConfig) -> dict[str, Any]:
    return {
        "mode": config.mode,
        "max_workers": config.max_workers,
        "reserve_cores": config.reserve_cores,
        "default_worker_cap": config.default_worker_cap,
        "min_process_tasks": config.min_process_tasks,
        "nested_policy": config.nested_policy,
        "process_start_method": config.process_start_method,
    }


def _deserialize_parallel_config(payload: dict[str, Any] | None) -> ParallelConfig:
    if payload is None:
        return ParallelConfig()
    if not isinstance(payload, dict):
        raise ValueError("parallel_config must be an object")
    if not payload:
        return ParallelConfig()
    process_start_method = _optional_string(payload, "process_start_method", "spawn")
    if process_start_method not in multiprocessing.get_all_start_methods():
        raise ValueError(f"Unsupported process_start_method: {process_start_method}")
    return ParallelConfig(
        mode=ParallelMode(payload.get("mode", ParallelMode.AUTO)),
        max_workers=payload.get("max_workers"),
        reserve_cores=int(payload.get("reserve_cores", 1)),
        default_worker_cap=int(payload.get("default_worker_cap", 16)),
        min_process_tasks=int(payload.get("min_process_tasks", 4)),
        nested_policy=NestedParallelPolicy(
            payload.get("nested_policy", NestedParallelPolicy.SERIAL_WHEN_NESTED)
        ),
        process_start_method=process_start_method,
    )


def _mp_to_string(value: Any, keep_digits: int) -> str:
    try:
        return mp.nstr(mp.mpf(value), keep_digits)
    except (TypeError, ValueError):
        return str(value)


def _serialize_optional_mpf(value: Any, keep_digits: int) -> str | None:
    if value is None:
        return None
    return _mp_to_string(value, keep_digits)


def _serialize_mpf_sequence(values: list[Any] | tuple[Any, ...], keep_digits: int) -> list[str | None]:
    return [_serialize_optional_mpf(value, keep_digits) for value in values]


def _deserialize_mpf_sequence(values: list[str | None]) -> list[mp.mpf | None]:
    return [mp.mpf(value) if value is not None else None for value in values]


def _serialize_sigma_value(value: Any, keep_digits: int) -> dict[str, Any] | str | None:
    if value is None:
        return None
    if hasattr(value, "value") and hasattr(value, "uncertainty"):
        return {
            "kind": "uncertain",
            "value": _mp_to_string(getattr(value, "value"), keep_digits),
            "uncertainty": _mp_to_string(getattr(value, "uncertainty"), keep_digits),
            "uncertainty_digits": getattr(value, "uncertainty_digits", None),
        }
    return _mp_to_string(value, keep_digits)


def _serialize_sigma_sequence(
    values: list[Any] | tuple[Any, ...], keep_digits: int
) -> list[dict[str, Any] | str | None]:
    return [_serialize_sigma_value(value, keep_digits) for value in values]


def _deserialize_sigma_value(value: dict[str, Any] | str | None) -> mp.mpf | UncertainValue | None:
    if value is None:
        return None
    if isinstance(value, dict):
        if value.get("kind") != "uncertain":
            raise ValueError("sigma entry has unsupported kind")
        return UncertainValue(
            value.get("value", "0"),
            value.get("uncertainty", "0"),
            uncertainty_digits=value.get("uncertainty_digits"),
        )
    return mp.mpf(value)


def _deserialize_sigma_sequence(
    values: list[dict[str, Any] | str | None],
) -> list[mp.mpf | UncertainValue | None]:
    return [_deserialize_sigma_value(value) for value in values]


def _serialize_mp_tree(value: Any, keep_digits: int) -> Any:
    if value is None:
        return None
    if hasattr(value, "_mpf_"):
        return _mp_to_string(value, keep_digits)
    if isinstance(value, dict):
        return {key: _serialize_mp_tree(item, keep_digits) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_serialize_mp_tree(item, keep_digits) for item in value]
    if isinstance(value, list):
        return [_serialize_mp_tree(item, keep_digits) for item in value]
    return value


def _serialize_implicit_definition(definition: ImplicitModelDefinition | None) -> dict[str, Any] | None:
    if definition is None:
        return None
    solve_options = definition.solve_options
    return {
        "x_variables": list(definition.x_variables),
        "implicit_variable": definition.implicit_variable,
        "equation": definition.equation,
        "output_expression": definition.output_expression,
        "parameters": list(definition.parameters),
        "constants": dict(definition.constants),
        "solve_options": {
            "method": solve_options.method,
            "initial": solve_options.initial,
            "tolerance": solve_options.tolerance,
            "max_iterations": solve_options.max_iterations,
        },
    }


def _deserialize_implicit_definition(payload: dict[str, Any] | None) -> ImplicitModelDefinition | None:
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError("implicit_definition must be an object")
    solve_payload = payload.get("solve_options")
    if solve_payload is None:
        solve_payload = {}
    if not isinstance(solve_payload, dict):
        raise ValueError("implicit_definition.solve_options must be an object")
    return ImplicitModelDefinition(
        x_variables=tuple(_required_string_sequence(payload, "x_variables")),
        implicit_variable=_required_string(payload, "implicit_variable"),
        equation=_required_string(payload, "equation"),
        output_expression=_required_string(payload, "output_expression"),
        parameters=tuple(_required_string_sequence(payload, "parameters")),
        constants=_optional_string_mapping(payload, "constants"),
        solve_options=ImplicitSolveOptions(
            method=_optional_string(solve_payload, "method", "fixed_point"),
            initial=_optional_string(solve_payload, "initial", "0"),
            tolerance=_optional_string(solve_payload, "tolerance", "1e-30"),
            max_iterations=int(solve_payload.get("max_iterations", 80)),
        ),
    )


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _optional_string(payload: Mapping[str, Any], key: str, default: str) -> str:
    value = payload.get(key, default)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _required_string_sequence(payload: Mapping[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if isinstance(value, str) or not isinstance(value, Sequence):
        raise ValueError(f"{key} must be a list of strings")
    result = list(value)
    if not all(isinstance(item, str) for item in result):
        raise ValueError(f"{key} must be a list of strings")
    return result


def _optional_string_mapping(payload: Mapping[str, Any], key: str) -> dict[str, str]:
    value = payload.get(key)
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    if not all(isinstance(name, str) and isinstance(item, str) for name, item in value.items()):
        raise ValueError(f"{key} must map strings to strings")
    return dict(value)


def _serialize_fit_job(job: FitJob) -> dict[str, Any]:
    keep_digits = max(int(job.precision) + 10, 30)
    return {
        "model_type": job.model_type,
        "headers": list(job.headers),
        "data_rows": [_serialize_mpf_sequence(row, keep_digits) for row in job.data_rows],
        "sigma_rows": [_serialize_sigma_sequence(row, keep_digits) for row in job.sigma_rows],
        "x_series": _serialize_mpf_sequence(job.x_series, keep_digits),
        "y_series": _serialize_mpf_sequence(job.y_series, keep_digits),
        "sigma_series": _serialize_mpf_sequence(job.sigma_series, keep_digits),
        "weights": _serialize_mpf_sequence(job.weights, keep_digits) if job.weights is not None else None,
        "variable_map": dict(job.variable_map),
        "variable_data": {
            key: _serialize_mpf_sequence(values, keep_digits)
            for key, values in job.variable_data.items()
        },
        "target_series": _serialize_mpf_sequence(job.target_series, keep_digits),
        "target_column": job.target_column,
        "model_expr": job.model_expr,
        "parameter_config": _serialize_mp_tree(job.parameter_config, keep_digits),
        "parameter_names": list(job.parameter_names),
        "template_expr": job.template_expr,
        "template_params": _serialize_mp_tree(job.template_params, keep_digits),
        "poly_degree": job.poly_degree,
        "inverse_min": job.inverse_min,
        "inverse_max": job.inverse_max,
        "pade_m": job.pade_m,
        "pade_n": job.pade_n,
        "auto_identifier": job.auto_identifier,
        "precision": job.precision,
        "generate_latex": job.generate_latex,
        "output_path": job.output_path,
        "use_dcolumn": job.use_dcolumn,
        "caption": job.caption,
        "verbose": job.verbose,
        "render_plots": job.render_plots,
        "latex_digits": job.latex_digits,
        "weighted": job.weighted,
        "label": job.label,
        "is_multidim": job.is_multidim,
        "implicit_definition": _serialize_implicit_definition(job.implicit_definition),
        "timeout_seconds": job.timeout_seconds,
        "custom_constants": dict(job.custom_constants or {}),
        "parallel_config": _serialize_parallel_config(job.parallel_config),
    }


def _deserialize_fit_job(payload: dict[str, Any]) -> FitJob:
    precision = int(payload.get("precision", 80))
    with _mp_precision_guard(precision):
        return FitJob(
            model_type=payload["model_type"],
            headers=list(payload["headers"]),
            data_rows=[tuple(value for value in _deserialize_mpf_sequence(row)) for row in payload["data_rows"]],
            sigma_rows=[tuple(value for value in _deserialize_sigma_sequence(row)) for row in payload["sigma_rows"]],
            x_series=[mp.mpf(value) for value in payload["x_series"]],
            y_series=[mp.mpf(value) for value in payload["y_series"]],
            sigma_series=[mp.mpf(value) if value is not None else None for value in payload["sigma_series"]],
            weights=(
                [mp.mpf(value) for value in payload["weights"]]
                if payload.get("weights") is not None else None
            ),
            variable_map=dict(payload["variable_map"]),
            variable_data={
                key: [mp.mpf(value) for value in values]
                for key, values in payload["variable_data"].items()
            },
            target_series=[mp.mpf(value) for value in payload["target_series"]],
            target_column=payload["target_column"],
            model_expr=payload["model_expr"],
            parameter_config=dict(payload.get("parameter_config") or {}),
            parameter_names=list(payload["parameter_names"]),
            template_expr=payload.get("template_expr"),
            template_params=payload.get("template_params"),
            poly_degree=int(payload.get("poly_degree", 0)),
            inverse_min=int(payload.get("inverse_min", 1)),
            inverse_max=int(payload.get("inverse_max", 3)),
            pade_m=int(payload.get("pade_m", 1)),
            pade_n=int(payload.get("pade_n", 1)),
            auto_identifier=payload.get("auto_identifier"),
            precision=precision,
            generate_latex=bool(payload.get("generate_latex", False)),
            output_path=str(payload.get("output_path", "")),
            use_dcolumn=bool(payload.get("use_dcolumn", True)),
            caption=payload.get("caption"),
            verbose=bool(payload.get("verbose", False)),
            render_plots=bool(payload.get("render_plots", True)),
            latex_digits=int(payload.get("latex_digits", 16)),
            weighted=bool(payload.get("weighted", False)),
            label=str(payload.get("label", "")),
            is_multidim=bool(payload.get("is_multidim", False)),
            implicit_definition=_deserialize_implicit_definition(payload.get("implicit_definition")),
            timeout_seconds=payload.get("timeout_seconds"),
            custom_constants=dict(payload.get("custom_constants") or {}),
            parallel_config=_deserialize_parallel_config(payload.get("parallel_config")),
        )


def _serialize_fit_result(result: FitResult, keep_digits: int) -> dict[str, Any]:
    return {
        "params": {key: _mp_to_string(value, keep_digits) for key, value in result.params.items()},
        "param_errors": {key: _mp_to_string(value, keep_digits) for key, value in result.param_errors.items()},
        "chi2": _mp_to_string(result.chi2, keep_digits),
        "reduced_chi2": _mp_to_string(result.reduced_chi2, keep_digits),
        "aic": _mp_to_string(result.aic, keep_digits),
        "bic": _mp_to_string(result.bic, keep_digits),
        "r2": _mp_to_string(result.r2, keep_digits),
        "rmse": _mp_to_string(result.rmse, keep_digits),
        "residuals": [_mp_to_string(value, keep_digits) for value in result.residuals],
        "fitted_curve": [_mp_to_string(value, keep_digits) for value in result.fitted_curve],
        "covariance": [
            [_mp_to_string(value, keep_digits) for value in row]
            for row in result.covariance
        ],
        "param_errors_stat": {
            key: _mp_to_string(value, keep_digits)
            for key, value in result.param_errors_stat.items()
        },
        "param_errors_sys": {
            key: _mp_to_string(value, keep_digits)
            for key, value in result.param_errors_sys.items()
        },
        "param_errors_total": {
            key: _mp_to_string(value, keep_digits)
            for key, value in result.param_errors_total.items()
        },
        "details": _serialize_mp_tree(result.details, keep_digits),
    }


def _deserialize_fit_result(payload: dict[str, Any]) -> FitResult:
    return FitResult(
        params={key: mp.mpf(value) for key, value in payload["params"].items()},
        param_errors={key: mp.mpf(value) for key, value in payload["param_errors"].items()},
        chi2=mp.mpf(payload["chi2"]),
        reduced_chi2=mp.mpf(payload["reduced_chi2"]),
        aic=mp.mpf(payload["aic"]),
        bic=mp.mpf(payload["bic"]),
        r2=mp.mpf(payload["r2"]),
        rmse=mp.mpf(payload["rmse"]),
        residuals=[mp.mpf(value) for value in payload["residuals"]],
        fitted_curve=[mp.mpf(value) for value in payload["fitted_curve"]],
        covariance=[[mp.mpf(value) for value in row] for row in payload["covariance"]],
        param_errors_stat={
            key: mp.mpf(value) for key, value in payload["param_errors_stat"].items()
        },
        param_errors_sys={
            key: mp.mpf(value) for key, value in payload["param_errors_sys"].items()
        },
        param_errors_total={
            key: mp.mpf(value) for key, value in payload["param_errors_total"].items()
        },
        details=dict(payload.get("details") or {}),
    )


def _serialize_fit_result_payload(payload: FitResultPayload) -> dict[str, Any]:
    keep_digits = max(int(payload.job.precision) + 10, 30)
    return {
        "job": _serialize_fit_job(payload.job),
        "fit_result": _serialize_fit_result(payload.fit_result, keep_digits),
        "expression": payload.expression,
        "logs": list(payload.logs),
        "warnings": list(payload.warnings),
    }


def _deserialize_fit_result_payload(payload: dict[str, Any]) -> FitResultPayload:
    precision = int(payload["job"].get("precision", 80))
    with _mp_precision_guard(precision):
        return FitResultPayload(
            job=_deserialize_fit_job(payload["job"]),
            fit_result=_deserialize_fit_result(payload["fit_result"]),
            expression=str(payload["expression"]),
            logs=list(payload.get("logs") or []),
            warnings=list(payload.get("warnings") or []),
        )


def _fit_job_subprocess_entry(job_payload: dict[str, Any]) -> dict[str, Any]:
    with _mp_precision_guard(int(job_payload["precision"])):
        job = _deserialize_fit_job(job_payload)
        payload = _execute_fit_job_payload(job)
        return _serialize_fit_result_payload(payload)


def _fit_job_subprocess_queue_entry(result_queue: Any, job_payload: dict[str, Any]) -> None:
    try:
        result_queue.put({"ok": True, "payload": _fit_job_subprocess_entry(job_payload)})
    except BaseException as exc:  # noqa: BLE001
        with suppress(Exception):
            result_queue.put({"ok": False, "error": str(exc)})


def _terminate_fit_subprocess(proc: multiprocessing.Process) -> None:
    if not proc.is_alive():
        proc.join(timeout=0.2)
        return
    try:
        proc.terminate()
        proc.join(timeout=1.0)
        if proc.is_alive():
            proc.kill()
            proc.join(timeout=1.0)
    except Exception:
        with suppress(Exception):
            proc.kill()
            proc.join(timeout=1.0)


def _execute_fit_job_payload_subprocess(
    job: FitJob,
    timeout_seconds: float | None,
    should_cancel: Callable[[], bool] | None = None,
) -> FitResultPayload:
    job_payload = _serialize_fit_job(job)
    timeout = timeout_seconds if timeout_seconds is not None and timeout_seconds > 0 else None
    try:
        runner = KillableProcessTaskRunner(config=job.parallel_config)
        payload = runner.run_killable(
            _fit_job_subprocess_entry,
            job_payload,
            timeout_seconds=timeout,
            should_cancel=should_cancel,
        )
    except InterruptedError as exc:
        raise InterruptedError(_dual_msg(
            "自洽隐式拟合已取消。",
            "Self-consistent fit cancelled.",
        )) from exc
    except TimeoutError as exc:
        display_timeout = timeout if timeout is not None else 0.0
        raise TimeoutError(_dual_msg(
            f"自洽隐式拟合超过 {display_timeout:.0f}s 仍未完成，已停止。",
            f"Self-consistent fit exceeded {display_timeout:.0f}s and was stopped.",
        )) from exc

    with _mp_precision_guard(job.precision):
        return _deserialize_fit_result_payload(payload)


def _execute_fit_job_payload_subprocess_legacy(
    job: FitJob,
    timeout_seconds: float | None,
    should_cancel: Callable[[], bool] | None = None,
) -> FitResultPayload:
    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    job_payload = _serialize_fit_job(job)
    proc = ctx.Process(
        target=_fit_job_subprocess_queue_entry,
        args=(result_queue, job_payload),
        name=f"datalab-fit-{job.model_type}",
    )
    proc.start()

    timeout = timeout_seconds if timeout_seconds is not None and timeout_seconds > 0 else None
    deadline = (
        time.monotonic() + timeout + _FIT_SUBPROCESS_TIMEOUT_SLACK
        if timeout is not None else None
    )
    try:
        while True:
            if should_cancel is not None and should_cancel():
                _terminate_fit_subprocess(proc)
                raise InterruptedError(_dual_msg(
                    "自洽隐式拟合已取消。",
                    "Self-consistent fit cancelled.",
                ))

            try:
                payload = result_queue.get(timeout=_FIT_SUBPROCESS_POLL_INTERVAL)
                proc.join(timeout=1.0)
                return _deserialize_fit_subprocess_queue_payload(job, payload)
            except queue.Empty:
                pass

            if deadline is not None and time.monotonic() > deadline:
                _terminate_fit_subprocess(proc)
                raise TimeoutError(_dual_msg(
                    f"自洽隐式拟合超过 {timeout:.0f}s 仍未完成，已停止。",
                    f"Self-consistent fit exceeded {timeout:.0f}s and was stopped.",
                ))

            if not proc.is_alive():
                proc.join(timeout=0.2)
                try:
                    payload = result_queue.get(timeout=0.2)
                    return _deserialize_fit_subprocess_queue_payload(job, payload)
                except queue.Empty:
                    pass
                raise RuntimeError(_dual_msg(
                    "自洽隐式拟合子进程退出但未返回结果。",
                    "Self-consistent fit subprocess exited without returning a result.",
                ))
    finally:
        if proc.is_alive():
            _terminate_fit_subprocess(proc)
        with suppress(Exception):
            result_queue.close()
            result_queue.join_thread()


def _deserialize_fit_subprocess_queue_payload(
    job: FitJob,
    payload: object,
) -> FitResultPayload:
    if isinstance(payload, dict) and payload.get("ok"):
        with _mp_precision_guard(job.precision):
            return _deserialize_fit_result_payload(payload["payload"])
    error = payload.get("error", "unknown error") if isinstance(payload, dict) else str(payload)
    raise RuntimeError(error)



def _self_consistent_hooks_replaced() -> bool:
    return (
        build_implicit_model_specification is not _ORIGINAL_BUILD_IMPLICIT_MODEL_SPECIFICATION
        or can_fit_observed_implicit_variable is not _ORIGINAL_CAN_FIT_OBSERVED_IMPLICIT_VARIABLE
        or fit_observed_implicit_variable_linear_model is not _ORIGINAL_FIT_OBSERVED_IMPLICIT_VARIABLE_LINEAR_MODEL
        or fit_custom_model is not _ORIGINAL_FIT_CUSTOM_MODEL
    )


def _fit_self_consistent_with_legacy_hooks(job: FitJob) -> FitResult:
    if job.implicit_definition is None:
        raise ValueError(
            _dual_msg(
                "自洽隐式模型缺少定义。",
                "Self-consistent fit model requires an implicit definition.",
            )
        )
    state = build_parameter_state(
        job.parameter_config or {},
        list(job.implicit_definition.parameters),
    )
    if (
        can_fit_observed_implicit_variable(job.implicit_definition)
        and fit_observed_implicit_variable_linear_model is not None
    ):
        try:
            fit_result = fit_observed_implicit_variable_linear_model(
                job.implicit_definition,
                state,
                job.variable_data,
                job.target_series,
                precision=job.precision,
                weights=job.weights,
                data_sigmas=job.sigma_series,
            )
            fit_result.details["implicit_diagnostics"] = {
                "points_solved": 0,
                "root_fallbacks": 0,
                "max_iterations_used": 0,
                "max_residual": "0",
            }
            return fit_result
        except ValueError:
            pass
    spec = build_implicit_model_specification(job.implicit_definition)
    fit_result = fit_custom_model(
        spec,
        state,
        job.variable_data,
        job.target_series,
        precision=job.precision,
        weights=job.weights,
        data_sigmas=job.sigma_series,
    )
    diagnostics = getattr(spec, "implicit_diagnostics")
    fit_result.details["implicit_diagnostics"] = {
        "points_solved": int(diagnostics.points_solved),
        "root_fallbacks": int(diagnostics.root_fallbacks),
        "max_iterations_used": int(diagnostics.max_iterations_used),
        "max_residual": str(diagnostics.max_residual),
    }
    return fit_result


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
        if model_type in {"polynomial", "inverse_power"}:
            if model_type == "polynomial":
                definition = build_polynomial_definition(job.poly_degree)
            else:
                definition = build_inverse_series_definition(job.inverse_min, job.inverse_max)
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
        elif model_type == "self_consistent":
            if job.implicit_definition is None:
                raise ValueError(
                    _dual_msg(
                        "自洽隐式模型缺少定义。",
                        "Self-consistent fit model requires an implicit definition.",
                    )
                )
            if _self_consistent_hooks_replaced():
                fit_result = _fit_self_consistent_with_legacy_hooks(job)
            else:
                problem = ModelProblem(
                    model_type="self_consistent",
                    expression=job.implicit_definition.output_expression,
                    variables=tuple(job.implicit_definition.x_variables),
                    target_name=job.target_column,
                    parameter_config=job.parameter_config or {},
                    constants=job.implicit_definition.constants,
                    constants_enabled=True,
                    implicit_definition=job.implicit_definition,
                )
                fit_result = FitRunner().fit(
                    problem,
                    job.variable_data,
                    job.target_series,
                    precision=job.precision,
                    weights=job.weights,
                    data_sigmas=job.sigma_series,
                )
            fit_result.details["implicit_variable"] = job.implicit_definition.implicit_variable
            fit_result.details["equation"] = job.implicit_definition.equation
            fit_result.details["output_expression"] = job.implicit_definition.output_expression
            expression = job.implicit_definition.output_expression
            logs.append("self_consistent 拟合完成。")
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
            if model_type == "custom":
                problem = ModelProblem(
                    model_type="custom",
                    expression=expr,
                    variables=tuple(var_names),
                    target_name=job.target_column,
                    parameter_config={name: (params or {}).get(name, {}) for name in parameter_names},
                    constants=job.custom_constants or {},
                    constants_enabled=True,
                )
                fit_result = FitRunner().fit(
                    problem,
                    job.variable_data,
                    job.target_series,
                    precision=job.precision,
                    weights=job.weights,
                    data_sigmas=job.sigma_series,
                )
            else:
                spec = build_model_specification(
                    expr,
                    var_names,
                    parameter_names,
                    None,
                )
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
    "CalcJob",
    "CalcResult",
    "FitBatchResultEntry",
    "FitBatchTask",
    "FitJob",
    "FitResultPayload",
    "RootSolvingJob",
    "ROOT_SOLVING_SUBPROCESS_TIMEOUT_SECONDS",
    "_execute_root_solving_job_payload",
    "_execute_root_solving_job_payload_subprocess",
    "_root_solving_job_entry",
    "_serialize_root_solving_job",
    "split_extrapolation_result",
]
