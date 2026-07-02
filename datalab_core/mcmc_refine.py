"""UI-neutral MCMC refinement for a completed fit (P1-3).

Historically MCMC posterior refinement ran only in the desktop worker
(``app_desktop/workers_core.py``), so the web and CLI frontends — which go
through ``datalab_core.run_fitting`` — could not access it. This module hosts a
frontend-agnostic entry point, ``refine_fit_with_mcmc``, that ``run_fitting``
calls while the live fit result and its evaluator are still in scope (the
evaluator is never serialized, so refinement must happen before serialization).

Coverage matches desktop exactly: refinement runs only for models whose fit
result carries a live ``evaluator`` in ``details`` (the ``polynomial`` /
``inverse_power`` auto-model paths). For ``custom`` / ``pade`` / ``power_limit``
models the evaluator is absent, so refinement self-skips — the same behaviour
the desktop path has today. Building a portable evaluator for those models is a
separate, larger effort and deliberately out of scope here.

``emcee`` is optional: the heavy imports are local to the entry point and gated
on ``HAS_EMCEE`` so ``datalab_core`` keeps zero module-level MCMC dependency.
"""

from __future__ import annotations

import base64
import inspect
import logging
import math
from typing import Any, Mapping, Sequence

from mpmath import mp

_logger = logging.getLogger(__name__)


def _params_from_theta(
    theta: Sequence[object],
    param_names: Sequence[str],
    base_params: Mapping[str, mp.mpf],
) -> dict[str, mp.mpf]:
    theta_values = [mp.mpf(value) for value in theta]
    params = dict(base_params)
    params.update(dict(zip(param_names, theta_values)))
    return params


def _set_evaluator_point_index(evaluator: Any, index: int) -> None:
    setter = getattr(evaluator, "set_implicit_point_index", None)
    if callable(setter):
        setter(index)


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


def _evaluate_prediction(evaluator: Any, params: Mapping[str, mp.mpf], observation: object) -> Any:
    scalar_observation = None
    if isinstance(observation, Mapping) and len(observation) == 1:
        scalar_observation = next(iter(observation.values()))
    candidates: list[tuple[object, ...]] = [(params, observation)]
    if scalar_observation is not None:
        candidates.append((params, scalar_observation))
        candidates.append((scalar_observation,))
    candidates.append((observation,))
    last_type_error: TypeError | None = None
    for args in candidates:
        if _callable_accepts_args(evaluator, args):
            try:
                return evaluator(*args)
            except TypeError as exc:
                # Arity bound but the call still rejected these args; try the
                # next candidate shape before giving up.
                last_type_error = exc
                continue
    if last_type_error is not None:
        raise last_type_error
    raise TypeError("MCMC evaluator does not accept supported argument shapes")


def _gaussian_log_probability(residuals_sq: float, rmse: float, *, weighted: bool) -> float:
    """Gaussian log-likelihood (up to an additive constant) for MCMC.

    ``residuals_sq`` is Σ wᵢ·rᵢ². When the fit is WEIGHTED the weights are already
    1/σᵢ² (see ``likelihood_weights_from_series``), so ``residuals_sq`` is the
    correct χ² = Σ rᵢ²/σᵢ² and the log-likelihood is simply ``-0.5·residuals_sq``.
    Dividing again by rmse² (the old code path) double-scaled the likelihood,
    acting as a constant "temperature" that rescaled every posterior variance and
    made the reported credible intervals wrong whenever σ/weights were supplied.

    When UNWEIGHTED (weights all 1, data noise unknown), rmse² is the plug-in
    variance estimate, so the Gaussian exponent is ``-0.5·Σrᵢ²/rmse²`` — keep the
    division there.
    """
    if weighted:
        return -0.5 * residuals_sq
    return -0.5 * residuals_sq / (rmse**2)


def _estimate_rmse(targets: Sequence[Any], fit_result: Any) -> float:
    """Estimate a strictly positive RMSE for MCMC proposal scaling."""
    residuals = fit_result.details.get("residuals") if fit_result.details else None
    if residuals:
        try:
            count = len(residuals)
            ss = sum(float(residual) ** 2 for residual in residuals)  # float-bridge: emcee proposal scaling
            return max(1e-8, float((ss / max(1, count)) ** 0.5))  # float-bridge: emcee proposal scaling
        except Exception:  # noqa: BLE001
            pass
    try:
        values = [float(value) for value in targets]  # float-bridge: emcee proposal scaling
        if len(values) < 2:
            return 1.0
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / len(values)
        return max(1e-8, float(variance**0.5))  # float-bridge: emcee proposal scaling
    except Exception:  # noqa: BLE001
        return 1.0


def refine_fit_with_mcmc(
    fit_result: Any,
    *,
    param_names: Sequence[str],
    base_params: Mapping[str, mp.mpf],
    observations: Sequence[object],
    targets: Sequence[mp.mpf],
    likelihood_weights: Sequence[mp.mpf] | None,
) -> None:
    """Run MCMC refinement on ``fit_result`` in place, writing diagnostics to
    ``fit_result.details``. Self-skips (with a log line) when emcee is missing,
    there are no free parameters, or the fit carries no live evaluator, so it is
    always safe to call when the caller opted in.
    """
    from fitting.mcmc_fitter import HAS_EMCEE, render_corner_plot, run_mcmc

    if not HAS_EMCEE:
        _logger.info("refine_with_mcmc=True but emcee not installed; skipping")
        return
    if not param_names:
        _logger.info("refine_with_mcmc=True but no free parameters; skipping")
        return
    evaluator = fit_result.details.get("evaluator") if fit_result.details else None
    if evaluator is None:
        _logger.info("MCMC refinement skipped: fit result did not provide an evaluator")
        return
    if len(observations) != len(targets):
        _logger.info("MCMC refinement skipped: observations/targets length mismatch")
        return
    if likelihood_weights is not None and len(likelihood_weights) != len(targets):
        _logger.info("MCMC refinement skipped: likelihood weights length mismatch")
        return

    initial_guess = [float(fit_result.params[name]) for name in param_names]  # float-bridge: emcee walker seeds
    rmse = _estimate_rmse(targets, fit_result)

    weighted = likelihood_weights is not None

    def _log_probability(theta: Sequence[object]) -> float:
        if not param_names or rmse <= 0:
            return float("-inf")  # float-bridge: emcee log-prob sentinel
        try:
            new_params = _params_from_theta(theta, param_names, base_params)
            residuals_sq = 0.0
            for index, (observation, target) in enumerate(zip(observations, targets)):
                _set_evaluator_point_index(evaluator, index)
                pred = float(_evaluate_prediction(evaluator, new_params, observation))  # float-bridge: emcee log-prob
                if not math.isfinite(pred):
                    return float("-inf")  # float-bridge: emcee log-prob sentinel
                residual = float(target) - pred  # float-bridge: emcee log-prob
                # Index against the direct None-check (not the hoisted `weighted`
                # flag) so mypy --strict narrows Sequence | None to indexable.
                weight = float(likelihood_weights[index]) if likelihood_weights is not None else 1.0  # float-bridge: emcee log-prob
                residuals_sq += weight * (residual**2)
                if not math.isfinite(residuals_sq):
                    return float("-inf")  # float-bridge: emcee log-prob sentinel
            return _gaussian_log_probability(residuals_sq, rmse, weighted=weighted)
        except (TypeError, ValueError, ArithmeticError, OverflowError, KeyError):
            return float("-inf")  # float-bridge: emcee log-prob sentinel

    proposal_scale = max(1e-4, rmse * 1e-2)
    pre_flight_lps = [_log_probability(initial_guess)]
    for sign in (-1, 1):
        perturbed = [value + sign * proposal_scale for value in initial_guess]
        pre_flight_lps.append(_log_probability(perturbed))
    if not any(math.isfinite(lp) for lp in pre_flight_lps):
        _logger.info(
            "MCMC pre-flight: all %d sample log-probabilities were -inf; skipping MCMC refinement.",
            len(pre_flight_lps),
        )
        if fit_result.details is None:
            fit_result.details = {}
        fit_result.details["mcmc_warning"] = (
            "MCMC 跳过：初始 log-probability 全部 -inf（数据过于病态）。 / "
            "MCMC skipped: all initial log-probabilities are -inf "
            "(data is too ill-conditioned for Gaussian sampling)."
        )
        return

    try:
        mcmc_result = run_mcmc(
            _log_probability,
            initial_guess,
            list(param_names),
            n_walkers=max(32, 2 * len(param_names) + 2),
            n_steps=800,
            n_burn_in=200,
            proposal_scale=proposal_scale,
        )
    except Exception as exc:  # noqa: BLE001
        _logger.warning("MCMC run failed: %s", exc)
        if fit_result.details is None:
            fit_result.details = {}
        fit_result.details["mcmc_warning"] = (
            f"MCMC 运行失败：{exc}。仅使用最小二乘结果。 / "
            f"MCMC run failed: {exc}. Using LSQ-only result."
        )
        return

    acc = mcmc_result.acceptance_fraction
    chain_warning: str | None = None
    if not math.isfinite(acc) or acc < 0.05:
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

    # Corner plot is stored as base64 text, not raw bytes: the fit-result
    # serializer repr()s any bytes it meets, which would corrupt the PNG.
    corner_b64 = ""
    try:
        corner_png = render_corner_plot(mcmc_result)
        if corner_png:
            corner_b64 = base64.b64encode(corner_png).decode("ascii")
    except Exception as exc:  # noqa: BLE001
        _logger.warning("corner plot render failed: %s", exc)

    if fit_result.details is None:
        fit_result.details = {}
    fit_result.details["mcmc_refinement"] = {
        "medians": mcmc_result.medians,
        "lo_ci": mcmc_result.lo_ci,
        "hi_ci": mcmc_result.hi_ci,
        "acceptance_fraction": mcmc_result.acceptance_fraction,
    }
    if chain_warning:
        fit_result.details["mcmc_warning"] = chain_warning
    if corner_b64:
        fit_result.details["mcmc_corner_png_b64"] = corner_b64


def free_parameter_names(
    parameter_names: Sequence[str],
    params: Mapping[str, Any],
    parameter_config: Mapping[str, Any] | None,
) -> list[str]:
    """Free (non-fixed, non-expression) parameter names present in the result."""
    config = parameter_config or {}

    def _is_fixed(name: str) -> bool:
        entry = config.get(name, {}) if isinstance(config, Mapping) else {}
        return isinstance(entry, Mapping) and (bool(entry.get("fixed")) or bool(entry.get("expr")))

    configured = [name for name in parameter_names if name in params and not _is_fixed(name)]
    if configured:
        return configured
    return [name for name in params if not _is_fixed(name)]


def likelihood_weights_from_series(
    weights: Sequence[Any] | None,
    sigma_series: Sequence[Any] | None,
    target_count: int,
) -> list[mp.mpf] | None:
    """Build MCMC likelihood weights from explicit weights or 1/σ²."""
    if weights is not None and len(weights) == target_count:
        # Validate explicit weights like the sigma path does: a non-positive or
        # non-finite weight makes worse residuals raise the log-probability,
        # corrupting the posterior. Reject (→ unweighted) rather than corrupt.
        parsed_weights: list[mp.mpf] = []
        for value in weights:
            weight = mp.mpf(value)
            if weight <= 0 or not mp.isfinite(weight):
                return None
            parsed_weights.append(weight)
        return parsed_weights
    if sigma_series is None or len(sigma_series) != target_count:
        return None
    parsed: list[mp.mpf] = []
    for sigma in sigma_series:
        if sigma is None:
            return None
        value = mp.mpf(sigma)
        if value <= 0:
            return None
        parsed.append(1 / (value * value))
    return parsed
