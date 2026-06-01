from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import mpmath as mp

from shared.bilingual import _dual_msg


@dataclass(frozen=True)
class FitUncertaintyState:
    data_sigmas: tuple[mp.mpf | None, ...]
    weights: tuple[mp.mpf, ...] | None
    weighted: bool


def fit_uncertainty_policy(
    sigma_values: Sequence[mp.mpf | None],
    *,
    weighted: bool,
) -> FitUncertaintyState:
    data_sigmas = [None if sigma is None else mp.mpf(sigma) for sigma in sigma_values]
    for idx, sigma in enumerate(data_sigmas, 1):
        if sigma is None:
            continue
        if not mp.isfinite(sigma) or sigma <= 0:
            raise ValueError(
                _dual_msg(
                    f"第 {idx} 行的不确定度必须为有限正数。",
                    f"Uncertainty on row {idx} must be a finite positive number.",
                )
            )
    if not weighted:
        return FitUncertaintyState(data_sigmas=tuple(data_sigmas), weights=None, weighted=False)
    if not data_sigmas:
        raise ValueError(
            _dual_msg(
                "未提供不确定度数据，无法执行加权拟合。",
                "No uncertainty data provided; cannot perform weighted fitting.",
            )
        )
    weights: list[mp.mpf] = []
    for idx, sigma in enumerate(data_sigmas, 1):
        if sigma is None:
            raise ValueError(
                _dual_msg(
                    f"第 {idx} 行缺少不确定度，无法执行加权拟合；请在数据中提供带不确定度的数值或包含 sigma/err 列。",
                    f"Row {idx} is missing uncertainty; cannot perform weighted fitting. Provide uncertainties or a sigma/err column.",
                )
            )
        weights.append(mp.mpf("1") / (sigma * sigma))
    return FitUncertaintyState(data_sigmas=tuple(data_sigmas), weights=tuple(weights), weighted=True)
