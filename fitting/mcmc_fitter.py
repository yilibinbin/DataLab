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
    "HAS_EMCEE",
    "MCMCResult",
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
