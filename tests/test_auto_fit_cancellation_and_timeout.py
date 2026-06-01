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
  2. ``per_model_timeout_seconds`` — wall-clock cap per model. Models
     that exceed the cap are recorded as failures ("model timed out")
     so the loop continues and the user sees a meaningful summary
     instead of an apparent freeze.

This test file pins both behaviours.
"""
from __future__ import annotations

import time

import pytest
from mpmath import mp

from fitting.auto_models import build_polynomial_definition
from fitting.model_selector import (
    AutoFitCancelled,
    auto_fit_dataset,
)


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


def test_per_model_timeout_aborts_runaway_model() -> None:
    """A model whose fit exceeds the cap is recorded as a failure
    with a bilingual "model timed out" error, and the loop continues
    so other models still run.

    We force the custom-fit slow path with a sleeping model evaluator
    so the test result is deterministic regardless of host speed (a
    sub-millisecond cap was previously flaky on fast machines where
    a real ``a + b*x`` fit can complete inside 1 ms).
    """
    summary = auto_fit_dataset(
        **_fit_kwargs(
            custom_entries=[_make_sleeping_custom("Slow Custom", 0.5)],
            # 50 ms cap — well below the 0.5 s sleep injected per
            # evaluation, so the custom fit must time out, but well
            # above the legitimate built-in fits' real time so they
            # are not falsely reported as failures.
            per_model_timeout_seconds=0.05,
        ),
    )
    _wait_for_sleeping_timeout_thread()
    assert isinstance(summary.results, list)
    custom_results = [r for r in summary.results if r.label == "Slow Custom"]
    assert len(custom_results) == 1
    custom = custom_results[0]
    assert not custom.success
    assert custom.error and (
        "超过" in custom.error or "exceeded" in custom.error
    )

    # Other models (built-in fast paths) still ran successfully —
    # proves the loop did not abort on the timeout.
    assert any(r.success for r in summary.results)


def test_timeout_message_uses_user_friendly_label_not_internal_id() -> None:
    """The bilingual timeout message renders the user's chosen model
    label (``"My Fit"``), NOT the internal allocation ID
    (``"CUSTOM"``, ``"CUSTOM#2"``, …). The user typed the label;
    surfacing the ID confuses them."""
    summary = auto_fit_dataset(
        **_fit_kwargs(
            custom_entries=[_make_sleeping_custom("我的拟合 / My Fit", 0.5)],
            per_model_timeout_seconds=0.05,
        ),
    )
    _wait_for_sleeping_timeout_thread()
    custom = next(r for r in summary.results if r.label == "我的拟合 / My Fit")
    assert custom.error
    assert "我的拟合" in custom.error or "My Fit" in custom.error
    assert "'CUSTOM'" not in custom.error
    assert "'CUSTOM#" not in custom.error


def test_timeout_does_not_corrupt_parent_mp_dps() -> None:
    """After a model times out, ``mp.dps`` must equal what the parent
    set it to — NOT whatever value the runaway daemon thread was
    using inside its ``precision_guard``.

    Regression guard for the precision-leak HIGH found during code
    review: a daemon thread inside ``with precision_guard(target):``
    that gets abandoned will eventually call ``__exit__`` and reset
    ``mp.dps`` to the value it captured on entry — silently
    corrupting whatever the parent has done since.
    ``_run_with_timeout`` defends by re-asserting ``mp.dps`` at the
    parent's expected value after the join.
    """
    parent_dps_target = 50
    mp.dps = parent_dps_target
    auto_fit_dataset(
        **_fit_kwargs(
            custom_entries=[_make_sleeping_custom("Slow", 0.5)],
            per_model_timeout_seconds=0.05,
        ),
    )
    _wait_for_sleeping_timeout_thread()
    # After the auto_fit completes, the parent's dps must NOT have
    # been reset by the runaway thread.
    assert mp.dps == parent_dps_target, (
        f"mp.dps was corrupted: expected {parent_dps_target}, got {mp.dps}"
    )
