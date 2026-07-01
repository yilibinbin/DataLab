"""Fitting-comparison cancellation (PR #70 swarm-review finding B1).

The desktop FittingComparisonWorker's Stop must actually interrupt a running
multi-candidate comparison, not merely set a flag that the candidate loop never
checks. run_fitting_comparison calls check_cancelled() before each candidate, so
wrapping the call in external_cancellation_scope(should_cancel) makes Stop break
the loop between candidates.
"""

from __future__ import annotations

import pytest

from datalab_core.session import CoreJobCancelled, external_cancellation_scope


def _comparison_request():
    from datalab_core.fitting_comparison import build_fitting_comparison_request

    # Two trivial polynomial candidates over a tiny dataset — fast to fit; we
    # only care that the loop honors cancellation between candidates.
    return build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "3"), ("2", "5"), ("3", "7")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
            {"candidate_id": "quadratic", "label": "Quadratic", "model_type": "polynomial", "poly_degree": 2},
        ),
        precision_digits=20,
    )


def test_comparison_runs_to_completion_without_cancellation():
    from datalab_core.fitting_comparison import run_fitting_comparison

    envelope = run_fitting_comparison(_comparison_request())
    from datalab_core.results import ResultStatus

    assert envelope.status is ResultStatus.SUCCEEDED
    assert envelope.payload["candidate_count"] == 2


def test_comparison_honors_cancellation_before_first_candidate():
    from datalab_core.fitting_comparison import run_fitting_comparison

    # A checker that is already cancelled: the loop must raise before fitting.
    with external_cancellation_scope(lambda: True):
        with pytest.raises(CoreJobCancelled):
            run_fitting_comparison(_comparison_request())


def test_comparison_cancels_between_candidates():
    from datalab_core.fitting_comparison import run_fitting_comparison

    calls = {"n": 0}

    def _cancel_after_first() -> bool:
        # Not cancelled for the first candidate's check, cancelled for the next.
        calls["n"] += 1
        return calls["n"] > 1

    with external_cancellation_scope(_cancel_after_first):
        with pytest.raises(CoreJobCancelled):
            run_fitting_comparison(_comparison_request())

    # The loop checked cancellation more than once (i.e. it did not run to the
    # end ignoring the flag) and stopped once the checker flipped.
    assert calls["n"] >= 2


def test_external_scope_none_leaves_cancellation_untouched():
    from datalab_core.session import cancellation_requested

    # A None checker must be a no-op (does not spuriously mark cancellation).
    with external_cancellation_scope(None):
        assert cancellation_requested() is False
