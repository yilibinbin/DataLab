"""Automatic model selection utilities."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional

from mpmath import mp

from shared.bilingual import _dual_msg
from shared.numerics import noise_floor

try:  # Allow running as a loose script or as a package
    from ..extrapolation_methods import (
        SequenceAcceleratorConfig,
        SequenceAccelerationError,
        apply_sequence_accelerator,
    )
except ImportError:  # pragma: no cover - fallback for script execution
    from extrapolation_methods import (  # type: ignore
        SequenceAcceleratorConfig,
        SequenceAccelerationError,
        apply_sequence_accelerator,
    )


class AutoFitCancelled(Exception):
    """Raised inside ``auto_fit_dataset`` when the caller-supplied
    ``should_cancel`` callback returns True between models. The worker
    catches this and surfaces it as a ``cancelled`` signal so the UI
    can revert the Run button without showing an error dialog."""


def _run_with_timeout(
    func: Callable[[], object],
    timeout_seconds: float,
    label: str,
    target_dps: int,
) -> object:
    """Run ``func`` on a daemon thread and raise ``TimeoutError`` if it
    exceeds ``timeout_seconds``.

    mpmath holds the GIL through long arithmetic, so a Python-level
    ``signal.alarm`` cannot interrupt it; the daemon-thread approach is
    deliberately advisory — the runaway thread is left to finish on its
    own. The caller treats the timed-out model as a failure and moves
    on, which is exactly what the UI needs to recover responsiveness.

    **mpmath precision-isolation** (CRITICAL): ``mp.dps`` is process-
    global. If the runaway daemon thread is inside a ``with
    precision_guard(dps): ...`` block when the parent abandons it,
    its eventual exit from that block will reset ``mp.dps`` to the
    pre-entry value — silently corrupting the next model that the
    parent has since started. We defend by snapshotting ``mp.dps``
    AFTER the join and restoring it before returning, so the parent's
    precision state is invariant across the timeout boundary.

    The runaway thread can still mutate ``mp.dps`` later when it
    finally exits its inner guard, but by then the parent has moved
    onto another model whose own ``precision_guard`` re-asserts the
    correct dps before any computation. The window of corruption is
    therefore confined to between models, not within a model — which
    matches the cancellation semantics already documented for
    ``should_cancel``.
    """
    holder: list[object] = [None]
    err: list[BaseException] = []

    def _target() -> None:
        try:
            holder[0] = func()
        except BaseException as exc:  # noqa: BLE001
            err.append(exc)

    parent_dps_before = mp.dps
    t = threading.Thread(target=_target, name=f"datalab-fit-{label}", daemon=True)
    t.start()
    t.join(timeout_seconds)
    if t.is_alive():
        # Re-assert the parent's dps in case the runaway thread already
        # mutated it (e.g. its precision_guard's __enter__ ran but
        # __exit__ hasn't yet, so the global is at ``target_dps`` —
        # which happens to be what we want for the next model anyway).
        # Either way, set it explicitly so subsequent code is
        # deterministic regardless of the daemon thread's race.
        mp.dps = max(parent_dps_before, target_dps)
        raise TimeoutError(
            _dual_msg(
                f"模型 {label!r} 超过 {timeout_seconds:.0f}s 仍未完成，已跳过。",
                f"Model {label!r} exceeded {timeout_seconds:.0f}s and was skipped.",
            )
        )
    # Thread completed cleanly. Its precision_guard already restored
    # ``mp.dps`` on exit; we re-assert anyway as a belt-and-suspenders
    # invariant against any future code path that might forget the
    # guard.
    mp.dps = parent_dps_before
    if err:
        raise err[0]
    return holder[0]

from .auto_models import AUTO_MODELS, AutoModelDefinition, fit_linear_model
from .hp_fitter import FitResult, combine_error_components, fit_custom_model
from .model_parser import ModelSpecification
from .constraints import ParameterState

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

    Two responsiveness controls (added because real-world ill-conditioned
    datasets can drive a single non-linear LM fit into the tens of
    seconds, which makes the GUI look frozen):

    - ``should_cancel``: optional callable that the loop polls
      between models. When it returns True, the loop raises
      :class:`AutoFitCancelled` so the GUI worker can convert that
      into a clean cancellation (no error dialog). The check happens
      between models, not inside a single fit, because ``mp.findroot``
      holds the GIL and there's no safe way to interrupt it mid-Newton.

    - ``per_model_timeout_seconds``: optional advisory cap. When set,
      each model fit runs on a daemon thread and is abandoned if it
      exceeds the cap; that model is recorded as a failure ("model
      timed out") and the loop continues. The runaway thread keeps
      running but is daemon=True, so it doesn't block process exit.
      Without this, an ill-conditioned PowerLimit fit on σ ≈ 1e-19
      data can take 50+ seconds while the user can't tell whether
      the GUI is alive.

    Both are off by default to preserve the historical behaviour of
    the function for non-GUI callers (CLI, tests).
    """
    x_series = [mp.mpf(val) for val in x_data]
    y_series = [mp.mpf(val) for val in y_data]
    results: List[AutoModelResult] = []

    def _check_cancel() -> None:
        if should_cancel is not None and should_cancel():
            raise AutoFitCancelled(
                _dual_msg("自动拟合已取消。", "Auto fit cancelled.")
            )

    def _run_one(label: str, fn: Callable[[], object]) -> object:
        """Wrap a single model fit with the optional timeout. Returns
        the fit result, or raises TimeoutError on cap breach. Errors
        from the fit itself propagate so the caller can record them.

        ``target_dps=precision`` is forwarded so ``_run_with_timeout``
        can re-assert the right ``mp.dps`` after a timeout, defending
        against the daemon thread corrupting the parent's precision
        state via ``precision_guard.__exit__``.
        """
        if per_model_timeout_seconds is None or per_model_timeout_seconds <= 0:
            return fn()
        return _run_with_timeout(
            fn, per_model_timeout_seconds, label, target_dps=precision,
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
            fit = _run_one(
                definition.label,
                lambda d=definition: fit_linear_model(
                    d,
                    x_series,
                    y_series,
                    precision=precision,
                    weights=weights,
                    data_sigmas=data_sigmas,
                ),
            )
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
            fit = _run_one(
                display_label,
                lambda s=spec, st=state: fit_custom_model(
                    s,
                    st,
                    {"x": x_series},
                    y_series,
                    precision=precision,
                    weights=weights,
                    data_sigmas=data_sigmas,
                ),
            )
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
