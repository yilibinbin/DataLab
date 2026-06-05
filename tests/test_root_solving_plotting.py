from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from mpmath import mp

from root_solving.batch import solve_root_batch
from root_solving.models import RootBatchResult, RootBatchRowResult, RootMode, RootProblem, RootResult, RootUnknown, RootValue
from root_solving.plotting import (
    RootPlotBudget,
    ROOT_PLOT_FAILED_WARNING,
    render_nominal_root_plot,
    render_nominal_root_plots,
    select_root_plot_requests,
    stable_select_mc_samples,
)
from shared.input_normalization import normalize_constants_state
from shared.uncertainty import parse_uncertainty_format


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


def test_render_nominal_scalar_root_plot_includes_curve_zero_line_and_root_marker() -> None:
    problem = RootProblem(
        equations=("x^2 - A",),
        unknowns=(RootUnknown("x", initial="1", lower="0", upper="4"),),
        row_values={"A": "4"},
        mode="scalar",
        precision=30,
    )
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={"A": "4"},
                result=RootResult(
                    roots=(RootValue(name="x", value=mp.mpf("2")),),
                    backend="mpmath",
                    mode="scalar",
                ),
            ),
        )
    )
    request = select_root_plot_requests(batch, budget=RootPlotBudget(max_grid_points=37)).requests[0]

    image = render_nominal_root_plot(request, problem)

    assert image is not None
    assert image.image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    assert image.row_index == 0
    assert image.metadata["curve"] == "nominal"
    assert image.metadata["equation"] == "x^2 - A"
    assert image.metadata["unknown"] == "x"
    assert image.metadata["grid_points"] == 37
    assert image.metadata["grid_points"] <= 300
    assert image.metadata["zero_line"] is True
    assert image.metadata["root_markers"] == ({"name": "x", "value": 2.0},)


def test_render_nominal_scalar_root_plot_uses_deterministic_bounded_grid() -> None:
    problem = RootProblem(
        equations=("x^2 - A",),
        unknowns=(RootUnknown("x", initial="1", lower="-10", upper="10"),),
        row_values={"A": "9"},
        mode="scalar",
        precision=30,
    )
    batch = RootBatchResult(rows=(_row(3),))
    request = select_root_plot_requests(batch, budget=RootPlotBudget(max_grid_points=1000)).requests[0]

    first = render_nominal_root_plot(request, problem)
    second = render_nominal_root_plot(request, problem)

    assert first is not None
    assert second is not None
    assert first.metadata["grid_points"] == 300
    assert first.metadata["x_range"] == second.metadata["x_range"]
    assert first.metadata["y_values"] == second.metadata["y_values"]


def test_render_nominal_scan_root_plot_uses_same_safe_expression_path() -> None:
    problem = RootProblem(
        equations=("x^2 - A",),
        unknowns=(RootUnknown("x", lower="-3", upper="3"),),
        row_values={"A": "1"},
        mode="scan_multiple",
        precision=30,
    )
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=4,
                source_values={"A": "1"},
                result=RootResult(
                    roots=(RootValue(name="x", value=mp.mpf("-1")), RootValue(name="x", value=mp.mpf("1"))),
                    backend="mpmath",
                    mode="scan_multiple",
                ),
            ),
        )
    )
    request = select_root_plot_requests(batch, budget=RootPlotBudget(max_grid_points=41)).requests[0]

    image = render_nominal_root_plot(request, problem)

    assert image is not None
    assert image.metadata["curve"] == "nominal"
    assert image.metadata["grid_points"] == 41
    assert image.metadata["root_markers"] == ({"name": "x", "value": -1.0}, {"name": "x", "value": 1.0})


def test_render_taylor_root_plot_includes_function_band_and_root_interval() -> None:
    problem = RootProblem(
        equations=("x^2 - A",),
        unknowns=(RootUnknown("x", initial="2", lower="1", upper="3"),),
        row_values={"A": "4.0(2)"},
        mode="scalar",
        precision=50,
    )
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={"A": "4.0(2)"},
                result=RootResult(
                    roots=(
                        RootValue(
                            name="x",
                            value=mp.mpf("2"),
                            uncertainty=mp.mpf("0.05"),
                            contributions={"A": mp.mpf("0.05")},
                        ),
                    ),
                    backend="mpmath",
                    mode="scalar",
                    details={"uncertainty_method": "taylor", "taylor_order": 1},
                ),
            ),
        )
    )
    request = select_root_plot_requests(batch, budget=RootPlotBudget(max_grid_points=9)).requests[0]

    image = render_nominal_root_plot(request, problem)

    assert image is not None
    visualization = cast(Mapping[str, object], image.metadata["uncertainty_visualization"])
    function_band = cast(Mapping[str, object], visualization["function_band"])
    assert visualization["method"] == "taylor"
    assert function_band["kind"] == "first_order"
    assert function_band["active_inputs"] == ("A",)
    assert len(cast(tuple[float | None, ...], function_band["lower_y_values"])) == 9
    assert len(cast(tuple[float | None, ...], function_band["upper_y_values"])) == 9
    assert visualization["root_intervals"] == ({"name": "x", "lower": 1.95, "upper": 2.05},)
    assert visualization["notes"] == ()


def test_render_taylor_root_plot_records_no_band_note_when_skipped() -> None:
    problem = RootProblem(
        equations=("x^2 - A",),
        unknowns=(RootUnknown("x", initial="2", lower="1", upper="3"),),
        row_values={"A": "4.0(2)"},
        mode="scalar",
        precision=50,
    )
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={"A": "4.0(2)"},
                result=RootResult(
                    roots=(RootValue(name="x", value=mp.mpf("2")),),
                    backend="mpmath",
                    mode="scalar",
                    details={"uncertainty_method": "skipped", "uncertainty_requested_method": "taylor"},
                ),
            ),
        )
    )
    request = select_root_plot_requests(batch, budget=RootPlotBudget(max_grid_points=9)).requests[0]

    image = render_nominal_root_plot(request, problem)

    assert image is not None
    visualization = cast(Mapping[str, object], image.metadata["uncertainty_visualization"])
    assert visualization["method"] == "skipped"
    assert visualization["function_band"] is None
    assert visualization["root_intervals"] == ()
    assert visualization["notes"] == ("uncertainty band unavailable: skipped",)


def test_render_monte_carlo_root_plot_downsamples_distribution_to_budget() -> None:
    problem = RootProblem(
        equations=("x^2 - A",),
        unknowns=(RootUnknown("x", initial="2", lower="1", upper="3"),),
        row_values={"A": "4.0(2)"},
        mode="scalar",
        precision=50,
    )
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={"A": "4.0(2)"},
                result=RootResult(
                    roots=(RootValue(name="x", value=mp.mpf("2"), uncertainty=mp.mpf("0.05")),),
                    backend="mpmath",
                    mode="scalar",
                    details={
                        "uncertainty_method": "monte_carlo",
                        "monte_carlo_samples": 250,
                        "monte_carlo_valid_samples": 230,
                        "monte_carlo_failures": 20,
                    },
                ),
            ),
        )
    )
    request = select_root_plot_requests(batch, budget=RootPlotBudget(max_grid_points=11, max_mc_curves=7)).requests[0]

    first = render_nominal_root_plot(request, problem)
    second = render_nominal_root_plot(request, problem)

    assert first is not None
    assert second is not None
    visualization = cast(Mapping[str, object], first.metadata["uncertainty_visualization"])
    second_visualization = cast(Mapping[str, object], second.metadata["uncertainty_visualization"])
    assert visualization["method"] == "monte_carlo"
    assert visualization["mc_curve_count"] == 7
    assert visualization["mc_input_sample_count"] == 7
    assert visualization["mc_sampled_inputs"] == ("A",)
    mc_envelope = cast(Mapping[str, object], visualization["mc_envelope"])
    assert mc_envelope["kind"] == "deterministic_input_samples"
    assert len(cast(tuple[Mapping[str, object], ...], visualization["mc_root_markers"])) == 7
    assert visualization["mc_root_markers"] == second_visualization["mc_root_markers"]
    assert visualization["budget_notes"] == ("Monte Carlo visualization downsampled 230 valid samples to 7 curves.",)
    assert visualization["detail_notes"] == (
        "Monte Carlo requested samples: 250.",
        "Monte Carlo valid samples: 230.",
        "Monte Carlo failed samples: 20.",
    )


def test_render_uncertainty_plot_uses_batch_payload_when_source_values_are_nominal() -> None:
    constants_state = normalize_constants_state(enabled=False, rows=[], numeric_mode="uncertainty")
    batch = solve_root_batch(
        equations=("x**2 - A",),
        unknowns=(RootUnknown("x", initial="2", lower="1", upper="3"),),
        data_headers=("A",),
        data_rows=((parse_uncertainty_format("4.0(2)"),),),
        constants_state=constants_state,
        mode="scalar",
        precision=50,
        uncertainty_options={"method": "taylor", "taylor_order": 1},
    )
    row = batch.rows[0]
    assert row.source_values == {"A": "4.0"}
    assert row.result is not None
    plot_uncertain_inputs = cast(Mapping[str, Mapping[str, str]], row.result.details["plot_uncertain_inputs"])
    assert plot_uncertain_inputs["A"]["value"] == "4.0"
    assert mp.almosteq(mp.mpf(plot_uncertain_inputs["A"]["uncertainty"]), mp.mpf("0.2"))
    problem = RootProblem(
        equations=("x**2 - A",),
        unknowns=(RootUnknown("x", initial="2", lower="1", upper="3"),),
        row_values=row.source_values,
        mode="scalar",
        precision=50,
    )
    request = select_root_plot_requests(batch, budget=RootPlotBudget(max_grid_points=9)).requests[0]

    image = render_nominal_root_plot(request, problem)

    assert image is not None
    visualization = cast(Mapping[str, object], image.metadata["uncertainty_visualization"])
    assert visualization["method"] == "taylor"
    function_band = cast(Mapping[str, object], visualization["function_band"])
    assert function_band["active_inputs"] == ("A",)
    assert visualization["notes"] == ()


def test_render_nominal_root_plots_returns_images_and_failure_warnings() -> None:
    problem = RootProblem(
        equations=("bad_func(x)",),
        unknowns=(RootUnknown("x", initial="1"),),
        row_values={"A": "4"},
        mode="scalar",
        precision=30,
    )
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={"A": "4"},
                result=RootResult(
                    roots=(RootValue(name="x", value=mp.mpf("2")),),
                    backend="mpmath",
                    mode="scalar",
                ),
            ),
        )
    )

    selection = render_nominal_root_plots(batch, problem)

    assert selection.requests
    assert selection.images == ()
    assert selection.warnings
    assert selection.warnings[0].startswith(ROOT_PLOT_FAILED_WARNING)


def test_render_nominal_root_plot_keeps_system_roots_as_no_image() -> None:
    problem = RootProblem(
        equations=("x + y - 1", "x - y"),
        unknowns=(RootUnknown("x", initial="1"), RootUnknown("y", initial="1")),
        mode="system",
    )
    batch = RootBatchResult(rows=(_row(0, mode="system"),))
    selection = select_root_plot_requests(batch)

    assert selection.requests == ()
    assert selection.warnings == ("System root plots are not supported.",)
    assert render_nominal_root_plot(None, problem) is None
