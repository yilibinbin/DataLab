"""Pin the responsiveness controls added to auto_fit_dataset.

Background: an end-user reported the desktop GUI's "Auto fit" command
freezing for several minutes on a 9-row dataset with σ ≈ 1e-19, and
the Stop button having no visible effect. Root cause was that

  - ``_execute_auto_fit_job`` runs ``auto_fit_dataset`` synchronously
    over ~16 candidate models with no inter-model cancellation point;
  - one model in particular (``A*x**(-p) + C`` non-linear LM at
    dps=80) needed >50 s on this ill-conditioned data because the
    Newton solver thrashed across 14 seed variants.

Two responsiveness controls were added (see ``fitting/model_selector.
py:auto_fit_dataset``):

  1. ``should_cancel`` — polled between models. When True, raises
     :class:`AutoFitCancelled` so the GUI worker can surface a clean
     cancellation (no error dialog).
  2. ``per_model_timeout_seconds`` used to spawn per-model timeout
     threads. That is no longer safe with process-global mpmath
     precision; hard cancellation belongs at the process-worker layer.

This test file pins both behaviours.
"""
from __future__ import annotations

import time

import pytest
from mpmath import mp

from fitting.auto_models import build_polynomial_definition
from fitting.model_selector import (
    AutoFitCancelled,
    _run_with_timeout,
    auto_fit_dataset,
)
from shared.precision import precision_guard


def _fit_kwargs(**overrides: object) -> dict[str, object]:
    """Tiny clean dataset (linear) so the built-in model loop is fast.

    Used by tests that don't need a pathological condition number —
    they just need ``auto_fit_dataset`` to traverse multiple models
    so the cancellation / timeout machinery can be observed.
    """
    base: dict[str, object] = {
        "x_data": [mp.mpf(i) for i in range(1, 11)],
        "y_data": [mp.mpf(2 * i + 3) for i in range(1, 11)],
        "precision": 50,
        # Limit to 3 polynomial extras so the test still runs in
        # well under a second when the cancel hook ISN'T tripped.
        "extra_models": [build_polynomial_definition(d) for d in (1, 2, 3)],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------- cancel API

def test_should_cancel_callback_raises_AutoFitCancelled() -> None:
    """When ``should_cancel`` returns True, the loop raises
    :class:`AutoFitCancelled` instead of completing.

    The GUI worker catches this and converts it to a clean
    ``cancelled`` signal — without it, hitting Stop would either
    do nothing (synchronous loop) or surface a misleading error.
    """
    cancel_after_calls = [0]

    def _flag() -> bool:
        cancel_after_calls[0] += 1
        # Cancel on the second poll so at least one model was visited
        # — proves the loop is actually polling, not just checking
        # before any work.
        return cancel_after_calls[0] >= 2

    with pytest.raises(AutoFitCancelled):
        auto_fit_dataset(**_fit_kwargs(should_cancel=_flag))


def test_should_cancel_default_None_does_not_raise() -> None:
    """The ``should_cancel`` parameter is optional. Existing callers
    that didn't pass it must keep working unchanged."""
    summary = auto_fit_dataset(**_fit_kwargs())
    # Sanity: at least one built-in fit succeeded.
    assert any(r.success for r in summary.results)


def test_should_cancel_returning_False_completes_normally() -> None:
    """Cancellation is opt-in. A callback that always returns False
    must not affect the fit outcome — it just means "don't cancel"."""
    summary = auto_fit_dataset(**_fit_kwargs(should_cancel=lambda: False))
    assert summary.best_model is not None


# ---------------------------------------------------------------- timeout API

def test_per_model_timeout_None_means_unbounded() -> None:
    """``None`` keeps the historical behaviour for CLI / batch
    callers that want the fit to run however long it takes."""
    summary = auto_fit_dataset(**_fit_kwargs(per_model_timeout_seconds=None))
    assert summary.best_model is not None


def test_per_model_timeout_zero_means_unbounded() -> None:
    """Defensive: a zero or negative cap is treated as "no cap" rather
    than "fail every model immediately" — the latter would silently
    break users who pass 0 thinking it disables the feature."""
    summary = auto_fit_dataset(**_fit_kwargs(per_model_timeout_seconds=0))
    assert summary.best_model is not None


def _make_sleeping_custom(label: str, sleep_seconds: float):
    """Return a (label, spec, state) custom-entry whose model evaluation
    deliberately sleeps. The slow path is forced by the model itself,
    not by hoping the timeout cap is small enough — that would make the
    test flaky on fast hardware.
    """
    from fitting.constraints import build_parameter_state
    from fitting.model_parser import build_model_specification

    spec = build_model_specification("a + b*x", ["x"], ["a", "b"])
    state = build_parameter_state(
        {"a": {"initial": 0.0}, "b": {"initial": 1.0}}, ["a", "b"]
    )

    # Patch ``spec.evaluate`` so each call sleeps before delegating.
    # The fitter calls evaluate / partial repeatedly inside Newton
    # iterations, so even a 0.5 s sleep guarantees we exceed the
    # 0.05 s cap below regardless of host speed.
    def slow_evaluate(*args, **kwargs):
        time.sleep(sleep_seconds)
        raise SystemExit("runaway model should have timed out before completion")

    spec.evaluate = slow_evaluate  # type: ignore[assignment]
    return (label, spec, state)


def _wait_for_sleeping_timeout_thread() -> None:
    """Let the timed-out test daemon finish before the next Qt/thread test."""

    time.sleep(0.6)


def test_per_model_timeout_is_not_an_in_process_kill_boundary() -> None:
    """The in-process auto-fit API no longer creates timeout threads.

    Passing a positive cap remains signature-compatible, but hard
    cancellation is owned by process-isolated desktop workers.
    """
    summary = auto_fit_dataset(**_fit_kwargs(per_model_timeout_seconds=0.05))
    assert any(r.success for r in summary.results)


def test_run_with_timeout_returns_completed_result_even_after_advisory_boundary() -> None:
    def slow_value() -> str:
        time.sleep(0.1)
        return "finished"

    assert _run_with_timeout(slow_value, 0.01, "Slow", target_dps=80) == "finished"


def test_timeout_wrapper_does_not_corrupt_parent_mp_dps() -> None:
    """The compatibility wrapper must not leak precision changes."""
    parent_dps_target = 50
    mp.dps = parent_dps_target
    _run_with_timeout(lambda: None, 0.01, "noop", target_dps=80)
    assert mp.dps == parent_dps_target, (
        f"mp.dps was corrupted: expected {parent_dps_target}, got {mp.dps}"
    )


def test_timeout_wrapper_does_not_spawn_thread_that_corrupts_later_precision_guard() -> None:
    mp.dps = 15

    def slow_guarded() -> None:
        with precision_guard(80):
            time.sleep(0.2)

    _run_with_timeout(slow_guarded, 0.05, "guarded", target_dps=80)

    with precision_guard(30):
        assert mp.dps == 30
        time.sleep(0.3)
        assert mp.dps == 30
