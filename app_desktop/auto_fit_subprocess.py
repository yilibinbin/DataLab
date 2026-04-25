"""Subprocess-based auto-fit orchestrator (B+C from the auto-fit
responsiveness review).

Why this module exists
----------------------

PR #26 added cooperative ``should_cancel`` polling and a per-model
wall-clock timeout to ``auto_fit_dataset``. Both were necessary
improvements but they cannot deliver "click Stop, GUI responds
immediately" — mpmath holds the GIL through ``mp.findroot`` Newton
iterations, so an in-process fit runs to completion or to its 15 s
timeout, whichever comes first. The user reported this 15 s wait
felt like the Stop button "didn't really stop".

This module replaces the in-process fit loop with a process-per-fit
architecture:

  - Each candidate model is fitted in its own ``multiprocessing.
    Process`` (clean Python interpreter, isolated ``mp.dps``).
  - The main process polls ``should_cancel`` and the subprocess
    liveness in 100 ms steps. On cancel, ``proc.kill()`` issues a
    SIGKILL — true OS-level immediate termination of the runaway
    Newton iterations. CPU is freed within milliseconds.
  - Progress is reported via ``progress_callback`` so the GUI
    status bar can show "(3/19) Fitting Padé(1|1)…".

Subprocess startup cost on macOS is ~150 ms per model (must use the
``spawn`` start method because PySide6's parent process isn't fork-
safe). For a 19-model auto-fit that's ~3 s of overhead — small
relative to the legitimate fitting time on real datasets, and a tiny
price for genuinely cancellable fits.

Serialization protocol
----------------------

mpmath callables (closures over ``basis_functions`` /
``evaluate_func`` / ``gradient_funcs``) are not picklable. The
orchestrator therefore sends **template descriptors** to the
subprocess (e.g. ``{"identifier": "M1"}`` or ``{"expression":
"a*x+b"}``), and the subprocess **rebuilds** the model from those
descriptors using the same factory functions the main process would.

Numeric data crosses the boundary as base-10 strings via ``mp.nstr``
at ``precision + 5`` digits. The subprocess re-materialises them
via ``mp.mpf(s)`` inside its own ``precision_guard``. Round-trip
loss is bounded by the 5-digit safety margin and is well below any
real fit's per-iteration tolerance.
"""
from __future__ import annotations

import logging
import multiprocessing
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from mpmath import mp

from fitting.model_selector import AutoFitSummary, AutoModelResult
from shared.bilingual import _dual_msg


# ---------------------------------------------------------------- task derivation
# These regex / identifier rules let us round-trip an
# ``AutoModelDefinition`` (which contains non-picklable closures)
# through the subprocess by inspecting its identifier and
# reconstructing the same definition on the other side.

import re

_POLY_RE = re.compile(r"^POLY(\d+)$")
_INV_RE = re.compile(r"^INV(\d+)_(\d+)$")


def _builtin_identifiers() -> set[str]:
    """Identifiers of the static AUTO_MODELS list (M1, M2, ...).

    Imported lazily so the orchestrator module loads cleanly even
    when fitting/ isn't on the path (e.g. in pytest's collection
    phase before sys.path tweaks).
    """
    from fitting.auto_models import AUTO_MODELS
    return {d.identifier for d in AUTO_MODELS}


def task_from_definition(definition: Any) -> "ModelTask":
    """Convert an in-process ``AutoModelDefinition`` (with closures)
    into a pickle-safe ``ModelTask`` that the subprocess can rebuild.

    Identifier-based dispatch:
    - ``M1..M8``: builtin lookup in AUTO_MODELS
    - ``POLY<n>``: rebuild via ``build_polynomial_definition(n)``
    - ``INV<a>_<b>``: rebuild via ``build_inverse_series_definition(a, b)``
    - anything else: raises ``ValueError`` so callers don't silently
      mis-route an unknown extra-model factory.
    """
    ident = definition.identifier
    if ident in _builtin_identifiers():
        return ModelTask(
            kind="auto_builtin", identifier=ident,
            label=definition.label,
            params={"identifier": ident},
        )
    m = _POLY_RE.match(ident)
    if m:
        return ModelTask(
            kind="auto_polynomial", identifier=ident,
            label=definition.label,
            params={"degree": int(m.group(1))},
        )
    m = _INV_RE.match(ident)
    if m:
        return ModelTask(
            kind="auto_inverse_series", identifier=ident,
            label=definition.label,
            params={
                "min_power": int(m.group(1)),
                "max_power": int(m.group(2)),
            },
        )
    raise ValueError(
        _dual_msg(
            f"无法将模型 {ident!r} 转换为子进程任务。",
            f"Cannot convert model {ident!r} to subprocess task.",
        )
    )


def task_from_custom_entry(
    label: str, spec: Any, state: Any,
) -> "ModelTask":
    """Convert a (label, ModelSpecification, ParameterState) tuple
    (with non-picklable closures) into a ``ModelTask`` the subprocess
    can rebuild via ``build_model_specification`` +
    ``build_parameter_state``.
    """
    return ModelTask(
        kind="custom", identifier="CUSTOM",
        label=label,
        params={
            "expression": spec.expression,
            "variable_names": list(spec.variables),
            "parameter_state": _serialize_parameter_state(state),
        },
    )


def _serialize_parameter_state(state: Any) -> dict[str, dict[str, Any]]:
    """Reverse of ``build_parameter_state`` — extract the original
    ``{name: {"initial": ..., "min": ..., ...}}`` dict so the
    subprocess can rebuild an equivalent ``ParameterState``.

    Only the user-visible fields (``initial``, ``min``, ``max``,
    ``fixed``) are propagated; ``dependent_defs`` carries non-
    picklable callables and is rejected explicitly — none of the
    GUI's default custom entries (Power-limit, Padé) use them, so
    raising here is a clear contract violation rather than a
    silent precision-loss surprise.
    """
    if getattr(state, "dependent_defs", None):
        raise ValueError(
            _dual_msg(
                "包含依赖参数的自定义模型暂不支持子进程路径。",
                "Custom models with dependent parameters are not yet "
                "supported by the subprocess path.",
            )
        )
    out: dict[str, dict[str, Any]] = {}

    # Iterate over both free and fixed params so the subprocess
    # rebuilds an identical ParameterState (free + fixed both
    # appear as keys in the resulting dict, distinguished by
    # whether ``fixed`` is present).
    all_names = list(state.free_params) + list(state.fixed_values.keys())
    for name in all_names:
        bundle: dict[str, Any] = {}
        if name in state.fixed_values:
            bundle["fixed"] = _stringify_for_state(state.fixed_values[name])
            out[name] = bundle
            continue
        if name in state.initial_guess:
            bundle["initial"] = _stringify_for_state(state.initial_guess[name])
        lower, upper = state.bounds.get(name, (None, None))
        if lower is not None:
            bundle["min"] = _stringify_for_state(lower)
        if upper is not None:
            bundle["max"] = _stringify_for_state(upper)
        out[name] = bundle
    return out


def _stringify_for_state(value: Any) -> Any:
    """Convert a numeric value to a transport-safe form. Strings
    survive ToExpression-style parsing in ``build_parameter_state``
    (which accepts ``str | int | float``), so prefer ``mp.nstr`` for
    high-precision values that ``float()`` would truncate."""
    if hasattr(value, "_mpf_"):
        return mp.nstr(value, 50)
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


_logger = logging.getLogger(__name__)

# Polling interval while waiting for a subprocess. 100 ms is fine
# for both responsiveness (Stop reacts within 0.1 s) and overhead
# (10 wakes/sec is negligible).
_POLL_INTERVAL = 0.1

# Slack added to the timeout when computing how long to actually
# wait — covers the 100 ms polling jitter so a 15 s cap doesn't
# falsely trip on a 15.05 s real-time fit.
_TIMEOUT_SLACK = 0.2


ProgressStatus = Literal["started", "ok", "timeout", "error", "cancelled"]


@dataclass(frozen=True)
class ProgressEvent:
    """One event emitted to ``progress_callback`` per state transition.

    ``index`` is the 0-based model number; ``total`` is the total
    number of tasks. ``status`` distinguishes the lifecycle states
    so the GUI can render them differently (e.g. "started" → grey
    spinner, "ok" → green check, "timeout" → orange warning).

    ``error`` carries the human-readable, bilingual reason on
    non-OK terminals; it's None on "started" and "ok".
    """

    index: int
    total: int
    label: str
    status: ProgressStatus
    error: str | None = None


@dataclass(frozen=True)
class ModelTask:
    """Pickle-safe descriptor for one model fit.

    The orchestrator sends this to the subprocess via a Queue;
    closures and Callables are forbidden. ``params`` carries the
    rebuild recipe, keyed by ``kind``:

    - ``auto_builtin``: ``{"identifier": "M1"}`` (look up in AUTO_MODELS)
    - ``auto_polynomial``: ``{"degree": 2}`` (build via build_polynomial_definition)
    - ``auto_inverse_series``: ``{"min_power": 1, "max_power": 3}``
    - ``custom``: ``{"expression": str, "variable_names": [...],
                    "parameter_state": {<param_name>: {...}}}``
    """

    kind: Literal[
        "auto_builtin", "auto_polynomial", "auto_inverse_series", "custom"
    ]
    identifier: str
    label: str
    params: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------- subprocess

def _serialize_mpf_list(values: list[Any], digits: int) -> list[str]:
    """Convert a list of mp.mpf (or numbers) into base-10 strings
    that round-trip safely through ``mp.mpf(...)``."""
    out: list[str] = []
    for v in values:
        if v is None:
            out.append("")  # represent None as empty string
        else:
            out.append(mp.nstr(mp.mpf(v), digits))
    return out


def _deserialize_mpf_list(strs: list[str]) -> list[Any]:
    """Inverse of ``_serialize_mpf_list`` (None encoded as "")."""
    return [None if s == "" else mp.mpf(s) for s in strs]


def _rebuild_task_callable(task: ModelTask, x_series: list, y_series: list,
                            sigmas: list, weights: list | None,
                            precision: int):
    """Inside the subprocess, reconstruct the right ``fit_*`` call
    for the task and execute it. Returns a ``FitResult``."""
    # Imports happen inside the subprocess (after spawn → fresh
    # interpreter) so the parent's import side-effects don't carry
    # over. Each subprocess pays ~50 ms for these imports; that's
    # part of the documented per-model overhead.
    from fitting.auto_models import (
        AUTO_MODELS, build_inverse_series_definition,
        build_polynomial_definition, fit_linear_model,
    )
    from fitting.constraints import build_parameter_state
    from fitting.hp_fitter import fit_custom_model
    from fitting.model_parser import build_model_specification

    if task.kind == "auto_builtin":
        ident = task.params["identifier"]
        defn = next(
            (d for d in AUTO_MODELS if d.identifier == ident), None,
        )
        if defn is None:
            raise ValueError(f"Unknown auto-builtin identifier: {ident!r}")
        return fit_linear_model(
            defn, x_series, y_series,
            precision=precision, weights=weights, data_sigmas=sigmas,
        )
    if task.kind == "auto_polynomial":
        defn = build_polynomial_definition(int(task.params["degree"]))
        return fit_linear_model(
            defn, x_series, y_series,
            precision=precision, weights=weights, data_sigmas=sigmas,
        )
    if task.kind == "auto_inverse_series":
        defn = build_inverse_series_definition(
            int(task.params["min_power"]), int(task.params["max_power"]),
        )
        return fit_linear_model(
            defn, x_series, y_series,
            precision=precision, weights=weights, data_sigmas=sigmas,
        )
    if task.kind == "custom":
        expression = task.params["expression"]
        variable_names = list(task.params["variable_names"])
        param_state_dict = task.params["parameter_state"]
        parameter_names = list(param_state_dict.keys())
        spec = build_model_specification(
            expression, variable_names, parameter_names,
        )
        state = build_parameter_state(param_state_dict, parameter_names)
        return fit_custom_model(
            spec, state, {variable_names[0]: x_series}, y_series,
            precision=precision, weights=weights, data_sigmas=sigmas,
        )
    raise ValueError(f"Unknown task kind: {task.kind!r}")


def _safe_nstr(value: Any, digits: int) -> str:
    """Robust mp.nstr — handles plain numbers, mp.mpf, mp.mpc, and
    falls back to str() for unexpected types so the subprocess
    serialization can't raise on edge values (mp.nan, mp.inf,
    integer-typed mpf, etc.). The downstream deserializer uses
    mp.mpf which accepts all these forms.
    """
    try:
        return mp.nstr(mp.mpf(value), digits)
    except (TypeError, ValueError):
        return str(value)


def _serialize_fit_result(fit: Any, keep_digits: int) -> dict[str, Any]:
    """Convert a ``FitResult`` into a pickle-safe dict. ``details``
    may contain non-picklable values (e.g. mpmath objects in the
    ``error_estimate`` field) so we pass it through ``_jsonify_details``
    rather than relying on ``dict(fit.details)`` to be transport-safe.
    """
    return {
        "ok": True,
        "params": {k: _safe_nstr(v, keep_digits)
                   for k, v in fit.params.items()},
        "param_errors": {k: _safe_nstr(v, keep_digits)
                         for k, v in fit.param_errors.items()},
        "param_errors_stat": {k: _safe_nstr(v, keep_digits)
                              for k, v in fit.param_errors_stat.items()},
        "param_errors_sys": {k: _safe_nstr(v, keep_digits)
                             for k, v in fit.param_errors_sys.items()},
        "param_errors_total": {k: _safe_nstr(v, keep_digits)
                               for k, v in fit.param_errors_total.items()},
        "chi2": _safe_nstr(fit.chi2, keep_digits),
        "reduced_chi2": _safe_nstr(fit.reduced_chi2, keep_digits),
        "aic": _safe_nstr(fit.aic, keep_digits),
        "bic": _safe_nstr(fit.bic, keep_digits),
        "r2": _safe_nstr(fit.r2, keep_digits),
        "rmse": _safe_nstr(fit.rmse, keep_digits),
        "residuals": [_safe_nstr(v, keep_digits) for v in fit.residuals],
        "fitted_curve": [_safe_nstr(v, keep_digits)
                         for v in fit.fitted_curve],
        "covariance": [
            [_safe_nstr(c, keep_digits) for c in row]
            for row in fit.covariance
        ],
        "details": _jsonify_details(fit.details, keep_digits),
    }


def _jsonify_details(details: dict[str, Any], digits: int) -> dict[str, Any]:
    """Make ``FitResult.details`` pickle-safe.

    Most ``details`` keys carry plain str/int/dict values, but a few
    (``error_estimate`` from sequence-acceleration, custom debugging
    keys) can hold ``mp.mpf`` instances. Pickling an ``mp.mpf`` works
    in CPython but loses precision context; stringifying via
    ``_safe_nstr`` is the same approach we use for the numeric
    fields and is robust against any future mpmath subtype.
    """
    out: dict[str, Any] = {}
    for key, val in details.items():
        if isinstance(val, (int, float, str, bool)) or val is None:
            out[key] = val
        elif isinstance(val, dict):
            out[key] = val  # nested dicts already pickle-safe in practice
        elif hasattr(val, "_mpf_"):
            out[key] = _safe_nstr(val, digits)
        else:
            try:
                out[key] = str(val)
            except Exception:
                out[key] = "<unserializable>"
    return out


def _fit_one_model_in_subprocess(
    queue: multiprocessing.Queue,
    task: ModelTask,
    xs_str: list[str],
    ys_str: list[str],
    sigmas_str: list[str] | None,
    weights_str: list[str] | None,
    precision: int,
) -> None:
    """Subprocess entry point: rebuild data + model, run the fit,
    send the serialized result back through the queue, exit.

    The function is at module scope (not a closure) so it survives
    the pickle round-trip required by ``multiprocessing.Process(
    target=...)`` under the ``spawn`` start method.

    Errors of any kind are caught and reported via ``queue.put``
    rather than allowed to crash the subprocess silently — the
    orchestrator times out on a missing message and treats that as
    a hard error, which is harder to debug than an explicit failure.
    """
    try:
        # Use ``precision_guard`` (the project-canonical context
        # manager) rather than ``mp.workdps`` directly. CLAUDE.md
        # documents this as a hard rule: every numerical computation
        # must wrap work via ``precision_guard``, which clamps the
        # value to ``[10, 1_000_000]`` and gives consistent error
        # paths for the malformed-precision case. This is process-
        # local in the subprocess so there's no GIL race risk —
        # we just want consistency with the rest of the codebase.
        from shared.precision import precision_guard

        with precision_guard(precision):
            x_series = _deserialize_mpf_list(xs_str)
            y_series = _deserialize_mpf_list(ys_str)
            sigmas = _deserialize_mpf_list(sigmas_str) if sigmas_str else None
            weights = _deserialize_mpf_list(weights_str) if weights_str else None

            fit = _rebuild_task_callable(
                task, x_series, y_series, sigmas, weights, precision,
            )

            keep_digits = precision + 5
            payload = _serialize_fit_result(fit, keep_digits)
            queue.put(payload)
    except BaseException as exc:  # noqa: BLE001
        # Any failure (even SystemExit) is reported as a structured
        # error so the orchestrator's queue.get doesn't block.
        try:
            queue.put({"ok": False, "error": str(exc)})
        except Exception:
            # Queue may already be closed (e.g. parent killed us);
            # nothing more we can do. The orchestrator's wait loop
            # treats a missing message as an error too.
            pass


# ---------------------------------------------------------------- payload → FitResult

def _deserialize_fit_payload(payload: dict[str, Any]) -> Any:
    """Inverse of the serialization in ``_fit_one_model_in_subprocess``.
    Returns a ``FitResult`` object so downstream code (renderers,
    LaTeX writers) doesn't need to know we round-tripped it."""
    from fitting.hp_fitter import FitResult

    return FitResult(
        params={k: mp.mpf(v) for k, v in payload["params"].items()},
        param_errors={k: mp.mpf(v) for k, v in payload["param_errors"].items()},
        chi2=mp.mpf(payload["chi2"]),
        reduced_chi2=mp.mpf(payload["reduced_chi2"]),
        aic=mp.mpf(payload["aic"]),
        bic=mp.mpf(payload["bic"]),
        r2=mp.mpf(payload["r2"]),
        rmse=mp.mpf(payload["rmse"]),
        residuals=[mp.mpf(v) for v in payload["residuals"]],
        fitted_curve=[mp.mpf(v) for v in payload["fitted_curve"]],
        covariance=[[mp.mpf(c) for c in row] for row in payload["covariance"]],
        param_errors_stat={k: mp.mpf(v)
                           for k, v in payload["param_errors_stat"].items()},
        param_errors_sys={k: mp.mpf(v)
                          for k, v in payload["param_errors_sys"].items()},
        param_errors_total={k: mp.mpf(v)
                            for k, v in payload["param_errors_total"].items()},
        details=payload["details"],
    )


# ---------------------------------------------------------------- orchestrator


@dataclass
class SubprocessAutoFitOrchestrator:
    """Run auto-fit by spawning one subprocess per candidate model.

    Public API mirrors the in-process ``auto_fit_dataset`` so callers
    can swap implementations with minimal change. Differences:

    - Cancellation is **immediate**: the running subprocess is killed
      via SIGKILL on the next 100 ms poll after ``should_cancel``
      returns True.
    - ``per_model_timeout_seconds`` is enforced by killing the
      subprocess at the cap, not by abandoning a daemon thread.
    - ``progress_callback`` receives one ``ProgressEvent`` per
      state transition for GUI status-bar updates.
    """

    precision: int = 80
    per_model_timeout_seconds: float | None = 30.0

    def run(
        self,
        tasks: list[ModelTask],
        x_data: list,
        y_data: list,
        sigma_data: list | None = None,
        weights: list | None = None,
        should_cancel: Callable[[], bool] | None = None,
        progress_callback: Callable[[ProgressEvent], None] | None = None,
    ) -> AutoFitSummary:
        ctx = multiprocessing.get_context("spawn")
        results: list[AutoModelResult] = []
        keep_digits = max(self.precision + 5, 20)

        # Pre-serialize datasets once (each subprocess deserializes
        # locally). Doing this in the parent saves us re-encoding
        # for every model.
        xs_str = _serialize_mpf_list(x_data, keep_digits)
        ys_str = _serialize_mpf_list(y_data, keep_digits)
        sigmas_str = (
            _serialize_mpf_list(sigma_data, keep_digits)
            if sigma_data is not None else None
        )
        weights_str = (
            _serialize_mpf_list(weights, keep_digits)
            if weights is not None else None
        )

        total = len(tasks)

        for idx, task in enumerate(tasks):
            if should_cancel is not None and should_cancel():
                self._emit(progress_callback, idx, total, task.label,
                           "cancelled")
                results.append(self._make_cancelled_result(task))
                # Don't try to start any further tasks.
                continue

            self._emit(progress_callback, idx, total, task.label, "started")

            queue = ctx.Queue()
            proc = ctx.Process(
                target=_fit_one_model_in_subprocess,
                args=(queue, task, xs_str, ys_str, sigmas_str,
                      weights_str, self.precision),
                name=f"datalab-fit-{task.identifier}",
            )
            proc.start()

            outcome, payload, error = self._wait_for_subprocess(
                proc, queue, task.label, should_cancel,
            )

            if outcome == "cancelled":
                self._emit(progress_callback, idx, total, task.label,
                           "cancelled", error)
                results.append(self._make_cancelled_result(task))
                # Subsequent tasks: skip them all with cancelled status.
                for j in range(idx + 1, total):
                    later = tasks[j]
                    self._emit(progress_callback, j, total, later.label,
                               "cancelled")
                    results.append(self._make_cancelled_result(later))
                break

            if outcome == "timeout":
                self._emit(progress_callback, idx, total, task.label,
                           "timeout", error)
                results.append(AutoModelResult(
                    task.identifier, task.label, False, None, error,
                ))
                continue

            if outcome == "error":
                self._emit(progress_callback, idx, total, task.label,
                           "error", error)
                results.append(AutoModelResult(
                    task.identifier, task.label, False, None, error,
                ))
                continue

            # outcome == "ok"
            try:
                fit = _deserialize_fit_payload(payload)
                self._emit(progress_callback, idx, total, task.label, "ok")
                results.append(AutoModelResult(
                    task.identifier, task.label, True, fit, None,
                ))
            except Exception as exc:  # noqa: BLE001
                err = f"failed to deserialize fit result: {exc}"
                self._emit(progress_callback, idx, total, task.label,
                           "error", err)
                results.append(AutoModelResult(
                    task.identifier, task.label, False, None, err,
                ))

        # Pick best-AIC like the in-process version does.
        best_model = self._pick_best(results)
        return AutoFitSummary(best_model=best_model, results=results)

    @staticmethod
    def _emit(
        callback: Callable[[ProgressEvent], None] | None,
        index: int, total: int, label: str,
        status: ProgressStatus, error: str | None = None,
    ) -> None:
        if callback is None:
            return
        try:
            callback(ProgressEvent(
                index=index, total=total, label=label,
                status=status, error=error,
            ))
        except Exception as exc:  # noqa: BLE001
            # Intentionally swallow — progress reporting must NEVER
            # break the actual fitting pipeline. Log the exception's
            # type+message+traceback at WARNING so a real bug in the
            # GUI signal connection or in ProgressEvent itself is
            # diagnosable rather than indistinguishable from a deleted
            # Qt widget.
            _logger.warning(
                "progress_callback raised: %s", exc, exc_info=True,
            )

    def _wait_for_subprocess(
        self,
        proc: multiprocessing.Process,
        queue: multiprocessing.Queue,
        label: str,
        should_cancel: Callable[[], bool] | None,
    ) -> tuple[
        Literal["ok", "timeout", "error", "cancelled"],
        dict[str, Any] | None,
        str | None,
    ]:
        """Poll the subprocess until completion, timeout, or cancel.

        Returns ``(outcome, payload_or_None, error_or_None)``.
        On timeout / cancel, sends SIGKILL and joins. The killed
        subprocess releases CPU within milliseconds.
        """
        timeout = self.per_model_timeout_seconds
        deadline = (
            time.monotonic() + timeout + _TIMEOUT_SLACK
            if timeout is not None and timeout > 0
            else None
        )

        # Receive-first polling: each iteration tries queue.get with a
        # short timeout. This avoids the documented race where
        # ``proc.is_alive()`` returns False before multiprocessing.Queue's
        # internal feeder thread has flushed the result to the parent's
        # pipe — a HIGH bug surfaced in code review.
        import queue as _queue_mod
        try:
            while True:
                # 1) Cancel takes precedence over result delivery so
                # the user sees a snappy stop even if the subprocess
                # was about to deliver.
                if should_cancel is not None and should_cancel():
                    proc.kill()
                    proc.join(timeout=2.0)
                    return ("cancelled",
                            None,
                            _dual_msg("自动拟合已取消。",
                                      "Auto fit cancelled."))

                # 2) Try to drain any pending result. ``Empty`` means
                # not ready yet; any other dict shape is the worker's
                # delivery (success or structured error).
                try:
                    payload = queue.get(timeout=_POLL_INTERVAL)
                except _queue_mod.Empty:
                    payload = None

                if payload is not None:
                    proc.join(timeout=2.0)
                    if isinstance(payload, dict) and payload.get("ok"):
                        return ("ok", payload, None)
                    err = (
                        payload.get("error", "unknown error")
                        if isinstance(payload, dict) else str(payload)
                    )
                    return ("error", None, err)

                # 3) Per-model timeout: kill the subprocess, return
                # a structured failure. The caller records it and
                # moves on to the next model.
                if deadline is not None and time.monotonic() > deadline:
                    proc.kill()
                    proc.join(timeout=2.0)
                    return ("timeout", None, _dual_msg(
                        f"模型 {label!r} 超过 {timeout:.0f}s 仍未完成，已跳过。",
                        f"Model {label!r} exceeded {timeout:.0f}s "
                        "and was skipped.",
                    ))

                # 4) Subprocess died without delivering a result
                # (segfault, OOM kill, ImportError that wasn't caught).
                # ``proc.join`` is a small guard window for the rare
                # case where the OS has reaped the process but the
                # feeder thread is mid-flush.
                if not proc.is_alive():
                    proc.join(timeout=0.5)
                    # Last-ditch drain attempt.
                    try:
                        payload = queue.get(timeout=0.2)
                        if isinstance(payload, dict) and payload.get("ok"):
                            return ("ok", payload, None)
                        err = (
                            payload.get("error", "unknown error")
                            if isinstance(payload, dict) else str(payload)
                        )
                        return ("error", None, err)
                    except _queue_mod.Empty:
                        return ("error", None, _dual_msg(
                            f"模型 {label!r} 子进程退出但未返回结果。",
                            f"Model {label!r} subprocess exited "
                            "without returning a result.",
                        ))
        finally:
            # Free the queue's pipe pair + feeder thread regardless of
            # how we exited the poll loop. Without this, repeated
            # cancellations on a long auto-fit session leak file
            # descriptors (HIGH #4 from review).
            try:
                queue.close()
                queue.join_thread()
            except Exception:
                pass

    @staticmethod
    def _make_cancelled_result(task: ModelTask) -> AutoModelResult:
        return AutoModelResult(
            task.identifier, task.label, False, None,
            _dual_msg("自动拟合已取消。", "Auto fit cancelled."),
        )

    @staticmethod
    def _pick_best(results: list[AutoModelResult]) -> str | None:
        best_model: str | None = None
        best_score = None
        for r in results:
            if not r.success or r.fit_result is None:
                continue
            score = r.fit_result.aic
            if mp.isnan(score):
                continue
            if best_score is None or score < best_score:
                best_score = score
                best_model = r.identifier
        return best_model
