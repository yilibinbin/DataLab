"""Shared fit-statistics helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from mpmath import mp

from shared.bilingual import _dual_msg
from shared.numerics import noise_floor


@dataclass(frozen=True)
class FitStatistics:
    chi2: mp.mpf
    reduced_chi2: mp.mpf
    r2: mp.mpf
    rmse: mp.mpf
    aic: mp.mpf
    bic: mp.mpf
    dof: int


def compute_fit_statistics(
    targets: Sequence[mp.mpf],
    residuals: Sequence[mp.mpf],
    weights: Sequence[mp.mpf] | None,
    *,
    free_param_count: int,
    validate_weights: bool = False,
) -> FitStatistics:
    """Compute shared weighted least-squares fit statistics."""

    row_count = len(targets)
    if row_count == 0:
        return FitStatistics(mp.nan, mp.nan, mp.nan, mp.nan, mp.nan, mp.nan, -free_param_count)

    if weights is not None and len(weights) != row_count:
        raise ValueError(
            _dual_msg(
                "权重数量必须与数据点数量一致。",
                "Weight count must match the number of data points.",
            )
        )
    if len(residuals) != row_count:
        raise ValueError(
            _dual_msg(
                "残差数量必须与数据点数量一致。",
                "Residual count must match the number of data points.",
            )
        )

    if weights:
        if validate_weights and any(weight <= 0 for weight in weights):
            raise ValueError(
                _dual_msg("权重必须为正。", "Weights must be positive.")
            )
        chi2 = mp.fsum(mp.mpf(weight) * (mp.mpf(residual) * mp.mpf(residual)) for weight, residual in zip(weights, residuals))
        total_weight = mp.fsum(weights)
        mean_target = (
            mp.fsum(mp.mpf(weight) * mp.mpf(target) for weight, target in zip(weights, targets)) / total_weight
            if total_weight > 0
            else mp.fsum(targets) / row_count
        )
        sst = mp.fsum(mp.mpf(weight) * (mp.mpf(target) - mean_target) ** 2 for weight, target in zip(weights, targets))
        rmse = mp.sqrt(chi2 / total_weight)
    else:
        chi2 = mp.fsum(mp.mpf(residual) * mp.mpf(residual) for residual in residuals)
        mean_target = mp.fsum(targets) / row_count
        sst = mp.fsum((mp.mpf(target) - mean_target) ** 2 for target in targets)
        rmse = mp.sqrt(chi2 / row_count)

    dof = row_count - free_param_count
    if dof <= 0:
        return FitStatistics(chi2, mp.nan, mp.nan, rmse, mp.nan, mp.nan, dof)

    reduced = chi2 / dof
    r2 = mp.mpf("1") - (chi2 / sst if sst != 0 else mp.mpf("0"))
    eps = noise_floor()
    noise = chi2 / row_count if chi2 > eps else eps
    aic = 2 * free_param_count + row_count * mp.log(noise)
    bic = free_param_count * mp.log(row_count) + row_count * mp.log(noise)
    return FitStatistics(chi2, reduced, r2, rmse, aic, bic, dof)
