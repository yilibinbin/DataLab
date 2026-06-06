"""Automatic model selection utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

from mpmath import mp

from extrapolation_methods import (
    SequenceAcceleratorConfig,
    SequenceAccelerationError,
    apply_sequence_accelerator,
)
from shared.bilingual import _dual_msg
from shared.numerics import noise_floor

from .auto_models import AUTO_MODELS, AutoModelDefinition, fit_linear_model
from .constraints import ParameterState
from .hp_fitter import FitResult, combine_error_components, fit_custom_model
from .model_parser import ModelSpecification


class AutoFitCancelled(Exception):
    """Raised inside ``auto_fit_dataset`` when the caller-supplied
    ``should_cancel`` callback returns True between models. The worker
    catches this and surfaces it as a ``cancelled`` signal so the UI
    can revert the Run button without showing an error dialog."""


SEQUENCE_MODEL_ID = "SEQ"
CUSTOM_MODEL_ID = "CUSTOM"


def _normalize_label(text: str | None) -> str:
    if text:
        stripped = text.strip()
        if stripped:
            return stripped
    return "自定义模型 / Custom model"


def _unique_label(label: str | None, used_labels: set[str]) -> str:
    base = _normalize_label(label)
    candidate = base
    counter = 2
    while candidate in used_labels:
        candidate = f"{base} #{counter}"
        counter += 1
    used_labels.add(candidate)
    return candidate


def _allocate_identifier(prefix: str, used_ids: set[str]) -> str:
    candidate = prefix
    counter = 2
    while candidate in used_ids:
        candidate = f"{prefix}#{counter}"
        counter += 1
    used_ids.add(candidate)
    return candidate


@dataclass
class AutoModelResult:
    identifier: str
    label: str
    success: bool
    fit_result: FitResult | None
    error: str | None = None


@dataclass
class AutoFitSummary:
    best_model: str | None
    results: list[AutoModelResult]

    def best(self) -> AutoModelResult | None:
        for result in self.results:
            if result.identifier == self.best_model:
                return result
        return None


def _sequence_model(y_data: list[mp.mpf], precision: int, weights_supplied: bool) -> AutoModelResult:
    config = SequenceAcceleratorConfig(precision=precision)
    try:
        accel = apply_sequence_accelerator("shanks", y_data, config)
    except SequenceAccelerationError as exc:
        return AutoModelResult(SEQUENCE_MODEL_ID, "Sequence acceleration", False, None, str(exc))
    limit = accel.value
    residuals = [limit - value for value in y_data]
    chi2 = sum(r * r for r in residuals)
    n = len(y_data)
    dof = max(1, n - 1)
    mean_target = sum(y_data) / n
    sst = sum((value - mean_target) ** 2 for value in y_data)
    floor = noise_floor()
    noise = chi2 / n if chi2 > floor else floor
    aic = 2 + n * mp.log(noise)
    bic = mp.log(n) + n * mp.log(noise)
    rmse = mp.sqrt(chi2 / n)
    r2 = mp.mpf("1") - (chi2 / sst if sst != 0 else mp.mpf("0"))
    error_estimate = accel.metadata.get("error_estimate")
    if error_estimate is None:
        error_estimate = mp.sqrt(noise)
    stat_errors = {"limit": mp.mpf(error_estimate)}
    sys_errors: dict[str, mp.mpf] = {"limit": mp.mpf("0")}
    _, _, total_errors = combine_error_components({"limit": limit}, stat_errors, sys_errors)
    fit = FitResult(
        params={"limit": limit},
        param_errors=total_errors,
        chi2=chi2,
        reduced_chi2=chi2 / dof,
        aic=aic,
        bic=bic,
        r2=r2,
        rmse=rmse,
        residuals=residuals,
        fitted_curve=[limit for _ in y_data],
        covariance=[[mp.mpf("0")]],
        param_errors_stat=stat_errors,
        param_errors_sys=sys_errors,
        param_errors_total=total_errors,
        details={
            "expression": "f(n) = limit",
            "substituted_expression": f"limit = {mp.nstr(limit, 8)}",
            "error_estimate": error_estimate,
            "uncertainty_note": {
                "zh": "序列加速的误差估计为方法自身的启发式量，非 χ² 拟合的统计标准差。",
                "en": "The error estimate of sequence acceleration is heuristic to that method itself, not the statistical σ from χ² fitting.",
            },
            "weights_ignored": weights_supplied,
        },
    )
    return AutoModelResult(SEQUENCE_MODEL_ID, "Sequence acceleration", True, fit)


def auto_fit_dataset(
    x_data: Iterable[mp.mpf],
    y_data: Iterable[mp.mpf],
    precision: int = 80,
    custom_entry: tuple[ModelSpecification, ParameterState] | None = None,
    extra_models: Iterable[AutoModelDefinition] | None = None,
    weights: list[mp.mpf] | None = None,
    custom_entries: Iterable[tuple[str, ModelSpecification, ParameterState]] | None = None,
    data_sigmas: list[mp.mpf | None] | None = None,
    should_cancel: Optional[Callable[[], bool]] = None,
    per_model_timeout_seconds: Optional[float] = None,
) -> AutoFitSummary:
    """Fit every built-in model + extras + customs to (x, y), pick the
    best by AIC, return a summary.

    Responsiveness control:

    - ``should_cancel``: optional callable that the loop polls
      between models. When it returns True, the loop raises
      :class:`AutoFitCancelled` so the GUI worker can convert that
      into a clean cancellation (no error dialog). The check happens
      between models, not inside a single fit, because ``mp.findroot``
      holds the GIL and there's no safe way to interrupt it mid-Newton.

    ``per_model_timeout_seconds`` is retained only as a compatibility
    parameter. Positive in-process timeouts are rejected because Python
    threads cannot safely kill mpmath work while preserving process-global
    ``mp.dps``. GUI paths that need hard cancellation must use process
    isolation.
    """
    if per_model_timeout_seconds is not None and per_model_timeout_seconds > 0:
        raise ValueError(
            _dual_msg(
                "进程内自动拟合不支持 per-model 超时；请使用进程隔离的取消路径。",
                "In-process auto fit does not support per-model timeouts; use process-isolated cancellation.",
            )
        )
    x_series = [mp.mpf(val) for val in x_data]
    y_series = [mp.mpf(val) for val in y_data]
    results: List[AutoModelResult] = []

    def _check_cancel() -> None:
        if should_cancel is not None and should_cancel():
            raise AutoFitCancelled(
                _dual_msg("自动拟合已取消。", "Auto fit cancelled.")
            )

    definitions = list(AUTO_MODELS)
    if extra_models:
        seen = {definition.identifier for definition in definitions}
        for model in extra_models:
            if model.identifier in seen:
                continue
            definitions.append(model)
            seen.add(model.identifier)

    used_ids = {definition.identifier for definition in definitions}
    used_labels = {definition.label for definition in definitions}
    used_ids.add(SEQUENCE_MODEL_ID)
    used_labels.add("Sequence acceleration")

    for definition in definitions:
        _check_cancel()
        try:
            def _linear_fit(d: AutoModelDefinition = definition) -> FitResult:
                return fit_linear_model(
                    d,
                    x_series,
                    y_series,
                    precision=precision,
                    weights=weights,
                    data_sigmas=data_sigmas,
                )
            fit = _linear_fit()
            results.append(AutoModelResult(definition.identifier, definition.label, True, fit))
        except Exception as exc:
            results.append(
                AutoModelResult(definition.identifier, definition.label, False, None, str(exc))
            )

    entries: List[tuple[str, ModelSpecification, ParameterState]] = []
    if custom_entry:
        spec, state = custom_entry
        entries.append(("自定义模型 / Custom model", spec, state))
    if custom_entries:
        entries.extend(list(custom_entries))
    for raw_label, spec, state in entries:
        _check_cancel()
        display_label = _unique_label(raw_label, used_labels)
        identifier = _allocate_identifier(CUSTOM_MODEL_ID, used_ids)
        try:
            def _custom_fit(
                s: ModelSpecification = spec,
                st: ParameterState = state,
            ) -> FitResult:
                return fit_custom_model(
                    s,
                    st,
                    {"x": x_series},
                    y_series,
                    precision=precision,
                    weights=weights,
                    data_sigmas=data_sigmas,
                )
            fit = _custom_fit()
            results.append(AutoModelResult(identifier, display_label, True, fit))
        except Exception as exc:
            results.append(AutoModelResult(identifier, display_label, False, None, str(exc)))

    _check_cancel()
    if len(y_series) >= 3:
        results.append(_sequence_model(y_series, precision, bool(weights) or bool(data_sigmas)))

    best_model = None
    best_score = None
    for result in results:
        if not result.success or not result.fit_result:
            continue
        score = result.fit_result.aic
        if mp.isnan(score):
            continue
        if best_score is None or score < best_score:
            best_score = score
            best_model = result.identifier

    return AutoFitSummary(best_model=best_model, results=results)
