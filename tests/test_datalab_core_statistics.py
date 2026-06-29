from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any, cast

import mpmath as mp
import pytest

from shared.precision import precision_guard


def test_confidence_quantile_helpers_reference_rejection_and_monotonic() -> None:
    from shared.precision import (
        normal_two_sided_critical_value,
        student_t_inverse_cdf,
        student_t_two_sided_critical_value,
    )

    with precision_guard(80):
        assert mp.almosteq(
            normal_two_sided_critical_value("0.95"),
            mp.mpf("1.9599639845400542355"),
            rel_eps=mp.mpf("1e-19"),
        )
        assert mp.almosteq(
            student_t_two_sided_critical_value("0.95", 1),
            mp.mpf("12.706204736174704"),
            rel_eps=mp.mpf("1e-15"),
        )
        assert mp.almosteq(
            student_t_two_sided_critical_value("0.95", 10),
            mp.mpf("2.2281388519649385"),
            rel_eps=mp.mpf("1e-10"),
        )
        assert student_t_inverse_cdf("0.975", 5) < student_t_inverse_cdf("0.995", 5)
        assert student_t_inverse_cdf("0.975", 30) < student_t_inverse_cdf("0.975", 5)

    with pytest.raises(ValueError, match="Confidence level"):
        normal_two_sided_critical_value("1")
    with pytest.raises(ValueError, match="Confidence level"):
        student_t_two_sided_critical_value("0", 3)
    with pytest.raises(ValueError, match="degrees of freedom"):
        student_t_two_sided_critical_value("0.95", 0)


def test_unweighted_confidence_interval_uses_sample_se_in_population_mode() -> None:
    from datalab_core.statistics_compute import compute_statistics

    with precision_guard(80):
        result = compute_statistics(
            [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")],
            [None, None, None, None],
            "mean_population",
            use_sample=False,
        )

    assert result["method_label"] == "Arithmetic mean (population)"
    assert result["mean_ci_method_label"] == "Student-t mean CI (sample standard deviation)"
    assert result["mean_ci_dof"] == 3
    assert mp.almosteq(result["std_mean"], mp.sqrt(mp.mpf("1.25")) / 2)
    assert mp.almosteq(result["mean_sample_se_for_ci"], mp.sqrt(mp.mpf("5") / 3) / 2)
    assert not mp.almosteq(result["std_mean"], result["mean_sample_se_for_ci"])
    assert mp.almosteq(result["mean_ci_lower"], mp.mpf("0.445739743239121"), rel_eps=mp.mpf("1e-12"))
    assert mp.almosteq(result["mean_ci_upper"], mp.mpf("4.554260256760879"), rel_eps=mp.mpf("1e-12"))


def test_confidence_interval_payload_semantic_csv_and_snapshot_parity() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        build_statistics_result_snapshot,
        render_statistics_snapshot_outputs,
        run_statistics,
        statistics_csv_rows_from_result,
        statistics_payload_to_compute_result,
    )

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["1", "2", "3", "4"],
                "stats_mode": "mean_population",
                "use_sample": False,
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-confidence-parity",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mean_ci_dof"] == 3
    assert result.payload["mean_ci_method_label"] == "Student-t mean CI (sample standard deviation)"
    assert result.payload["mean_sample_se_for_ci"].startswith("0.645497224367902")
    rows_by_key = {row.key: row for row in analysis_rows_from_json(result.payload["analysis_rows"])}
    assert rows_by_key["mean_ci_lower"].value == result.payload["mean_ci_lower"]
    assert rows_by_key["mean_ci_method"].value == result.payload["mean_ci_method_label"]

    roundtrip = statistics_payload_to_compute_result(result.payload, result.warnings)
    csv_by_metric = {
        str(row["metric"]): row
        for row in statistics_csv_rows_from_result(roundtrip, row_count=4, include_batch=False)
    }
    assert csv_by_metric["mean_ci_lower"]["value"] == result.payload["mean_ci_lower"]
    assert csv_by_metric["mean_ci_method"]["value"] == result.payload["mean_ci_method_label"]

    snapshot = build_statistics_result_snapshot(
        "statistics_single",
        {"result": roundtrip, "value_col": "A", "n": 4},
    )
    assert snapshot is not None
    assert {row["key"] for row in snapshot["metric_rows"]} >= {"mean_ci_lower", "mean_ci_upper"}
    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, _headers = rendered
    assert "Mean CI lower" in text
    assert {str(row["metric"]) for row in csv_rows} >= {"mean_ci_lower", "mean_ci_upper"}


def test_statistics_snapshot_numeric_text_preserves_precision_without_global_guard() -> None:
    from datalab_core.statistics import build_statistics_result_snapshot

    value = "1.123456789012345678901234567890123456789"
    result = {
        "mode": "mean_sample",
        "mean": value,
        "std_mean": "0.000000000000000000000000000000000000001",
        "std": "0.000000000000000000000000000000000000001",
        "v_min": value,
        "v_max": value,
        "method_label": "Arithmetic mean (sample)",
        "dropped": 0,
        "source_row_ids": ("1",),
    }

    with mp.workdps(15):
        snapshot = build_statistics_result_snapshot(
            "statistics_single",
            {"result": result, "value_col": "A", "n": 1},
            precision={"compute_digits": 45, "uncertainty_digits": 2},
        )

    assert snapshot is not None
    rows_by_key = {str(row["key"]): row for row in snapshot["metric_rows"]}
    assert "901234567890123456789" in str(rows_by_key["mean"]["value"])


def test_statistics_snapshot_rejects_python_float_numeric_values() -> None:
    from datalab_core.statistics import build_statistics_result_snapshot

    result = {
        "mode": "mean_sample",
        "mean": 1.25,
        "std_mean": "0.1",
        "std": "0.2",
        "v_min": "1.0",
        "v_max": "2.0",
        "method_label": "Arithmetic mean (sample)",
        "dropped": 0,
        "source_row_ids": ("1", "2"),
    }

    with pytest.raises(TypeError, match="JSON floats"):
        build_statistics_result_snapshot(
            "statistics_single",
            {"result": result, "value_col": "A", "n": 2},
            precision={"compute_digits": 30, "uncertainty_digits": 2},
        )


def test_confidence_interval_suppresses_unweighted_singleton_with_diagnostic() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={"values": ["7"], "stats_mode": "mean_sample"},
            options=JobOptions(precision_digits=50),
            request_id="stats-confidence-singleton",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert "mean_ci_lower" not in result.payload
    assert "mean_ci_n_lt_2" in result.payload["warning_codes"]
    rows_by_key = {row.key: row for row in analysis_rows_from_json(result.payload["analysis_rows"])}
    assert "mean_ci_lower" not in rows_by_key
    assert rows_by_key["warning.mean_ci_n_lt_2"].message_key == "statistics.warning.mean_ci_n_lt_2"


def test_shared_monte_carlo_distribution_summary_uses_type7_percentiles() -> None:
    from shared.distribution_summary import build_monte_carlo_distribution_summary

    with precision_guard(50):
        summary = build_monte_carlo_distribution_summary(
            sample_count=4,
            accepted_count=4,
            rejected_count=0,
            mean=mp.mpf("2.5"),
            std=mp.mpf("1.2909944487358056284"),
            accepted_samples=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")],
        )

    assert summary["schema"] == "datalab.monte_carlo_distribution_summary"
    assert summary["finite_sample_count"] == 4
    percentiles = cast(dict[str, object], summary["percentiles"])
    histogram = cast(dict[str, object], summary["histogram"])
    counts = cast(list[int], histogram["counts"])
    assert mp.almosteq(mp.mpf(str(percentiles["2.5"])), mp.mpf("1.075"))
    assert mp.almosteq(mp.mpf(str(percentiles["50"])), mp.mpf("2.5"))
    assert mp.almosteq(mp.mpf(str(percentiles["97.5"])), mp.mpf("3.925"))
    assert sum(counts) == 4


def test_statistics_bootstrap_payload_is_seeded_json_safe_and_reproducible() -> None:
    from copy import deepcopy

    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "workflow_mode": "bootstrap_confidence_intervals",
            "values": ["1", "2", "3", "4"],
            "source_row_ids": ["r1", "r2", "r3", "r4"],
            "value_column": "A",
            "target_statistic": "mean",
            "resample_count": 128,
            "seed": 12345,
        },
        options=JobOptions(precision_digits=50, parallel={"mode": "serial"}),
        request_id="stats-bootstrap-serial",
    )
    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})

    first = service.submit(request)
    second = service.submit(request)

    assert first.status is ResultStatus.SUCCEEDED
    assert second.status is ResultStatus.SUCCEEDED
    assert first.payload == second.payload
    assert first.payload["schema"] == "datalab.statistics.bootstrap.v1"
    assert first.payload["workflow_mode"] == "bootstrap_confidence_intervals"
    assert first.payload["seeded"] is True
    assert first.payload["rng_algorithm"] == "python_random_v1"
    assert first.payload["rng_schedule"] == "per_replicate_seed_v1"
    column = first.payload["columns"][0]
    assert column["value_column"] == "A"
    assert column["source_row_ids"] == ["r1", "r2", "r3", "r4"]
    assert "mean" not in column
    distribution = column["distribution"]
    assert distribution["schema"] == "datalab.monte_carlo_distribution_summary"
    assert distribution["requested_sample_count"] == 128
    assert distribution["accepted_sample_count"] == 128
    assert isinstance(distribution["mean"], str)
    assert set(distribution["percentiles"]) == {"2.5", "50", "97.5"}
    json.dumps(deepcopy(first.payload))


def test_statistics_bootstrap_reads_nested_bootstrap_config_and_rejects_conflicts() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})
    nested = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["1", "2", "3", "4"],
                "bootstrap": {
                    "target_statistic": "median",
                    "resample_count": 128,
                    "seed": 99,
                    "sample_mode": "population",
                },
            },
            options=JobOptions(precision_digits=50, parallel={"mode": "serial"}),
            request_id="stats-bootstrap-nested-config",
        )
    )

    assert nested.status is ResultStatus.SUCCEEDED
    assert nested.payload["target_statistic"] == "median"
    assert nested.payload["resample_count"] == 128
    assert nested.payload["seed"] == 99
    assert nested.payload["sample_mode"] == "population"

    conflicting = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["1", "2", "3", "4"],
                "target_statistic": "mean",
                "bootstrap": {"target_statistic": "median", "resample_count": 128},
            },
            options=JobOptions(precision_digits=50, parallel={"mode": "serial"}),
            request_id="stats-bootstrap-conflicting-config",
        )
    )

    assert conflicting.status is ResultStatus.FAILED
    assert "Conflicting bootstrap option: target_statistic" in conflicting.payload["message"]


def test_statistics_bootstrap_seeded_results_do_not_depend_on_process_parallelism() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    inputs = {
        "workflow_mode": "bootstrap_confidence_intervals",
        "values": ["1", "2", "3", "4", "5"],
        "target_statistic": "median",
        "resample_count": 128,
        "seed": 77,
    }
    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})
    serial = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs=inputs,
            options=JobOptions(precision_digits=50, parallel={"mode": "serial"}),
            request_id="stats-bootstrap-serial",
        )
    )
    process = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs=inputs,
            options=JobOptions(
                precision_digits=50,
                parallel={
                    "mode": "process",
                    "max_workers": 2,
                    "reserve_cores": 0,
                    "min_process_tasks": 1,
                },
            ),
            request_id="stats-bootstrap-process",
        )
    )

    assert serial.status is ResultStatus.SUCCEEDED
    assert process.status is ResultStatus.SUCCEEDED
    assert serial.payload["columns"][0]["distribution"] == process.payload["columns"][0]["distribution"]


@pytest.mark.parametrize(
    ("target", "sample_mode", "trim_fraction", "expected"),
    [
        ("mean", "sample", None, "3.0"),
        ("median", "sample", None, "3.0"),
        ("trimmed_mean", "sample", "0.2", "3.0"),
        ("std", "sample", None, "1.5811388300841896659994467722163592668597775696626"),
        ("variance", "population", None, "2.0"),
    ],
)
def test_statistics_bootstrap_original_statistic_matches_statistics_definitions(
    target: str,
    sample_mode: str,
    trim_fraction: str | None,
    expected: str,
) -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    inputs: dict[str, object] = {
        "workflow_mode": "bootstrap_confidence_intervals",
        "values": ["1", "2", "3", "4", "5"],
        "target_statistic": target,
        "sample_mode": sample_mode,
        "resample_count": 100,
        "seed": 11,
    }
    if trim_fraction is not None:
        inputs["trim_fraction"] = trim_fraction

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs=inputs,
            options=JobOptions(precision_digits=50, parallel={"mode": "serial"}),
            request_id=f"stats-bootstrap-{target}",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    original = mp.mpf(result.payload["columns"][0]["original_statistic"])
    assert mp.almosteq(original, mp.mpf(expected), rel_eps=mp.mpf("1e-45"))


def test_statistics_bootstrap_rejects_first_release_unsupported_confidence_level() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["1", "2", "3"],
                "target_statistic": "mean",
                "confidence_level": "0.9",
                "resample_count": 100,
                "seed": 1,
            },
            options=JobOptions(precision_digits=40),
            request_id="stats-bootstrap-invalid-confidence",
        )
    )

    assert result.status is ResultStatus.FAILED
    assert "confidence_level is fixed to 0.95" in result.payload["message"]


def test_statistics_bootstrap_validator_rejects_forged_or_float_payload_fields() -> None:
    from copy import deepcopy

    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics
    from datalab_core.statistics_bootstrap import validate_statistics_bootstrap_payload

    valid = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["1", "2", "3", "4"],
                "target_statistic": "mean",
                "resample_count": 100,
                "seed": 1,
            },
            options=JobOptions(precision_digits=40, parallel={"mode": "serial"}),
            request_id="stats-bootstrap-validator-base",
        )
    )
    base = cast(dict[str, Any], deepcopy(valid.payload))
    validate_statistics_bootstrap_payload(base)

    extra = deepcopy(base)
    extra["unexpected"] = "x"
    with pytest.raises(ValueError, match="unsupported fields"):
        validate_statistics_bootstrap_payload(extra)

    float_seed = deepcopy(base)
    float_seed["seed"] = 1.0
    with pytest.raises(TypeError, match="JSON floats"):
        validate_statistics_bootstrap_payload(float_seed)

    seeded_mismatch = deepcopy(base)
    seeded_mismatch["seed"] = None
    seeded_mismatch["seeded"] = True
    with pytest.raises(ValueError, match="seeded must match"):
        validate_statistics_bootstrap_payload(seeded_mismatch)

    float_row_id = deepcopy(base)
    float_row_id["columns"][0]["source_row_ids"][0] = 1.5
    with pytest.raises(TypeError, match="JSON floats"):
        validate_statistics_bootstrap_payload(float_row_id)

    bad_histogram = deepcopy(base)
    bad_histogram["columns"][0]["distribution"]["histogram"]["counts"][0] += 1
    with pytest.raises(ValueError, match="counts must sum"):
        validate_statistics_bootstrap_payload(bad_histogram)

    bad_units = deepcopy(base)
    bad_units["units"] = {"enabled": True, "mode": "active"}
    with pytest.raises(ValueError, match="statistics units only support display_only"):
        validate_statistics_bootstrap_payload(bad_units)


def test_statistics_bootstrap_snapshot_renders_semantic_text_csv_and_metadata() -> None:
    from copy import deepcopy

    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        build_statistics_result_snapshot,
        render_statistics_snapshot_outputs,
        run_statistics,
        statistics_csv_rows_from_analysis_rows,
        validate_statistics_bootstrap_snapshot,
    )

    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})
    first = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["1", "2", "3", "4"],
                "source_row_ids": ["a1", "a2", "a3", "a4"],
                "value_column": "A",
                "column_index": 1,
                "target_statistic": "mean",
                "resample_count": 100,
                "seed": 42,
            },
            options=JobOptions(precision_digits=50, parallel={"mode": "serial"}),
            request_id="stats-bootstrap-snapshot-a",
        )
    )
    second = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["10", "20", "30", "40"],
                "source_row_ids": ["b1", "b2", "b3", "b4"],
                "value_column": "B",
                "column_index": 2,
                "target_statistic": "mean",
                "resample_count": 100,
                "seed": 42,
            },
            options=JobOptions(precision_digits=50, parallel={"mode": "serial"}),
            request_id="stats-bootstrap-snapshot-b",
        )
    )

    assert first.status is ResultStatus.SUCCEEDED
    assert second.status is ResultStatus.SUCCEEDED
    payload = cast(dict[str, Any], deepcopy(first.payload))
    payload["columns"] = [
        deepcopy(cast(list[dict[str, object]], first.payload["columns"])[0]),
        deepcopy(cast(list[dict[str, object]], second.payload["columns"])[0]),
    ]

    snapshot = build_statistics_result_snapshot(
        "statistics_bootstrap",
        payload,
        precision={"compute_digits": 50},
    )

    assert snapshot is not None
    validate_statistics_bootstrap_snapshot(snapshot)
    json.dumps(snapshot)
    assert snapshot["mode"] == "bootstrap_confidence_intervals"
    assert snapshot["source"]["value_columns"] == ["A", "B"]
    assert snapshot["source"]["column_count"] == 2
    assert snapshot["source"]["target_statistic"] == "mean"
    assert snapshot["source"]["resample_count"] == 100
    assert snapshot["bootstrap"]["schema"] == "datalab.statistics.bootstrap.v1"

    lower_rows = [row for row in snapshot["metric_rows"] if row["key"] == "bootstrap_ci_lower"]
    assert [row["source"] for row in lower_rows] == ["A", "B"]
    assert lower_rows[0]["value"] == payload["columns"][0]["distribution"]["percentiles"]["2.5"]
    assert any(row["key"] == "bootstrap_original_statistic" for row in snapshot["metric_rows"])
    rng_schedule_rows = [row for row in snapshot["diagnostic_rows"] if row["key"] == "bootstrap_rng_schedule"]
    assert [row["source"] for row in rng_schedule_rows] == ["A", "B"]

    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, headers = rendered
    assert headers == ["column", "batch", "metric", "value", "uncertainty"]
    assert "=== Statistics: Column A ===" in text
    assert "Bootstrap CI lower" in text
    ci_rows = [row for row in csv_rows if row["metric"] == "bootstrap_ci_lower"]
    assert [(row["column"], row["value"]) for row in ci_rows] == [
        ("A", payload["columns"][0]["distribution"]["percentiles"]["2.5"]),
        ("B", payload["columns"][1]["distribution"]["percentiles"]["2.5"]),
    ]
    aggregate_csv = statistics_csv_rows_from_analysis_rows(snapshot["metric_rows"], include_batch=False)
    aggregate_ci_rows = [row for row in aggregate_csv if row["metric"] == "bootstrap_ci_lower"]
    assert [row["value"] for row in aggregate_ci_rows] == [
        payload["columns"][0]["distribution"]["percentiles"]["2.5"],
        payload["columns"][1]["distribution"]["percentiles"]["2.5"],
    ]


def test_statistics_bootstrap_snapshot_single_column_index_is_not_column_scoped() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import build_statistics_result_snapshot, render_statistics_snapshot_outputs, run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["1", "2", "3", "4"],
                "source_row_ids": ["a1", "a2", "a3", "a4"],
                "value_column": "A",
                "column_index": 1,
                "target_statistic": "mean",
                "resample_count": 100,
                "seed": 42,
            },
            options=JobOptions(precision_digits=50, parallel={"mode": "serial"}),
            request_id="stats-bootstrap-single-column-index",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    snapshot = build_statistics_result_snapshot(
        "statistics_bootstrap",
        result.payload,
        precision={"compute_digits": 50},
    )

    assert snapshot is not None
    assert snapshot["source"]["value_column"] == "A"
    assert snapshot["source"]["column_count"] == 1
    assert "column_index" not in snapshot["source"]["batches"][0]
    assert all("source" not in row for row in snapshot["metric_rows"])
    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    _text, _csv_rows, headers = rendered
    assert headers == ["batch", "metric", "value", "uncertainty"]


def test_statistics_bootstrap_snapshot_uses_bootstrap_plot_spec_key() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import build_statistics_result_snapshot, run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["1", "2", "3", "4"],
                "value_column": "A",
                "target_statistic": "mean",
                "resample_count": 100,
                "seed": 42,
            },
            options=JobOptions(precision_digits=40, parallel={"mode": "serial"}),
            request_id="stats-bootstrap-plot-key",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    snapshot = build_statistics_result_snapshot(
        "statistics_bootstrap",
        result.payload,
        precision={"compute_digits": 40},
        plot_metadata=[
            {
                "role": "statistics_bootstrap",
                "plot_key": "statistics.bootstrap_distribution",
                "column": "A",
            }
        ],
    )

    assert snapshot is not None
    assert snapshot["plot_spec_keys"] == ["statistics.bootstrap_distribution"]
    assert snapshot["plot_metadata"]["plots"][0]["plot_key"] == "statistics.bootstrap_distribution"


def test_statistics_bootstrap_snapshot_rejects_malformed_distribution() -> None:
    from copy import deepcopy

    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.session import SessionService
    from datalab_core.statistics import build_statistics_result_snapshot, run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["1", "2", "3", "4"],
                "target_statistic": "mean",
                "resample_count": 100,
                "seed": 9,
            },
            options=JobOptions(precision_digits=40, parallel={"mode": "serial"}),
            request_id="stats-bootstrap-snapshot-bad-distribution",
        )
    )
    payload = cast(dict[str, Any], deepcopy(result.payload))
    payload["columns"][0]["distribution"]["percentiles"]["2.5"] = "999"

    with pytest.raises(ValueError, match="percentiles must be ordered"):
        build_statistics_result_snapshot("statistics_bootstrap", payload)


def test_statistics_bootstrap_snapshot_validation_binds_rows_to_embedded_payload() -> None:
    from copy import deepcopy

    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        build_statistics_result_snapshot,
        render_statistics_snapshot_outputs,
        run_statistics,
        validate_statistics_bootstrap_snapshot,
    )

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "workflow_mode": "bootstrap_confidence_intervals",
                "values": ["1", "2", "3", "4"],
                "target_statistic": "mean",
                "resample_count": 100,
                "seed": 3,
            },
            options=JobOptions(precision_digits=40, parallel={"mode": "serial"}),
            request_id="stats-bootstrap-snapshot-row-binding",
        )
    )
    snapshot = build_statistics_result_snapshot("statistics_bootstrap", result.payload)
    assert snapshot is not None

    tampered_batch = deepcopy(snapshot)
    tampered_batch["batches"][0]["metric_rows"][2]["value"] = "999"
    with pytest.raises(ValueError, match="rows do not match"):
        validate_statistics_bootstrap_snapshot(tampered_batch)
    with pytest.raises(ValueError, match="rows do not match"):
        render_statistics_snapshot_outputs(tampered_batch)

    tampered_root = deepcopy(snapshot)
    tampered_root["metric_rows"][2]["value"] = "999"
    with pytest.raises(ValueError, match="top-level rows do not match"):
        validate_statistics_bootstrap_snapshot(tampered_root)


def test_statistics_bootstrap_checks_cancellation_during_resampling(monkeypatch: pytest.MonkeyPatch) -> None:
    from datalab_core.session import CoreJobCancelled
    from datalab_core.statistics_bootstrap import StatisticsBootstrapOptions, run_statistics_bootstrap
    import datalab_core.statistics_bootstrap as statistics_bootstrap

    calls = 0

    def fake_check_cancelled() -> None:
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise CoreJobCancelled("cancelled in test")

    monkeypatch.setattr(statistics_bootstrap, "check_cancelled", fake_check_cancelled)

    with pytest.raises(CoreJobCancelled):
        run_statistics_bootstrap(
            values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")],
            source_row_ids=None,
            precision_digits=40,
            options=StatisticsBootstrapOptions(
                target_statistic="mean",
                confidence_level="0.95",
                resample_count=2000,
                seed=1,
                sample_mode="sample",
                trim_fraction=None,
            ),
            parallel_config=None,
        )
    assert calls >= 2


def test_weighted_known_sigma_confidence_interval_singleton_disabled_variance_and_zero_anchor() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})
    weighted = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["7"],
                "sigmas": ["2"],
                "stats_mode": "weighted_sigma",
                "use_weighted_variance": False,
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-weighted-confidence-singleton",
        )
    )

    assert weighted.status is ResultStatus.SUCCEEDED
    assert weighted.payload["mean_ci_method_label"] == "Known-sigma weighted normal CI"
    assert weighted.payload["weighted_se_known_sigma"] == "2.0"
    assert weighted.payload["mean_ci_lower"].startswith("3.08007203091989")
    assert weighted.payload["mean_ci_upper"].startswith("10.9199279690801")
    assert "mean_ci_dof" not in weighted.payload

    zero_anchor = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["7"],
                "sigmas": ["0"],
                "stats_mode": "weighted_sigma",
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-weighted-confidence-zero-anchor",
        )
    )

    assert zero_anchor.status is ResultStatus.SUCCEEDED
    assert zero_anchor.payload["zero_sigma_anchor"] is True
    assert "mean_ci_lower" not in zero_anchor.payload
    assert zero_anchor.payload["warning_codes"] == ["zero_sigma_anchor"]


def test_analysis_row_json_roundtrip_preserves_stable_keys_and_optional_fields() -> None:
    from datalab_core.results import AnalysisRow, analysis_row_from_json

    row = AnalysisRow(
        key="mean",
        label_key="statistics.metric.mean",
        value="1.234567890123456789",
        uncertainty="0.000000000000000001",
        source="A",
        row_index=7,
        method="mean_sample",
    )

    payload = row.to_json()

    assert payload == {
        "key": "mean",
        "label_key": "statistics.metric.mean",
        "severity": "info",
        "render_group": "metric",
        "value": "1.234567890123456789",
        "uncertainty": "0.000000000000000001",
        "source": "A",
        "row_index": 7,
        "method": "mean_sample",
    }
    assert analysis_row_from_json(payload) == row


def test_analysis_row_omits_unused_optional_fields_from_json() -> None:
    from datalab_core.results import AnalysisRow

    payload = AnalysisRow(key="row_count", label_key="statistics.metric.row_count", value=3).to_json()

    assert payload == {
        "key": "row_count",
        "label_key": "statistics.metric.row_count",
        "severity": "info",
        "render_group": "metric",
        "value": 3,
    }


def test_analysis_warning_row_uses_semantic_message_key_not_localized_text() -> None:
    from datalab_core.results import AnalysisRow, analysis_row_from_json

    payload = AnalysisRow(
        key="warning.zero_sigma_anchor",
        label_key="statistics.warning",
        severity="warning",
        message_key="statistics.warning.zero_sigma_anchor",
        render_group="diagnostic",
        method="weighted_sigma",
    ).to_json()

    assert payload["message_key"] == "statistics.warning.zero_sigma_anchor"
    assert "message" not in payload
    assert "Detected" not in repr(payload)
    assert "检测" not in repr(payload)
    assert analysis_row_from_json(payload).severity == "warning"


@pytest.mark.parametrize(
    "field,payload",
    [
        ("value", {"key": "mean", "label_key": "statistics.metric.mean", "value": 1.25}),
        (
            "uncertainty",
            {"key": "mean", "label_key": "statistics.metric.mean", "uncertainty": 0.01},
        ),
        (
            "row_index",
            {"key": "source", "label_key": "statistics.source", "row_index": 2.0},
        ),
    ],
)
def test_analysis_row_rejects_json_float_payloads(field: str, payload: dict[str, object]) -> None:
    from datalab_core.results import analysis_row_from_json

    with pytest.raises(TypeError, match=f"JSON floats are not allowed at {field}"):
        analysis_row_from_json(payload)


def test_analysis_rows_from_json_rejects_unknown_fields() -> None:
    from datalab_core.results import analysis_row_from_json

    with pytest.raises(ValueError, match="unsupported fields: label"):
        analysis_row_from_json(
            {
                "key": "mean",
                "label_key": "statistics.metric.mean",
                "label": "Mean",
            }
        )


def test_analysis_rows_from_json_rejects_non_sequence_roots_clearly() -> None:
    from datalab_core.results import analysis_rows_from_json

    with pytest.raises(TypeError, match="not a mapping"):
        analysis_rows_from_json({"key": "mean", "label_key": "statistics.metric.mean"})

    with pytest.raises(TypeError, match="must be a sequence of mappings"):
        analysis_rows_from_json(1)

    with pytest.raises(TypeError, match="must be a sequence of mappings"):
        analysis_rows_from_json("[]")


def test_analysis_row_module_keeps_core_import_hygiene() -> None:
    source_path = Path(__file__).resolve().parents[1] / "datalab_core" / "results.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_roots = {
        "app_desktop",
        "app_web",
        "PySide6",
        "flask",
        "matplotlib",
        "statistics_utils",
    }
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".", 1)[0])

    assert imports.isdisjoint(forbidden_roots)


def test_statistics_warning_rows_use_stable_warning_codes_not_prose_matching() -> None:
    from datalab_core.statistics import _STATISTICS_WARNING_MESSAGE_KEYS, statistics_analysis_rows_from_payload

    payload = {
        "mode": "weighted_sigma",
        "row_count": 2,
        "mean": "1.0",
        "std_mean": "0.0",
        "std": "0.0",
        "min": "1.0",
        "max": "1.0",
        "dropped": 0,
        "effective_n": None,
        "zero_sigma_anchor": False,
    }

    rows = statistics_analysis_rows_from_payload(
        payload,
        warning_codes=tuple(_STATISTICS_WARNING_MESSAGE_KEYS),
    )
    warning_rows = [row for row in rows if row.severity == "warning"]

    assert {row.message_key for row in warning_rows} == set(_STATISTICS_WARNING_MESSAGE_KEYS.values())
    assert all(row.value for row in warning_rows)
    assert not any(str(row.value).startswith("statistics.warning.") for row in warning_rows)
    assert {row.key for row in warning_rows} == {
        message_key.removeprefix("statistics.")
        for message_key in _STATISTICS_WARNING_MESSAGE_KEYS.values()
    }

    generic_rows = statistics_analysis_rows_from_payload(payload, warnings=("Detected σ=0; treated as infinite weight.",))
    generic_warning_rows = [row for row in generic_rows if row.severity == "warning"]
    assert [row.message_key for row in generic_warning_rows] == ["statistics.warning.generic"]
    assert [row.value for row in generic_warning_rows] == ["Detected σ=0; treated as infinite weight."]

    partial_rows = statistics_analysis_rows_from_payload(
        payload,
        warnings=("first legacy warning", "second legacy warning"),
        warning_codes=("zero_sigma_anchor",),
    )
    partial_warning_rows = [row for row in partial_rows if row.severity == "warning"]
    assert [row.message_key for row in partial_warning_rows] == [
        "statistics.warning.zero_sigma_anchor",
        "statistics.warning.generic",
    ]
    assert [row.value for row in partial_warning_rows] == ["first legacy warning", "second legacy warning"]


def test_descriptive_statistics_reference_values_sample_and_population() -> None:
    from datalab_core.statistics_compute import compute_statistics

    values = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
    sample = compute_statistics(values, [None] * len(values), "descriptive", use_sample=True)
    population = compute_statistics(values, [None] * len(values), "descriptive", use_sample=False)

    assert sample["count"] == 4
    assert sample["mean"] == mp.mpf("2.5")
    assert mp.almosteq(sample["variance"], mp.mpf("5") / 3)
    assert mp.almosteq(sample["std"], mp.sqrt(mp.mpf("5") / 3))
    assert mp.almosteq(sample["std_mean"], mp.sqrt(mp.mpf("5") / 3) / 2)
    assert sample["q1"] == mp.mpf("1.75")
    assert sample["median"] == mp.mpf("2.5")
    assert sample["q3"] == mp.mpf("3.25")
    assert sample["iqr"] == mp.mpf("1.5")
    assert sample["mad"] == mp.mpf("1")
    assert sample["skewness"] == mp.mpf("0")
    assert mp.almosteq(sample["excess_kurtosis"], mp.mpf("-1.2"))
    assert sample["warning_codes"] == []

    assert mp.almosteq(population["variance"], mp.mpf("1.25"))
    assert mp.almosteq(population["std"], mp.sqrt(mp.mpf("1.25")))
    assert mp.almosteq(population["std_mean"], mp.sqrt(mp.mpf("1.25")) / 2)
    assert population["skewness"] == mp.mpf("0")
    assert mp.almosteq(population["excess_kurtosis"], mp.mpf("-1.36"))
    assert population["method_label"] == "Descriptive statistics (population)"


def test_descriptive_trimmed_mean_disabled_keeps_default_output_absent() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics, statistics_csv_rows_from_result, statistics_payload_to_compute_result
    from datalab_core.statistics_compute import compute_statistics

    values = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
    omitted = compute_statistics(values, [None] * len(values), "descriptive")
    blank = compute_statistics(values, [None] * len(values), "descriptive", trim_fraction="")
    zero = compute_statistics(values, [None] * len(values), "descriptive", trim_fraction="0")

    assert "trimmed_mean" not in omitted
    assert blank.keys() == omitted.keys()
    assert zero.keys() == omitted.keys()

    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})
    for trim_fraction in (None, "", "0"):
        inputs = {"values": ["1", "2", "3", "4"], "stats_mode": "descriptive"}
        if trim_fraction is not None:
            inputs["trim_fraction"] = trim_fraction
        result = service.submit(
            ComputeJobRequest(
                mode=JobMode.STATISTICS,
                inputs=inputs,
                options=JobOptions(precision_digits=60),
                request_id=f"trim-disabled-{trim_fraction!r}",
            )
        )

        assert result.status is ResultStatus.SUCCEEDED
        assert "trimmed_mean" not in result.payload
        roundtrip = statistics_payload_to_compute_result(result.payload, result.warnings)
        assert "trimmed_mean" not in roundtrip
        metrics = {str(row["metric"]) for row in statistics_csv_rows_from_result(roundtrip, row_count=4)}
        assert "trimmed_mean" not in metrics


@pytest.mark.parametrize(
    ("trim_fraction", "message"),
    [
        ("-0.1", "non-negative|负数"),
        ("nan", "finite|有限"),
        ("inf", "finite|有限"),
        ("abc", "valid number|有效数字"),
        ("0.5", "too large|过大"),
    ],
)
def test_descriptive_trim_fraction_validation(trim_fraction: str, message: str) -> None:
    from datalab_core.statistics_compute import compute_statistics

    with pytest.raises(ValueError, match=message):
        compute_statistics(
            [mp.mpf("1"), mp.mpf("2")],
            [None, None],
            "descriptive",
            trim_fraction=trim_fraction,
        )


def test_descriptive_trimmed_mean_reference_fixtures() -> None:
    from datalab_core.statistics_compute import compute_statistics

    symmetric = compute_statistics(
        [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4"), mp.mpf("100")],
        [None] * 5,
        "descriptive",
        trim_fraction="0.2",
    )
    asymmetric = compute_statistics(
        [mp.mpf("1"), mp.mpf("2"), mp.mpf("100"), mp.mpf("101"), mp.mpf("102")],
        [None] * 5,
        "descriptive",
        trim_fraction="0.2",
    )
    positive_without_removed_tail = compute_statistics(
        [mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        [None] * 3,
        "descriptive",
        trim_fraction="0.1",
    )

    assert symmetric["trimmed_mean"] == mp.mpf("3")
    assert asymmetric["trimmed_mean"] == mp.mpf(203) / 3
    assert positive_without_removed_tail["trimmed_mean"] == positive_without_removed_tail["mean"]


@pytest.mark.parametrize(
    "values,expected_codes,finite_keys,nan_keys",
    [
        (
            [mp.mpf("7")],
            {
                "descriptive_sample_variance_n_lt_2",
                "descriptive_sample_skewness_n_lt_3",
                "descriptive_sample_kurtosis_n_lt_4",
                "descriptive_zero_variance",
            },
            {"mean", "median", "q1", "q3", "iqr", "mad"},
            {"variance", "std", "std_mean", "skewness", "excess_kurtosis"},
        ),
        (
            [mp.mpf("1"), mp.mpf("3")],
            {
                "descriptive_sample_skewness_n_lt_3",
                "descriptive_sample_kurtosis_n_lt_4",
            },
            {"variance", "std", "std_mean", "median"},
            {"skewness", "excess_kurtosis"},
        ),
        (
            [mp.mpf("1"), mp.mpf("2"), mp.mpf("4")],
            {"descriptive_sample_kurtosis_n_lt_4"},
            {"variance", "std", "std_mean", "skewness"},
            {"excess_kurtosis"},
        ),
    ],
)
def test_descriptive_statistics_sample_small_n_diagnostics(
    values: list[mp.mpf],
    expected_codes: set[str],
    finite_keys: set[str],
    nan_keys: set[str],
) -> None:
    from datalab_core.statistics_compute import compute_statistics

    result = compute_statistics(values, [None] * len(values), "descriptive", use_sample=True)

    assert expected_codes <= set(result["warning_codes"])
    for key in finite_keys:
        assert not mp.isnan(mp.mpf(result[key]))
    for key in nan_keys:
        assert mp.isnan(mp.mpf(result[key]))


def test_descriptive_population_singleton_reports_zero_variance_moment_diagnostic() -> None:
    from datalab_core.statistics_compute import compute_statistics

    result = compute_statistics([mp.mpf("7")], [None], "descriptive", use_sample=False)

    assert result["variance"] == mp.mpf("0")
    assert result["std"] == mp.mpf("0")
    assert result["std_mean"] == mp.mpf("0")
    assert mp.isnan(result["skewness"])
    assert mp.isnan(result["excess_kurtosis"])
    assert result["warning_codes"] == ["descriptive_zero_variance", "mean_ci_n_lt_2"]


def test_descriptive_zero_variance_keeps_location_and_dispersion_but_not_moments() -> None:
    from datalab_core.statistics_compute import compute_statistics

    result = compute_statistics([mp.mpf("5"), mp.mpf("5"), mp.mpf("5"), mp.mpf("5")], [None] * 4, "descriptive")

    assert result["mean"] == mp.mpf("5")
    assert result["median"] == mp.mpf("5")
    assert result["variance"] == mp.mpf("0")
    assert result["std"] == mp.mpf("0")
    assert result["mad"] == mp.mpf("0")
    assert mp.isnan(result["skewness"])
    assert mp.isnan(result["excess_kurtosis"])
    assert result["warning_codes"] == ["descriptive_zero_variance"]


@pytest.mark.parametrize("bad_value", ["nan", "inf", "-inf"])
def test_descriptive_statistics_rejects_non_finite_values_directly(bad_value: str) -> None:
    from datalab_core.statistics_compute import compute_statistics

    values = [mp.mpf("1"), mp.mpf(bad_value), mp.mpf("2")]

    with pytest.raises(ValueError, match="finite|有限"):
        compute_statistics(values, [None] * len(values), "descriptive")


@pytest.mark.parametrize("bad_value", ["nan", "inf", "-inf"])
def test_core_statistics_handler_rejects_descriptive_non_finite_values(bad_value: str) -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["1", bad_value, "2"],
                "stats_mode": "descriptive",
            },
            options=JobOptions(precision_digits=60),
            request_id=f"descriptive-nonfinite-{bad_value}",
        )
    )

    assert result.status is ResultStatus.FAILED
    assert "finite" in result.payload["message"]


def test_statistics_result_snapshot_schema_is_json_safe_and_semantic() -> None:
    from datalab_core.results import AnalysisRow
    from datalab_core.statistics import build_statistics_result_snapshot

    result = {
        "mode": "weighted_sigma",
        "mean": mp.mpf("1.25"),
        "std_mean": mp.mpf("0"),
        "std": mp.mpf("0"),
        "v_min": mp.mpf("1.25"),
        "v_max": mp.mpf("2.5"),
        "method_label": "Weighted mean (sigma=0 anchor)",
        "dropped": 1,
        "effective_n": mp.mpf("1"),
        "zero_sigma_anchor": True,
        "warnings": ["Detected zero sigma."],
        "source_row_ids": ("line-10", "line-11"),
        "analysis_rows": [
            AnalysisRow(
                key="mean",
                label_key="statistics.metric.mean",
                value="1.25",
                uncertainty="0",
                method="weighted_sigma",
            ).to_json(),
            AnalysisRow(
                key="zero_sigma_anchor",
                label_key="statistics.flag.zero_sigma_anchor",
                value="true",
                method="weighted_sigma",
                render_group="row_flag",
            ).to_json(),
            AnalysisRow(
                key="warning.zero_sigma_anchor",
                label_key="statistics.warning",
                severity="warning",
                message_key="statistics.warning.zero_sigma_anchor",
                render_group="diagnostic",
                method="weighted_sigma",
            ).to_json(),
        ],
    }

    snapshot = build_statistics_result_snapshot(
        "statistics_single",
        {"result": result, "value_col": "A", "n": 2},
        overview_state="complete",
        plot_metadata=[{"path": "attachments/plots/plot-001.png", "format": "png", "order": 0}],
        precision={
            "compute_digits": 80,
            "display_digits": 12,
            "uncertainty_digits": 2,
            "latex_input_digits": 20,
        },
    )

    assert snapshot is not None
    json.dumps(snapshot)
    assert snapshot["schema_version"] == 1
    assert snapshot["family"] == "statistics"
    assert snapshot["mode"] == "weighted_sigma"
    assert snapshot["metric_rows"][0]["key"] == "mean"
    assert snapshot["diagnostic_rows"][0]["message_key"] == "statistics.warning.zero_sigma_anchor"
    assert snapshot["row_flags"][0]["key"] == "zero_sigma_anchor"
    assert snapshot["warnings"] == ["Detected zero sigma."]
    assert snapshot["plot_spec_keys"] == ["statistics.series_with_mean"]
    assert snapshot["source"]["source_row_ids"] == ["line-10", "line-11"]
    assert snapshot["precision"]["compute_digits"] == 80
    assert snapshot["compatibility"]["rendered_caches_authoritative"] is False
    assert snapshot["compatibility"]["latex_regeneration"] == "cache_only_until_p0_5_shared_latex"


def test_core_statistics_request_builder_creates_string_batches_through_session() -> None:
    from datalab_core.jobs import JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        build_statistics_requests,
        build_statistics_result_snapshot,
        render_statistics_snapshot_outputs,
        run_statistics,
        statistics_csv_rows_from_analysis_rows,
        statistics_payload_to_compute_result,
    )

    batches = build_statistics_requests(
        headers=("A", "sigma"),
        rows=(
            ("1.0000000000000000001", "0.10000000000000000001"),
            ("2.0000000000000000002", "0.2"),
            ("3.0000000000000000003", "0.3"),
        ),
        value_col="A",
        sigma_col="sigma",
        stats_mode="weighted_sigma",
        precision_digits=80,
        segments=((-5, 2), (2, 99), (3, 3)),
        request_id_prefix="stats-batch",
        units={
            "enabled": True,
            "mode": "display_only",
            "inputs": {"A": {"unit": "m"}, "sigma": {"unit": "m"}},
            "outputs": {"mean": {"unit": "m"}, "std_mean": {"unit": "m"}},
        },
    )

    assert [batch.index for batch in batches] == [1, 2]
    assert [batch.row_count for batch in batches] == [2, 1]
    assert batches[0].request.request_id == "stats-batch-1"
    assert batches[0].request.mode is JobMode.STATISTICS
    assert list(batches[0].request.inputs["values"]) == [
        "1.0000000000000000001",
        "2.0000000000000000002",
    ]
    assert list(batches[0].request.inputs["sigmas"]) == ["0.10000000000000000001", "0.2"]
    assert list(batches[0].request.inputs["source_row_ids"]) == ["1", "2"]
    assert batches[0].request.inputs["headers"] == ("A", "sigma")
    assert batches[0].request.inputs["value_col"] == "A"
    assert batches[0].request.inputs["sigma_col"] == "sigma"
    assert batches[0].request.inputs["units"]["inputs"] == {"A": {"unit": "m"}, "sigma": {"unit": "m"}}
    assert list(batches[1].request.inputs["source_row_ids"]) == ["3"]
    assert batches[0].source_row_ids == ("1", "2")
    assert batches[1].source_row_ids == ("3",)

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(batches[0].request)

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["row_count"] == 2
    assert result.payload["mode"] == "weighted_sigma"
    assert list(result.payload["source_row_ids"]) == ["1", "2"]
    assert result.payload["units"]["outputs"] == {"mean": {"unit": "m"}, "std_mean": {"unit": "m"}}
    snapshot = build_statistics_result_snapshot(
        "statistics_single",
        {
            "result": statistics_payload_to_compute_result(result.payload, result.warnings),
            "value_col": "A",
            "n": 2,
            "units": result.payload["units"],
        },
    )
    assert snapshot is not None
    assert snapshot["units"]["inputs"] == {"A": {"unit": "m"}, "sigma": {"unit": "m"}}

    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, headers = rendered
    assert "Metric | Value | Value unit | Uncertainty | Uncertainty unit" in text
    assert headers == ["batch", "metric", "value", "uncertainty", "value_unit", "uncertainty_unit"]
    mean_rows = [row for row in csv_rows if row["metric"] == "mean"]
    assert mean_rows
    assert mean_rows[0]["value_unit"] == "m"
    assert mean_rows[0]["uncertainty_unit"] == "m"

    aggregate_rows = statistics_csv_rows_from_analysis_rows(
        snapshot["metric_rows"],
        include_batch=False,
        units=snapshot["units"],
    )
    aggregate_mean = [row for row in aggregate_rows if row["metric"] == "mean"][0]
    assert aggregate_mean["value_unit"] == "m"
    assert aggregate_mean["uncertainty_unit"] == "m"


def test_core_statistics_rejects_active_unit_modes_before_computation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core import statistics

    def fail_if_called(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("statistics computation should not run before unit mode validation")

    monkeypatch.setattr(statistics, "compute_statistics", fail_if_called)
    request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "values": ("1", "2"),
            "units": {
                "enabled": True,
                "mode": "validate_expression",
                "inputs": {"values": {"unit": "m"}},
            },
        },
        options=JobOptions(precision_digits=50),
        request_id="stats-active-units",
    )

    with pytest.raises(ValueError, match="statistics units only support display_only"):
        statistics.run_statistics(request)


def test_core_statistics_units_do_not_expose_internal_sigmas_key_when_columns_exist() -> None:
    from datalab_core.statistics import build_statistics_requests

    with pytest.raises(ValueError, match="inputs annotation key 'sigmas' is not a canonical symbol"):
        build_statistics_requests(
            headers=("A", "sigma"),
            rows=(("1", "0.1"), ("2", "0.2")),
            value_col="A",
            sigma_col="sigma",
            units={
                "enabled": True,
                "mode": "display_only",
                "inputs": {"sigmas": {"unit": "m"}},
            },
        )


def test_core_statistics_input_only_units_do_not_change_text_or_csv_shape() -> None:
    from datalab_core.jobs import JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        build_statistics_requests,
        build_statistics_result_snapshot,
        render_statistics_snapshot_outputs,
        run_statistics,
        statistics_csv_rows_from_analysis_rows,
        statistics_payload_to_compute_result,
    )

    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})
    request = build_statistics_requests(
        headers=("A",),
        rows=(("1",), ("2",), ("3",)),
        value_col="A",
        units={
            "enabled": True,
            "mode": "display_only",
            "inputs": {"A": {"unit": "m"}},
        },
    )[0].request
    result = service.submit(request)

    assert result.status is ResultStatus.SUCCEEDED
    snapshot = build_statistics_result_snapshot(
        "statistics_single",
        {
            "result": statistics_payload_to_compute_result(result.payload, result.warnings),
            "value_col": "A",
            "units": result.payload["units"],
        },
    )
    assert snapshot is not None

    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, headers = rendered
    assert "Metric | Value | Uncertainty" in text
    assert "Value unit" not in text
    assert headers == ["batch", "metric", "value", "uncertainty"]
    assert "value_unit" not in csv_rows[0]

    aggregate_rows = statistics_csv_rows_from_analysis_rows(
        snapshot["metric_rows"],
        include_batch=False,
        units=snapshot["units"],
    )
    assert "value_unit" not in aggregate_rows[0]


def test_statistics_output_unit_helpers_map_values_and_uncertainties() -> None:
    from datalab_core.statistics import (
        statistics_output_uncertainty_unit,
        statistics_output_value_unit,
        statistics_units_have_output_annotations,
    )

    units = {
        "enabled": True,
        "mode": "display_only",
        "outputs": {
            "mean": {"unit": "m"},
            "std_mean": {"unit": "cm"},
            "result": {"unit": "fallback"},
        },
    }

    assert statistics_units_have_output_annotations(units) is True
    assert statistics_units_have_output_annotations({"inputs": {"A": {"unit": "m"}}}) is False
    assert statistics_output_value_unit(units, "mean") == "m"
    assert statistics_output_uncertainty_unit(units, "mean") == "cm"
    assert statistics_output_value_unit(units, "unknown") == ""


def test_core_multi_column_statistics_requests_preserve_order_and_match_single_column_runs() -> None:
    from datalab_core.jobs import JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        build_multi_column_statistics_requests,
        build_statistics_requests,
        normalize_statistics_value_columns,
        run_statistics,
    )

    headers = ("A", "B", "sigma")
    rows = (
        ("1.0", "10.0", "0.1"),
        ("2.0", "20.0", "0.2"),
        ("3.0", "30.0", "0.3"),
    )

    assert normalize_statistics_value_columns(value_columns="B, A", headers=headers) == ("B", "A")
    with pytest.raises(ValueError, match="Duplicate statistics value column"):
        normalize_statistics_value_columns(value_columns=("A", "A"), headers=headers)
    with pytest.raises(ValueError, match="Column not found: Z"):
        normalize_statistics_value_columns(value_columns=("Z",), headers=headers)

    grouped = build_multi_column_statistics_requests(
        headers=headers,
        rows=rows,
        value_columns="B, A",
        sigma_col="sigma",
        stats_mode="weighted_sigma",
        precision_digits=60,
        request_id_prefix="stats-multi",
    )

    assert [(group.column_index, group.value_col) for group in grouped] == [(1, "B"), (2, "A")]
    assert [group.batches[0].request.request_id for group in grouped] == ["stats-multi-c1-1", "stats-multi-c2-1"]
    assert list(grouped[0].batches[0].request.inputs["values"]) == ["10.0", "20.0", "30.0"]
    assert list(grouped[1].batches[0].request.inputs["values"]) == ["1.0", "2.0", "3.0"]
    assert list(grouped[0].batches[0].request.inputs["sigmas"]) == ["0.1", "0.2", "0.3"]

    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})
    multi_b = service.submit(grouped[0].batches[0].request)
    single_b = service.submit(
        build_statistics_requests(
            headers=headers,
            rows=rows,
            value_col="B",
            sigma_col="sigma",
            stats_mode="weighted_sigma",
            precision_digits=60,
        )[0].request
    )

    assert multi_b.status is ResultStatus.SUCCEEDED
    assert single_b.status is ResultStatus.SUCCEEDED
    assert multi_b.payload["mean"] == single_b.payload["mean"]
    assert multi_b.payload["std_mean"] == single_b.payload["std_mean"]


def test_core_statistics_request_builder_preserves_negative_sigmas_for_core_error() -> None:
    from datalab_core.jobs import JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import build_statistics_requests, run_statistics

    explicit_batches = build_statistics_requests(
        headers=("A", "sigma"),
        rows=(("1.0", "-0.1"), ("2.0", "0.2")),
        value_col="A",
        sigma_col="sigma",
        stats_mode="weighted_sigma",
        precision_digits=50,
        request_id_prefix="stats-negative-explicit-sigma",
    )
    sigma_row_batches = build_statistics_requests(
        headers=("A",),
        rows=(("1.0",), ("2.0",)),
        sigma_rows=((mp.mpf("-0.1"),), (mp.mpf("0.2"),)),
        value_col="A",
        stats_mode="weighted_sigma",
        precision_digits=50,
        request_id_prefix="stats-negative-sigma-row",
    )

    assert list(explicit_batches[0].request.inputs["sigmas"]) == ["-0.1", "0.2"]
    assert list(sigma_row_batches[0].request.inputs["sigmas"]) == ["-0.1", "0.2"]

    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})
    for batch in (explicit_batches[0], sigma_row_batches[0]):
        result = service.submit(batch.request)
        assert result.status is ResultStatus.FAILED
        assert "Negative uncertainty" in result.payload["message"]


def test_core_statistics_request_builder_uses_sigma_rows_when_no_sigma_column() -> None:
    from datalab_core.statistics import build_statistics_requests

    class _Uncertain:
        def __init__(self, uncertainty: str) -> None:
            self.uncertainty = mp.mpf(uncertainty)

    batches = build_statistics_requests(
        headers=("A",),
        rows=((mp.mpf("1.5"),), (mp.mpf("2.5"),)),
        sigma_rows=((_Uncertain("0.05"),), (None,)),
        value_col="A",
        stats_mode="mean_sample",
    )

    assert list(batches[0].request.inputs["values"]) == ["1.5", "2.5"]
    assert list(batches[0].request.inputs["sigmas"]) == ["0.05", None]


def test_core_statistics_request_builder_accepts_explicit_source_row_ids() -> None:
    from datalab_core.statistics import build_statistics_requests

    batches = build_statistics_requests(
        headers=("A",),
        rows=(("1",), ("2",), ("3",)),
        value_col="A",
        segments=((1, 3),),
        source_row_ids=("line-10", "line-20", "line-30"),
    )

    assert list(batches[0].request.inputs["source_row_ids"]) == ["line-20", "line-30"]
    assert batches[0].source_row_ids == ("line-20", "line-30")


def test_core_statistics_request_builder_rejects_bytes_source_row_ids() -> None:
    from datalab_core.statistics import build_statistics_requests

    with pytest.raises(ValueError, match="source_row_ids must be a list"):
        build_statistics_requests(
            headers=("A",),
            rows=(("1",), ("2",)),
            value_col="A",
            source_row_ids=b"12",
        )


def test_core_statistics_request_builder_rejects_binary_float_inputs() -> None:
    from datalab_core.statistics import build_statistics_requests

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        build_statistics_requests(
            headers=("A",),
            rows=((1.25,),),
            value_col="A",
        )


@pytest.mark.parametrize("segment", [(("0", 1),), ((True, 2),), ((0.0, 1),)])
def test_core_statistics_request_builder_rejects_non_integer_segment_bounds(
    segment: tuple[tuple[object, int], ...],
) -> None:
    from datalab_core.statistics import build_statistics_requests

    with pytest.raises(TypeError):
        build_statistics_requests(
            headers=("A",),
            rows=(("1",), ("2",)),
            value_col="A",
            segments=cast(Any, segment),
        )


@pytest.mark.parametrize("precision_digits", [80.0, True])
def test_core_statistics_request_builder_rejects_malformed_precision_before_payload_formatting(
    monkeypatch: pytest.MonkeyPatch,
    precision_digits: object,
) -> None:
    from datalab_core import statistics

    def fail_if_called(*_args: object, **_kwargs: object) -> str:
        raise AssertionError("payload formatting should not run before precision validation")

    monkeypatch.setattr(statistics, "_numeric_to_payload_string", fail_if_called)

    with pytest.raises(TypeError):
        statistics.build_statistics_requests(
            headers=("A",),
            rows=(("1",),),
            value_col="A",
            precision_digits=cast(Any, precision_digits),
        )


def test_core_statistics_request_builder_preserves_preparsed_mpf_precision() -> None:
    from datalab_core.statistics import build_statistics_requests

    with precision_guard(80):
        value = mp.mpf("1.0000000000000000001")

    batches = build_statistics_requests(
        headers=("A",),
        rows=((value,),),
        value_col="A",
        precision_digits=80,
    )

    assert list(batches[0].request.inputs["values"]) == ["1.0000000000000000001"]


def test_core_statistics_request_builder_does_not_clamp_high_precision_mpf_to_default() -> None:
    from datalab_core.statistics import build_statistics_requests

    text = "1.12345678901234567890123456789012345678901234567890123456789"
    with precision_guard(90):
        value = mp.mpf(text)

    batches = build_statistics_requests(
        headers=("A",),
        rows=((value,),),
        value_col="A",
    )

    assert list(batches[0].request.inputs["values"]) == [text]


def test_core_statistics_request_builder_preserves_signed_infinite_sigma_text() -> None:
    from datalab_core.statistics import build_statistics_requests

    batches = build_statistics_requests(
        headers=("A", "sigma"),
        rows=(("1", "-inf"), ("2", "+Infinity")),
        value_col="A",
        sigma_col="sigma",
    )

    assert list(batches[0].request.inputs["sigmas"]) == ["-inf", "+Infinity"]


def test_core_statistics_request_builder_preserves_signed_sigma_rows() -> None:
    from datalab_core.statistics import build_statistics_requests

    batches = build_statistics_requests(
        headers=("A",),
        rows=(("1",), ("2",)),
        sigma_rows=(("-0.05",), (mp.mpf("-0.10"),)),
        value_col="A",
    )

    assert list(batches[0].request.inputs["sigmas"]) == ["-0.05", "-0.1"]


def test_core_statistics_request_builder_validates_columns_and_empty_segments() -> None:
    from datalab_core.statistics import build_statistics_requests

    with pytest.raises(ValueError, match="Column not found"):
        build_statistics_requests(headers=("A",), rows=((mp.mpf("1"),),), value_col="B")

    with pytest.raises(ValueError, match="at least one value"):
        build_statistics_requests(headers=("A",), rows=((mp.mpf("1"),),), value_col="A", segments=((1, 1),))


def test_core_statistics_handler_runs_arithmetic_mean_through_session() -> None:
    from datalab_core.results import analysis_rows_from_json
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultKind, ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "values": ["1.0000000000000000001", "2.0000000000000000002", "3.0000000000000000003"],
            "stats_mode": "mean_sample",
            "use_sample": True,
        },
        options=JobOptions(precision_digits=80, uncertainty_digits=2),
        request_id="stats-mean",
    )
    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})

    result = service.submit(request)

    assert result.kind is ResultKind.TABLE
    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mode"] == "mean_sample"
    assert result.payload["row_count"] == 3
    assert result.payload["precision_used"] == 80
    assert result.payload["mean"] == "2.0000000000000000002"
    assert result.payload["std"] == "1.0000000000000000001"
    assert result.payload["std_mean"].startswith("0.5773502691896257645")
    assert result.payload["method_label"] == "Arithmetic mean (sample)"
    rows = analysis_rows_from_json(result.payload["analysis_rows"])
    rows_by_key = {row.key: row for row in rows}
    assert {
        "method",
        "row_count",
        "mean",
        "std_mean",
        "mean_ci_lower",
        "mean_ci_upper",
        "mean_ci_margin",
        "mean_ci_confidence_level",
        "mean_ci_method",
        "mean_sample_se_for_ci",
        "mean_ci_dof",
        "mean_ci_critical_value",
        "std",
        "min",
        "max",
    } <= set(rows_by_key)
    assert rows_by_key["method"].value == "mean_sample"
    assert rows_by_key["method"].label_key == "statistics.method"
    assert rows_by_key["mean"].value == result.payload["mean"]
    assert rows_by_key["mean"].uncertainty == result.payload["std_mean"]
    assert rows_by_key["min"].value == result.payload["min"]
    assert rows_by_key["max"].value == result.payload["max"]
    serialized_rows = [row.to_json() for row in rows]
    assert "Arithmetic mean" not in repr(serialized_rows)
    assert "method_label" not in repr(serialized_rows)


def test_core_statistics_handler_runs_weighted_mean_and_restores_precision() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    previous = mp.mp.dps
    mp.mp.dps = 31
    try:
        request = ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["1", "2"],
                "sigmas": ["0.1", "0.2"],
                "stats_mode": "weighted_sigma",
                "use_sample": True,
                "use_weighted_variance": True,
            },
            options=JobOptions(precision_digits=70),
            request_id="stats-weighted",
        )
        result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(request)
    finally:
        observed_after = mp.mp.dps
        mp.mp.dps = previous

    assert observed_after == 31
    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mean"] == "1.2"
    assert result.payload["std_mean"].startswith("0.08944271909999158785")
    assert result.payload["effective_n"].startswith(
        "1.470588235294117647058823529411764705882352941176470588235294117647"
    )
    assert result.payload["dropped"] == 0


@pytest.mark.parametrize("sigma_text", ["inf", "nan"])
def test_weighted_statistics_rejects_non_finite_sigmas_loudly(sigma_text: str) -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics
    from datalab_core.statistics_compute import compute_statistics

    with pytest.raises(ValueError, match="Non-finite uncertainty"):
        compute_statistics(
            [mp.mpf("1")],
            [mp.mpf(sigma_text)],
            "weighted_sigma",
        )

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["1"],
                "sigmas": [sigma_text],
                "stats_mode": "weighted_sigma",
            },
            options=JobOptions(precision_digits=50),
            request_id=f"stats-non-finite-sigma-{sigma_text}",
        )
    )

    assert result.status is ResultStatus.FAILED
    assert "Non-finite uncertainty" in result.payload["message"]


def test_weighted_consistency_diagnostics_reference_values_and_surfaces() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        run_statistics,
        statistics_csv_rows_from_result,
        statistics_payload_to_compute_result,
    )
    from datalab_core.statistics_compute import compute_statistics

    values = [mp.mpf("1"), mp.mpf("2"), mp.mpf("4")]
    sigmas = [mp.mpf("1"), mp.mpf("1"), mp.mpf("2")]
    direct = compute_statistics(values, sigmas, "weighted_sigma")

    assert mp.almosteq(direct["mean"], mp.mpf(16) / 9)
    assert mp.almosteq(direct["weighted_chi_square"], mp.mpf(17) / 9)
    assert direct["weighted_consistency_dof"] == 2
    assert mp.almosteq(direct["weighted_reduced_chi_square"], mp.mpf(17) / 18)
    assert mp.almosteq(direct["birge_ratio"], mp.sqrt(mp.mpf(17) / 18))
    assert mp.almosteq(direct["effective_n"], mp.mpf(81) / 33)

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": [str(value) for value in values],
                "sigmas": [str(sigma) for sigma in sigmas],
                "stats_mode": "weighted_sigma",
                "use_sample": True,
                "use_weighted_variance": True,
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-weighted-consistency-reference",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mean"].startswith("1.777777777777777777777")
    assert result.payload["weighted_chi_square"].startswith("1.888888888888888888888")
    assert result.payload["weighted_consistency_dof"] == 2
    assert result.payload["weighted_reduced_chi_square"].startswith("0.944444444444444444444")
    assert result.payload["birge_ratio"].startswith("0.971825315807550")
    rows_by_key = {row.key: row for row in analysis_rows_from_json(result.payload["analysis_rows"])}
    assert rows_by_key["weighted_chi_square"].value == result.payload["weighted_chi_square"]
    assert rows_by_key["weighted_consistency_dof"].value == 2
    assert rows_by_key["weighted_reduced_chi_square"].value == result.payload["weighted_reduced_chi_square"]
    assert rows_by_key["birge_ratio"].value == result.payload["birge_ratio"]

    roundtrip = statistics_payload_to_compute_result(result.payload, result.warnings)
    assert mp.almosteq(roundtrip["weighted_chi_square"], mp.mpf(17) / 9)
    assert roundtrip["weighted_consistency_dof"] == 2
    csv_rows = statistics_csv_rows_from_result(roundtrip, row_count=3, include_batch=False)
    csv_by_metric = {str(row["metric"]): row for row in csv_rows}
    assert csv_by_metric["weighted_chi_square"]["value"] == result.payload["weighted_chi_square"]
    assert csv_by_metric["weighted_consistency_dof"]["value"] == 2
    assert csv_by_metric["weighted_reduced_chi_square"]["value"] == result.payload["weighted_reduced_chi_square"]
    assert csv_by_metric["birge_ratio"]["value"] == result.payload["birge_ratio"]


def test_weighted_consistency_diagnostics_exclude_missing_sigma_rows() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["999", "1", "2", "4"],
                "sigmas": [None, "1", "1", "2"],
                "stats_mode": "weighted_sigma",
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-weighted-consistency-dropped",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["dropped"] == 1
    assert result.payload["min"] == "1.0"
    assert result.payload["max"] == "4.0"
    assert result.payload["weighted_chi_square"].startswith("1.888888888888888888888")
    assert result.payload["weighted_consistency_dof"] == 2


def test_core_statistics_handler_reports_zero_sigma_anchor_in_payload() -> None:
    from datalab_core.results import analysis_rows_from_json
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "values": ["1.25", "2.5"],
            "sigmas": ["0", "0.1"],
            "stats_mode": "weighted_sigma",
        },
        options=JobOptions(precision_digits=60),
        request_id="stats-zero-anchor",
    )

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(request)

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mean"] == "1.25"
    assert result.payload["std_mean"] == "0.0"
    assert result.payload["zero_sigma_anchor"] is True
    assert "weighted_chi_square" not in result.payload
    assert "weighted_reduced_chi_square" not in result.payload
    assert "birge_ratio" not in result.payload
    assert any("infinite weight" in warning for warning in result.warnings)
    rows = analysis_rows_from_json(result.payload["analysis_rows"])
    rows_by_key = {row.key: row for row in rows}
    assert rows_by_key["effective_n"].value == "1.0"
    assert rows_by_key["zero_sigma_anchor"].value == "true"
    assert "weighted_chi_square" not in rows_by_key
    assert "weighted_reduced_chi_square" not in rows_by_key
    assert "birge_ratio" not in rows_by_key
    assert rows_by_key["warning.zero_sigma_anchor"].severity == "warning"
    assert rows_by_key["warning.zero_sigma_anchor"].message_key == "statistics.warning.zero_sigma_anchor"
    assert rows_by_key["warning.zero_sigma_anchor"].value == result.warnings[0]


def test_core_statistics_roundtrip_preserves_current_legacy_key_mapping_and_warnings() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics, statistics_payload_to_compute_result
    from datalab_core.statistics_compute import compute_statistics

    values = [mp.mpf("-999"), mp.mpf("1.25"), mp.mpf("2.5"), mp.mpf("999")]
    sigmas = [None, mp.mpf("0"), mp.mpf("0.1"), None]
    direct = compute_statistics(values, sigmas, "weighted_sigma")

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": [str(value) for value in values],
                "sigmas": [None if sigma is None else str(sigma) for sigma in sigmas],
                "stats_mode": "weighted_sigma",
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-roundtrip-zero-anchor",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert "min" in result.payload
    assert "max" in result.payload
    assert "v_min" not in result.payload
    assert "v_max" not in result.payload

    roundtrip = statistics_payload_to_compute_result(result.payload, result.warnings)

    assert mp.almosteq(roundtrip["mean"], direct["mean"])
    assert mp.almosteq(roundtrip["std_mean"], direct["std_mean"])
    assert mp.almosteq(roundtrip["std"], direct["std"])
    assert mp.almosteq(roundtrip["v_min"], direct["v_min"])
    assert mp.almosteq(roundtrip["v_max"], direct["v_max"])
    assert roundtrip["dropped"] == direct["dropped"] == 2
    assert roundtrip["effective_n"] == direct["effective_n"] == mp.mpf("1")
    assert roundtrip["zero_sigma_anchor"] is True
    assert roundtrip["warnings"] == list(result.warnings)
    assert roundtrip["mode"] == "weighted_sigma"
    assert roundtrip["analysis_rows"] == result.payload["analysis_rows"]
    assert any("infinite weight" in warning for warning in roundtrip["warnings"])


def test_descriptive_statistics_payload_roundtrip_semantic_rows_and_csv() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        run_statistics,
        statistics_csv_rows_from_result,
        statistics_payload_to_compute_result,
    )

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["1", "2", "3", "4"],
                "stats_mode": "descriptive",
                "use_sample": True,
            },
            options=JobOptions(precision_digits=70),
            request_id="stats-descriptive-roundtrip",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mode"] == "descriptive"
    assert result.payload["count"] == 4
    assert result.payload["variance"].startswith("1.666666666666666666666666666666")
    assert result.payload["median"] == "2.5"
    assert result.payload["q1"] == "1.75"
    assert result.payload["q3"] == "3.25"
    assert result.payload["iqr"] == "1.5"
    assert result.payload["mad"] == "1.0"
    assert result.payload["skewness"] == "0.0"
    assert result.payload["excess_kurtosis"].startswith("-1.2")

    rows_by_key = {row.key: row for row in analysis_rows_from_json(result.payload["analysis_rows"])}
    assert {
        "row_count",
        "count",
        "mean",
        "std_mean",
        "std",
        "variance",
        "min",
        "max",
        "median",
        "q1",
        "q3",
        "iqr",
        "mad",
        "skewness",
        "excess_kurtosis",
    } <= set(rows_by_key)
    assert rows_by_key["mean"].uncertainty == result.payload["std_mean"]
    assert rows_by_key["variance"].label_key == "statistics.metric.variance"

    roundtrip = statistics_payload_to_compute_result(result.payload, result.warnings)
    assert mp.almosteq(roundtrip["median"], mp.mpf("2.5"))
    assert mp.almosteq(roundtrip["q1"], mp.mpf("1.75"))
    assert mp.almosteq(roundtrip["excess_kurtosis"], mp.mpf("-1.2"))
    assert roundtrip["count"] == 4

    csv_rows = statistics_csv_rows_from_result(roundtrip, row_count=4, include_batch=False)
    csv_by_metric = {str(row["metric"]): row for row in csv_rows}
    assert {
        "count",
        "variance",
        "median",
        "q1",
        "q3",
        "iqr",
        "mad",
        "skewness",
        "excess_kurtosis",
    } <= set(csv_by_metric)
    assert csv_by_metric["median"]["value"] == "2.5"


def test_trimmed_mean_payload_semantic_csv_and_snapshot_parity() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        build_statistics_result_snapshot,
        render_statistics_snapshot_outputs,
        run_statistics,
        statistics_csv_rows_from_result,
        statistics_payload_to_compute_result,
    )

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["1", "2", "3", "4", "100"],
                "stats_mode": "descriptive",
                "use_sample": True,
                "trim_fraction": "0.2",
            },
            options=JobOptions(precision_digits=70),
            request_id="stats-trimmed-mean-parity",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["trimmed_mean"] == "3.0"
    rows_by_key = {row.key: row for row in analysis_rows_from_json(result.payload["analysis_rows"])}
    assert rows_by_key["trimmed_mean"].label_key == "statistics.metric.trimmed_mean"
    assert rows_by_key["trimmed_mean"].value == "3.0"

    roundtrip = statistics_payload_to_compute_result(result.payload, result.warnings)
    assert roundtrip["trimmed_mean"] == mp.mpf("3")
    csv_by_metric = {
        str(row["metric"]): row
        for row in statistics_csv_rows_from_result(roundtrip, row_count=5, include_batch=False)
    }
    assert csv_by_metric["trimmed_mean"]["value"] == "3.0"

    snapshot = build_statistics_result_snapshot(
        "statistics_single",
        {"result": roundtrip, "value_col": "A", "n": 5},
    )
    assert snapshot is not None
    assert any(row["key"] == "trimmed_mean" and row["value"] == "3.0" for row in snapshot["metric_rows"])
    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, _headers = rendered
    assert "Trimmed mean | 3.0 |" in text
    assert any(row["metric"] == "trimmed_mean" and row["value"] == "3.0" for row in csv_rows)


def test_single_column_statistics_batch_with_column_index_is_not_column_scoped() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        build_statistics_result_snapshot,
        render_statistics_snapshot_outputs,
        run_statistics,
        statistics_payload_to_compute_result,
    )

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={"values": ["1", "2", "3"], "stats_mode": "mean_sample"},
            options=JobOptions(precision_digits=60),
            request_id="stats-single-column-index-batch",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    legacy = statistics_payload_to_compute_result(result.payload, result.warnings)
    snapshot = build_statistics_result_snapshot(
        "statistics_batches",
        {
            "batches": [
                {
                    "index": 1,
                    "column_index": 1,
                    "batch_index": 1,
                    "value_col": "A",
                    "row_count": 3,
                    "result": legacy,
                },
            ],
        },
    )

    assert snapshot is not None
    assert "column_count" not in snapshot["source"]
    assert "column_index" not in snapshot["source"]["batches"][0]
    assert all("source" not in row for row in snapshot["metric_rows"])
    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, headers = rendered
    assert headers == ["batch", "metric", "value", "uncertainty"]
    assert "=== Statistics ===" in text
    assert "Column A" not in text
    assert "column" not in csv_rows[0]


def test_multi_column_statistics_snapshot_renders_column_scoped_rows_and_csv() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        build_statistics_result_snapshot,
        render_statistics_snapshot_outputs,
        run_statistics,
        statistics_payload_to_compute_result,
    )

    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})
    result_b = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={"values": ["10", "20", "30"], "stats_mode": "mean_sample"},
            options=JobOptions(precision_digits=60),
            request_id="stats-column-b",
        )
    )
    result_a = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={"values": ["1", "2", "3"], "stats_mode": "mean_sample"},
            options=JobOptions(precision_digits=60),
            request_id="stats-column-a",
        )
    )

    assert result_b.status is ResultStatus.SUCCEEDED
    assert result_a.status is ResultStatus.SUCCEEDED
    legacy_b = statistics_payload_to_compute_result(result_b.payload, result_b.warnings)
    legacy_a = statistics_payload_to_compute_result(result_a.payload, result_a.warnings)
    snapshot = build_statistics_result_snapshot(
        "statistics_batches",
        {
            "value_columns": ["B", "A"],
            "batches": [
                {
                    "index": 1,
                    "column_index": 1,
                    "batch_index": 1,
                    "value_col": "B",
                    "row_count": 3,
                    "result": legacy_b,
                },
                {
                    "index": 2,
                    "column_index": 2,
                    "batch_index": 1,
                    "value_col": "A",
                    "row_count": 3,
                    "result": legacy_a,
                },
            ],
        },
    )

    assert snapshot is not None
    assert snapshot["source"]["value_columns"] == ["B", "A"]
    assert snapshot["source"]["column_count"] == 2
    assert snapshot["source"]["batches"][0]["value_column"] == "B"
    assert snapshot["source"]["batches"][0]["column_index"] == 1
    assert snapshot["source"]["batches"][1]["value_column"] == "A"
    means = [row for row in snapshot["metric_rows"] if row["key"] == "mean"]
    assert [row["source"] for row in means] == ["B", "A"]

    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, headers = rendered
    assert headers == ["column", "batch", "metric", "value", "uncertainty"]
    assert text.index("=== Statistics: Column B ===") < text.index("=== Statistics: Column A ===")
    csv_means = [row for row in csv_rows if row["metric"] == "mean"]
    assert [(row["column"], row["batch"], row["value"]) for row in csv_means] == [
        ("B", 1, result_b.payload["mean"]),
        ("A", 1, result_a.payload["mean"]),
    ]
    json.dumps(snapshot)


def test_statistics_robust_outlier_flags_are_two_tailed() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["-100", "-1", "0", "1", "2"],
                "stats_mode": "descriptive",
                "source_row_ids": ["source-neg", "2", "3", "4", "5"],
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-robust-two-tailed-outlier",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    rows = [row for row in analysis_rows_from_json(result.payload["analysis_rows"]) if row.key.startswith("outlier.")]
    assert len(rows) == 1
    assert rows[0].key == "outlier.robust_modified_z.1"
    assert rows[0].row_index == "source-neg"
    assert rows[0].value == "-100.0"
    assert rows[0].source == "robust_modified_z"
    assert rows[0].message_key == "statistics.flag.outlier_robust.modified_z_gt_3_5"


def test_statistics_mad_zero_flags_non_median_values_and_diagnostic() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["1", "1", "1", "2"],
                "stats_mode": "descriptive",
                "source_row_ids": ["r1", "r2", "r3", "r4"],
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-mad-zero-outlier",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert "outlier_robust_mad_zero_fallback" in result.payload["warning_codes"]
    rows_by_key = {row.key: row for row in analysis_rows_from_json(result.payload["analysis_rows"])}
    assert rows_by_key["outlier.robust_mad_zero.1"].row_index == "r4"
    assert rows_by_key["outlier.robust_mad_zero.1"].value == "2.0"
    assert rows_by_key["outlier.robust_mad_zero.1"].message_key == "statistics.flag.outlier_robust.mad_zero_nonmedian"
    assert rows_by_key["warning.outlier_robust_mad_zero_fallback"].message_key == (
        "statistics.warning.outlier_robust_mad_zero_fallback"
    )


def test_statistics_sigma_outlier_flags_positive_sigma_source_rows() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["0", "0", "10"],
                "sigmas": ["10", "10", "1"],
                "stats_mode": "mean_sample",
                "source_row_ids": ["line-10", "line-11", "line-12"],
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-sigma-outlier",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    rows = [row for row in analysis_rows_from_json(result.payload["analysis_rows"]) if row.key.startswith("outlier.")]
    assert len(rows) == 1
    assert rows[0].key == "outlier.sigma.1"
    assert rows[0].row_index == "line-12"
    assert rows[0].value == "10.0"
    assert rows[0].source == "sigma"
    assert rows[0].message_key == "statistics.flag.outlier_sigma.residual_gt_3sigma"


def test_statistics_missing_sigma_does_not_create_sigma_outlier_or_change_weighted_diagnostics() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["999", "1", "2", "4"],
                "sigmas": [None, "1", "1", "2"],
                "stats_mode": "weighted_sigma",
                "source_row_ids": ["missing-sigma", "r2", "r3", "r4"],
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-missing-sigma-no-outlier",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["dropped"] == 1
    assert result.payload["min"] == "1.0"
    assert result.payload["max"] == "4.0"
    assert result.payload["weighted_chi_square"].startswith("1.888888888888888888888")
    assert result.payload["weighted_consistency_dof"] == 2
    outlier_rows = [
        row for row in analysis_rows_from_json(result.payload["analysis_rows"]) if row.key.startswith("outlier.")
    ]
    assert outlier_rows == []


def test_statistics_outlier_flags_roundtrip_csv_latex_and_snapshot() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        build_statistics_result_snapshot,
        render_statistics_snapshot_outputs,
        run_statistics,
        statistics_csv_rows_from_result,
        statistics_payload_to_compute_result,
    )
    from datalab_latex.latex_tables_common import build_statistics_latex_diagnostic_rows

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["0", "0", "10"],
                "sigmas": ["10", "10", "1"],
                "stats_mode": "mean_sample",
                "source_row_ids": ["r1", "r2", "r3"],
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-outlier-output-parity",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    rows_by_key = {row.key: row for row in analysis_rows_from_json(result.payload["analysis_rows"])}
    assert rows_by_key["outlier.sigma.1"].row_index == "r3"

    roundtrip = statistics_payload_to_compute_result(result.payload, result.warnings)
    csv_rows = statistics_csv_rows_from_result(roundtrip, row_count=3, include_batch=False)
    csv_by_metric = {str(row["metric"]): row for row in csv_rows}
    assert csv_by_metric["outlier.sigma.1"]["value"] == "10.0"
    assert csv_by_metric["outlier.sigma.1"]["uncertainty"] == (
        "source row r3; metric sigma; absolute residual exceeds 3 sigma"
    )

    latex_rows = build_statistics_latex_diagnostic_rows(roundtrip)
    assert ("Outlier flag", r"\multicolumn{1}{l}{value 10.0; source row r3; metric sigma; absolute residual exceeds 3 sigma}") in latex_rows

    snapshot = build_statistics_result_snapshot(
        "statistics_single",
        {"result": roundtrip, "value_col": "A", "n": 3},
    )
    assert snapshot is not None
    assert snapshot["row_flags"][0]["key"] == "outlier.sigma.1"
    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, snapshot_csv, _headers = rendered
    assert "Sigma outlier | 10.0 | source row r3; metric sigma; absolute residual exceeds 3 sigma" in text
    snapshot_outlier = {str(row["metric"]): row for row in snapshot_csv}["outlier.sigma.1"]
    assert snapshot_outlier["value"] == csv_by_metric["outlier.sigma.1"]["value"]
    assert snapshot_outlier["uncertainty"] == csv_by_metric["outlier.sigma.1"]["uncertainty"]


def test_statistics_csv_serializer_consumes_semantic_rows_and_diagnostics() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import AnalysisRow, ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        run_statistics,
        statistics_csv_rows_from_analysis_rows,
        statistics_csv_rows_from_result,
        statistics_payload_to_compute_result,
    )

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["1.25", "2.5"],
                "sigmas": ["0", "0.1"],
                "stats_mode": "weighted_sigma",
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-csv-diagnostics",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    analysis_rows = (
        *analysis_rows_from_json(result.payload["analysis_rows"]),
        AnalysisRow(
            key="plot.mean_band_annotation",
            label_key="statistics.plot.mean_band_annotation",
            value="Mean band crosses anchor",
            severity="warning",
            message_key="statistics.plot.mean_band_annotation",
            render_group="plot_annotation",
        ),
        AnalysisRow(
            key="mean",
            label_key="statistics.plot.annotation.mean",
            value="999",
            severity="warning",
            message_key="statistics.plot.annotation.mean",
            render_group="plot_annotation",
        ),
    )
    csv_rows = statistics_csv_rows_from_analysis_rows(analysis_rows, batch=2)
    rows_by_metric = {str(row["metric"]): row for row in csv_rows}

    assert [row["metric"] for row in csv_rows] == [
        "method",
        "mean",
        "rows",
        "std",
        "min",
        "max",
        "effective_n",
        "zero_sigma_anchor",
        "outlier.sigma.1",
        "warning.zero_sigma_anchor",
    ]
    assert rows_by_metric["mean"]["uncertainty"] == result.payload["std_mean"]
    assert rows_by_metric["rows"]["value"] == 2
    assert rows_by_metric["zero_sigma_anchor"]["value"] == "True"
    assert rows_by_metric["outlier.sigma.1"]["uncertainty"] == (
        "source row 2; metric sigma; absolute residual exceeds 3 sigma"
    )
    assert rows_by_metric["warning.zero_sigma_anchor"]["value"] == result.warnings[0]
    assert all("batch" in row for row in csv_rows)
    assert "std_mean" not in rows_by_metric
    assert "plot.mean_band_annotation" not in rows_by_metric
    assert rows_by_metric["mean"]["value"] == result.payload["mean"]
    assert rows_by_metric["method"]["value"] == "weighted_sigma"

    legacy = statistics_payload_to_compute_result(result.payload, result.warnings)
    public_rows = statistics_csv_rows_from_result(legacy, row_count=2, batch=2)
    public_by_metric = {str(row["metric"]): row for row in public_rows}
    assert [row["metric"] for row in public_rows] == [row["metric"] for row in csv_rows]
    assert public_by_metric["method"]["value"] == result.payload["method_label"]
    assert public_by_metric["warning.zero_sigma_anchor"]["value"] == result.warnings[0]

    legacy_without_analysis_rows = dict(legacy)
    legacy_without_analysis_rows.pop("analysis_rows")
    legacy_rows = statistics_csv_rows_from_result(legacy_without_analysis_rows, row_count=2, batch=2)
    legacy_by_metric = {str(row["metric"]): row for row in legacy_rows}
    assert legacy_by_metric["method"]["value"] == result.payload["method_label"]


def test_statistics_snapshot_text_and_csv_exclude_plot_annotations() -> None:
    from datalab_core.results import AnalysisRow
    from datalab_core.statistics import render_statistics_snapshot_outputs

    diagnostic_row = AnalysisRow(
        key="warning.zero_sigma_anchor",
        label_key="statistics.warning",
        value="Detected zero sigma.",
        severity="warning",
        message_key="statistics.warning.zero_sigma_anchor",
        render_group="diagnostic",
    ).to_json()
    plot_annotation_row = AnalysisRow(
        key="mean",
        label_key="statistics.plot.annotation.mean",
        value="999",
        severity="warning",
        message_key="statistics.plot.annotation.mean",
        render_group="plot_annotation",
    ).to_json()
    snapshot = {
        "family": "statistics",
        "mode": "weighted_sigma",
        "batches": [
            {
                "index": 1,
                "mode": "weighted_sigma",
                "metric_rows": [
                    AnalysisRow(
                        key="mean",
                        label_key="statistics.metric.mean",
                        value="1.25",
                        uncertainty="0",
                    ).to_json(),
                ],
                "row_flags": [],
                "diagnostic_rows": [diagnostic_row, plot_annotation_row],
                "source": {"row_count": 2, "value_column": "Data"},
            }
        ],
    }

    rendered = render_statistics_snapshot_outputs(snapshot)

    assert rendered is not None
    text, csv_rows, headers = rendered
    rows_by_metric = {str(row["metric"]): row for row in csv_rows}
    assert headers == ["batch", "metric", "value", "uncertainty"]
    assert "Mean | 1.25 | 0" in text
    assert "Detected zero sigma." in text
    assert "statistics.warning.zero_sigma_anchor" not in text
    assert "statistics.plot.annotation.mean" not in text
    assert "999" not in text
    assert [row["metric"] for row in csv_rows] == ["mean", "warning.zero_sigma_anchor"]
    assert rows_by_metric["mean"]["value"] == "1.25"
    assert rows_by_metric["warning.zero_sigma_anchor"]["value"] == "Detected zero sigma."


def test_statistics_warning_code_only_fallbacks_render_human_text_not_message_key() -> None:
    from datalab_core.results import AnalysisRow
    from datalab_core.statistics import render_statistics_snapshot_outputs, statistics_csv_rows_from_analysis_rows

    warning_row = AnalysisRow(
        key="warning.zero_sigma_anchor",
        label_key="statistics.warning",
        severity="warning",
        message_key="statistics.warning.zero_sigma_anchor",
        render_group="diagnostic",
    )

    csv_rows = statistics_csv_rows_from_analysis_rows([warning_row], include_batch=False)
    assert csv_rows == [
        {
            "metric": "warning.zero_sigma_anchor",
            "value": "Detected σ=0; treated as infinite weight.",
            "uncertainty": "",
        }
    ]

    snapshot = {
        "family": "statistics",
        "mode": "weighted_sigma",
        "batches": [
            {
                "index": 1,
                "mode": "weighted_sigma",
                "metric_rows": [],
                "row_flags": [],
                "diagnostic_rows": [warning_row.to_json()],
                "source": {"row_count": 2, "value_column": "Data"},
            }
        ],
    }

    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, rendered_csv_rows, _headers = rendered
    assert "Detected σ=0; treated as infinite weight." in text
    assert "statistics.warning.zero_sigma_anchor" not in text
    assert rendered_csv_rows[0]["value"] == csv_rows[0]["value"]


def test_core_statistics_roundtrip_preserves_high_precision_under_precision_guard() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics, statistics_payload_to_compute_result

    value_a = "1.0000000000000000000000000000000000000000000000001"
    value_b = "2.0000000000000000000000000000000000000000000000002"
    previous = mp.mp.dps
    mp.mp.dps = 31
    try:
        with precision_guard(90):
            request = ComputeJobRequest(
                mode=JobMode.STATISTICS,
                inputs={
                    "values": [value_a, value_b],
                    "sigmas": [None, None],
                    "stats_mode": "mean",
                },
                options=JobOptions(precision_digits=80),
                request_id="stats-high-precision-roundtrip",
            )
            result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(request)
            roundtrip = statistics_payload_to_compute_result(result.payload, result.warnings)
        observed_after = mp.mp.dps
    finally:
        mp.mp.dps = previous

    assert observed_after == 31
    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mean"] == "1.50000000000000000000000000000000000000000000000015"
    assert mp.nstr(roundtrip["mean"], 80) == "1.50000000000000000000000000000000000000000000000015"


def test_core_statistics_zero_sigma_anchor_range_excludes_dropped_rows() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "values": ["-999", "1.25", "2.5", "999"],
            "sigmas": [None, "0", "0.1", None],
            "stats_mode": "weighted_sigma",
        },
        options=JobOptions(precision_digits=60),
        request_id="stats-zero-anchor-dropped-range",
    )

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(request)

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mean"] == "1.25"
    assert result.payload["min"] == "1.25"
    assert result.payload["max"] == "2.5"
    assert result.payload["dropped"] == 2
    assert result.payload["zero_sigma_anchor"] is True


def test_core_statistics_handler_rejects_high_precision_conflicting_zero_sigma_values() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": [
                    "1.0000000000000000000000000000001",
                    "1.0000000000000000000000000000002",
                ],
                "sigmas": ["0", "0"],
                "stats_mode": "weighted_sigma",
            },
            options=JobOptions(precision_digits=80),
            request_id="stats-zero-conflict",
        )
    )

    assert result.status is ResultStatus.FAILED
    assert "Conflicting zero-uncertainty points" in result.payload["message"]


def test_core_statistics_handler_runs_weighted_mean_without_weighted_variance() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["1", "2", "4"],
                "sigmas": ["0.1", "0.2", "0.3"],
                "stats_mode": "weighted_sigma",
                "use_weighted_variance": False,
            },
            options=JobOptions(precision_digits=50),
            request_id="stats-weighted-unweighted-variance",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mean"] == "1.4285714285714285714285714285714285714285714285714"
    assert result.payload["std"].startswith("1.8871206876604152069026602033116074352540292526328")
    assert result.payload["zero_sigma_anchor"] is False


def test_core_statistics_handler_single_weighted_row_warns_for_consistency_dof() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["7"],
                "sigmas": ["2"],
                "stats_mode": "weighted_sigma",
            },
            options=JobOptions(precision_digits=50),
            request_id="stats-weighted-single-consistency-dof",
        )
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["weighted_chi_square"] == "0.0"
    assert result.payload["weighted_consistency_dof"] == 0
    assert "weighted_reduced_chi_square" not in result.payload
    assert "birge_ratio" not in result.payload
    assert result.payload["warning_codes"] == ["weighted_consistency_dof_insufficient"]
    assert any("at least two finite positive sigma" in warning for warning in result.warnings)
    rows_by_key = {row.key: row for row in analysis_rows_from_json(result.payload["analysis_rows"])}
    assert rows_by_key["weighted_consistency_dof"].value == 0
    assert "weighted_reduced_chi_square" not in rows_by_key
    assert "birge_ratio" not in rows_by_key
    assert (
        rows_by_key["warning.weighted_consistency_dof_insufficient"].message_key
        == "statistics.warning.weighted_consistency_dof_insufficient"
    )


def test_core_statistics_handler_rejects_non_finite_sigmas_before_weight_fallback() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ["1", "3"],
                "sigmas": ["inf", "inf"],
                "stats_mode": "weighted_sigma",
            },
            options=JobOptions(precision_digits=50),
            request_id="stats-zero-total-weight",
        )
    )

    assert result.status is ResultStatus.FAILED
    assert "Non-finite uncertainty" in result.payload["message"]
    assert not result.warnings


def test_core_statistics_handler_reports_bad_sigma_shape_as_failure_envelope() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    previous = mp.mp.dps
    mp.mp.dps = 29
    try:
        result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
            ComputeJobRequest(
                mode=JobMode.STATISTICS,
                inputs={"values": ["1", "2"], "sigmas": ["0.1"]},
                request_id="bad-stats",
            )
        )
    finally:
        observed_after = mp.mp.dps
        mp.mp.dps = previous

    assert observed_after == 29
    assert result.status is ResultStatus.FAILED
    assert result.payload["error_code"] == "handler_exception"
    assert result.payload["message"] == "sigmas must have the same length as values."


def test_core_statistics_handler_validates_source_row_id_shape() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={"values": ["1", "2"], "source_row_ids": ["1"]},
            request_id="bad-source-rows",
        )
    )

    assert result.status is ResultStatus.FAILED
    assert result.payload["error_code"] == "handler_exception"
    assert result.payload["message"] == "source_row_ids must have the same length as values."


def test_core_statistics_handler_reports_bad_stats_mode_type() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={"values": ["1", "2"], "stats_mode": ["mean_sample"]},
            request_id="bad-stats-mode",
        )
    )

    assert result.status is ResultStatus.FAILED
    assert result.payload["error_code"] == "handler_exception"
    assert result.payload["message"] == "stats_mode must be a string."


def test_core_statistics_handler_uses_stable_default_precision() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    previous = mp.mp.dps
    mp.mp.dps = 23
    try:
        result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
            ComputeJobRequest(
                mode=JobMode.STATISTICS,
                inputs={"values": ["1.1", "2.2"], "stats_mode": "mean_sample"},
                request_id="stats-default-precision",
            )
        )
    finally:
        observed_after = mp.mp.dps
        mp.mp.dps = previous

    assert observed_after == 23
    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["precision_used"] == 50
