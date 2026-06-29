from __future__ import annotations

import os
import pickle
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, cast
import warnings

import mpmath as mp
import pytest

from data_extrapolation_latex_latest import ExtrapolationOptions

import app_desktop.workers_core as workers_core
from app_desktop.workers_core import (
    CalcJob,
    FitBatchTask,
    FitJob,
    RootSolvingJob,
    _deserialize_root_solving_job,
    _execute_root_solving_job_payload,
    _execute_root_solving_job_payload_subprocess,
    _serialize_root_solving_job,
    _deserialize_fit_job,
    _execute_calc_job,
    _execute_fit_job_payload,
    _execute_fit_job_payload_subprocess,
    _fit_job_requires_process_boundary,
    _serialize_fit_job,
)
from app_desktop.workers_qt import FitBatchWorker
from app_desktop.workers_qt import RootSolvingWorker
from fitting.hp_fitter import FitResult
from fitting.implicit_model import ImplicitModelDefinition, ImplicitSolveOptions
from shared.parallel_config import ParallelConfig
from shared.parallel_backend import KillableProcessTaskRunner, current_parallel_depth
from shared.uncertainty import UncertainValue


def _valid_distribution_summary() -> dict[str, object]:
    return {
        "schema": "datalab.monte_carlo_distribution_summary",
        "schema_version": 1,
        "requested_sample_count": 100,
        "evaluated_sample_count": 100,
        "accepted_sample_count": 100,
        "rejected_sample_count": 0,
        "finite_sample_count": 100,
        "mean": "1.0",
        "std": "0.2",
        "histogram": {"bin_edges": ["0.0", "1.0", "2.0"], "counts": [50, 50]},
        "percentiles": {"2.5": "0.1", "50": "1.0", "97.5": "1.9"},
    }


def test_error_contribution_plot_uses_cjk_safe_shared_plotting() -> None:
    pytest.importorskip("matplotlib")
    from shared.plotting import cjk_font_properties, rcParams

    if cjk_font_properties() is None:
        pytest.skip("No CJK-capable Matplotlib font available in this environment.")

    summary = [
        {"name": "V2", "variance": mp.mpf("2"), "sigma": mp.sqrt(2), "percent": 50.51},
        {"name": "V1", "variance": mp.mpf("1.96"), "sigma": mp.sqrt(mp.mpf("1.96")), "percent": 49.49},
    ]

    previous_family = rcParams["font.family"]
    previous_sans = rcParams["font.sans-serif"]
    try:
        rcParams["font.family"] = ["DejaVu Sans"]
        rcParams["font.sans-serif"] = ["DejaVu Sans"]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            png = workers_core._render_contribution_plot(summary, "zh", title_suffix="row 1")
    finally:
        rcParams["font.family"] = previous_family
        rcParams["font.sans-serif"] = previous_sans

    missing_glyph_warnings = [
        str(item.message)
        for item in caught
        if "glyph" in str(item.message).lower() and "missing" in str(item.message).lower()
    ]
    assert png is not None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert missing_glyph_warnings == []


def test_core_contribution_plot_routes_shared_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    from shared import plotting

    captured: dict[str, Any] = {}

    def fake_render(spec: Any) -> bytes:
        captured["spec"] = spec
        return b"\x89PNG\r\n\x1a\ncore-contribution"

    monkeypatch.setattr(plotting, "render_error_contribution_plot_from_spec", fake_render)

    png = workers_core._render_contribution_plot(
        [
            {"name": "B", "variance": mp.mpf("2"), "sigma": mp.sqrt(2), "percent": 66.6667},
            {"name": "A", "variance": mp.mpf("1"), "sigma": mp.mpf("1"), "percent": 33.3333},
        ],
        "en",
        title_suffix="batch 2",
    )

    assert png == b"\x89PNG\r\n\x1a\ncore-contribution"
    spec = captured["spec"]
    assert spec.labels == ("B", "A")
    assert spec.percents == pytest.approx((66.6667, 33.3333))
    assert spec.cumulative_percents == pytest.approx((66.6667, 100.0))
    assert spec.plot_labels.x_axis == "Uncertainty contribution (%)"
    assert spec.plot_labels.title == "Uncertainty breakdown"
    assert spec.plot_labels.cumulative_label == "Cumulative contribution"
    assert spec.title_suffix == "batch 2"


def test_qt_contribution_plot_routes_shared_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop.workers_qt import CalcWorker
    from shared import plotting

    captured: dict[str, Any] = {}

    def fake_render(spec: Any) -> bytes:
        captured["spec"] = spec
        return b"\x89PNG\r\n\x1a\nqt-contribution"

    monkeypatch.setattr(plotting, "render_error_contribution_plot_from_spec", fake_render)
    worker = CalcWorker(cast(Any, SimpleNamespace(lang="zh")))

    png = worker._render_contribution_plot(
        [{"name": "输入A", "variance": mp.mpf("1"), "sigma": mp.mpf("1"), "percent": 100.0}],
        "zh",
    )

    assert png == b"\x89PNG\r\n\x1a\nqt-contribution"
    spec = captured["spec"]
    assert spec.labels == ("输入A",)
    assert spec.percents == (100.0,)
    assert spec.cumulative_percents == (100.0,)
    assert spec.plot_labels.x_axis == "不确定度贡献 (%)"
    assert spec.plot_labels.title == "不确定度贡献分解"
    assert spec.plot_labels.cumulative_label == "累计贡献"


def test_core_monte_carlo_distribution_plot_routes_shared_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    from shared import plotting

    captured: dict[str, Any] = {}

    def fake_render(spec: Any) -> bytes:
        captured["spec"] = spec
        return b"\x89PNG\r\n\x1a\ncore-distribution"

    monkeypatch.setattr(plotting, "render_monte_carlo_distribution_plot_from_spec", fake_render)

    png = workers_core._render_monte_carlo_distribution_plot(
        _valid_distribution_summary(),
        "en",
        row_index=3,
        value_unit="m",
    )

    assert png == b"\x89PNG\r\n\x1a\ncore-distribution"
    spec = captured["spec"]
    assert spec.labels.title == "Monte Carlo distribution"
    assert spec.labels.x_axis == "Result value [m]"
    assert spec.labels.y_axis == "Sample count"
    assert spec.title_suffix == "row 3"


def test_desktop_monte_carlo_distribution_collection_gating() -> None:
    assert workers_core._should_collect_monte_carlo_distribution(
        propagation_method="mc",
        propagation_order=1,
        mc_samples=100,
        mc_seed=7,
        render_plots=True,
    )
    assert not workers_core._should_collect_monte_carlo_distribution(
        propagation_method="monte_carlo",
        propagation_order=1,
        mc_samples=100,
        mc_seed=7,
        render_plots=False,
    )
    assert not workers_core._should_collect_monte_carlo_distribution(
        propagation_method="taylor",
        propagation_order=1,
        mc_samples=100,
        mc_seed=7,
        render_plots=True,
    )


def test_statistics_worker_plot_routes_shared_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop.workers_qt import CalcWorker
    from shared import plotting

    captured: dict[str, Any] = {}

    def fake_render(spec: Any) -> bytes:
        captured["spec"] = spec
        return b"\x89PNG\r\n\x1a\nworker"

    monkeypatch.setattr(plotting, "render_statistics_plot_from_spec", fake_render)
    worker = CalcWorker(cast(Any, SimpleNamespace(lang="en")))

    png = worker._render_statistics_plot(
        [mp.mpf("1.0"), mp.mpf("2.0")],
        [mp.mpf("0.1"), None],
        {"mean": mp.mpf("1.5"), "std_mean": mp.mpf("0.25")},
        batch_idx=3,
    )

    assert png == b"\x89PNG\r\n\x1a\nworker"
    spec = captured["spec"]
    assert spec.values == (mp.mpf("1.0"), mp.mpf("2.0"))
    assert spec.labels.title == "Statistical mean"
    assert spec.labels.mean_band == "Mean ± standard error"
    assert spec.batch_suffix == " - 3"


def test_statistics_worker_plot_gallery_routes_shared_specs(monkeypatch: pytest.MonkeyPatch) -> None:
    from app_desktop.workers_qt import CalcWorker
    from shared import plotting

    captured: dict[str, Any] = {}

    def fake_render(specs: Any) -> list[bytes]:
        captured["specs"] = specs
        return [b"\x89PNG\r\n\x1a\nseries", b"\x89PNG\r\n\x1a\nhist"]

    monkeypatch.setattr(plotting, "render_statistics_plots_from_specs", fake_render)
    worker = CalcWorker(cast(Any, SimpleNamespace(lang="en")))

    pngs = worker._render_statistics_plots(
        [mp.mpf("1.0"), mp.mpf("2.0"), mp.mpf("4.0")],
        [mp.mpf("0.1"), mp.mpf("0.2"), mp.mpf("0.3")],
        {
            "mode": "weighted_sigma",
            "mean": mp.mpf("2.0"),
            "std": mp.mpf("1.5"),
            "std_mean": mp.mpf("0.5"),
            "median": mp.mpf("2.0"),
            "weighted_consistency_dof": 2,
        },
        batch_idx=3,
    )

    assert pngs == [b"\x89PNG\r\n\x1a\nseries", b"\x89PNG\r\n\x1a\nhist"]
    specs = captured["specs"]
    assert [spec.plot_key for spec in specs] == [
        "statistics.series_with_mean",
        "statistics.histogram",
        "statistics.box",
        "statistics.qq",
        "statistics.weighted_residual",
    ]
    assert specs[0].labels.title == "Statistical mean"
    assert specs[1].labels.histogram_title == "Histogram"
    assert specs[0].batch_suffix == " - 3"


def test_statistics_worker_plot_gallery_omits_weighted_residual_for_unweighted_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_desktop.workers_qt import CalcWorker
    from shared import plotting

    captured: dict[str, Any] = {}

    def fake_render(specs: Any) -> list[bytes]:
        captured["specs"] = specs
        return []

    monkeypatch.setattr(plotting, "render_statistics_plots_from_specs", fake_render)
    worker = CalcWorker(cast(Any, SimpleNamespace(lang="en")))

    worker._render_statistics_plots(
        [mp.mpf("1.0"), mp.mpf("2.0"), mp.mpf("4.0")],
        [mp.mpf("0.1"), mp.mpf("0.2"), mp.mpf("0.3")],
        {
            "mode": "mean_sample",
            "mean": mp.mpf("2.3333333333333333"),
            "std": mp.mpf("1.5"),
            "std_mean": mp.mpf("0.5"),
        },
        batch_idx=3,
    )

    assert "statistics.weighted_residual" not in [spec.plot_key for spec in captured["specs"]]


def _assert_primitive_payload(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert isinstance(key, str)
            _assert_primitive_payload(item)
        return
    if isinstance(value, tuple):
        for item in value:
            _assert_primitive_payload(item)
        return
    assert isinstance(value, (str, int, float, bool, type(None)))


def _small_self_consistent_fit_job(
    *,
    precision: int = 50,
    parallel_config: ParallelConfig | None = None,
) -> FitJob:
    x_series = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
    y_series = [mp.mpf("1") + mp.mpf("2") * x for x in x_series]
    data_rows = list(zip(x_series, y_series))
    sigma_rows: list[tuple[mp.mpf | None, ...]] = [(None, None) for _ in data_rows]
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="u",
        parameters=("a", "b"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="root",
            initial="1",
            tolerance="1e-30",
            max_iterations=50,
        ),
    )
    return FitJob(
        model_type="self_consistent",
        headers=["x", "u"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={"x": "x"},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="u",
        model_expr="u",
        parameter_config={
            "a": {"initial": "0.8"},
            "b": {"initial": "1.8"},
        },
        parameter_names=["a", "b"],
        precision=precision,
        weighted=False,
        label="small-self-consistent",
        implicit_definition=definition,
        timeout_seconds=10.0,
        parallel_config=parallel_config or ParallelConfig(),
    )


def test_statistics_calc_job_uses_core_statistics_request_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datalab_core.statistics import build_multi_column_statistics_requests as real_build_multi_column_statistics_requests
    from datalab_core.statistics import run_statistics as real_run_statistics

    calls: dict[str, object] = {}

    def fake_build_multi_column_statistics_requests(**kwargs: object) -> object:
        calls["builder_kwargs"] = kwargs
        return real_build_multi_column_statistics_requests(**kwargs)

    def fake_run_statistics(request: object) -> object:
        calls.setdefault("request_ids", []).append(getattr(request, "request_id", ""))
        return real_run_statistics(request)  # type: ignore[arg-type]

    class FakeService:
        def submit(self, request: object) -> object:
            calls.setdefault("submit_request_ids", []).append(getattr(request, "request_id", ""))
            return fake_run_statistics(request)

    def fake_create_core_session_service(*, cancellation_checker=None) -> FakeService:
        calls["factory_calls"] = int(calls.get("factory_calls", 0)) + 1
        calls["cancellation_checker"] = cancellation_checker
        return FakeService()

    monkeypatch.setattr(workers_core, "build_multi_column_statistics_requests", fake_build_multi_column_statistics_requests, raising=False)
    monkeypatch.setattr(workers_core, "run_statistics", fake_run_statistics, raising=False)
    monkeypatch.setattr(workers_core, "create_core_session_service", fake_create_core_session_service, raising=False)

    with mp.workdps(80):
        rows = [
            (mp.mpf("1.0000000000000000001"), mp.mpf("0.1")),
            (mp.mpf("2.0000000000000000002"), mp.mpf("0.2")),
        ]

    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=80, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_sigma_col="sigma",
        stats_mode="weighted_sigma",
        stats_sample=True,
        stats_weighted_variance=True,
        dataset=(
            ["A", "sigma"],
            rows,
            [(None, None), (None, None)],
        ),
        latex_digits=16,
        segments=[(0, 2)],
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    assert calls["factory_calls"] == 1
    assert callable(calls["cancellation_checker"])
    assert calls["submit_request_ids"] == ["statistics-c1-1"]
    assert calls["request_ids"] == ["statistics-c1-1"]
    builder_kwargs = calls["builder_kwargs"]
    assert isinstance(builder_kwargs, dict)
    assert builder_kwargs["headers"] == ["A", "sigma"]
    assert builder_kwargs["value_columns"] == "A"
    assert builder_kwargs["sigma_col"] == "sigma"
    assert builder_kwargs["precision_digits"] == 80
    assert builder_kwargs["segments"] == [(0, 2)]
    assert result.mode == "statistics"
    batch = result.payload["batches"][0]  # type: ignore[index]
    assert batch["value_col"] == "A"
    assert batch["row_count"] == 2
    assert batch["source_row_ids"] == ("1", "2")
    assert batch["result"]["source_row_ids"] == ("1", "2")
    assert [mp.nstr(value, 30) for value in batch["values"]] == [
        "1.0000000000000000001",
        "2.0000000000000000002",
    ]
    assert [mp.nstr(sigma, 30) if sigma is not None else None for sigma in batch["sigmas"]] == ["0.1", "0.2"]
    assert mp.nstr(batch["result"]["mean"], 30) == "1.20000000000000000012"


def test_statistics_calc_job_runs_multiple_value_columns_in_selected_order() -> None:
    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=60, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="B, A",
        stats_mode="mean",
        stats_sample=True,
        stats_weighted_variance=True,
        dataset=(
            ["A", "B"],
            [(mp.mpf("1"), mp.mpf("10")), (mp.mpf("2"), mp.mpf("20"))],
            [(None, None), (None, None)],
        ),
        latex_digits=16,
        segments=[(0, 2)],
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    assert result.payload["value_col"] == "B, A"
    assert result.payload["value_columns"] == ["B", "A"]
    batches = result.payload["batches"]
    assert [batch["value_col"] for batch in batches] == ["B", "A"]  # type: ignore[index]
    assert [batch["column_index"] for batch in batches] == [1, 2]  # type: ignore[index]
    assert [batch["batch_index"] for batch in batches] == [1, 1]  # type: ignore[index]
    assert [mp.nstr(batch["result"]["mean"], 20) for batch in batches] == ["15.0", "1.5"]  # type: ignore[index]


def test_statistics_calc_job_rejects_negative_explicit_sigma_column() -> None:
    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=60, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_sigma_col="sigma",
        stats_mode="weighted_sigma",
        stats_sample=True,
        stats_weighted_variance=True,
        dataset=(
            ["A", "sigma"],
            [
                (mp.mpf("1.0"), mp.mpf("-0.1")),
                (mp.mpf("2.0"), mp.mpf("0.2")),
            ],
            [(None, None), (None, None)],
        ),
        latex_digits=16,
        segments=[(0, 2)],
        uncertainty_digits=2,
    )

    with pytest.raises(ValueError, match="Negative uncertainty"):
        _execute_calc_job(job)


def test_statistics_calc_job_preserves_result_envelope_warnings_in_batch_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus

    class WarningService:
        def submit(self, _request: object) -> object:
            return ResultEnvelope(
                kind=ResultKind.TABLE,
                status=ResultStatus.SUCCEEDED,
                payload={
                    "mode": "weighted_sigma",
                    "row_count": 2,
                    "precision_used": 60,
                    "mean": "1.25",
                    "std_mean": "0.0",
                    "std": "0.0",
                    "min": "1.25",
                    "max": "2.5",
                    "method_label": "Weighted mean (σ=0 anchor)",
                    "dropped": 1,
                    "effective_n": "1.0",
                    "zero_sigma_anchor": True,
                },
                warnings=("Detected σ=0; treated as infinite weight.",),
            )

    monkeypatch.setattr(
        workers_core,
        "create_core_session_service",
        lambda *, cancellation_checker=None: WarningService(),
        raising=False,
    )

    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=60, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_mode="weighted_sigma",
        dataset=(
            ["A"],
            [(mp.mpf("1.25"),), (mp.mpf("2.5"),)],
            [(mp.mpf("0"),), (mp.mpf("0.1"),)],
        ),
        latex_digits=16,
        segments=[(0, 2)],
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    batch_result = result.payload["batches"][0]["result"]  # type: ignore[index]
    assert batch_result["warnings"] == ["Detected σ=0; treated as infinite weight."]
    assert result.warnings == ["Detected σ=0; treated as infinite weight."]
    assert batch_result["v_min"] == mp.mpf("1.25")
    assert batch_result["v_max"] == mp.mpf("2.5")
    assert batch_result["zero_sigma_anchor"] is True


def test_statistics_calc_job_descriptive_singleton_surfaces_core_warnings() -> None:
    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=60, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_mode="descriptive",
        stats_sample=True,
        stats_weighted_variance=True,
        dataset=(["A"], [(mp.mpf("7"),)], [(None,)]),
        latex_digits=16,
        segments=[(0, 1)],
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    assert result.warnings
    assert any("Sample descriptive statistics require n>=2" in warning for warning in result.warnings)
    assert any("Zero variance" in warning for warning in result.warnings)
    batch_result = result.payload["batches"][0]["result"]  # type: ignore[index]
    assert batch_result["warnings"] == result.warnings


def test_statistics_calc_job_descriptive_trimmed_mean_routes_core_option() -> None:
    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=60, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_mode="descriptive",
        stats_sample=True,
        stats_weighted_variance=True,
        stats_trim_fraction="0.2",
        dataset=(["A"], [(mp.mpf("1"),), (mp.mpf("2"),), (mp.mpf("3"),), (mp.mpf("4"),), (mp.mpf("100"),)], [(None,)] * 5),
        latex_digits=16,
        segments=[(0, 5)],
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    batch_result = result.payload["batches"][0]["result"]  # type: ignore[index]
    assert batch_result["trimmed_mean"] == mp.mpf("3")


def test_statistics_calc_job_rejects_malformed_segments_before_core_builder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_called(**_kwargs: object) -> object:
        raise AssertionError("core builder should not receive malformed worker segments")

    monkeypatch.setattr(workers_core, "build_multi_column_statistics_requests", fail_if_called, raising=False)

    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=80, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_mode="mean",
        dataset=(["A"], [(mp.mpf("1"),), (mp.mpf("2"),)], [(None,), (None,)]),
        latex_digits=16,
        segments=cast(Any, [("0", 2)]),
        uncertainty_digits=2,
    )

    with pytest.raises(TypeError, match="segments\\[0\\] bounds must be integers"):
        _execute_calc_job(job)


def test_statistics_calc_job_preserves_legacy_value_precision_above_compute_dps() -> None:
    value_text = "1.12345678901234567890123456789012345678901234567890123456789"
    with mp.workdps(90):
        rows = [(mp.mpf(value_text),), (mp.mpf("2.0"),)]

    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=50, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_mode="mean",
        dataset=(["A"], rows, [(None,), (None,)]),
        latex_digits=16,
        segments=[(0, 2)],
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    batch = result.payload["batches"][0]  # type: ignore[index]
    assert mp.nstr(batch["values"][0], 80) == value_text
    assert result.payload["precision_used"] == 50


def test_statistics_calc_job_restores_global_mpmath_precision_after_service_submit() -> None:
    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=70, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_mode="mean",
        dataset=(
            ["A"],
            [(mp.mpf("1.0000000000000000001"),), (mp.mpf("2.0000000000000000002"),)],
            [(None,), (None,)],
        ),
        latex_digits=16,
        segments=[(0, 2)],
        uncertainty_digits=2,
    )
    previous = mp.mp.dps
    mp.mp.dps = 29
    try:
        result = _execute_calc_job(job)
        observed_after = mp.mp.dps
    finally:
        mp.mp.dps = previous

    assert observed_after == 29
    assert result.payload["precision_used"] == 70
    batch = result.payload["batches"][0]  # type: ignore[index]
    assert mp.nstr(batch["result"]["mean"], 30) == "1.5"


def test_statistics_calc_job_maps_explicit_sigma_column_to_latex_sigma_rows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    captured: dict[str, object] = {}

    def fake_generate_statistics_latex(
        value_col: str,
        rows: list[tuple[mp.mpf, ...]],
        sigma_rows: list[tuple[mp.mpf | None, ...]],
        *args: object,
        **kwargs: object,
    ) -> None:
        captured["value_col"] = value_col
        captured["rows"] = rows
        captured["sigma_rows"] = sigma_rows

    monkeypatch.setattr(workers_core, "generate_statistics_latex", fake_generate_statistics_latex)

    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=80, warnings=[]),
        caption=None,
        generate_latex=True,
        output_path=str(tmp_path / "stats.tex"),
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_sigma_col="sigma",
        stats_mode="weighted_sigma",
        dataset=(
            ["A", "sigma"],
            [(mp.mpf("1.0"), mp.mpf("0.1")), (mp.mpf("2.0"), mp.mpf("0.2"))],
            [(None, None), (None, None)],
        ),
        latex_digits=16,
        segments=[(0, 2)],
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    assert result.latex_path == str(tmp_path / "stats.tex")
    assert captured["value_col"] == "A"
    assert [
        tuple(mp.nstr(value, 30) if value is not None else None for value in row)
        for row in captured["sigma_rows"]  # type: ignore[index]
    ] == [("0.1", None), ("0.2", None)]


def test_statistics_calc_job_preserves_multi_segment_batch_alignment() -> None:
    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=60, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_mode="mean",
        dataset=(
            ["A"],
            [(mp.mpf("1"),), (mp.mpf("2"),), (mp.mpf("3"),)],
            [(None,), (None,), (None,)],
        ),
        latex_digits=16,
        segments=[(0, 1), (1, 3)],
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    batches = result.payload["batches"]
    assert [batch["index"] for batch in batches] == [1, 2]  # type: ignore[index]
    assert [batch["row_count"] for batch in batches] == [1, 2]  # type: ignore[index]
    assert [batch["source_row_ids"] for batch in batches] == [("1",), ("2", "3")]  # type: ignore[index]
    assert [[mp.nstr(value, 10) for value in batch["values"]] for batch in batches] == [["1.0"], ["2.0", "3.0"]]  # type: ignore[index]


def test_statistics_calc_job_wraps_core_handler_errors_with_batch_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus

    class FailingService:
        def submit(self, _request: object) -> object:
            return ResultEnvelope(
                kind=ResultKind.TEXT,
                status=ResultStatus.FAILED,
                payload={"message": "core exploded"},
            )

    monkeypatch.setattr(
        workers_core,
        "create_core_session_service",
        lambda *, cancellation_checker=None: FailingService(),
        raising=False,
    )

    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=60, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_mode="mean",
        dataset=(
            ["A"],
            [(mp.mpf("1"),), (mp.mpf("2"),)],
            [(None,), (None,)],
        ),
        latex_digits=16,
        segments=[(0, 2)],
        uncertainty_digits=2,
    )

    with pytest.raises(ValueError, match="Batch 1 failed: core exploded"):
        _execute_calc_job(job)


def test_statistics_calc_job_handles_failed_envelope_without_mapping_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datalab_core.results import ResultStatus

    class FailingEnvelope:
        status = ResultStatus.FAILED
        payload = None

    class FailingService:
        def submit(self, _request: object) -> object:
            return FailingEnvelope()

    monkeypatch.setattr(
        workers_core,
        "create_core_session_service",
        lambda *, cancellation_checker=None: FailingService(),
        raising=False,
    )

    job = CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=60, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_mode="mean",
        dataset=(
            ["A"],
            [(mp.mpf("1"),), (mp.mpf("2"),)],
            [(None,), (None,)],
        ),
        latex_digits=16,
        segments=[(0, 2)],
        uncertainty_digits=2,
    )

    with pytest.raises(ValueError, match="Batch 1 failed: Statistics failed\\."):
        _execute_calc_job(job)


def test_root_solving_job_payload_uses_data_rows_and_is_spawn_picklable() -> None:
    job = RootSolvingJob(
        equations=("x**2 - A",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=("A",),
        data_rows=(("4.0(2)",),),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        uncertainty_digits=2,
        generate_latex=True,
        output_path="/tmp/root.tex",
        latex_caption="Frozen caption",
        latex_digits=12,
        latex_group_size=4,
        latex_include_dcolumn=True,
        latex_language="zh",
        render_plots=True,
    )

    payload = _serialize_root_solving_job(job)
    restored = pickle.loads(pickle.dumps(payload))

    _assert_primitive_payload(restored)
    assert restored["data_headers"] == ("A",)
    assert restored["data_rows"] == (("4.0(2)",),)
    assert restored["scan_config"] == {}
    assert restored["uncertainty_digits"] == 2
    assert restored["latex_caption"] == "Frozen caption"
    assert restored["latex_digits"] == 12
    assert restored["latex_group_size"] == 4
    assert restored["latex_include_dcolumn"] is True
    assert restored["latex_language"] == "zh"
    assert restored["render_plots"] is True


def test_root_worker_payload_round_trips_frozen_latex_settings() -> None:
    from datalab_core.root_solving import build_root_solving_request

    core_request = build_root_solving_request(
        equations=("x**2 - A",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=("A",),
        data_rows=(("4.0(2)",),),
        mode="scalar",
        precision_digits=16,
        display_digits=10,
        uncertainty_digits=2,
        request_id="root-roundtrip",
    )
    job = RootSolvingJob(
        equations=("x**2 - A",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=("A",),
        data_rows=(("4.0(2)",),),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        uncertainty_digits=2,
        generate_latex=True,
        output_path="/tmp/root.tex",
        latex_caption="Root run",
        latex_digits=11,
        latex_group_size=2,
        latex_include_dcolumn=True,
        latex_language="en",
        core_request=core_request,
    )

    restored = _deserialize_root_solving_job(_serialize_root_solving_job(job))

    assert restored.latex_caption == "Root run"
    assert restored.latex_digits == 11
    assert restored.latex_group_size == 2
    assert restored.latex_include_dcolumn is True
    assert restored.latex_language == "en"
    assert restored.uncertainty_digits == 2
    assert restored.core_request is not None
    assert restored.core_request.mode is core_request.mode
    assert restored.core_request.request_id == "root-roundtrip"
    assert restored.core_request.inputs["data_rows"] == [["4.0(2)"]]
    assert restored.core_request.options.precision_digits == 16


def test_root_worker_payload_defaults_legacy_render_plots_to_false() -> None:
    payload = {
        "equations": ("x**2 - 2",),
        "unknown_rows": ({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        "data_headers": (),
        "data_rows": (),
        "constants_enabled": False,
        "constants_rows": (),
        "constants_view": "table",
        "constants_text": "",
        "mode": "scalar",
        "scan_config": {},
        "precision": 16,
        "display_digits": 10,
    }

    restored = _deserialize_root_solving_job(payload)

    assert restored.render_plots is False


def test_root_worker_payload_defaults_latex_language_to_job_language() -> None:
    payload = {
        "equations": ("x**2 - 2",),
        "unknown_rows": ({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        "data_headers": (),
        "data_rows": (),
        "constants_enabled": False,
        "constants_rows": (),
        "constants_view": "table",
        "constants_text": "",
        "mode": "scalar",
        "scan_config": {},
        "precision": 16,
        "display_digits": 10,
        "language": "en",
    }

    restored = _deserialize_root_solving_job(payload)

    assert restored.latex_language == "en"


def test_root_worker_payload_preserves_uncertainty_options() -> None:
    job = RootSolvingJob(
        equations=("x^2 - C",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=True,
        constants_rows=({"name": "C", "value": "4.0(2)"},),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=80,
        display_digits=20,
        uncertainty_digits=3,
        uncertainty_options={"method": "monte_carlo", "monte_carlo_samples": 25, "monte_carlo_seed": "7"},
    )

    payload = _serialize_root_solving_job(job)
    restored = _deserialize_root_solving_job(payload)

    assert restored.uncertainty_options == {
        "method": "monte_carlo",
        "taylor_order": 1,
        "monte_carlo_samples": 25,
        "monte_carlo_seed": "7",
    }


def test_root_worker_payload_safely_normalizes_bad_uncertainty_options() -> None:
    payload = {
        "equations": ("x^2 - C",),
        "unknown_rows": ({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        "data_headers": (),
        "data_rows": (),
        "constants_enabled": True,
        "constants_rows": ({"name": "C", "value": "4.0(2)"},),
        "constants_view": "table",
        "constants_text": "",
        "mode": "scalar",
        "scan_config": {},
        "precision": 80,
        "display_digits": 20,
        "uncertainty_options": {
            "method": "monte_carlo",
            "monte_carlo_samples": "bad",
            "monte_carlo_seed": 0,
        },
    }

    restored = _deserialize_root_solving_job(payload)

    assert restored.uncertainty_options == {
        "method": "monte_carlo",
        "taylor_order": 1,
        "monte_carlo_samples": 2000,
        "monte_carlo_seed": "0",
    }


def test_root_worker_payload_safely_normalizes_unknown_uncertainty_method() -> None:
    payload = {
        "equations": ("x^2 - C",),
        "unknown_rows": ({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        "data_headers": (),
        "data_rows": (),
        "constants_enabled": True,
        "constants_rows": ({"name": "C", "value": "4.0(2)"},),
        "constants_view": "table",
        "constants_text": "",
        "mode": "scalar",
        "scan_config": {},
        "precision": 80,
        "display_digits": 20,
        "uncertainty_options": {"method": "future_method"},
    }

    restored = _deserialize_root_solving_job(payload)

    assert restored.uncertainty_options["method"] == "taylor"
    assert restored.uncertainty_options["taylor_order"] == 1


def test_execute_root_solving_job_payload_forwards_uncertainty_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    job = RootSolvingJob(
        equations=("x^2 - C",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=True,
        constants_rows=({"name": "C", "value": "4.0(2)"},),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=80,
        display_digits=20,
        uncertainty_digits=3,
        uncertainty_options={"method": "monte_carlo", "monte_carlo_samples": 25, "monte_carlo_seed": "7"},
    )

    def fake_solve_root_batch(**kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(rows=(), warnings=(), headers=(), details={})

    def fake_render_root_batch_result(
        _batch: object,
        *,
        display_digits: int,
        uncertainty_digits: int,
        language: str,
        root_units_by_name: object = None,
    ) -> tuple[str, list[dict[str, str]], list[str]]:
        captured["display_digits"] = display_digits
        captured["uncertainty_digits"] = uncertainty_digits
        captured["language"] = language
        return "markdown", [], ["name"]

    monkeypatch.setattr(workers_core, "solve_root_batch", fake_solve_root_batch)
    monkeypatch.setattr(workers_core, "render_root_batch_result", fake_render_root_batch_result)

    payload = _execute_root_solving_job_payload(job)

    assert payload["kind"] == "root_solving"
    assert captured["uncertainty_options"] == {
        "method": "monte_carlo",
        "monte_carlo_samples": 25,
        "monte_carlo_seed": "7",
    }
    assert captured["display_digits"] == 20
    assert captured["uncertainty_digits"] == 3
    assert captured["language"] == "en"


def _root_batch_payload_with_scalar_root(value: str) -> dict[str, object]:
    return {
        "headers": [],
        "warnings": [],
        "details": {},
        "rows": [
            {
                "row_index": None,
                "source_values": {},
                "failure": None,
                "warnings": [],
                "result": {
                    "roots": [
                        {
                            "name": "x",
                            "value": {"kind": "real", "value": value},
                            "uncertainty": None,
                            "contributions": {},
                        }
                    ],
                    "backend": "mpmath",
                    "mode": "scalar",
                    "residual_norm": {"kind": "real", "value": "0"},
                    "jacobian_condition": None,
                    "warnings": [],
                    "details": {},
                },
            }
        ],
    }


def test_execute_root_solving_job_payload_uses_core_service_when_request_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus
    from datalab_core.root_solving import build_root_solving_request

    core_request = build_root_solving_request(
        equations=("x^2 - 4",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "0", "upper": "10"},),
        mode="scalar",
        units={
            "enabled": True,
            "mode": "display_only",
            "outputs": {"x": {"unit": "m"}},
        },
        precision_digits=50,
        display_digits=12,
        request_id="desktop-root-test",
    )
    calls: dict[str, object] = {}

    class FakeService:
        def submit(self, request: ComputeJobRequest) -> ResultEnvelope:
            calls["request"] = request
            return ResultEnvelope(
                kind=ResultKind.TABLE,
                status=ResultStatus.SUCCEEDED,
                payload={
                    "batch": _root_batch_payload_with_scalar_root("7"),
                    "row_count": 1,
                    "roots_count": 1,
                    "precision_used": 50,
                    "units": request.inputs["units"],
                },
            )

    def fake_create_core_session_service(*, cancellation_checker=None) -> FakeService:
        calls["cancellation_checker"] = cancellation_checker
        return FakeService()

    monkeypatch.setattr(workers_core, "create_core_session_service", fake_create_core_session_service)
    monkeypatch.setattr(
        workers_core,
        "solve_root_batch",
        lambda **_kwargs: pytest.fail("root solving should use the core batch service"),
    )
    job = RootSolvingJob(
        equations=("x^2 - 4",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "0", "upper": "10"},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=50,
        display_digits=12,
        core_request=core_request,
    )

    payload = _execute_root_solving_job_payload(job, should_cancel=lambda: True)

    assert calls["request"] is core_request
    assert calls["request"].mode is JobMode.ROOT_SOLVING
    assert callable(calls["cancellation_checker"])
    assert calls["cancellation_checker"]() is True
    assert payload["batch"] == _root_batch_payload_with_scalar_root("7")
    assert payload["compute_digits"] == 50
    assert payload["display_digits"] == 12
    assert payload["uncertainty_digits"] == 1
    assert payload["language"] == "en"
    assert payload["units"]["outputs"] == {"x": {"unit": "m"}}
    assert "root_unit" in payload["csv_headers"]
    assert cast(list[dict[str, str]], payload["csv_rows"])[0]["root_unit"] == "m"
    raw_rows = cast(list[dict[str, str]], payload["raw_rows"])
    assert raw_rows[0]["value"] == "7.0"


def test_execute_root_solving_job_payload_core_service_deserializes_under_precision_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datalab_core.jobs import ComputeJobRequest
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus
    from datalab_core.root_solving import build_root_solving_request

    value_text = "1.234567890123456789012345678901234567890123456789"
    core_request = build_root_solving_request(
        equations=("x - 1",),
        unknown_rows=({"name": "x", "initial": "1"},),
        mode="scalar",
        precision_digits=90,
        display_digits=45,
        request_id="desktop-root-high-precision-service",
    )

    class FakeService:
        def submit(self, _request: ComputeJobRequest) -> ResultEnvelope:
            return ResultEnvelope(
                kind=ResultKind.TABLE,
                status=ResultStatus.SUCCEEDED,
                payload={
                    "batch": _root_batch_payload_with_scalar_root(value_text),
                    "row_count": 1,
                    "roots_count": 1,
                    "precision_used": 90,
                },
            )

    monkeypatch.setattr(workers_core, "create_core_session_service", lambda **_kwargs: FakeService())
    job = RootSolvingJob(
        equations=("x - 1",),
        unknown_rows=({"name": "x", "initial": "1"},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=45,
        core_request=core_request,
    )

    previous_dps = mp.mp.dps
    try:
        mp.mp.dps = 15
        payload = _execute_root_solving_job_payload(job)
    finally:
        mp.mp.dps = previous_dps

    assert payload["compute_digits"] == 90
    csv_rows = cast(list[dict[str, str]], payload["csv_rows"])
    raw_rows = cast(list[dict[str, str]], payload["raw_rows"])
    assert csv_rows[0]["value"].startswith("1.23456789012345678901234567890123456789012")
    assert raw_rows[0]["value"].startswith("1.234567890123456789012345678901234567890123456789")


def test_execute_root_solving_job_payload_formats_under_job_precision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, int] = {}
    job = RootSolvingJob(
        equations=("x^2 - C",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=True,
        constants_rows=({"name": "C", "value": "4.0(2)"},),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=80,
        display_digits=40,
        uncertainty_digits=2,
    )

    with mp.mp.workdps(80):
        fake_root = SimpleNamespace(
            name="x",
            value=mp.mpf("1.23456789012345678901234567890123456789"),
            uncertainty=mp.mpf("1e-40"),
            contributions={},
        )
        fake_result = SimpleNamespace(
            roots=(fake_root,),
            backend="mpmath",
            mode="scalar",
            residual_norm=mp.mpf("0"),
            jacobian_condition=None,
            warnings=(),
            details={},
        )
    fake_batch = SimpleNamespace(
        rows=(
            SimpleNamespace(
                row_index=None,
                source_values={},
                result=fake_result,
                failure=None,
                warnings=(),
            ),
        ),
        warnings=(),
        headers=(),
        details={},
    )

    def fake_solve_root_batch(**_kwargs: object) -> object:
        return fake_batch

    def fake_render_root_batch_result(*_args: object, **_kwargs: object) -> tuple[str, list[dict[str, str]], list[str]]:
        captured["render_dps"] = mp.mp.dps
        return "markdown", [], ["name"]

    monkeypatch.setattr(workers_core, "solve_root_batch", fake_solve_root_batch)
    monkeypatch.setattr(workers_core, "render_root_batch_result", fake_render_root_batch_result)
    previous = mp.mp.dps
    try:
        mp.mp.dps = 15
        payload = _execute_root_solving_job_payload(job)
    finally:
        mp.mp.dps = previous

    assert captured["render_dps"] == 80
    batch_payload = cast(dict[str, Any], payload["batch"])
    first_row = cast(dict[str, Any], cast(list[Any], batch_payload["rows"])[0])
    result_payload = cast(dict[str, Any], first_row["result"])
    first_root = cast(dict[str, Any], cast(list[Any], result_payload["roots"])[0])
    value_payload = cast(dict[str, str], first_root["value"])
    assert value_payload["value"].startswith("1.23456789012345678901234567890123456789")
    raw_rows = cast(list[dict[str, str]], payload["raw_rows"])
    assert raw_rows[0]["value"].startswith("1.23456789012345678901234567890123456789")


def test_root_solving_legacy_known_rows_payload_migrates_to_data_rows() -> None:
    payload = {
        "equations": ("x**2 - A",),
        "unknown_rows": ({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        "known_rows": ({"name": "A", "value": "4.0(2)"},),
        "constants_enabled": False,
        "constants_rows": (),
        "constants_view": "table",
        "constants_text": "",
        "mode": "scalar",
        "precision": 16,
        "display_digits": 10,
    }

    job = _deserialize_root_solving_job(payload)

    assert job.data_headers == ("A",)
    assert job.data_rows == (("4.0(2)",),)
    assert job.scan_config == {}


def test_execute_root_solving_job_payload_returns_markdown_csv_and_log() -> None:
    job = RootSolvingJob(
        equations=("x^2 - C",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=True,
        constants_rows=({"name": "C", "value": "4.0000000000000000000000000001(2)"},),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=50,
        display_digits=20,
    )

    payload = _execute_root_solving_job_payload(job)

    assert payload["kind"] == "root_solving"
    markdown = payload["markdown"]
    assert isinstance(markdown, str)
    assert "| input_row_index | root_index | name | value | classification_tags | backend |" in markdown
    assert "| uncertainty |" not in markdown
    assert payload["csv_headers"] == [
        "input_row_index",
        "root_index",
        "name",
        "value",
        "uncertainty",
        "display_value",
        "classification_tags",
        "backend",
        "mode",
        "residual_norm",
        "failure",
    ]
    csv_rows = cast(list[dict[str, str]], payload["csv_rows"])
    assert csv_rows[0]["name"] == "x"
    assert csv_rows[0]["uncertainty"]
    assert csv_rows[0]["display_value"]
    log = payload["log"]
    assert isinstance(log, str)
    assert "root solving completed" in log
    assert isinstance(payload["batch"], dict)
    assert payload["compute_digits"] == 50
    assert payload["display_digits"] == 20
    assert payload["uncertainty_digits"] == 1
    assert payload["language"] == "en"


def test_execute_root_solving_job_payload_skips_root_plot_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_render(*args: object, **kwargs: object) -> object:
        raise AssertionError("root plotting should not run")

    monkeypatch.setattr(workers_core, "render_nominal_root_plots", fail_render)
    job = RootSolvingJob(
        equations=("x**2 - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        render_plots=False,
    )

    payload = _execute_root_solving_job_payload(job)

    assert "plot_bytes" not in payload


def test_execute_root_solving_job_payload_returns_first_root_plot_png(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    png = b"\x89PNG\r\n\x1a\nroot"
    captured: dict[str, object] = {}

    def fake_render(batch: object, problem: object, *, budget: object = None) -> object:
        captured["batch"] = batch
        captured["problem"] = problem
        captured["budget"] = budget
        return SimpleNamespace(
            images=(SimpleNamespace(image_bytes=png, metadata={"row_index": 0}),),
            warnings=("plot warning",),
        )

    monkeypatch.setattr(workers_core, "render_nominal_root_plots", fake_render)
    job = RootSolvingJob(
        equations=("x**2 - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        render_plots=True,
    )

    payload = _execute_root_solving_job_payload(job)

    assert payload["plot_bytes"] == png
    assert "plot_images" not in payload
    assert "plot warning" in payload["warnings"]
    assert captured["budget"] is not None


def test_execute_root_solving_job_payload_uses_successful_row_values_for_plot_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_render(batch: object, problem: object, *, budget: object = None) -> object:
        captured["batch"] = batch
        captured["problem"] = problem
        captured["budget"] = budget
        return SimpleNamespace(images=(), warnings=())

    monkeypatch.setattr(workers_core, "render_nominal_root_plots", fake_render)
    job = RootSolvingJob(
        equations=("x - A",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=("A",),
        data_rows=(("2.5",),),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=32,
        display_digits=10,
        render_plots=True,
    )

    _execute_root_solving_job_payload(job)

    problem = cast(Any, captured["problem"])
    assert problem.row_values == {"A": "2.5"}
    assert captured["budget"] is not None


def test_execute_root_solving_job_payload_returns_real_png_when_root_plots_enabled() -> None:
    job = RootSolvingJob(
        equations=("x**2 - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        render_plots=True,
    )

    payload = _execute_root_solving_job_payload(job)

    plot_bytes = payload["plot_bytes"]
    assert isinstance(plot_bytes, bytes)
    assert plot_bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_execute_root_solving_job_payload_returns_real_png_for_two_dimensional_system_plot() -> None:
    job = RootSolvingJob(
        equations=("x + y - 3", "x - y - 1"),
        unknown_rows=(
            {"name": "x", "initial": "2", "lower": "0", "upper": "4"},
            {"name": "y", "initial": "1", "lower": "0", "upper": "4"},
        ),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="system",
        scan_config={},
        precision=16,
        display_digits=10,
        render_plots=True,
    )

    payload = _execute_root_solving_job_payload(job)

    plot_bytes = payload["plot_bytes"]
    assert isinstance(plot_bytes, bytes)
    assert plot_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    warnings = cast(list[str], payload["warnings"])
    assert not any("System root plots require exactly two equations" in warning for warning in warnings)


def test_execute_root_solving_job_payload_warns_for_unsupported_system_plot_in_chinese() -> None:
    job = RootSolvingJob(
        equations=("x + y + z - 1", "x - y", "z - 1"),
        unknown_rows=(
            {"name": "x", "initial": "0.5", "lower": "0", "upper": "2"},
            {"name": "y", "initial": "0.5", "lower": "0", "upper": "2"},
            {"name": "z", "initial": "1", "lower": "0", "upper": "2"},
        ),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="system",
        scan_config={},
        precision=16,
        display_digits=10,
        language="zh",
        render_plots=True,
    )

    payload = _execute_root_solving_job_payload(job)

    assert "plot_bytes" not in payload
    warnings = cast(list[str], payload["warnings"])
    assert any("方程组绘图需要正好两个方程和两个实数未知量" in warning for warning in warnings)


def test_execute_root_solving_job_payload_does_not_plot_failed_root_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_solve_root_batch(**_kwargs: object) -> object:
        return SimpleNamespace(
            rows=(SimpleNamespace(row_index=0, source_values={}, failure="no root", result=None, warnings=()),),
            warnings=(),
            headers=(),
            details={},
        )

    def fake_render_root_batch_result(
        _batch: object,
        *,
        display_digits: int,
        uncertainty_digits: int,
        language: str,
        root_units_by_name: object = None,
    ) -> tuple[str, list[dict[str, str]], list[str]]:
        return "failed", [], ["name"]

    def fail_render(*args: object, **kwargs: object) -> object:
        raise AssertionError("root plotting should only run for successful root rows")

    monkeypatch.setattr(workers_core, "solve_root_batch", fake_solve_root_batch)
    monkeypatch.setattr(workers_core, "render_root_batch_result", fake_render_root_batch_result)
    monkeypatch.setattr(workers_core, "render_nominal_root_plots", fail_render)
    job = RootSolvingJob(
        equations=("x**2 - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=10,
        render_plots=True,
    )

    payload = _execute_root_solving_job_payload(job)

    assert "plot_bytes" not in payload


def test_execute_root_solving_job_payload_localizes_root_output_to_chinese() -> None:
    job = RootSolvingJob(
        equations=("x^2 - C",),
        unknown_rows=({"name": "x", "initial": "2", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=True,
        constants_rows=({"name": "C", "value": "4.0(2)"},),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=16,
        display_digits=8,
        language="zh",
    )

    payload = _execute_root_solving_job_payload(job)

    markdown = cast(str, payload["markdown"])
    assert "| 输入行 | 根序号 | 名称 | 值 | 分类标签 | 后端 |" in markdown
    assert "不确定度" not in markdown.split("\n", maxsplit=1)[0]
    assert "求根完成" in cast(str, payload["log"])
    assert payload["csv_headers"] == [
        "input_row_index",
        "root_index",
        "name",
        "value",
        "uncertainty",
        "display_value",
        "classification_tags",
        "backend",
        "mode",
        "residual_norm",
        "failure",
    ]


def test_execute_root_solving_job_payload_preserves_original_data_cell_precision() -> None:
    original = "1.0000000000000000000000000000000000000000000000001"
    job = RootSolvingJob(
        equations=("x - A",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=("A",),
        data_rows=((original,),),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=80,
        display_digits=80,
    )

    payload = _execute_root_solving_job_payload(job)

    csv_rows = cast(list[dict[str, str]], payload["csv_rows"])
    assert csv_rows[0]["A"] == original
    assert csv_rows[0]["value"].startswith(original)
    raw_rows = cast(list[dict[str, str]], payload["raw_rows"])
    assert raw_rows[0]["input_A"] == original
    assert raw_rows[0]["value"].startswith(original)


def test_root_raw_rows_assign_default_input_index_for_no_data_multi_root_latex() -> None:
    job = RootSolvingJob(
        equations=("x^2 - 4",),
        unknown_rows=({"name": "x", "initial": "0", "lower": "-3", "upper": "3"},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scan_multiple",
        scan_config={"sample_count": 100, "max_roots": 5},
        precision=16,
        display_digits=10,
    )

    payload = _execute_root_solving_job_payload(job)

    raw_rows = cast(list[dict[str, str]], payload["raw_rows"])
    assert len(raw_rows) == 2
    assert {row["input_row_index"] for row in raw_rows} == {"0"}
    assert [row["root_index"] for row in raw_rows] == ["0", "1"]


def test_root_solving_subprocess_uses_killable_runner_and_forwards_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = RootSolvingJob(
        equations=("x - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=50,
        display_digits=12,
    )
    calls: dict[str, object] = {}
    expected: dict[str, object] = {
        "kind": "root_solving",
        "markdown": "ok",
        "csv_rows": [],
        "csv_headers": ["name", "value", "uncertainty", "backend", "mode", "residual_norm"],
        "log": "ok",
        "warnings": [],
    }

    class FakeRunner:
        def __init__(self, *, config: ParallelConfig) -> None:
            calls["config"] = config

        def run_killable(
            self,
            target: Callable[[dict[str, Any]], dict[str, object]],
            payload: dict[str, Any],
            *,
            timeout_seconds: float | None = None,
            should_cancel: Callable[[], bool] | None = None,
        ) -> dict[str, object]:
            calls["target"] = target
            calls["payload"] = payload
            calls["timeout_seconds"] = timeout_seconds
            calls["should_cancel"] = should_cancel
            return expected

    monkeypatch.setattr(workers_core, "KillableProcessTaskRunner", FakeRunner)

    result = _execute_root_solving_job_payload_subprocess(
        job,
        timeout_seconds=12.5,
        should_cancel=lambda: False,
    )

    assert result is expected
    assert isinstance(calls["config"], ParallelConfig)
    assert calls["target"] is workers_core._root_solving_job_entry
    assert calls["payload"] == _serialize_root_solving_job(job)
    assert calls["timeout_seconds"] == 12.5
    assert callable(calls["should_cancel"])


def test_root_solving_worker_emits_cancelled_when_subprocess_interrupts(
    monkeypatch: pytest.MonkeyPatch,
    qtbot,
) -> None:
    job = RootSolvingJob(
        equations=("x - 2",),
        unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="scalar",
        scan_config={},
        precision=50,
        display_digits=12,
    )
    observed: dict[str, object] = {}

    def fake_subprocess(
        received_job: RootSolvingJob,
        *,
        timeout_seconds: float | None,
        should_cancel: Callable[[], bool] | None,
    ) -> dict[str, object]:
        observed["job"] = received_job
        observed["timeout_seconds"] = timeout_seconds
        observed["should_cancel"] = should_cancel
        if should_cancel and should_cancel():
            raise InterruptedError("root solving cancelled")
        raise AssertionError("expected cancellation")

    monkeypatch.setattr(workers_core, "_execute_root_solving_job_payload_subprocess", fake_subprocess)
    worker = RootSolvingWorker(job)
    worker.request_stop()

    with qtbot.waitSignal(worker.cancelled, timeout=3000):
        worker.start()

    assert worker.wait(3000)
    assert observed["job"] is job
    assert observed["timeout_seconds"] == workers_core.ROOT_SOLVING_SUBPROCESS_TIMEOUT_SECONDS
    assert callable(observed["should_cancel"])


def _depth_probe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "payload": payload,
        "env_depth": os.environ.get("DATALAB_PARALLEL_DEPTH"),
        "current_depth": current_parallel_depth(),
    }


def test_execute_fit_job_payload_poly_recovers_linear_params():
    x_series = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
    y_series = [mp.mpf("2") * x + mp.mpf("1") for x in x_series]

    data_rows = list(zip(x_series, y_series))
    sigma_rows = [(None, None) for _ in data_rows]

    job = FitJob(
        model_type="polynomial",
        headers=["x", "y"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="y",
        model_expr="",
        parameter_config={},
        parameter_names=[],
        poly_degree=1,
        precision=80,
        weighted=False,
        label="unit-test",
    )

    payload = _execute_fit_job_payload(job)
    fit = payload.fit_result
    assert fit is not None
    assert mp.almosteq(fit.params["b0"], mp.mpf("1"), abs_eps=mp.mpf("1e-50"))
    assert mp.almosteq(fit.params["b1"], mp.mpf("2"), abs_eps=mp.mpf("1e-50"))


def _fit_result_payload_with_params(params: dict[str, str]) -> dict[str, object]:
    return {
        "params": params,
        "param_errors": {},
        "chi2": "0",
        "reduced_chi2": "0",
        "aic": "0",
        "bic": "0",
        "r2": "1",
        "rmse": "0",
        "residuals": [],
        "fitted_curve": [],
        "covariance": [],
        "param_errors_stat": {},
        "param_errors_sys": {},
        "param_errors_total": {},
        "details": {},
    }


def test_execute_fit_job_payload_direct_fit_uses_core_service_when_request_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datalab_core.fitting import build_fitting_request
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus

    x_series = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
    y_series = [mp.mpf("2") * x + mp.mpf("1") for x in x_series]
    core_request = build_fitting_request(
        model_type="polynomial",
        headers=("x", "y"),
        data_rows=tuple(zip(x_series, y_series)),
        variable_map={"x": "x"},
        target_column="y",
        poly_degree=1,
        precision_digits=80,
        request_id="desktop-fit-test",
    )
    calls: dict[str, object] = {}

    class FakeService:
        def submit(self, request: ComputeJobRequest) -> ResultEnvelope:
            calls["request"] = request
            return ResultEnvelope(
                kind=ResultKind.TABLE,
                status=ResultStatus.SUCCEEDED,
                payload={
                    "model_type": "polynomial",
                    "fit_result": _fit_result_payload_with_params({"b0": "10", "b1": "20"}),
                    "expression": "core-expression",
                    "logs": ["core fit complete"],
                    "warnings": [],
                    "units": {"parameters": {"b0": {"unit": "m"}}},
                },
            )

    def fake_create_core_session_service(*, cancellation_checker=None) -> FakeService:
        calls["cancellation_checker"] = cancellation_checker
        return FakeService()

    monkeypatch.setattr(workers_core, "create_core_session_service", fake_create_core_session_service)
    job = FitJob(
        model_type="polynomial",
        headers=["x", "y"],
        data_rows=list(zip(x_series, y_series)),
        sigma_rows=[(None, None) for _ in x_series],
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={"x": "x"},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="y",
        model_expr="",
        parameter_config={},
        parameter_names=[],
        poly_degree=1,
        precision=80,
        weighted=False,
        label="desktop-fit-core",
        core_request=core_request,
    )

    payload = _execute_fit_job_payload(job)

    assert calls["request"] is core_request
    assert callable(calls["cancellation_checker"])
    assert calls["request"].mode is JobMode.FITTING
    assert payload.fit_result.params == {"b0": mp.mpf("10"), "b1": mp.mpf("20")}
    assert payload.expression == "core-expression"
    assert payload.logs == ["core fit complete"]
    assert payload.units == {"parameters": {"b0": {"unit": "m"}}}


def test_execute_fit_job_payload_self_consistent_does_not_use_core_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datalab_core.fitting import build_fitting_request

    job = _small_self_consistent_fit_job()
    job.core_request = build_fitting_request(
        model_type="self_consistent",
        headers=job.headers,
        data_rows=job.data_rows,
        sigma_rows=job.sigma_rows,
        variable_map=job.variable_map,
        target_column=job.target_column,
        model_expr=job.model_expr,
        parameter_config=job.parameter_config,
        parameter_names=job.parameter_names,
        implicit_definition=job.implicit_definition,
        precision_digits=job.precision,
    )
    monkeypatch.setattr(
        workers_core,
        "create_core_session_service",
        lambda: pytest.fail("self_consistent fit must not use direct core service"),
    )
    monkeypatch.setattr(workers_core, "_self_consistent_hooks_replaced", lambda: True)
    monkeypatch.setattr(
        workers_core,
        "_fit_self_consistent_with_legacy_hooks",
        lambda received_job: FitResult(
            params={"a": mp.mpf("1"), "b": mp.mpf("2")},
            param_errors={},
            chi2=mp.mpf("0"),
            reduced_chi2=mp.mpf("0"),
            aic=mp.mpf("0"),
            bic=mp.mpf("0"),
            r2=mp.mpf("1"),
            rmse=mp.mpf("0"),
            residuals=[],
            fitted_curve=[],
            covariance=[],
            details={},
        ),
    )

    payload = _execute_fit_job_payload(job)

    assert payload.fit_result.params == {"a": mp.mpf("1"), "b": mp.mpf("2")}
    assert payload.expression == "u"


def test_execute_fit_job_payload_self_consistent_wires_definition_and_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    x_series = [mp.mpf(v) for v in ["0", "1", "2"]]
    y_series = [mp.mpf(v) for v in ["0.3", "0.4", "0.5"]]

    data_rows = list(zip(x_series, y_series))
    sigma_rows = [(None, None) for _ in data_rows]
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*Cos[u] + c*x",
        output_expression="u",
        parameters=("a", "b", "c"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="root",
            initial="0.3",
            tolerance="1e-36",
        ),
    )
    spec = SimpleNamespace(
        implicit_diagnostics=SimpleNamespace(
            points_solved=7,
            root_fallbacks=2,
            max_iterations_used=5,
            max_residual="1.0e-42",
        )
    )
    calls: dict[str, object] = {}

    def fake_build_implicit_model_specification(
        received_definition: ImplicitModelDefinition,
    ) -> object:
        calls["definition"] = received_definition
        return spec

    def fake_fit_custom_model(
        received_spec: object,
        state: object,
        variable_data: dict[str, list[mp.mpf]],
        target_series: list[mp.mpf],
        **kwargs: object,
    ) -> FitResult:
        calls["spec"] = received_spec
        calls["free_params"] = tuple(state.free_params)
        calls["variable_data"] = variable_data
        calls["target_series"] = target_series
        calls["kwargs"] = kwargs
        return FitResult(
            params={"a": mp.mpf("0.1"), "b": mp.mpf("0.2"), "c": mp.mpf("0.4")},
            param_errors={},
            chi2=mp.mpf("0"),
            reduced_chi2=mp.mpf("0"),
            aic=mp.mpf("0"),
            bic=mp.mpf("0"),
            r2=mp.mpf("1"),
            rmse=mp.mpf("0"),
            residuals=[],
            fitted_curve=list(target_series),
            covariance=[],
            details={},
        )

    monkeypatch.setattr(
        workers_core,
        "build_implicit_model_specification",
        fake_build_implicit_model_specification,
    )
    monkeypatch.setattr(workers_core, "can_fit_observed_implicit_variable", lambda _definition: False)
    monkeypatch.setattr(workers_core, "fit_custom_model", fake_fit_custom_model)

    job = FitJob(
        model_type="self_consistent",
        headers=["x", "u"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={"x": "x"},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="u",
        model_expr="",
        parameter_config={
            "a": {"initial": 0.1},
            "b": {"initial": 0.2},
            "c": {"initial": 0.4},
        },
        parameter_names=["a", "b", "c"],
        precision=30,
        weighted=False,
        label="self-consistent-test",
        implicit_definition=definition,
    )

    payload = _execute_fit_job_payload(job)
    fit = payload.fit_result

    assert calls["definition"] is definition
    assert calls["spec"] is spec
    assert calls["free_params"] == ("a", "b", "c")
    assert calls["variable_data"] == {"x": x_series}
    assert calls["target_series"] == y_series
    assert calls["kwargs"] == {
        "precision": 30,
        "weights": None,
        "data_sigmas": [None] * len(y_series),
    }
    assert {name: float(value) for name, value in fit.params.items()} == {
        "a": 0.1,
        "b": 0.2,
        "c": 0.4,
    }
    assert payload.expression == "u"
    details = fit.details
    assert details["implicit_variable"] == "u"
    assert details["equation"] == "a + b*Cos[u] + c*x"
    assert details["output_expression"] == "u"
    assert details["implicit_diagnostics"] == {
        "points_solved": 7,
        "root_fallbacks": 2,
        "max_iterations_used": 5,
        "max_residual": "1.0e-42",
    }


def test_execute_fit_job_payload_self_consistent_requires_definition() -> None:
    with pytest.raises(ValueError, match="requires an implicit definition"):
        _execute_fit_job_payload(
            FitJob(
                model_type="self_consistent",
                headers=["x", "u"],
                data_rows=[],
                sigma_rows=[],
                x_series=[],
                y_series=[],
                sigma_series=[],
                weights=None,
                variable_map={"x": "x"},
                variable_data={"x": []},
                target_series=[],
                target_column="u",
                model_expr="",
                parameter_config={"a": {"initial": 0.1}},
                parameter_names=["a"],
                precision=30,
                weighted=False,
                label="missing-definition-test",
            )
        )


def test_self_consistent_fit_job_is_marked_for_process_boundary() -> None:
    job = _small_self_consistent_fit_job()
    assert _fit_job_requires_process_boundary(job) is True

    direct_job = FitJob(
        model_type="polynomial",
        headers=["x", "y"],
        data_rows=[],
        sigma_rows=[],
        x_series=[],
        y_series=[],
        sigma_series=[],
        weights=None,
        variable_map={},
        variable_data={},
        target_series=[],
        target_column="y",
        model_expr="",
        parameter_config={},
        parameter_names=[],
    )
    assert _fit_job_requires_process_boundary(direct_job) is False


def test_self_consistent_fit_job_payload_is_spawn_picklable() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    roundtrip = pickle.loads(pickle.dumps(payload))
    restored = _deserialize_fit_job(roundtrip)

    assert restored.model_type == "self_consistent"
    assert restored.implicit_definition is not None
    assert restored.implicit_definition.equation == "a + b*x"
    assert restored.implicit_definition.solve_options.method == "root"
    assert restored.timeout_seconds == 10.0
    assert restored.parallel_config.process_start_method == "spawn"


def test_self_consistent_fit_job_serialization_preserves_uncertain_sigma_rows() -> None:
    job = _small_self_consistent_fit_job()
    job.sigma_rows[0] = (None, UncertainValue("204397210.721", "0.002", uncertainty_digits=1))

    payload = _serialize_fit_job(job)
    roundtrip = pickle.loads(pickle.dumps(payload))
    restored = _deserialize_fit_job(roundtrip)

    entry = restored.sigma_rows[0][1]
    assert isinstance(entry, UncertainValue)
    assert entry.value == mp.mpf("204397210.721")
    assert entry.uncertainty == mp.mpf("0.002")
    assert entry.uncertainty_digits == 1


@pytest.mark.parametrize(
    ("path", "value", "match"),
    [
        (("implicit_definition", "equation"), 123, "equation must be a string"),
        (("implicit_definition", "output_expression"), 123, "output_expression must be a string"),
        (("implicit_definition", "implicit_variable"), 123, "implicit_variable must be a string"),
        (("implicit_definition", "x_variables"), ["x", 1], "x_variables must be a list of strings"),
        (("implicit_definition", "parameters"), ["a", 1], "parameters must be a list of strings"),
        (("implicit_definition", "constants"), [], "constants must be an object"),
        (("implicit_definition", "constants"), {"C": 1}, "constants must map strings to strings"),
        (("implicit_definition", "solve_options"), [], "solve_options must be an object"),
        (("implicit_definition", "solve_options", "method"), 123, "method must be a string"),
        (("implicit_definition", "solve_options", "initial"), 123, "initial must be a string"),
        (("implicit_definition", "solve_options", "tolerance"), 123, "tolerance must be a string"),
    ],
)
def test_deserialize_fit_job_rejects_malformed_implicit_definition_fields(
    path: tuple[str, ...],
    value: object,
    match: str,
) -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    target: dict[str, Any] = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(ValueError, match=match):
        _deserialize_fit_job(payload)


def test_deserialize_fit_job_rejects_malformed_implicit_solve_options() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["implicit_definition"]["solve_options"] = "root"

    with pytest.raises(ValueError, match="solve_options must be an object"):
        _deserialize_fit_job(payload)


def test_deserialize_fit_job_rejects_unsupported_process_start_method() -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["parallel_config"]["process_start_method"] = "definitely-not-a-start-method"

    with pytest.raises(ValueError, match="Unsupported process_start_method"):
        _deserialize_fit_job(payload)


@pytest.mark.parametrize("value", [[], ""])
def test_deserialize_fit_job_rejects_malformed_parallel_config(value: object) -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["parallel_config"] = value

    with pytest.raises(ValueError, match="parallel_config must be an object"):
        _deserialize_fit_job(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_workers", 2.5),
        ("max_workers", True),
        ("reserve_cores", 1.25),
        ("reserve_cores", False),
        ("default_worker_cap", 8.5),
        ("default_worker_cap", True),
        ("min_process_tasks", 4.5),
        ("min_process_tasks", False),
    ],
)
def test_deserialize_fit_job_rejects_lossy_parallel_config_numeric_fields(
    field: str,
    value: object,
) -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["parallel_config"][field] = value

    with pytest.raises(ValueError, match=rf"parallel_config\.{field} must be an integer"):
        _deserialize_fit_job(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("precision", 50.5),
        ("precision", True),
        ("poly_degree", 2.5),
        ("poly_degree", False),
        ("inverse_min", 1.25),
        ("inverse_max", True),
        ("pade_m", 1.5),
        ("pade_n", False),
        ("latex_digits", 16.5),
    ],
)
def test_deserialize_fit_job_rejects_lossy_integer_fields(
    field: str,
    value: object,
) -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload[field] = value

    with pytest.raises(ValueError, match=rf"fit_job\.{field} must be an integer"):
        _deserialize_fit_job(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("generate_latex", "False"),
        ("use_dcolumn", "False"),
        ("verbose", 0),
        ("render_plots", 1),
        ("weighted", "true"),
        ("is_multidim", None),
    ],
)
def test_deserialize_fit_job_rejects_non_boolean_fields(
    field: str,
    value: object,
) -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload[field] = value

    with pytest.raises(ValueError, match=rf"fit_job\.{field} must be a boolean"):
        _deserialize_fit_job(payload)


def test_fit_subprocess_entry_rejects_malformed_precision_before_precision_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _serialize_fit_job(_small_self_consistent_fit_job())
    payload["precision"] = 50.5

    def fail_guard(_dps: object) -> object:
        raise AssertionError("precision guard should not run before payload validation")

    monkeypatch.setattr(workers_core, "_mp_precision_guard", fail_guard)

    with pytest.raises(ValueError, match=r"fit_job\.precision must be an integer"):
        workers_core._fit_job_subprocess_entry(payload)


def test_fit_result_payload_rejects_malformed_job_precision_before_precision_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job()
    result_payload = workers_core._serialize_fit_result_payload(
        workers_core.FitResultPayload(
            job=job,
            fit_result=FitResult(
                params={"a": mp.mpf("1"), "b": mp.mpf("2")},
                param_errors={},
                chi2=mp.mpf("0"),
                reduced_chi2=mp.mpf("0"),
                aic=mp.mpf("0"),
                bic=mp.mpf("0"),
                r2=mp.mpf("1"),
                rmse=mp.mpf("0"),
                residuals=[],
                fitted_curve=[],
                covariance=[],
                details={},
            ),
            expression="u",
            logs=[],
            warnings=[],
        )
    )
    result_payload["job"]["precision"] = 50.5

    def fail_guard(_dps: object) -> object:
        raise AssertionError("precision guard should not run before payload validation")

    monkeypatch.setattr(workers_core, "_mp_precision_guard", fail_guard)

    with pytest.raises(ValueError, match=r"fit_job\.precision must be an integer"):
        workers_core._deserialize_fit_result_payload(result_payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_workers", 2.5),
        ("reserve_cores", 1.25),
        ("default_worker_cap", True),
        ("min_process_tasks", False),
    ],
)
def test_deserialize_root_solving_job_rejects_lossy_parallel_config_numeric_fields(
    field: str,
    value: object,
) -> None:
    payload = _serialize_root_solving_job(
        RootSolvingJob(
            equations=("x^2 - A",),
            unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
            data_headers=("A",),
            data_rows=(("2",),),
            constants_enabled=False,
            constants_rows=(),
            constants_view="table",
            constants_text="",
            mode="scalar",
            scan_config={},
            precision=50,
            display_digits=12,
        )
    )
    payload["parallel_config"][field] = value

    with pytest.raises(ValueError, match=rf"parallel_config\.{field} must be an integer"):
        _deserialize_root_solving_job(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("precision", 50.5),
        ("precision", True),
        ("display_digits", 12.5),
        ("display_digits", False),
        ("uncertainty_digits", 1.5),
        ("latex_digits", True),
        ("latex_group_size", 3.25),
    ],
)
def test_deserialize_root_solving_job_rejects_lossy_integer_fields(
    field: str,
    value: object,
) -> None:
    payload = _serialize_root_solving_job(
        RootSolvingJob(
            equations=("x^2 - A",),
            unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
            data_headers=("A",),
            data_rows=(("2",),),
            constants_enabled=False,
            constants_rows=(),
            constants_view="table",
            constants_text="",
            mode="scalar",
            scan_config={},
            precision=50,
            display_digits=12,
        )
    )
    payload[field] = value

    with pytest.raises(ValueError, match=rf"root_solving_job\.{field} must be an integer"):
        _deserialize_root_solving_job(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("constants_enabled", "False"),
        ("generate_latex", "true"),
        ("latex_include_dcolumn", 0),
        ("render_plots", 1),
    ],
)
def test_deserialize_root_solving_job_rejects_non_boolean_fields(
    field: str,
    value: object,
) -> None:
    payload = _serialize_root_solving_job(
        RootSolvingJob(
            equations=("x^2 - A",),
            unknown_rows=({"name": "x", "initial": "1", "lower": "", "upper": ""},),
            data_headers=("A",),
            data_rows=(("2",),),
            constants_enabled=False,
            constants_rows=(),
            constants_view="table",
            constants_text="",
            mode="scalar",
            scan_config={},
            precision=50,
            display_digits=12,
        )
    )
    payload[field] = value

    with pytest.raises(ValueError, match=rf"root_solving_job\.{field} must be a boolean"):
        _deserialize_root_solving_job(payload)


def test_self_consistent_fit_subprocess_uses_killable_runner_and_forwards_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job()
    calls: dict[str, object] = {}

    class FakeRunner:
        def __init__(self, *, config: ParallelConfig) -> None:
            calls["config"] = config

        def run_killable(
            self,
            target: Callable[[dict[str, Any]], dict[str, Any]],
            payload: dict[str, Any],
            *,
            timeout_seconds: float | None = None,
            should_cancel: Callable[[], bool] | None = None,
        ) -> dict[str, Any]:
            calls["target"] = target
            calls["payload"] = payload
            calls["timeout_seconds"] = timeout_seconds
            calls["should_cancel"] = should_cancel
            return workers_core._serialize_fit_result_payload(
                workers_core.FitResultPayload(
                    job=job,
                    fit_result=FitResult(
                        params={"a": mp.mpf("1"), "b": mp.mpf("2")},
                        param_errors={},
                        chi2=mp.mpf("0"),
                        reduced_chi2=mp.mpf("0"),
                        aic=mp.mpf("0"),
                        bic=mp.mpf("0"),
                        r2=mp.mpf("1"),
                        rmse=mp.mpf("0"),
                        residuals=[],
                        fitted_curve=[],
                        covariance=[],
                        details={},
                    ),
                    expression="u",
                    logs=[],
                    warnings=[],
                )
            )

    monkeypatch.setattr(workers_core, "KillableProcessTaskRunner", FakeRunner)

    result = _execute_fit_job_payload_subprocess(
        job,
        timeout_seconds=12.5,
        should_cancel=lambda: False,
    )

    assert result.fit_result.params["a"] == mp.mpf("1")
    assert calls["config"] is job.parallel_config
    assert calls["target"] is workers_core._fit_job_subprocess_entry
    assert calls["payload"] == _serialize_fit_job(job)
    assert calls["timeout_seconds"] == 12.5
    assert callable(calls["should_cancel"])


def test_self_consistent_fit_subprocess_target_uses_job_precision_under_low_ambient_dps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job(precision=90)
    precise = mp.mpf("1.234567890123456789012345678901234567890123456789")
    job.y_series[0] = precise
    job.target_series[0] = precise
    observed: dict[str, object] = {}

    def fake_execute(received_job: FitJob) -> workers_core.FitResultPayload:
        observed["mp_dps"] = mp.mp.dps
        observed["target_value"] = received_job.target_series[0]
        return workers_core.FitResultPayload(
            job=received_job,
            fit_result=FitResult(
                params={"a": precise},
                param_errors={},
                chi2=precise,
                reduced_chi2=mp.mpf("0"),
                aic=mp.mpf("0"),
                bic=mp.mpf("0"),
                r2=mp.mpf("1"),
                rmse=mp.mpf("0"),
                residuals=[precise],
                fitted_curve=[precise],
                covariance=[],
                details={},
            ),
            expression="u",
            logs=[],
            warnings=[],
        )

    monkeypatch.setattr(workers_core, "_execute_fit_job_payload", fake_execute)
    payload = _serialize_fit_job(job)

    with mp.workdps(15):
        result_payload = workers_core._fit_job_subprocess_entry(payload)
        restored = workers_core._deserialize_fit_result_payload(result_payload)

    assert observed["mp_dps"] == 90
    with mp.workdps(100):
        assert mp.almosteq(observed["target_value"], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.params["a"], precise, abs_eps=mp.mpf("1e-70"))


def test_self_consistent_fit_subprocess_maps_backend_interruption_to_cancelled_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job()

    class InterruptingRunner:
        def __init__(self, *, config: ParallelConfig) -> None:
            self.config = config

        def run_killable(self, *args: object, **kwargs: object) -> object:
            raise InterruptedError("backend interrupted")

    monkeypatch.setattr(workers_core, "KillableProcessTaskRunner", InterruptingRunner)

    with pytest.raises(InterruptedError, match="Self-consistent fit cancelled"):
        _execute_fit_job_payload_subprocess(job, timeout_seconds=10.0)


def test_fit_killable_runner_child_depth_marker_is_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATALAB_PARALLEL_DEPTH", raising=False)
    runner = KillableProcessTaskRunner(config=ParallelConfig())

    payload = runner.run_killable(
        _depth_probe_payload,
        {"kind": "fit"},
        timeout_seconds=2.0,
    )

    assert payload["payload"] == {"kind": "fit"}
    assert payload["env_depth"] == "1" or payload["current_depth"] >= 1


def test_self_consistent_fit_job_serialization_preserves_high_precision_values() -> None:
    with mp.workdps(100):
        precise = mp.mpf("1.234567890123456789012345678901234567890123456789")
        job = _small_self_consistent_fit_job(precision=80)
        job.x_series[0] = precise
        row = list(job.data_rows[0])
        row[0] = precise
        job.data_rows[0] = tuple(row)
        job.variable_data["x"][0] = precise

        payload = _serialize_fit_job(job)

    with mp.workdps(15):
        restored = _deserialize_fit_job(payload)

    with mp.workdps(100):
        assert mp.almosteq(restored.x_series[0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.data_rows[0][0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.variable_data["x"][0], precise, abs_eps=mp.mpf("1e-70"))


def test_self_consistent_fit_result_deserialization_preserves_high_precision_values() -> None:
    with mp.workdps(100):
        precise = mp.mpf("2.34567890123456789012345678901234567890123456789")
        job = _small_self_consistent_fit_job(precision=80)
        fit = FitResult(
            params={"a": precise},
            param_errors={"a": mp.mpf("1e-40")},
            chi2=precise,
            reduced_chi2=mp.mpf("0"),
            aic=mp.mpf("0"),
            bic=mp.mpf("0"),
            r2=mp.mpf("1"),
            rmse=mp.mpf("0"),
            residuals=[precise],
            fitted_curve=[precise],
            covariance=[[precise]],
            details={"metric": precise},
        )
        result_payload = workers_core._serialize_fit_result_payload(
            workers_core.FitResultPayload(
                job=job,
                fit_result=fit,
                expression="u",
                logs=[],
                warnings=[],
            )
        )

    with mp.workdps(15):
        restored = workers_core._deserialize_fit_result_payload(result_payload)

    with mp.workdps(100):
        assert mp.almosteq(restored.fit_result.params["a"], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.chi2, precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.residuals[0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.fitted_curve[0], precise, abs_eps=mp.mpf("1e-70"))
        assert mp.almosteq(restored.fit_result.covariance[0][0], precise, abs_eps=mp.mpf("1e-70"))


def test_self_consistent_subprocess_executes_real_fit_roundtrip() -> None:
    job = _small_self_consistent_fit_job()

    payload = _execute_fit_job_payload_subprocess(job, timeout_seconds=10.0)
    fit = payload.fit_result

    assert mp.almosteq(fit.params["a"], mp.mpf("1"), abs_eps=mp.mpf("1e-20"))
    assert mp.almosteq(fit.params["b"], mp.mpf("2"), abs_eps=mp.mpf("1e-20"))
    assert payload.job.model_type == "self_consistent"
    assert payload.expression == "u"


def test_fit_batch_worker_routes_self_consistent_fit_through_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _small_self_consistent_fit_job()
    calls: dict[str, object] = {}

    def fake_subprocess(received_job, *, timeout_seconds, should_cancel):
        calls["job"] = received_job
        calls["timeout_seconds"] = timeout_seconds
        calls["should_cancel"] = should_cancel
        return SimpleNamespace(fit_result=None, logs=[], warnings=[])

    monkeypatch.setattr(workers_core, "_execute_fit_job_payload_subprocess", fake_subprocess)

    worker = FitBatchWorker([], capture_output=False)
    payload = worker._run_fit_task(job)

    assert payload.fit_result is None
    assert calls["job"] is job
    assert calls["timeout_seconds"] == 10.0
    assert callable(calls["should_cancel"])


def test_fit_batch_worker_emits_cancelled_when_self_consistent_subprocess_interrupts(
    monkeypatch: pytest.MonkeyPatch,
    qtbot,
) -> None:
    job = _small_self_consistent_fit_job()

    def fake_subprocess(received_job, *, timeout_seconds, should_cancel):
        raise InterruptedError("cancelled")

    monkeypatch.setattr(workers_core, "_execute_fit_job_payload_subprocess", fake_subprocess)

    worker = FitBatchWorker([FitBatchTask(index=0, fit_job=job)], capture_output=False)
    with qtbot.waitSignal(worker.cancelled, timeout=3000):
        worker.start()

    assert worker.wait(3000)


def test_execute_calc_job_extrapolation_returns_payload() -> None:
    from datalab_core.jobs import JobMode

    with mp.workdps(80):
        limit = mp.mpf("1")
        amp = mp.mpf("0.5")
        terms = [limit + amp / mp.power(n, 2) for n in range(1, 9)]  # 8 columns
        headers = [f"S{idx}" for idx in range(1, len(terms) + 1)]
        data_text = " ".join(headers) + "\n" + " ".join(mp.nstr(v, 50) for v in terms) + "\n"

        opts = ExtrapolationOptions(method="richardson", mp_precision=80)
        job = CalcJob(
            mode="extrapolation",
            data_path=None,
            manual_content=data_text,
            manual_constants="",
            constants_file_path=None,
            options=opts,
            caption=None,
            generate_latex=False,
            output_path="",
            use_dcolumn=False,
            verbose=False,
            render_plots=False,
            lang="en",
            latex_digits=16,
            latex_group_size=3,
            uncertainty_digits=2,
        )

        result = _execute_calc_job(job)
        assert result.mode == "extrapolation"
        assert result.latex_path is None
        payload = result.payload
        assert payload["headers"] == headers
        assert len(payload["data_rows"]) == 1
        assert len(payload["results"]) == 1
        assert payload["precision_used"] == 80
        assert payload["render_plots"] is False
        assert "plots" not in payload
        assert payload["core_request"].mode is JobMode.EXTRAPOLATION
        assert payload["core_request"].inputs["headers"] == headers
        assert payload["core_request"].inputs["rows"][0][0] == mp.nstr(terms[0], 80)
        assert payload["core_request"].inputs["method"] == "richardson"
        assert payload["core_request"].inputs["segments"] == [[0, 1]]

        res0 = payload["results"][0]
        assert mp.fabs(res0.value - limit) < mp.mpf("1e-2")


def test_execute_calc_job_extrapolation_uses_core_service_when_request_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _legacy_process_should_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("desktop extrapolation worker should use the core extrapolation service")

    monkeypatch.setattr(workers_core, "process_data_string", _legacy_process_should_not_run)

    job = CalcJob(
        mode="extrapolation",
        data_path=None,
        manual_content="A B C\n1 1.5 1.75\n",
        manual_constants="",
        constants_file_path=None,
        options=ExtrapolationOptions(method="quadratic", mp_precision=80),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        latex_digits=16,
        latex_group_size=3,
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    assert result.mode == "extrapolation"
    payload = result.payload
    assert payload["headers"] == ["A", "B", "C"]
    assert len(payload["data_rows"]) == 1
    assert payload["results"][0].method == "quadratic"
    assert payload["results"][0].value == mp.mpf("1.875")
    assert payload["core_request"].request_id == "desktop-worker-extrapolation"


def test_execute_calc_job_error_returns_core_request_snapshot() -> None:
    from datalab_core.jobs import JobMode

    job = CalcJob(
        mode="error",
        data_path=None,
        manual_content="x y\n1.0(1) 2.0(2)\n",
        manual_constants="C 3.0(3)\n",
        constants_file_path=None,
        options=ExtrapolationOptions(mp_precision=50),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        constants_enabled=True,
        use_constants_file=False,
        formula="x + C",
        error_propagation_method="taylor",
        error_propagation_order=2,
        error_mc_samples=123,
        error_mc_seed=7,
        lang="en",
        latex_digits=16,
        latex_group_size=3,
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    assert result.mode == "error"
    payload = result.payload
    assert payload["core_request"].mode is JobMode.UNCERTAINTY
    assert payload["core_request"].inputs["headers"] == ["x", "y"]
    assert payload["core_request"].inputs["formula"] == "x + C"
    assert payload["core_request"].inputs["constants"]["C"]["value"] == "3.0"
    assert payload["core_request"].inputs["constants"]["C"]["uncertainty"] == "0.3"
    assert payload["core_request"].inputs["propagation"] == {
        "method": "taylor",
        "order": 2,
        "mc_samples": None,
        "mc_seed": None,
    }
    assert payload["propagation"] == {
        "method": "taylor",
        "order": 2,
        "mc_samples": None,
        "mc_seed": None,
    }
    assert payload["core_request"].inputs["segments"] == [[0, 1]]


def test_execute_calc_job_error_passes_units_to_core_request_payload_and_latex(tmp_path: Path) -> None:
    output_path = tmp_path / "error_units.tex"
    job = CalcJob(
        mode="error",
        data_path=None,
        manual_content="x\n1.0(1)\n",
        manual_constants="",
        constants_file_path=None,
        options=ExtrapolationOptions(mp_precision=50),
        caption=None,
        generate_latex=True,
        output_path=str(output_path),
        use_dcolumn=True,
        verbose=False,
        render_plots=False,
        constants_enabled=False,
        use_constants_file=False,
        formula="x",
        error_propagation_method="taylor",
        error_propagation_order=1,
        lang="en",
        latex_digits=16,
        latex_group_size=3,
        uncertainty_digits=2,
        units_config={
            "enabled": True,
            "mode": "display_only",
            "inputs": {"x": "m"},
            "outputs": {"result": "m"},
        },
    )

    result = _execute_calc_job(job)

    payload = result.payload
    assert payload["core_request"].inputs["units"]["inputs"] == {"x": {"unit": "m"}}
    assert payload["core_request"].inputs["units"]["outputs"] == {"result": {"unit": "m"}}
    assert payload["units"] == payload["core_request"].inputs["units"]
    latex = output_path.read_text(encoding="utf-8")
    assert "\\multicolumn{1}{c}{x~[\\texttt{m}]}" in latex
    assert "\\multicolumn{1}{c}{Result~[\\texttt{m}]}" in latex


def test_execute_calc_job_error_units_allow_unused_configured_constants() -> None:
    job = CalcJob(
        mode="error",
        data_path=None,
        manual_content="x\n1.0(1)\n",
        manual_constants="K 2.0(2)\nL 5.0(5)\n",
        constants_file_path=None,
        options=ExtrapolationOptions(mp_precision=50),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        constants_enabled=True,
        use_constants_file=False,
        formula="x + K",
        error_propagation_method="taylor",
        error_propagation_order=1,
        lang="en",
        latex_digits=16,
        latex_group_size=3,
        uncertainty_digits=2,
        units_config={
            "enabled": True,
            "mode": "display_only",
            "inputs": {"x": "m"},
            "constants": {"K": "m", "L": "m"},
            "outputs": {"result": "m"},
        },
    )

    result = _execute_calc_job(job)

    payload = result.payload
    assert payload["core_request"].inputs["constants"]["K"]["value"] == "2.0"
    assert payload["core_request"].inputs["constants"]["L"]["value"] == "5.0"
    assert payload["units"]["constants"] == {"K": {"unit": "m"}, "L": {"unit": "m"}}
    assert payload["results"][0].value == mp.mpf("3.0")


def test_execute_calc_job_error_uses_core_service_when_request_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _direct_apply_should_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("desktop error worker should use the core uncertainty service")

    monkeypatch.setattr(workers_core, "apply_formula_to_data", _direct_apply_should_not_run)

    job = CalcJob(
        mode="error",
        data_path=None,
        manual_content="x\n1.0(1)\n",
        manual_constants="",
        constants_file_path=None,
        options=ExtrapolationOptions(mp_precision=50),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        constants_enabled=False,
        use_constants_file=False,
        formula="x",
        error_propagation_method="taylor",
        error_propagation_order=1,
        lang="en",
        latex_digits=16,
        latex_group_size=3,
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    assert result.mode == "error"
    assert len(result.payload["results"]) == 1
    assert result.payload["results"][0].value == mp.mpf("1.0")
    assert mp.almosteq(result.payload["results"][0].uncertainty, mp.mpf("0.1"))


def test_execute_calc_job_error_outputs_monte_carlo_distribution_row_plot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus

    captured: dict[str, object] = {}

    class FakeService:
        def submit(self, request):
            captured["collect"] = request.inputs["collect_monte_carlo_distribution"]
            return ResultEnvelope(
                kind=ResultKind.TABLE,
                status=ResultStatus.SUCCEEDED,
                payload={
                    "headers": ["x"],
                    "formula": "x",
                    "segments": [[0, 1]],
                    "precision_used": 50,
                    "propagation": {
                        "method": "monte_carlo",
                        "order": 1,
                        "mc_samples": 100,
                        "mc_seed": 7,
                    },
                    "units": {
                        "schema": "datalab.units.annotations.v1",
                        "schema_version": 1,
                        "enabled": True,
                        "mode": "display_only",
                        "inputs": {"x": {"unit": "m"}},
                        "constants": {},
                        "parameters": {},
                        "outputs": {"result": {"unit": "m"}},
                    },
                    "results": [
                        {
                            "value": "1.0",
                            "uncertainty": "0.2",
                            "contributions": {"x": "0.04"},
                            "monte_carlo_distribution": _valid_distribution_summary(),
                        }
                    ],
                },
            )

    monkeypatch.setattr(workers_core, "create_core_session_service", lambda **_kwargs: FakeService())
    monkeypatch.setattr(workers_core, "_render_contribution_plot", lambda *_args, **_kwargs: b"contrib")
    distribution_kwargs: dict[str, object] = {}

    def fake_distribution_plot(*_args: object, **kwargs: object) -> bytes:
        distribution_kwargs.update(kwargs)
        return b"distribution"

    monkeypatch.setattr(workers_core, "_render_monte_carlo_distribution_plot", fake_distribution_plot)

    job = CalcJob(
        mode="error",
        data_path=None,
        manual_content="x\n1.0(1)\n",
        manual_constants="",
        constants_file_path=None,
        options=ExtrapolationOptions(mp_precision=50),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=True,
        constants_enabled=False,
        use_constants_file=False,
        formula="x",
        error_propagation_method="monte_carlo",
        error_propagation_order=1,
        error_mc_samples=100,
        error_mc_seed=7,
        lang="en",
        latex_digits=16,
        latex_group_size=3,
        uncertainty_digits=2,
        units_config={
            "enabled": True,
            "mode": "display_only",
            "inputs": {"x": "m"},
            "outputs": {"result": "m"},
        },
    )

    result = _execute_calc_job(job)

    assert captured["collect"] is True
    assert result.payload["row_contribution_plots"] == [b"contrib"]
    assert result.payload["row_distribution_plots"] == [b"distribution"]
    assert distribution_kwargs["value_unit"] == "m"


def test_execute_calc_job_extrapolation_core_snapshot_failure_is_nonfatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_snapshot(**_kwargs: object) -> object:
        raise RuntimeError("snapshot failed")

    monkeypatch.setattr(workers_core, "build_extrapolation_request", _fail_snapshot)

    job = CalcJob(
        mode="extrapolation",
        data_path=None,
        manual_content="A B C\n1.0 1.5 1.75\n",
        manual_constants="",
        constants_file_path=None,
        options=ExtrapolationOptions(method="quadratic", mp_precision=50),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        latex_digits=16,
        latex_group_size=3,
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    assert result.mode == "extrapolation"
    assert "core_request" not in result.payload
    assert len(result.payload["results"]) == 1


def test_extrapolation_method_options_accept_integer_levin_order() -> None:
    options = ExtrapolationOptions(method="levin_u", levin_order=4)

    payload = workers_core._extrapolation_method_options(options)

    assert payload["levin_order"] == 4


def test_extrapolation_method_options_preserve_power_law_payload() -> None:
    from extrapolation_methods import PowerLawConfig

    options = ExtrapolationOptions(
        method="power_law",
        power_law_config=PowerLawConfig(
            x_values=("4", "5", "6"),
            precision=90,
            exponent_override="3.5",
            initial_guess="1.25",
            seed_guesses=("0.5", "1.0", "2.0"),
        ),
    )

    payload = workers_core._extrapolation_method_options(options)

    assert payload["power_law_config"] == {
        "x_values": ["4", "5", "6"],
        "precision": "90",
        "initial_guess": "1.25",
        "exponent_override": "3.5",
        "seed_guesses": ["0.5", "1.0", "2.0"],
    }


@pytest.mark.parametrize("malformed", [4.9, True, "4"])
def test_extrapolation_method_options_reject_malformed_levin_order(malformed: object) -> None:
    options = ExtrapolationOptions(method="levin_u")
    options.levin_order = malformed  # type: ignore[assignment]

    with pytest.raises(TypeError, match="levin_order"):
        workers_core._extrapolation_method_options(options)


def test_execute_calc_job_error_core_snapshot_failure_is_nonfatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_snapshot(**_kwargs: object) -> object:
        raise RuntimeError("snapshot failed")

    monkeypatch.setattr(workers_core, "build_uncertainty_request", _fail_snapshot)

    job = CalcJob(
        mode="error",
        data_path=None,
        manual_content="x\n1.0(1)\n",
        manual_constants="",
        constants_file_path=None,
        options=ExtrapolationOptions(mp_precision=50),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        constants_enabled=False,
        use_constants_file=False,
        formula="x",
        error_propagation_method="taylor",
        error_propagation_order=1,
        lang="en",
        latex_digits=16,
        latex_group_size=3,
        uncertainty_digits=2,
    )

    result = _execute_calc_job(job)

    assert result.mode == "error"
    assert "core_request" not in result.payload
    assert len(result.payload["results"]) == 1


def test_execute_calc_job_error_units_enabled_disables_legacy_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail_snapshot(**_kwargs: object) -> object:
        raise RuntimeError("snapshot failed")

    def _direct_apply_should_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("unit-enabled error jobs must not fall back to legacy apply")

    monkeypatch.setattr(workers_core, "build_uncertainty_request", _fail_snapshot)
    monkeypatch.setattr(workers_core, "apply_formula_to_data", _direct_apply_should_not_run)

    job = CalcJob(
        mode="error",
        data_path=None,
        manual_content="x\n1.0(1)\n",
        manual_constants="",
        constants_file_path=None,
        options=ExtrapolationOptions(mp_precision=50),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        constants_enabled=False,
        use_constants_file=False,
        formula="x",
        error_propagation_method="taylor",
        error_propagation_order=1,
        lang="en",
        latex_digits=16,
        latex_group_size=3,
        uncertainty_digits=2,
        units_config={"enabled": True, "mode": "display_only", "inputs": {"x": "m"}},
    )

    with pytest.raises(RuntimeError, match="snapshot failed"):
        _execute_calc_job(job)


def test_run_calculation_uses_content_driven_error_constants_from_calc_job(
    qtbot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app_desktop import window_extrapolation_mixin
    from app_desktop.window import ExtrapolationWindow

    class _Signal:
        def connect(self, _callback: object) -> None:
            return

    class _DummyCalcWorker:
        finished_ok = _Signal()
        failed = _Signal()
        finished = _Signal()
        cancelled = _Signal()
        log_ready = _Signal()

        def __init__(self, job: CalcJob) -> None:
            captured["job"] = job

        def start(self) -> None:
            captured["started"] = True

        def isRunning(self) -> bool:  # noqa: N802 - Qt-style test double
            return False

    captured: dict[str, object] = {}
    monkeypatch.setattr(window_extrapolation_mixin, "CalcWorker", _DummyCalcWorker)

    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    win.mode_combo.setCurrentIndex(win.mode_combo.findData("error"))
    win._data_stack.setCurrentIndex(1)
    win.manual_data_edit.setPlainText("A B\n1 2\n")
    win.formula_edit.setPlainText("A + B")
    win.error_constants_editor.set_rows([{"name": "K", "value": "1.23(4)"}])
    win.error_constants_editor.setChecked(False)

    win.run_calculation()

    job = captured["job"]
    assert isinstance(job, CalcJob)
    assert captured["started"] is True
    assert win.error_constants_editor.constants_dict(validate=False) == {"K": "1.23(4)"}
    assert job.constants_enabled is True
    assert job.manual_constants == "K 1.23(4)"
