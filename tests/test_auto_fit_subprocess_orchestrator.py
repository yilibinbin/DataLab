"""TDD pins for the subprocess-based auto-fit orchestrator (B+C).

Background
----------

PR #26 added `should_cancel` and `per_model_timeout_seconds` to
`auto_fit_dataset`, but stop semantics still required waiting up
to 15 s for the current mpmath model to finish (mpmath holds the
GIL through `mp.findroot` Newton iterations — there's no safe way
to interrupt mid-solve in-process).

This module implements the user-facing requirement: "I clicked Stop;
the GUI must respond immediately and the CPU must be released."

Approach (option B+C from review):
  - Each model fit runs in its own `multiprocessing.Process` (true
    OS-level isolation, including separate `mp.dps` state).
  - Main process polls `should_cancel` while waiting on the child;
    on cancel it calls `proc.kill()` (SIGKILL) — true immediate
    termination, not a daemon-thread "abandon".
  - Progress is reported via a callback so the GUI can show
    "(3/19) Fitting Padé(1|1)..." between models.

Why subprocess and not just threads?
  - `daemon=True` threads keep eating CPU until they finish on
    their own. After Stop, a user immediately re-running auto-fit
    would compete with the zombie thread — the user reported this
    feels like a "fake stop".
  - `Process.kill()` is real and immediate. CPU is freed within ms.
  - As a bonus: `mp.dps` is process-global, but each subprocess has
    its own — so the precision-leak HIGH from PR #26 stops being a
    concern entirely (it's structurally impossible).

Trade-off: ~100-200 ms subprocess startup overhead per model on
macOS (must use `spawn` not `fork` because PySide6's parent process
isn't fork-safe). On a 19-model auto-fit that's ~2 s extra; on
slow ill-conditioned data that's <5 % overhead.
"""
from __future__ import annotations

import time
from typing import Any

import pytest
from mpmath import mp


# ---------------------------------------------------------------- imports
# (These will fail at import-time until the module exists — that's
# the RED state. Each test then provides finer-grained RED messages.)
def _import_orchestrator() -> Any:
    from app_desktop.auto_fit_subprocess import (
        SubprocessAutoFitOrchestrator,
        ModelTask,
        ProgressEvent,
    )
    return SubprocessAutoFitOrchestrator, ModelTask, ProgressEvent


# ---------------------------------------------------------------- helpers

def _linear_data() -> dict[str, list]:
    """Tiny linear dataset used by the happy-path tests."""
    return {
        "xs": [mp.mpf(i) for i in range(1, 11)],
        "ys": [mp.mpf(2 * i + 3) for i in range(1, 11)],
        "sigmas": [None] * 10,
    }


def _make_builtin_task(identifier: str, label: str | None = None) -> Any:
    """Build a serializable ModelTask for one of the built-in
    AUTO_MODELS by identifier."""
    _, ModelTask, _ = _import_orchestrator()
    return ModelTask(
        kind="auto_builtin",
        identifier=identifier,
        label=label or identifier,
        params={"identifier": identifier},
    )


def _make_custom_task(label: str, expression: str, params: dict) -> Any:
    """Build a serializable custom-model ModelTask. ``params`` is the
    parameter-state dict passed to ``build_parameter_state``."""
    _, ModelTask, _ = _import_orchestrator()
    return ModelTask(
        kind="custom",
        identifier="CUSTOM",
        label=label,
        params={
            "expression": expression,
            "variable_names": ["x"],
            "parameter_state": params,
        },
    )


# ---------------------------------------------------------------- happy path

def test_orchestrator_runs_simple_linear_fit_in_subprocess() -> None:
    """A single linear model task completes via the subprocess
    pipeline and returns a usable ``AutoModelResult``-like dict.

    This is the must-work baseline: if subprocess IPC is broken,
    every other test fails with the same misleading symptom, so
    catch the breakage here first.
    """
    Orchestrator, _, _ = _import_orchestrator()
    data = _linear_data()
    summary = Orchestrator(precision=50).run(
        tasks=[_make_builtin_task("M1", "Linear")],
        x_data=data["xs"],
        y_data=data["ys"],
        sigma_data=data["sigmas"],
    )
    assert len(summary.results) == 1
    result = summary.results[0]
    assert result.success, f"Expected success, got error: {result.error!r}"
    assert result.fit_result is not None
    # Linear fit y = 2x + 3 → b1 ≈ 2, b0 ≈ 3.
    fitted_b0 = float(result.fit_result.params["b0"])
    fitted_b1 = float(result.fit_result.params["b1"])
    assert abs(fitted_b1 - 2.0) < 1e-6, f"b1={fitted_b1}"
    assert abs(fitted_b0 - 3.0) < 1e-6, f"b0={fitted_b0}"


def test_orchestrator_runs_multiple_models_independently() -> None:
    """Multiple tasks each get their own subprocess; results come
    back in the same order and don't interfere with each other."""
    Orchestrator, _, _ = _import_orchestrator()
    data = _linear_data()
    tasks = [
        _make_builtin_task("M1", "Linear"),
        _make_builtin_task("M2", "Quadratic"),
        _make_builtin_task("M3", "Cubic"),
    ]
    summary = Orchestrator(precision=50).run(
        tasks=tasks,
        x_data=data["xs"],
        y_data=data["ys"],
        sigma_data=data["sigmas"],
    )
    assert len(summary.results) == 3
    # All three should fit a clean linear dataset successfully.
    assert all(r.success for r in summary.results), \
        [r.error for r in summary.results if not r.success]
    # Order preserved.
    assert [r.identifier for r in summary.results] == ["M1", "M2", "M3"]


# ---------------------------------------------------------------- progress

def test_orchestrator_emits_progress_events_per_model() -> None:
    """The orchestrator calls ``progress_callback`` with a
    ``ProgressEvent`` describing each model start + completion so
    the GUI status bar can show "(3/19) Fitting Padé(1|1)…".

    The exact event structure is part of the contract: ``index``,
    ``total``, ``label``, and ``status`` ("started" | "ok" |
    "timeout" | "error" | "cancelled").
    """
    Orchestrator, _, ProgressEvent = _import_orchestrator()
    events: list[Any] = []
    data = _linear_data()
    tasks = [
        _make_builtin_task("M1", "Linear"),
        _make_builtin_task("M2", "Quadratic"),
    ]
    Orchestrator(precision=50).run(
        tasks=tasks,
        x_data=data["xs"],
        y_data=data["ys"],
        sigma_data=data["sigmas"],
        progress_callback=events.append,
    )
    # At minimum: 1 "started" + 1 "ok" per model = 4 events for 2 tasks.
    assert len(events) >= 4
    # First event is for the first model, in "started" state.
    assert events[0].index == 0
    assert events[0].total == 2
    assert events[0].label == "Linear"
    assert events[0].status == "started"
    # Final event is the second model finishing successfully.
    assert events[-1].index == 1
    assert events[-1].status == "ok"


# ---------------------------------------------------------------- cancellation

def test_orchestrator_kills_subprocess_immediately_on_cancel() -> None:
    """When ``should_cancel`` returns True, the running subprocess
    is killed via ``Process.kill()`` and the orchestrator returns
    promptly — NOT after the model would have finished on its own.

    "Promptly" here means within the polling-interval bound (we
    document 100 ms in the orchestrator). We assert ≤2 s as a very
    generous bound to avoid flake on slow CI.
    """
    Orchestrator, _, _ = _import_orchestrator()
    data = _linear_data()

    # A custom model with a deliberately slow-evaluating expression.
    # The trick: the orchestrator can't peek inside the subprocess'
    # mpmath calls, so we use a model whose Newton iterations need
    # many evaluations and the dataset gives a hard-to-find root.
    # In practice we just need the subprocess to not finish in 2s.
    slow_task = _make_custom_task(
        "Pathological",
        "A*x**(-p) + C",
        {
            "A": {"initial": 1.0},
            "p": {"initial": 1.0, "min": 0.1},
            "C": {"initial": 0.0},
        },
    )
    # Provide ill-conditioned data (σ ≈ 1e-19 makes χ² landscape
    # nasty so the LM solver thrashes).
    xs_mp = [mp.mpf(i) for i in range(2, 11)]
    ys_mp = [mp.mpf(f"-{1e-4 / i**2}") for i in range(2, 11)]
    sigmas_mp = [mp.mpf("1e-19")] * 9

    cancel_after = time.monotonic() + 0.5
    def _flag() -> bool:
        return time.monotonic() >= cancel_after

    t0 = time.monotonic()
    summary = Orchestrator(precision=80).run(
        tasks=[slow_task],
        x_data=xs_mp,
        y_data=ys_mp,
        sigma_data=sigmas_mp,
        should_cancel=_flag,
    )
    elapsed = time.monotonic() - t0

    # Must respond to cancel within 2 s of the flag flipping at
    # 0.5 s — total wall budget 2.5 s (generous for slow CI).
    assert elapsed < 2.5, (
        f"Cancel did not stop the orchestrator quickly: {elapsed:.2f}s"
    )
    # The cancelled run records a single "cancelled" result, not a
    # success or a normal timeout.
    assert len(summary.results) == 1
    result = summary.results[0]
    assert not result.success
    assert result.error is not None
    assert "cancel" in result.error.lower() or "取消" in result.error


def test_cancel_event_emitted_on_progress_callback() -> None:
    """When cancellation occurs, the progress callback receives a
    final event with status ``cancelled`` so the GUI can update its
    status bar uniformly with the success / timeout paths."""
    Orchestrator, _, _ = _import_orchestrator()
    data = _linear_data()
    events: list[Any] = []

    # Cancel immediately so we don't wait for any model to finish.
    Orchestrator(precision=50).run(
        tasks=[_make_builtin_task("M1", "Linear")],
        x_data=data["xs"],
        y_data=data["ys"],
        sigma_data=data["sigmas"],
        should_cancel=lambda: True,
        progress_callback=events.append,
    )
    # At least one event with status "cancelled" must have fired.
    assert any(e.status == "cancelled" for e in events), (
        f"No cancelled event emitted; got: {[e.status for e in events]}"
    )


# ---------------------------------------------------------------- timeout

def test_orchestrator_kills_subprocess_after_per_model_timeout() -> None:
    """A model that exceeds ``per_model_timeout_seconds`` is killed
    via ``Process.kill()`` and recorded as a timeout failure. Other
    models still run."""
    Orchestrator, _, _ = _import_orchestrator()
    data = _linear_data()

    # Pathological custom + a fast linear fallback.
    slow = _make_custom_task(
        "Slow",
        "A*x**(-p) + C",
        {
            "A": {"initial": 1.0},
            "p": {"initial": 1.0, "min": 0.1},
            "C": {"initial": 0.0},
        },
    )
    fast = _make_builtin_task("M1", "Linear")
    xs_mp = [mp.mpf(i) for i in range(2, 11)]
    ys_mp = [mp.mpf(f"-{1e-4 / i**2}") for i in range(2, 11)]
    sigmas_mp = [mp.mpf("1e-19")] * 9

    # Cap chosen well above subprocess startup latency (~150 ms on
    # macOS with spawn) but well below the 30+ s the pathological fit
    # would otherwise need. 1.5 s leaves room for variation when the
    # full test suite runs concurrently.
    summary = Orchestrator(
        precision=80,
        per_model_timeout_seconds=1.5,
    ).run(
        tasks=[slow, fast],
        x_data=xs_mp,
        y_data=ys_mp,
        sigma_data=sigmas_mp,
    )
    assert len(summary.results) == 2
    # First (slow) should be a timeout failure.
    slow_r = summary.results[0]
    assert not slow_r.success
    assert slow_r.error and (
        "超过" in slow_r.error or "exceeded" in slow_r.error
        or "timeout" in slow_r.error.lower()
    )
    # Second (fast) should still complete — proves the loop
    # continues after timeout.
    fast_r = summary.results[1]
    assert fast_r.success, f"Fast fit shouldn't fail: {fast_r.error}"


# ---------------------------------------------------------------- isolation

def test_subprocess_failure_does_not_corrupt_main_process_mp_dps() -> None:
    """The whole point of the subprocess approach: even if a model
    crashes hard inside its child process, the parent's ``mp.dps``
    is untouched (process boundary).

    This is a structural invariant — the test passes by construction
    once the subprocess pipeline works at all. It still has value as
    a regression guard: any future "optimization" that brings the
    fits back into the main process must update this test, which
    forces the engineer to think about the trade-off.
    """
    Orchestrator, _, _ = _import_orchestrator()
    parent_dps_target = 50
    mp.dps = parent_dps_target
    data = _linear_data()

    # Run a fit at a different dps in the subprocess.
    Orchestrator(precision=120).run(
        tasks=[_make_builtin_task("M1", "Linear")],
        x_data=data["xs"],
        y_data=data["ys"],
        sigma_data=data["sigmas"],
    )
    # Parent dps unchanged.
    assert mp.dps == parent_dps_target
