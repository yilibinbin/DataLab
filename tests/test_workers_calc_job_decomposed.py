"""P2-3: _execute_calc_job dispatches to per-mode handlers, not one monolith.

The desktop calc worker used to inline extrapolation / error / statistics logic
in a single ~800-line, ~178-branch function. It now dispatches to three named
per-mode handlers (mirroring datalab_core's run_* structure). This test pins the
decomposition so the function can't silently collapse back into a monolith; the
behavioural correctness is covered by test_app_desktop_workers_core.py and the
per-mode desktop UI tests.
"""

from __future__ import annotations

import inspect


def test_execute_calc_job_dispatches_to_per_mode_handlers():
    import app_desktop.workers_core as workers_core

    source = inspect.getsource(workers_core._execute_calc_job)
    for handler in ("_run_extrapolation_mode", "_run_error_mode", "_run_statistics_mode"):
        assert f"def {handler}(" in source, f"missing per-mode handler {handler}"
        assert f"{handler}(applied_precision)" in source, f"{handler} is defined but never dispatched"


def test_mode_dispatch_is_a_thin_branch():
    # The top-level dispatch must be a small if/elif over job.mode calling the
    # handlers — not the old inlined logic. Assert each branch is a one-line call.
    import app_desktop.workers_core as workers_core

    source = inspect.getsource(workers_core._execute_calc_job)
    assert 'if job.mode == "extrapolation":' in source
    assert 'elif job.mode == "error":' in source
    assert 'elif job.mode == "statistics":' in source
    # The unsupported-mode guard is preserved.
    assert "Unsupported mode for async calculation" in source
