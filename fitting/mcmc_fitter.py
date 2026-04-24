"""Optional MCMC (Markov-chain Monte Carlo) posterior fitting via emcee.

Primary use case: after a least-squares fit converges, the user asks
"what does the posterior look like around these parameters?" — MCMC
yields credible intervals that the Hessian-based statistical errors
can't capture when the posterior is non-Gaussian.

If ``emcee`` is installed, ``run_mcmc`` returns a full ``MCMCResult``
with chains + log-probabilities + quantiles. If emcee is absent, the
module loads cleanly but every public function raises
``ModuleNotFoundError`` with an actionable install message.

Not wired into the default auto-fit flow. Enable via a toolbar
checkbox "Refine with MCMC" — opt-in only, since emcee typically
takes 10–60 s on modest problems.

Scaffolded as Phase 3 Task 3.6 — full GUI wiring and the
``app_desktop.window_fitting_mixin`` integration is deferred until
emcee lands in ``gui_requirements.txt`` and a corner-plot renderer
is chosen (``corner``, ``arviz``, or ``matplotlib`` directly).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Sequence

__all__ = [
    "HAS_CORNER",
    "HAS_EMCEE",
    "MCMCResult",
    "render_corner_plot",
    "run_mcmc",
]

_logger = logging.getLogger(__name__)

try:
    import emcee as _emcee  # noqa: F401
    import numpy as _np

    HAS_EMCEE = True
except ImportError:
    _emcee = None  # type: ignore[assignment]
    _np = None  # type: ignore[assignment]
    HAS_EMCEE = False

try:
    import corner as _corner  # noqa: F401

    HAS_CORNER = True
except ImportError:
    _corner = None  # type: ignore[assignment]
    HAS_CORNER = False


@dataclass
class MCMCResult:
    """Summary of an MCMC run.

    Fields intentionally mirror common emcee output so callers can
    pass them to ``corner.corner`` / ``arviz`` with a single .chain
    reshape.

    - ``chain``: shape (n_walkers, n_steps, n_params) or a flattened
      (n_walkers * n_steps, n_params) if ``flatten=True``.
    - ``log_prob``: log-probability trace, parallel shape to chain
      less the last axis.
    - ``param_names``: names in order matching the chain's last axis.
    - ``medians``, ``lo_ci``, ``hi_ci``: 50 / 16 / 84 percentile
      summaries (the ±1σ credible interval for Gaussian posteriors).
    - ``acceptance_fraction``: diagnostic; should be 0.2–0.5 for a
      well-tuned run.
    """

    chain: Any  # numpy ndarray when HAS_EMCEE
    log_prob: Any
    param_names: list[str]
    medians: dict[str, float]
    lo_ci: dict[str, float]
    hi_ci: dict[str, float]
    acceptance_fraction: float


def run_mcmc(
    log_probability: Callable[[Sequence[float]], float],
    initial_guess: Sequence[float],
    param_names: Sequence[str],
    *,
    n_walkers: int = 32,
    n_steps: int = 2000,
    n_burn_in: int = 500,
    proposal_scale: float = 1e-3,
) -> MCMCResult:
    """Run emcee on the supplied log-probability function.

    Parameters
    ----------
    log_probability:
        Callable returning ``log(p(params))`` including the prior. The
        caller is responsible for composing prior + likelihood — this
        helper doesn't impose a model structure.
    initial_guess:
        Centre of the initial walker cloud. Usually the least-squares
        best-fit parameters.
    param_names:
        Names in order matching ``initial_guess``. Used to key the
        ``medians`` / ``lo_ci`` / ``hi_ci`` summary dicts.
    n_walkers:
        Number of MCMC walkers. emcee recommends ≥ 2 * n_params; the
        default (32) is a pragmatic floor that works for up to ~15
        parameters without needing tuning.
    n_steps:
        Total iterations per walker (including burn-in).
    n_burn_in:
        Leading iterations discarded from the chain summaries.
    proposal_scale:
        Stddev of the Gaussian used to scatter walkers around
        ``initial_guess``.

    Returns
    -------
    MCMCResult

    Raises
    ------
    ModuleNotFoundError:
        If emcee isn't installed.
    ValueError:
        On malformed arguments (mismatched lengths, non-positive walker
        count, burn-in >= total steps).
    """
    if not HAS_EMCEE:
        raise ModuleNotFoundError(
            "emcee is not installed. Add 'emcee' and 'numpy' to your "
            "requirements to enable MCMC refinement in DataLab."
        )

    n_params = len(list(initial_guess))
    if n_params == 0:
        raise ValueError("initial_guess must be non-empty")
    if len(list(param_names)) != n_params:
        raise ValueError(
            f"param_names length {len(list(param_names))} does not match "
            f"initial_guess length {n_params}"
        )
    if n_walkers < max(4, 2 * n_params):
        raise ValueError(
            f"n_walkers={n_walkers} below emcee's recommended "
            f"max(4, 2*n_params)={max(4, 2 * n_params)} — raise to "
            "improve mixing"
        )
    if n_burn_in >= n_steps:
        raise ValueError(
            f"n_burn_in={n_burn_in} must be less than n_steps={n_steps}"
        )

    rng = _np.random.default_rng()
    p0 = _np.array(list(initial_guess), dtype=float)
    walker_start = p0 + proposal_scale * rng.standard_normal(
        (n_walkers, n_params)
    )
    sampler = _emcee.EnsembleSampler(
        n_walkers, n_params, log_probability
    )
    sampler.run_mcmc(walker_start, n_steps, progress=False)

    chain = sampler.get_chain(discard=n_burn_in)
    log_prob = sampler.get_log_prob(discard=n_burn_in)
    flat_chain = chain.reshape(-1, n_params)
    percentiles = _np.percentile(flat_chain, [16, 50, 84], axis=0)
    param_list = list(param_names)
    medians = {name: float(percentiles[1, i]) for i, name in enumerate(param_list)}
    lo_ci = {name: float(percentiles[0, i]) for i, name in enumerate(param_list)}
    hi_ci = {name: float(percentiles[2, i]) for i, name in enumerate(param_list)}
    return MCMCResult(
        chain=chain,
        log_prob=log_prob,
        param_names=param_list,
        medians=medians,
        lo_ci=lo_ci,
        hi_ci=hi_ci,
        acceptance_fraction=float(_np.mean(sampler.acceptance_fraction)),
    )


# --------------------------------------------------------------------
# Corner-plot rendering (Phase 3 #12 GUI wiring)
# --------------------------------------------------------------------
#
# If ``corner`` is installed, use it (preferred — shows all 2D
# projections of the posterior). Otherwise fall back to a matplotlib
# 1D histogram-per-parameter grid so the desktop can still show
# *something* when a user checks "Refine with MCMC" without having
# installed corner. Both paths return PNG bytes.


def _flatten_chain(chain: Any) -> Any:
    """Reshape ``(walkers, steps, params)`` → ``(walkers * steps, params)``.

    Accepts either a numpy ndarray or a nested Python list; the list
    path exists so the regression tests don't require numpy. Handles
    both 2-D ("already flat") and 3-D inputs — a 2-D list of
    ``[[p1, p2, ...], ...]`` passes through unchanged.
    """
    if chain is None:
        raise ValueError("chain is None — cannot flatten")
    if _np is not None:
        try:
            arr = _np.asarray(chain, dtype=float)
            if arr.ndim == 0:
                raise ValueError(
                    "chain produced a 0-D array — invalid shape"
                )
            if arr.ndim == 3:
                return arr.reshape(-1, arr.shape[-1])
            if arr.ndim == 2:
                # Already flat — (samples, params) shape.
                return arr
            raise ValueError(
                f"chain has unexpected ndim={arr.ndim}; "
                "expected 2 or 3"
            )
        except ValueError:
            raise
        except Exception:  # noqa: BLE001
            pass
    # Fallback: python-list flatten. Detect whether the input is
    # already flat (list of param-vectors) vs 3-D (walkers of steps
    # of param-vectors). The test is: is the first element a flat
    # list of floats, or a list of lists?
    if not chain:
        return []
    first = chain[0]
    if not isinstance(first, (list, tuple)):
        raise ValueError(
            "chain is a 1-D list — expected 2-D (samples, params) "
            "or 3-D (walkers, steps, params)"
        )
    # First element is a list/tuple. If ITS first element is also a
    # list/tuple, we're in the 3-D case. Otherwise we're already flat.
    if first and isinstance(first[0], (list, tuple)):
        flat: list[list[float]] = []
        for walker in chain:
            for step_vector in walker:
                flat.append([float(v) for v in step_vector])
        return flat
    # 2-D list: each element is [p1, p2, ...]
    return [[float(v) for v in row] for row in chain]


def _render_fallback_corner(
    flat_chain: Any,
    param_names: list[str],
) -> bytes:
    """matplotlib-only fallback: histogram per parameter stacked into
    a single PNG. Used when ``corner`` is not installed."""
    from shared.plotting import plt

    import io

    n = len(param_names)
    if n == 0:
        fig = plt.figure(figsize=(4, 3), dpi=150)
        fig.text(0.5, 0.5, "no parameters", ha="center", va="center")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150)
        plt.close(fig)
        return buf.getvalue()

    cols = min(n, 3)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(
        rows, cols, figsize=(3.5 * cols, 2.8 * rows), dpi=150,
        squeeze=False,
    )
    for i, name in enumerate(param_names):
        ax = axes[i // cols][i % cols]
        # Extract param i values from flat chain — works for both
        # numpy arrays and Python lists.
        if _np is not None and hasattr(flat_chain, "shape"):
            values = flat_chain[:, i]
        else:
            values = [row[i] for row in flat_chain]
        ax.hist(values, bins=40, color="#1f77b4", alpha=0.7)
        ax.set_title(name)
        ax.grid(True, alpha=0.3)
    # Blank the unused grid cells.
    for j in range(n, rows * cols):
        axes[j // cols][j % cols].axis("off")
    fig.suptitle("MCMC posteriors (corner fallback)", fontsize=11)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    return buf.getvalue()


def _error_png(message: str) -> bytes:
    """Render a 1-line error message to PNG. Used as a last-resort
    failure sentinel so ``render_corner_plot`` can honour its
    "never raises" contract."""
    import io

    from shared.plotting import plt

    fig = plt.figure(figsize=(5, 3), dpi=120)
    fig.text(
        0.5, 0.5, message,
        ha="center", va="center", wrap=True,
        fontsize=10,
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    return buf.getvalue()


def render_corner_plot(result: Any) -> bytes:
    """Render an MCMC posterior as PNG bytes.

    Accepts ``MCMCResult`` or any object with ``.chain`` +
    ``.param_names``. Uses ``corner.corner`` when available,
    otherwise a per-parameter histogram fallback.

    **Never raises.** Every failure mode (None chain, invalid shape,
    corner.corner crash, fallback crash) returns a minimal error-
    message PNG instead of propagating the exception. Callers
    embedding the PNG in a UI don't have to try/except.
    """
    import io

    from shared.plotting import plt

    param_names = list(getattr(result, "param_names", []) or [])
    if not param_names:
        return _error_png("no parameters to plot")

    try:
        flat = _flatten_chain(getattr(result, "chain", None))
    except Exception as exc:  # noqa: BLE001
        _logger.warning("render_corner_plot: chain flatten failed: %s", exc)
        return _error_png(f"corner plot failed: {exc}")

    if HAS_CORNER and _np is not None:
        fig = None
        try:
            # Prefer the proper corner plot when both deps are present.
            arr = _np.asarray(flat, dtype=float)
            if arr.ndim != 2 or arr.shape[1] != len(param_names):
                raise ValueError(
                    f"flat chain shape {arr.shape} incompatible with "
                    f"{len(param_names)} parameter names"
                )
            fig = _corner.corner(arr, labels=param_names, show_titles=True)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=150)
            plt.close(fig)
            return buf.getvalue()
        except Exception as exc:  # noqa: BLE001
            _logger.warning(
                "render_corner_plot: corner.corner raised (%s); "
                "falling back to matplotlib histograms", exc,
            )
            # Belt-and-braces: close the figure if one was partially
            # constructed before the exception.
            if fig is not None:
                try:
                    plt.close(fig)
                except Exception:  # noqa: BLE001
                    pass
    try:
        return _render_fallback_corner(flat, param_names)
    except Exception as exc:  # noqa: BLE001
        _logger.warning(
            "render_corner_plot: fallback renderer raised (%s)", exc
        )
        return _error_png(f"corner plot unavailable: {exc}")
