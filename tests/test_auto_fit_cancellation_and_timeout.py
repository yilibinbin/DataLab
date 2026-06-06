"""Pin the responsiveness controls retained by auto_fit_dataset.

Background: an end-user reported the desktop GUI's "Auto fit" command
freezing for several minutes on a 9-row dataset with σ ≈ 1e-19, and
the Stop button having no visible effect. Root cause was that

  - ``_execute_auto_fit_job`` runs ``auto_fit_dataset`` synchronously
    over ~16 candidate models with no inter-model cancellation point;
  - one model in particular (``A*x**(-p) + C`` non-linear LM at
    dps=80) needed >50 s on this ill-conditioned data because the
    Newton solver thrashed across 14 seed variants.

Responsiveness controls (see ``fitting/model_selector.py:auto_fit_dataset``):

  1. ``should_cancel`` — polled between models. When True, raises
     :class:`AutoFitCancelled` so the GUI worker can surface a clean
     cancellation (no error dialog).
  2. Positive ``per_model_timeout_seconds`` is rejected. It used to spawn
     per-model timeout threads, which is unsafe with process-global mpmath
     precision; hard cancellation belongs at the process-worker layer.

This test file pins both behaviours.
"""
from __future__ import annotations

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


def test_per_model_timeout_positive_is_rejected() -> None:
    with pytest.raises(ValueError, match="per-model|进程内"):
        auto_fit_dataset(**_fit_kwargs(per_model_timeout_seconds=0.05))
