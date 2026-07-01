from __future__ import annotations

import pytest
from mpmath import mp

from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
from datalab_core.service_factory import create_core_session_service
from datalab_core.session import ResultStatus
from datalab_core.statistics_time_series import (
    TIME_SERIES_RESULT_CACHE_KIND,
    TIME_SERIES_WORKFLOW_MODE,
    run_statistics_time_series,
    validate_statistics_time_series_payload,
    validate_statistics_time_series_snapshot,
)


def test_time_series_rolling_mean_preserves_labels_and_propagates_independent_sigma() -> None:
    payload = run_statistics_time_series(
        values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        source_row_ids=["r1", "r2", "r3"],
        precision_digits=30,
        inputs={
            "series_method": "rolling_mean",
            "window_size": 2,
            "min_periods": 2,
            "alignment": "right",
            "sigmas": ["0.1", "0.2", "0.3"],
            "sigma_column": "A_sigma",
            "time_labels": ["0.0", "1.0", "2.0"],
            "time_column": "t",
        },
        value_column="A",
        column_index=1,
    )

    validate_statistics_time_series_payload(payload)
    assert payload["workflow_mode"] == TIME_SERIES_WORKFLOW_MODE
    assert payload["sigma_columns"] == {"A": "A_sigma"}
    assert payload["uncertainty_assumptions"] == {"A": "independent"}
    points = payload["columns"][0]["points"]
    assert points[0]["status"] == "insufficient_window"
    assert points[0]["value"] is None
    assert any(item["code"] == "insufficient_window" for item in payload["diagnostics"])
    assert points[1]["value"] == "1.5"
    assert mp.almosteq(mp.mpf(points[1]["uncertainty"]), mp.sqrt(mp.mpf("0.05")) / 2)
    assert points[2]["window_source_row_ids"] == ["r2", "r3"]
    assert points[2]["time"] == "2.0"


def test_time_series_rolling_median_uses_type7_quantile_and_center_alignment() -> None:
    payload = run_statistics_time_series(
        values=[mp.mpf("1"), mp.mpf("10"), mp.mpf("2"), mp.mpf("8")],
        source_row_ids=None,
        precision_digits=20,
        inputs={
            "series_method": "rolling_median",
            "window_size": 3,
            "min_periods": 1,
            "alignment": "center",
        },
        value_column="A",
    )

    points = payload["columns"][0]["points"]
    assert [point["value"] for point in points] == ["5.5", "2.0", "8.0", "5.0"]


def test_time_series_rolling_std_honors_sample_population_and_sample_window_size() -> None:
    sample_payload = run_statistics_time_series(
        values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        source_row_ids=None,
        precision_digits=30,
        inputs={
            "series_method": "rolling_std",
            "window_size": 2,
            "min_periods": 1,
            "alignment": "right",
            "denominator": "sample",
        },
        value_column="A",
    )
    population_payload = run_statistics_time_series(
        values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        source_row_ids=None,
        precision_digits=30,
        inputs={
            "series_method": "rolling_std",
            "window_size": 2,
            "min_periods": 1,
            "alignment": "right",
            "denominator": "population",
        },
        value_column="A",
    )

    sample_points = sample_payload["columns"][0]["points"]
    population_points = population_payload["columns"][0]["points"]
    assert sample_points[0]["status"] == "insufficient_window"
    assert sample_points[0]["value"] is None
    assert mp.almosteq(mp.mpf(sample_points[1]["value"]), mp.sqrt(mp.mpf("0.5")))
    assert population_points[0]["value"] == "0.0"
    assert mp.almosteq(mp.mpf(population_points[1]["value"]), mp.mpf("0.5"))


def test_time_series_ewma_adjusted_and_unadjusted_formulas() -> None:
    unadjusted = run_statistics_time_series(
        values=[mp.mpf("1"), mp.mpf("3"), mp.mpf("5")],
        source_row_ids=None,
        precision_digits=30,
        inputs={"series_method": "ewma", "alpha": "0.5", "adjust": False},
        value_column="A",
    )
    adjusted = run_statistics_time_series(
        values=[mp.mpf("1"), mp.mpf("3"), mp.mpf("5")],
        source_row_ids=None,
        precision_digits=30,
        inputs={"series_method": "ewma", "alpha": "0.5", "adjust": True},
        value_column="A",
    )

    assert [point["value"] for point in unadjusted["columns"][0]["points"]] == ["1.0", "2.0", "3.5"]
    adjusted_last = adjusted["columns"][0]["points"][2]["value"]
    assert mp.almosteq(mp.mpf(adjusted_last), mp.mpf("27") / 7)
    assert adjusted["ewma"]["alpha"] == "0.5"
    assert [point["window_source_row_ids"] for point in adjusted["columns"][0]["points"]] == [
        ["1"],
        ["2"],
        ["3"],
    ]


def test_time_series_validator_rejects_json_floats_and_tampered_points() -> None:
    payload = run_statistics_time_series(
        values=[mp.mpf("1"), mp.mpf("2")],
        source_row_ids=None,
        precision_digits=20,
        inputs={"series_method": "rolling_mean", "window_size": 2, "min_periods": 1},
        value_column="A",
    )

    tampered_float = dict(payload)
    tampered_float["precision_used"] = 20.0
    with pytest.raises(TypeError, match="JSON floats"):
        validate_statistics_time_series_payload(tampered_float)

    tampered_point = dict(payload)
    tampered_column = dict(payload["columns"][0])
    tampered_points = [dict(point) for point in tampered_column["points"]]
    tampered_points[0]["status"] = "insufficient_window"
    tampered_points[0]["value"] = "1.0"
    tampered_column["points"] = tampered_points
    tampered_point["columns"] = [tampered_column]
    with pytest.raises(ValueError, match="insufficient_window"):
        validate_statistics_time_series_payload(tampered_point)

    tampered_source = dict(payload)
    source_column = dict(payload["columns"][0])
    source_points = [dict(point) for point in source_column["points"]]
    source_points[0]["source_row_id"] = "shifted"
    source_column["points"] = source_points
    tampered_source["columns"] = [source_column]
    with pytest.raises(ValueError, match="source_row_id"):
        validate_statistics_time_series_payload(tampered_source)

    tampered_window = dict(payload)
    bad_window = dict(payload["window"])
    bad_window["unexpected"] = "x"
    tampered_window["window"] = bad_window
    with pytest.raises(ValueError, match="window"):
        validate_statistics_time_series_payload(tampered_window)

    bad_units = dict(payload)
    bad_units["units"] = {"enabled": True, "mode": "active"}
    with pytest.raises(ValueError, match="statistics units only support display_only"):
        validate_statistics_time_series_payload(bad_units)


def test_statistics_service_dispatches_time_series_workflow() -> None:
    request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "workflow_mode": TIME_SERIES_WORKFLOW_MODE,
            "series_method": "rolling_mean",
            "values": ["1", "2", "3"],
            "source_row_ids": ["1", "2", "3"],
            "value_column": "A",
            "window_size": 2,
            "min_periods": 2,
        },
        options=JobOptions(precision_digits=30),
        request_id="time-series-service",
    )

    envelope = create_core_session_service().submit(request)

    assert envelope.status is ResultStatus.SUCCEEDED
    assert envelope.payload["workflow_mode"] == TIME_SERIES_WORKFLOW_MODE
    assert envelope.payload["columns"][0]["points"][1]["value"] == "1.5"


def test_time_series_snapshot_renders_text_and_csv_from_semantic_payload() -> None:
    from datalab_core.statistics import build_statistics_result_snapshot, render_statistics_snapshot_outputs

    payload = run_statistics_time_series(
        values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        source_row_ids=["1", "2", "3"],
        precision_digits=30,
        inputs={"series_method": "rolling_mean", "window_size": 2, "min_periods": 2},
        value_column="A",
        column_index=1,
    )

    snapshot = build_statistics_result_snapshot(TIME_SERIES_RESULT_CACHE_KIND, payload)

    assert snapshot is not None
    validate_statistics_time_series_snapshot(snapshot)
    assert snapshot["mode"] == TIME_SERIES_WORKFLOW_MODE
    assert snapshot["source"]["series_method"] == "rolling_mean"
    assert snapshot["time_series"][0]["points"][1]["value"] == "1.5"
    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, rows, headers = rendered
    assert "=== Time-Series Statistics ===" in text
    assert headers == ["column", "row", "time", "method", "value", "uncertainty", "status", "window_source_rows"]
    assert rows[1]["column"] == "A"
    assert rows[1]["value"] == "1.5"
    assert rows[1]["window_source_rows"] == "1 2"


def test_time_series_snapshot_units_add_value_and_uncertainty_columns() -> None:
    from datalab_core.statistics import build_statistics_result_snapshot, render_statistics_snapshot_outputs

    payload = run_statistics_time_series(
        values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        source_row_ids=["1", "2", "3"],
        precision_digits=30,
        inputs={
            "series_method": "rolling_mean",
            "window_size": 2,
            "min_periods": 2,
            "sigmas": ["0.1", "0.2", "0.3"],
        },
        value_column="A",
        column_index=1,
    )
    payload["units"] = {
        "enabled": True,
        "mode": "display_only",
        "outputs": {"A": {"unit": "m"}},
    }
    snapshot = build_statistics_result_snapshot(TIME_SERIES_RESULT_CACHE_KIND, payload)
    assert snapshot is not None

    rendered = render_statistics_snapshot_outputs(snapshot)

    assert rendered is not None
    text, rows, headers = rendered
    assert "Value unit" in text
    assert headers == [
        "column",
        "row",
        "time",
        "method",
        "value",
        "value_unit",
        "uncertainty",
        "uncertainty_unit",
        "status",
        "window_source_rows",
    ]
    assert rows[1]["value_unit"] == "m"
    assert rows[1]["uncertainty_unit"] == "m"


def test_time_series_snapshot_validator_rejects_tampered_point_source_rows() -> None:
    from datalab_core.statistics import build_statistics_result_snapshot

    payload = run_statistics_time_series(
        values=[mp.mpf("1"), mp.mpf("2")],
        source_row_ids=["1", "2"],
        precision_digits=20,
        inputs={"series_method": "rolling_mean", "window_size": 2, "min_periods": 1},
        value_column="A",
    )
    snapshot = build_statistics_result_snapshot(TIME_SERIES_RESULT_CACHE_KIND, payload)
    assert snapshot is not None
    tampered = dict(snapshot)
    time_series = [dict(column) for column in snapshot["time_series"]]
    points = [dict(point) for point in time_series[0]["points"]]
    points[0]["source_row_id"] = "shifted"
    time_series[0]["points"] = points
    tampered["time_series"] = time_series

    with pytest.raises(ValueError, match="source_row_id"):
        validate_statistics_time_series_snapshot(tampered)
