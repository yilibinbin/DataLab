"""Matplotlib-based visualization helpers for fitting results."""

from __future__ import annotations

import io
import logging
from functools import lru_cache
from typing import Any, Callable, Hashable, Iterable, NamedTuple, Optional, Sequence, TypeAlias

# Centralised matplotlib init — backend=Agg, CJK font fallback, and
# axes.unicode_minus=False are all configured at import time via
# shared.plotting. Per Phase 4 #20 we do NOT call matplotlib.use
# locally: if a future maintainer adds a local use() call the
# shared.plotting module's backend would already be locked, which
# correctly makes the local call a no-op with a warning.
from shared.plotting import plt, rcParams  # noqa: F401
from mpmath import mp

from shared.caching import sample_with_cache
from shared.precision import precision_guard

_logger = logging.getLogger(__name__)


def sample_mp_function(
    func: Callable[[mp.mpf], mp.mpf],
    x_values: Sequence[mp.mpf],
    precision: int | None = None,
    *,
    cache_token: Hashable = None,
) -> list[mp.mpf]:
    """Evaluate an mp function across a sequence while preserving precision.

    Uses ``shared.precision.precision_guard`` so ``mp.dps`` mutations are
    routed through the single canonical context manager (thread-safe for
    concurrent worker jobs — ``mp.dps`` is process-global in mpmath).
    When ``precision`` is ``None``, ``mp.dps`` is not touched **and the
    cache is bypassed** (callers passing ``None`` are assumed to be inside
    an outer ``precision_guard`` whose dps we must not observe as a
    cache-key input).

    When ``precision`` is an int, delegates to
    :func:`shared.caching.sample_with_cache`. The outer
    ``precision_guard`` on this path is load-bearing for the R10 C3
    regression test
    (``tests/test_r10_c3_plot_fitting_precision_guard.py``), which
    patches ``plot_fitting.precision_guard`` with a spy — removing it
    would silently pass the test via the inner guard in
    ``shared.caching`` but fail the intent of the regression.
    ``precision_guard`` is re-entrant, so the nesting is correctness-
    neutral at runtime.

    ``cache_token`` is forwarded unchanged to ``sample_with_cache`` and
    lets callers whose ``func`` closes over mutable state (changing
    between renders) force cache invalidation by bumping the token. For
    DataLab's built-in evaluators (``build_linear_evaluator`` et al.)
    each fit produces a fresh closure with frozen parameters, so the
    default token ``None`` is appropriate.
    """

    if precision is None:
        # Bypass the cache entirely. The caller is presumed to be inside
        # an outer precision_guard, so we must not observe mp.dps as a
        # cache-key input.
        samples: list[mp.mpf] = []
        for value in x_values:
            mp_x = mp.mpf(value)
            try:
                samples.append(mp.mpf(func(mp_x)))
            except Exception:
                samples.append(mp.nan)
        return samples

    with precision_guard(precision):
        return sample_with_cache(
            func, x_values, precision, cache_token=cache_token
        )


def render_fitting_overview(
    x_values: Sequence[float],
    y_values: Sequence[float],
    fitted_series: Sequence[tuple[str, Sequence[float]]],
    residual_series: Sequence[tuple[str, Sequence[float]]],
    uncertainties: Sequence[float] | None = None,
    comparison: Sequence[tuple[str, float, float, float]] | None = None,
    parameter_info: tuple[str, dict[str, object], dict[str, object]] | None = None,
    log_scale: str | None = None,
    dpi: int = 220,
    export_pdf_path: str | None = None,
    export_eps_path: str | None = None,
    show_curves: bool = True,
) -> bytes:
    # Clamp dpi at the public boundary. An Agg raster at dpi=10 000 on
    # the default 11×8 figure would allocate ~35 GB of pixel memory
    # before PNG compression; clamp to the same [72, 600] range used by
    # ``app_desktop.window_latex_pdf_mixin._clamp_dpi``. (Untrusted
    # callers — e.g. a future web API that forwards a form field — rely
    # on this guard.)
    dpi = _clamp_dpi(dpi)
    x_plot = [float(val) for val in x_values]
    y_plot = [float(val) for val in y_values]
    if show_curves and not x_plot:
        raise ValueError("show_curves=True requires non-empty x_values.")
    # For multidimensional cases (no curve plot), synthesize a dummy x axis to keep downstream plots stable.
    if (not show_curves) or not x_plot:
        x_plot = list(range(len(y_plot)))
    n = len(x_plot)
    if show_curves:
        if len(y_plot) != n:
            raise ValueError("x_values and y_values must have the same length.")
        if uncertainties is not None and len(uncertainties) != n:
            raise ValueError("uncertainties must have the same length as x_values.")
        if fitted_series:
            if len(fitted_series[0][1]) != n:
                raise ValueError("fitted_series[0] length must match x_values length.")
        if residual_series:
            if len(residual_series[0][1]) != n:
                raise ValueError("residual_series[0] length must match x_values length.")
    else:
        if residual_series and residual_series[0][1]:
            if len(residual_series[0][1]) != len(y_plot):
                raise ValueError("In multidimensional mode, residual_series[0] must match y_values length.")
    fig = plt.figure(figsize=(11, 8), dpi=dpi)
    gs = fig.add_gridspec(2, 2, height_ratios=[3, 2])

    ax_main = fig.add_subplot(gs[0, 0])
    ax_resid = fig.add_subplot(gs[1, 0], sharex=ax_main)
    ax_hist = fig.add_subplot(gs[0, 1])
    ax_param = fig.add_subplot(gs[1, 1])

    # 1) 数据散点 + 拟合曲线/置信带
    if show_curves and x_plot and y_plot:
        if uncertainties:
            yerr = [abs(float(u)) for u in uncertainties]
            ax_main.errorbar(
                x_plot,
                y_plot,
                yerr=yerr,
                fmt="o",
                color="#1f77b4",
                ecolor="#555555",
                capsize=3,
                label="Data±σ",
                zorder=3,
            )
        else:
            ax_main.scatter(x_plot, y_plot, c="#1f77b4", label="Data", zorder=3)

        if fitted_series:
            label, series = fitted_series[0]
            fit_vals = [float(v) for v in series]
            ax_main.plot(x_plot, fit_vals, label=label, color="#d62728")
            # 置信带: 使用 residual_series 或直接计算 (y_fit - y_data) 的 RMSE
            rmse = None
            if residual_series and residual_series[0][1]:
                resid = [float(r) for r in residual_series[0][1]]
                rmse = (sum(r * r for r in resid) / max(1, len(resid))) ** 0.5
            if rmse is None and len(fit_vals) == len(y_plot):
                resid = [f - y for f, y in zip(fit_vals, y_plot)]
                rmse = (sum(r * r for r in resid) / max(1, len(resid))) ** 0.5 if resid else None
            if rmse is not None:
                band_half = 2.0 * rmse  # show ±2×RMSE and label accordingly
                upper = [y + band_half for y in fit_vals]
                lower = [y - band_half for y in fit_vals]
                ax_main.fill_between(
                    x_plot,
                    lower,
                    upper,
                    facecolor="#e99c9c",
                    edgecolor="#d62728",
                    linewidth=0.5,
                    alpha=0.35,
                    label="±2×RMSE band",
                    zorder=1,
                )

        if log_scale:
            if "x" in log_scale.lower():
                ax_main.set_xscale("log")
            if "y" in log_scale.lower():
                ax_main.set_yscale("log")

        ax_main.set_title("Data & Fit")
        ax_main.set_ylabel("y")
        ax_main.legend(frameon=False)
        ax_main.grid(True, alpha=0.3)

        # 2) 残差 vs x
        if residual_series:
            label_r, series_r = residual_series[0]
            ax_resid.scatter(x_plot, [float(v) for v in series_r], s=22, color="#1f77b4", label=label_r)
        ax_resid.axhline(0, color="black", linewidth=0.6, linestyle="--")
        ax_resid.set_xlabel("x")
        ax_resid.set_ylabel("Residual")
        ax_resid.set_title("Residual vs x")
        ax_resid.grid(True, alpha=0.3)
    else:
        ax_main.axis("off")
        ax_main.text(0.5, 0.5, "Multidimensional model\n(curve plot skipped)", ha="center", va="center")
        if residual_series and residual_series[0][1]:
            resid_vals = [float(v) for v in residual_series[0][1]]
            idx = list(range(len(resid_vals)))
            ax_resid.scatter(idx, resid_vals, s=22, color="#1f77b4")
            ax_resid.axhline(0, color="black", linewidth=0.6, linestyle="--")
            ax_resid.set_xlabel("Point index")
            ax_resid.set_ylabel("Residual")
            ax_resid.set_title("Residual vs index")
            ax_resid.grid(True, alpha=0.3)
        else:
            ax_resid.axis("off")

    # 3) 残差直方图
    hist_drawn = False
    if residual_series:
        resid_vals = [float(v) for v in residual_series[0][1]]
        if len(resid_vals) >= 4:
            ax_hist.hist(resid_vals, bins=max(8, int(len(resid_vals) ** 0.5)), color="#9467bd", alpha=0.8)
            ax_hist.set_title("Residual Histogram")
            ax_hist.set_xlabel("Residual")
            ax_hist.set_ylabel("Count")
            ax_hist.grid(True, alpha=0.25)
            hist_drawn = True
    if not hist_drawn:
        ax_hist.set_title("Residual Summary")
        ax_hist.axis("off")

    if comparison:
        lines = ["Model comparison (AIC/BIC/R2):"]
        sorted_comp: Sequence[tuple[str, float, float, float]]
        try:
            sorted_comp = sorted(comparison, key=lambda t: t[1])
        except Exception:
            sorted_comp = comparison
        for name, aic, bic, r2 in sorted_comp:
            lines.append(f"{name}: AIC={aic:.3g}, BIC={bic:.3g}, R2={r2:.4g}")
        ax_hist.text(
            0.99,
            0.95,
            "\n".join(lines),
            transform=ax_hist.transAxes,
            ha="right",
            va="top",
            fontsize="x-small",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#f6f6f6", edgecolor="#cccccc"),
        )

    if parameter_info:
        label, params_dict, errors_dict = parameter_info
        names = list(params_dict.keys())
        # dict values are typed as ``object`` to accept ``mp.mpf`` / float /
        # int / numeric strings — every supported source materialises as
        # something ``float()`` accepts. See the unit tests in
        # ``tests/test_plot_fitting_*``.
        values = [float(params_dict[name]) for name in names]  # type: ignore[arg-type]
        yerr = [abs(float(errors_dict.get(name, 0))) for name in names]  # type: ignore[arg-type]
        positions = range(len(names))
        # use scientific notation for x-axis
        ax_param.ticklabel_format(axis="x", style="sci", scilimits=(-3, 3))
        ax_param.errorbar(
            values,
            positions,
            xerr=yerr,
            fmt="o",
            color="#7570b3",
            ecolor="#555555",
            capsize=4,
        )
        for pos, name, value in zip(positions, names, values):
            ax_param.text(
                value,
                pos,
                f"{name} = {value:.4g}",
                va="center",
                ha="left",
                fontsize="small",
            )
        ax_param.set_yticks(list(positions))
        ax_param.set_yticklabels(names)
        ax_param.set_xlabel("Value")
        ax_param.set_title("Parameter Uncertainties")
        ax_param.grid(True, axis="x", alpha=0.3)
    else:
        ax_param.axis("off")

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=dpi)
    if export_pdf_path:
        try:
            fig.savefig(export_pdf_path, format="pdf", dpi=dpi)
        except OSError as exc:
            # Previously swallowed silently — log so a user who picked a
            # non-writable directory (or a read-only mount) gets a clue
            # in the app's log stream rather than a mystery "no file".
            _logger.warning(
                "render_fitting_overview: PDF export failed (%s): %s",
                export_pdf_path,
                exc,
            )
    if export_eps_path:
        try:
            fig.savefig(export_eps_path, format="eps", dpi=dpi)
        except OSError as exc:
            _logger.warning(
                "render_fitting_overview: EPS export failed (%s): %s",
                export_eps_path,
                exc,
            )
    plt.close(fig)
    return buf.getvalue()


def render_residual_diff(
    x_values: Sequence[float],
    series: Sequence[tuple[str, Sequence[float]]],
    log_scale: str | None = None,
    dpi: int = 220,
) -> bytes:
    """Overlay multiple models' residual curves on a single axis.

    Used by the Phase 2 residual-comparison view: after auto-fit, the
    user sees a single plot comparing each candidate model's residuals
    on the same x-axis. Distinct colours cycle via matplotlib's default
    tab10 palette (10 colours); beyond 10 series the cycle repeats.

    Parameters
    ----------
    x_values:
        x-axis values. ``mp.mpf`` values are cast via ``float()``.
    series:
        List of ``(label, residuals)`` tuples. Every ``residuals`` list
        must have the same length as ``x_values`` — mismatch raises
        ``ValueError`` so a broken caller doesn't silently produce a
        misaligned plot.
    log_scale:
        ``None`` / ``"x"`` / ``"y"`` / ``"xy"``.
    dpi:
        Matplotlib dpi, clamped to ``[_DPI_MIN, _DPI_MAX]`` via
        ``_clamp_dpi`` — same DoS defence as ``render_fitting_overview``.

    Returns
    -------
    bytes
        PNG-encoded figure. Byte-deterministic for identical inputs
        (so the caller can layer an LRU cache like the one for
        ``render_fitting_overview_cached``).
    """
    dpi = _clamp_dpi(dpi)
    x_plot = [float(v) for v in x_values]
    n = len(x_plot)
    if series and n == 0:
        raise ValueError(
            "render_residual_diff: series provided but x_values is empty"
        )
    for label, resids in series:
        if len(resids) != n:
            raise ValueError(
                f"render_residual_diff: series '{label}' has "
                f"{len(resids)} residuals; expected {n} to match x_values"
            )

    fig = plt.figure(figsize=(9, 5), dpi=dpi)
    ax = fig.add_subplot(1, 1, 1)

    # tab10 palette via matplotlib's default prop_cycle.
    colors = plt.rcParams["axes.prop_cycle"].by_key().get("color", [])
    if not colors:
        # Fallback hard-coded palette so headless test env without a
        # configured cycle still produces deterministic colours.
        colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]

    for i, (label, resids) in enumerate(series):
        color = colors[i % len(colors)]
        ax.plot(
            x_plot,
            [float(r) for r in resids],
            marker="o",
            markersize=4,
            linewidth=1.4,
            label=str(label),
            color=color,
            alpha=0.85,
        )

    ax.axhline(0, color="black", linewidth=0.6, linestyle="--", zorder=0)
    if log_scale:
        normalized = _normalize_log_scale(log_scale)
        if normalized and "x" in normalized:
            ax.set_xscale("log")
        if normalized and "y" in normalized:
            ax.set_yscale("log")

    ax.set_xlabel("x")
    ax.set_ylabel("Residual")
    ax.set_title("Residual comparison across models")
    ax.grid(True, alpha=0.3)
    if series:
        ax.legend(loc="best", frameon=False, fontsize="small")

    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=dpi)
    plt.close(fig)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# PNG-bytes LRU cache for render_fitting_overview (#4 pivot)
# ----------------------------------------------------------------------------
#
# ``render_fitting_overview`` is called multiple times during normal user
# interaction (log-scale toggle, LaTeX re-export, tab switches that restore
# the preview). Each call runs ~150–300 ms of matplotlib setup/draw work.
# Matplotlib's PNG backend is deterministic: identical inputs produce
# byte-identical output, so we can memoise the result by hashing a frozen
# representation of every input that affects the draw.
#
# Cache key composition:
#   - Scalar inputs (log_scale, dpi, show_curves) go in directly.
#   - Sequence inputs (x_values, y_values, fitted_series, residual_series,
#     uncertainties) are normalised to tuples of floats via ``_freeze_*``
#     helpers. Non-numeric values abort the freeze → cache bypass.
#   - ``comparison`` is normalised into a tuple of 4-tuples.
#   - ``parameter_info`` is normalised into a tuple of (label, sorted
#     params, sorted errors) to be insensitive to dict ordering (dict
#     iteration order is insertion-based in Python 3.7+ but an upstream
#     caller could legitimately build the same fit with a different
#     insertion order — two identical renders must still hit the cache).
#
# Export-path kwargs (``export_pdf_path`` / ``export_eps_path``) bypass the
# cache entirely: those have filesystem side effects that the cache cannot
# replay. Callers that want the cached PNG and a fresh PDF/EPS side effect
# must call ``render_fitting_overview`` directly.

# Bounded so a long interactive session doesn't grow the cache unbounded.
# Each entry is ~200 KB (DPI=220 fitting preview) × 64 = ~13 MB ceiling —
# well inside the desktop RAM budget but meaningfully larger than the
# ``sample_with_cache`` LRU (256 mpmath string tuples). The per-entry
# ceiling only holds if ``dpi`` is clamped to ``[_DPI_MIN, _DPI_MAX]``
# (see ``_clamp_dpi``): a 4 000-dpi figure at the default 11×8 inch size
# would balloon a single entry into hundreds of megabytes.
_FIT_RENDER_CACHE_MAXSIZE = 64

# DPI range matches the desktop's ``window_latex_pdf_mixin._clamp_dpi`` —
# 72 is the screen baseline; 600 is "poster-quality print" and the highest
# value a fitting preview image usefully reaches. Anything above 600 is
# either a user typo or an attacker trying to force a multi-gigabyte Agg
# allocation through the web endpoint.
_DPI_MIN = 72
_DPI_MAX = 600

# Maximum label length accepted into the cache key. Model labels are
# typically <50 chars ("Linear / 3-term polynomial fit"); anything beyond
# a few hundred chars is either a user-entered formula mistake or a
# cache-key bloat attempt. Truncate rather than reject so callers still
# get a correct render.
_FIT_RENDER_LABEL_MAX = 512


def _clamp_dpi(dpi: int) -> int:
    """Clamp ``dpi`` to ``[_DPI_MIN, _DPI_MAX]``.

    Called by both ``render_fitting_overview`` and
    ``render_fitting_overview_cached`` — the cache ceiling is only valid
    when every caller sees the same clamped value, so the clamp must be
    applied **before** the value enters the cache key.
    """
    try:
        value = int(dpi)
    except (TypeError, ValueError):
        value = _DPI_MIN
    return max(_DPI_MIN, min(_DPI_MAX, value))


def _normalize_log_scale(log_scale: str | None) -> str | None:
    """Canonicalise ``log_scale`` to ``None`` / ``"x"`` / ``"y"`` / ``"xy"``.

    ``render_fitting_overview`` checks ``"x" in log_scale.lower()`` and
    ``"y" in log_scale.lower()``, so the strings ``"x"``, ``"X"``,
    ``"xy"``, ``"yx"``, ``"x y"`` and ``"xxxxxxxx"`` all produce identical
    renders. Without normalization they'd produce six distinct cache
    entries and let an attacker evict legitimate entries by cycling
    through variants. Normalising to a canonical form collapses them to
    a single entry.
    """
    if not log_scale:
        return None
    lowered = str(log_scale).lower()
    has_x = "x" in lowered
    has_y = "y" in lowered
    if has_x and has_y:
        return "xy"
    if has_x:
        return "x"
    if has_y:
        return "y"
    return None


def _truncate_label(label: object) -> str:
    """Stringify + truncate labels to ``_FIT_RENDER_LABEL_MAX`` chars."""
    text = str(label)
    if len(text) <= _FIT_RENDER_LABEL_MAX:
        return text
    return text[:_FIT_RENDER_LABEL_MAX]


class _FitRenderCacheInfo(NamedTuple):
    """Mirror of ``functools._CacheInfo`` for stability across Python
    versions (the private name could move; we want a public shape)."""

    hits: int
    misses: int
    currsize: int
    maxsize: int


def _freeze_float_seq(seq: Sequence[Any] | None) -> tuple[str, ...] | None:
    """Convert a numeric sequence to a tuple of ``repr`` strings.

    ``repr(float(v))`` round-trips losslessly for IEEE 754 doubles and —
    unlike raw ``float`` — is equality-stable for NaN values: the string
    ``"nan"`` compares equal to ``"nan"``, so a repeated NaN-containing
    fit (failed fit, NaN covariance) still hits the cache rather than
    permanently missing because ``float('nan') != float('nan')``.

    Returns ``None`` only for **unfreezable** input (a value that cannot
    be cast to ``float``); callers then bypass the cache. A ``None``
    input and an empty sequence both return ``()`` — the caller is
    responsible for using a separate boolean flag if the downstream
    renderer distinguishes the two (see ``render_fitting_overview_cached``
    for how ``uncertainties`` handles this).
    """
    if seq is None:
        return ()
    try:
        return tuple(repr(float(v)) for v in seq)
    except (TypeError, ValueError):
        return None


def _freeze_named_series(
    series: Sequence[tuple[str, Sequence[Any]]] | None,
) -> tuple[tuple[str, tuple[str, ...]], ...] | None:
    """Freeze a list of ``(label, values)`` pairs. Returns ``None`` on
    failure so the caller can bypass the cache. Labels are truncated to
    ``_FIT_RENDER_LABEL_MAX`` chars so a caller (or attacker) can't pad
    the cache key with megabyte-sized strings. Values are ``repr``-stringified
    via ``_freeze_float_seq`` for NaN-equality stability."""
    if not series:
        return ()
    out: list[tuple[str, tuple[str, ...]]] = []
    for entry in series:
        try:
            label, values = entry
        except (TypeError, ValueError):
            return None
        frozen_values = _freeze_float_seq(values)
        if frozen_values is None:
            return None
        out.append((_truncate_label(label), frozen_values))
    return tuple(out)


def _freeze_comparison(
    comparison: Sequence[tuple[str, float, float, float]] | None,
) -> tuple[tuple[str, str, str, str], ...] | None:
    """Freeze the model comparison list. Returns ``None`` on failure.

    Sorted by AIC to mirror ``render_fitting_overview``'s internal
    ``sorted(comparison, key=lambda t: t[1])`` at line ~236 — otherwise
    two callers passing the same models in different arrival orders
    would miss the cache despite rendering byte-identical output. Names
    are truncated so oversized labels don't bloat the cache key. Numeric
    values are ``repr``-stringified for NaN-equality stability (raw
    ``float('nan')`` would never equal itself and defeat the LRU).
    """
    if not comparison:
        return ()
    # Keep (name, aic_str, bic_str, r2_str, aic_float) — the float is
    # used only for sorting and discarded. NaN-safe sort falls back to
    # arrival order.
    scratch: list[tuple[str, str, str, str, float]] = []
    for entry in comparison:
        try:
            name, aic, bic, r2 = entry
            aic_f = float(aic)
            scratch.append(
                (
                    _truncate_label(name),
                    repr(aic_f),
                    repr(float(bic)),
                    repr(float(r2)),
                    aic_f,
                )
            )
        except (TypeError, ValueError):
            return None
    try:
        # ``sorted`` is stable and tolerates NaN in a mixed key thanks to
        # Python's IEEE 754 handling, but to be defensive we sort only by
        # the numeric AIC and ignore comparisons that raise.
        scratch.sort(key=lambda t: t[4])
    except TypeError:
        pass
    return tuple((n, a, b, r) for (n, a, b, r, _aic) in scratch)


def _value_key(value: object) -> str:
    """Collision-resistant string representation of a numeric value used
    as part of a cache key.

    Plain ``float(v)`` truncates high-precision ``mp.mpf`` values to 53
    bits of mantissa — two fits whose parameter values differ only beyond
    15 significant digits would collide in the cache and return stale
    bytes even though the rendered annotations (``f"{value:.4g}"``) could
    plausibly differ. For an ``mp.mpf`` we serialise at 20 significant
    digits (more than a float64 can represent), which prevents false hits
    while keeping the key small.

    For plain ``float`` / ``int`` values we use ``repr`` — round-trip
    safe for IEEE 754 and stable across platforms. Falls back to ``str``
    if ``repr`` raises (shouldn't for the numeric types we accept).
    """
    if hasattr(value, "_mpf_"):  # mpmath.mpf marker attribute
        try:
            # mpmath has no stubs, so mp.nstr() returns Any; widen to
            # str explicitly to satisfy ``no-any-return``.
            return str(mp.nstr(value, 20))
        except Exception:
            return repr(float(value))  # type: ignore[arg-type]
    try:
        return repr(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return str(value)


def _freeze_parameter_info(
    parameter_info: tuple[str, dict[str, object], dict[str, object]] | None,
) -> tuple[str, tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]] | None:
    """Freeze the ``(label, params, errors)`` triple into a fully hashable
    representation.

    Critically, **insertion order is preserved** — ``render_fitting_overview``
    does ``list(params_dict.keys())`` at line 254 and plots Y-axis ticks in
    that order. Two dicts with identical content but different insertion
    order produce **different** renders (different Y-axis ordering), so the
    cache key must distinguish them or we'd serve a stale render on hit.
    Do NOT sort these.

    Numeric values go through ``_value_key`` to preserve mpmath precision
    — ``float()`` would silently truncate high-precision ``mp.mpf`` values
    to double and cause false cache hits for refined fits.
    """
    if parameter_info is None:
        return None  # valid "absent" sentinel; cache key will be None
    try:
        label, params_dict, errors_dict = parameter_info
    except (TypeError, ValueError):
        return None
    try:
        params = tuple(
            (_truncate_label(k), _value_key(v)) for k, v in params_dict.items()
        )
        errors = tuple(
            (_truncate_label(k), _value_key(v)) for k, v in errors_dict.items()
        )
    except (TypeError, ValueError, AttributeError):
        return None
    return (_truncate_label(label), params, errors)


def _restore_floats(values: _FrozenFloatSeq) -> list[float]:
    """Invert ``_freeze_float_seq`` — ``repr`` strings → floats. ``"nan"``
    and ``"inf"`` round-trip correctly through ``float()``."""
    return [float(v) for v in values]


# Frozen LRU cache key for ``_cached_render``. Mirrors the packing in
# ``render_fitting_overview_cached`` (line ~880). Each component is the
# output of one of the ``_freeze_*`` helpers, so every member is fully
# hashable.
_FrozenFloatSeq: TypeAlias = tuple[str, ...]
_FrozenNamedSeries: TypeAlias = tuple[tuple[str, _FrozenFloatSeq], ...]
# ``_freeze_comparison`` stringifies AIC/BIC/R2 via ``repr(float)`` for
# NaN-equality stability, so the cached key holds 4-tuples of ``str``.
_FrozenComparison: TypeAlias = tuple[tuple[str, str, str, str], ...]
_FrozenParamInfo: TypeAlias = tuple[
    str,
    tuple[tuple[str, str], ...],
    tuple[tuple[str, str], ...],
]
_FitRenderKey: TypeAlias = tuple[
    _FrozenFloatSeq,                  # xs
    _FrozenFloatSeq,                  # ys
    _FrozenNamedSeries,               # fitted
    _FrozenNamedSeries,               # residuals
    Optional[_FrozenFloatSeq],        # uncertainties
    bool,                             # has_uncertainties
    Optional[_FrozenComparison],      # comparison
    Optional[_FrozenParamInfo],       # parameter_info
    Optional[str],                    # log_scale
    int,                              # dpi
    bool,                             # show_curves
]


@lru_cache(maxsize=_FIT_RENDER_CACHE_MAXSIZE)
def _cached_render(key: _FitRenderKey) -> bytes:
    """LRU-cached render wrapper.

    The ``key`` tuple contains the frozen ``(xs, ys, fitted, residuals,
    uncertainties_tuple, has_uncertainties, comparison, parameter_info,
    log_scale, dpi, show_curves)`` — see ``render_fitting_overview_cached``
    for the packing. Unpacked here so the cache miss path calls the heavy
    matplotlib renderer with the original-style arguments.

    ``has_uncertainties`` distinguishes ``uncertainties=None`` (no error
    bars — the renderer takes the scatter branch) from
    ``uncertainties=[]`` (the renderer validates length and may raise).
    Without this flag both would collapse to ``()``.
    """
    (
        xs,
        ys,
        fitted,
        residuals,
        uncertainties,
        has_uncertainties,
        comparison,
        parameter_info,
        log_scale,
        dpi,
        show_curves,
    ) = key
    # ``has_uncertainties`` was packed in lockstep with whether
    # ``uncertainties`` is non-None; assert the invariant for mypy.
    if has_uncertainties:
        assert uncertainties is not None
        unc_arg: list[float] | None = _restore_floats(uncertainties)
    else:
        unc_arg = None
    if parameter_info is None:
        param_arg = None
    else:
        param_label, param_values, param_errors = parameter_info
        # _freeze_parameter_info stored values as strings from _value_key
        # to preserve mpmath precision. Reconstruct mpmath / float values:
        # the rendering function calls ``float()`` on them anyway, so
        # returning ``mp.mpf`` values via ``mp.mpf(<string>)`` is
        # behaviour-preserving.
        param_arg = (
            param_label,
            {k: mp.mpf(v) for k, v in param_values},
            {k: mp.mpf(v) for k, v in param_errors},
        )
    # NB: rename comprehension loop vars to avoid shadowing ``param_label``
    # if anyone later refactors this block into a non-comprehension scope.
    # Comparison tuples are (name, aic_str, bic_str, r2_str) — inflate the
    # numeric fields back to float.
    comparison_arg = (
        [(n, float(a), float(b), float(r)) for (n, a, b, r) in comparison]
        if comparison
        else None
    )
    return render_fitting_overview(
        _restore_floats(xs),
        _restore_floats(ys),
        [(series_label, _restore_floats(vals))
         for series_label, vals in fitted],
        [(series_label, _restore_floats(vals))
         for series_label, vals in residuals],
        unc_arg,
        comparison_arg,
        param_arg,
        log_scale,
        dpi,
        None,
        None,
        show_curves,
    )


def render_fitting_overview_cached(
    x_values: Sequence[float],
    y_values: Sequence[float],
    fitted_series: Sequence[tuple[str, Sequence[float]]],
    residual_series: Sequence[tuple[str, Sequence[float]]],
    uncertainties: Sequence[float] | None = None,
    comparison: Sequence[tuple[str, float, float, float]] | None = None,
    parameter_info: tuple[str, dict[str, object], dict[str, object]] | None = None,
    log_scale: str | None = None,
    dpi: int = 220,
    export_pdf_path: str | None = None,
    export_eps_path: str | None = None,
    show_curves: bool = True,
) -> bytes:
    """Cached variant of :func:`render_fitting_overview`.

    Returns byte-identical output to the uncached function for identical
    inputs. On any input that cannot be frozen into a hashable key (e.g.
    non-numeric values in a sequence) falls back to the uncached renderer.

    Callers that need to emit the PDF/EPS side effect must call the
    uncached function directly — passing ``export_pdf_path`` or
    ``export_eps_path`` here short-circuits the cache to avoid skipping
    the file write on a cache hit.

    **Cache-correctness invariants:**
    - Matplotlib ``rcParams`` (fonts, backend, DPI defaults) must not
      change between calls. This module sets ``rcParams`` at import time
      and does not mutate them thereafter. Tests or plugins that modify
      ``rcParams`` should call :func:`clear_fit_render_cache` first,
      otherwise the cache may serve PNG bytes rendered with the old
      settings.
    - Dict keys in ``parameter_info`` must be strings (the renderer's
      signature is ``dict[str, object]``). Non-string keys are stringified
      before being used as cache-key components, which means a caller
      passing ``{1: ..., "1": ...}`` produces the same cache key as
      ``{"1": ...}``. This matches the declared type contract; callers
      outside the contract get undefined cache-hit semantics.
    - ``dpi`` is clamped to ``[_DPI_MIN, _DPI_MAX]`` both here and in
      ``render_fitting_overview`` — passing ``dpi=220.5`` or ``dpi=10000``
      is equivalent for both cached and direct calls.
    """
    # Clamp dpi BEFORE any downstream call so the cache entry size is
    # bounded and cache-hit and cache-bypass paths agree on the value of
    # dpi actually passed to matplotlib. Normalise log_scale for the same
    # reason — it's a set-membership check downstream but a direct cache
    # key component here, so ``"xy"`` and ``"yx"`` must collapse to one
    # entry.
    safe_dpi = _clamp_dpi(dpi)
    safe_log_scale = _normalize_log_scale(log_scale)

    # Side-effect kwargs bypass the cache: a cache hit would skip the
    # export_*_path file writes that the original call expects.
    if export_pdf_path is not None or export_eps_path is not None:
        return render_fitting_overview(
            x_values,
            y_values,
            fitted_series,
            residual_series,
            uncertainties,
            comparison,
            parameter_info,
            safe_log_scale,
            safe_dpi,
            export_pdf_path,
            export_eps_path,
            show_curves,
        )

    xs_frozen = _freeze_float_seq(x_values)
    ys_frozen = _freeze_float_seq(y_values)
    fitted_frozen = _freeze_named_series(fitted_series)
    residuals_frozen = _freeze_named_series(residual_series)
    unc_frozen = _freeze_float_seq(uncertainties)
    comparison_frozen = _freeze_comparison(comparison)
    param_frozen = _freeze_parameter_info(parameter_info)

    freezables = (
        xs_frozen,
        ys_frozen,
        fitted_frozen,
        residuals_frozen,
        unc_frozen,
        comparison_frozen,
    )
    # Any ``None`` in freezables (except ``parameter_info``, which uses
    # ``None`` as a legitimate sentinel for "absent") means the input was
    # unfreezable → bypass the cache.
    if any(frozen is None for frozen in freezables):
        _logger.debug(
            "render_fitting_overview_cached: unhashable input, bypassing cache"
        )
        # Pass the real export paths through — the side-effect-bypass
        # guard at the top of this function already short-circuited when
        # they were non-None, but forwarding them here keeps the unhashable
        # bypass robust against a future refactor that removes that guard.
        return render_fitting_overview(
            x_values,
            y_values,
            fitted_series,
            residual_series,
            uncertainties,
            comparison,
            parameter_info,
            safe_log_scale,
            safe_dpi,
            export_pdf_path,
            export_eps_path,
            show_curves,
        )
    # _freeze_parameter_info returns None for both "absent" and
    # "unfreezable". Distinguish: only the caller-provided None is legal.
    if parameter_info is not None and param_frozen is None:
        _logger.debug(
            "render_fitting_overview_cached: unhashable parameter_info, "
            "bypassing cache"
        )
        return render_fitting_overview(
            x_values,
            y_values,
            fitted_series,
            residual_series,
            uncertainties,
            comparison,
            parameter_info,
            safe_log_scale,
            safe_dpi,
            export_pdf_path,
            export_eps_path,
            show_curves,
        )

    # Distinguish uncertainties=None (no error bars) from uncertainties=[]
    # (renderer validates length) — see _cached_render's docstring.
    has_uncertainties = uncertainties is not None
    # The ``any(... is None)`` bypass above guarantees the four required
    # freezables are non-None on this path. Repeat the asserts for the
    # type-checker so the _FitRenderKey tuple's required slots resolve.
    # ``unc_frozen``, ``comparison_frozen`` and ``param_frozen`` stay
    # Optional in the key shape — None is a legitimate "absent" sentinel
    # for those fields and the LRU treats the difference correctly.
    assert xs_frozen is not None
    assert ys_frozen is not None
    assert fitted_frozen is not None
    assert residuals_frozen is not None
    key: _FitRenderKey = (
        xs_frozen,
        ys_frozen,
        fitted_frozen,
        residuals_frozen,
        unc_frozen,
        has_uncertainties,
        comparison_frozen,
        param_frozen,
        safe_log_scale,
        safe_dpi,
        bool(show_curves),
    )
    return _cached_render(key)


def clear_fit_render_cache() -> None:
    """Flush the LRU cache. Call between tests and on logout / dataset
    reset to free memory proactively."""
    _cached_render.cache_clear()


def fit_render_cache_info() -> _FitRenderCacheInfo:
    """Return the current LRU state — hits / misses / current size /
    configured maxsize. Mirrors ``functools._CacheInfo`` shape."""
    info = _cached_render.cache_info()
    return _FitRenderCacheInfo(
        hits=info.hits,
        misses=info.misses,
        currsize=info.currsize,
        maxsize=info.maxsize or _FIT_RENDER_CACHE_MAXSIZE,
    )
