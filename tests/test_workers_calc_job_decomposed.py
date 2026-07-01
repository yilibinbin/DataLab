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
    for handler in ("_execute_extrapolation_mode", "_execute_error_mode", "_execute_statistics_mode"):
        assert f"def {handler}(" in source, f"missing per-mode handler {handler}"
        assert f"{handler}(applied_precision)" in source, f"{handler} is defined but never dispatched"


def test_mode_dispatch_is_a_thin_branch():
    # The top-level dispatch must be a small if/elif over job.mode calling the
    # handlers — not the old inlined logic. Assert each mode branch's body is a
    # single call to its handler (real extraction), so the dispatch can't quietly
    # re-inline the logic while keeping the handler defs around.
    import app_desktop.workers_core as workers_core

    source = inspect.getsource(workers_core._execute_calc_job).splitlines()

    def _branch_body(header_substr: str) -> list[str]:
        for i, line in enumerate(source):
            if header_substr in line:
                body = []
                header_indent = len(line) - len(line.lstrip())
                for follow in source[i + 1:]:
                    if not follow.strip():
                        continue
                    if len(follow) - len(follow.lstrip()) <= header_indent:
                        break
                    body.append(follow.strip())
                return body
        raise AssertionError(f"branch not found: {header_substr}")

    assert _branch_body('if job.mode == "extrapolation":') == ["_execute_extrapolation_mode(applied_precision)"]
    assert _branch_body('elif job.mode == "error":') == ["_execute_error_mode(applied_precision)"]
    assert _branch_body('elif job.mode == "statistics":') == ["_execute_statistics_mode(applied_precision)"]
    assert "Unsupported mode for async calculation" in "\n".join(source)
