from __future__ import annotations

from mpmath import mp

from root_solving.models import RootBatchResult, RootBatchRowResult, RootMode, RootResult, RootValue
from root_solving.plotting import (
    RootPlotBudget,
    select_root_plot_requests,
    stable_select_mc_samples,
)


def _row(row_index: int, *, mode: RootMode = "scalar", failure: str | None = None) -> RootBatchRowResult:
    result = None
    if failure is None:
        result = RootResult(
            roots=(RootValue(name="x", value=mp.mpf(row_index)),),
            backend="mpmath",
            mode=mode,
        )
    return RootBatchRowResult(
        row_index=row_index,
        source_values={"A": str(row_index)},
        result=result,
        failure=failure,
    )


def test_root_plot_budget_defaults_are_bounded() -> None:
    budget = RootPlotBudget()

    assert budget.max_grid_points == 300
    assert budget.max_mc_curves == 100
    assert budget.max_batch_rows == 25
    assert budget.max_images_per_run == 25


def test_select_root_plot_requests_preserves_input_row_order_and_budget() -> None:
    batch = RootBatchResult(
        rows=(
            _row(7),
            _row(2, failure="failed"),
            _row(3),
            _row(1),
            _row(9),
        )
    )

    selected = select_root_plot_requests(batch, budget=RootPlotBudget(max_batch_rows=2))

    assert [request.row.row_index for request in selected.requests] == [7, 3]
    assert selected.warnings == ()


def test_select_root_plot_requests_warns_and_skips_system_roots() -> None:
    batch = RootBatchResult(rows=(_row(0, mode="system"), _row(1, mode="scalar")))

    selected = select_root_plot_requests(batch)

    assert [request.row.row_index for request in selected.requests] == [1]
    assert selected.images == ()
    assert selected.warnings == ("System root plots are not supported.",)


def test_select_root_plot_requests_returns_no_images_for_unsupported_only() -> None:
    batch = RootBatchResult(rows=(_row(0, mode="system"), _row(1, failure="failed")))

    selected = select_root_plot_requests(batch)

    assert selected.requests == ()
    assert selected.images == ()
    assert selected.warnings == ("System root plots are not supported.",)


def test_stable_select_mc_samples_downsamples_without_randomness() -> None:
    samples = tuple(range(250))

    selected = stable_select_mc_samples(samples, max_samples=100)

    assert len(selected) == 100
    assert selected[0] == 0
    assert selected[-1] == 249
    assert selected == stable_select_mc_samples(samples, max_samples=100)
