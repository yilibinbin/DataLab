from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
from mpmath import mp

from datalab_core.history_compare import build_history_comparison
from shared.precision import precision_guard


def test_statistics_history_comparison_uses_semantic_metric_rows_only() -> None:
    left = _history_snapshot(
        "statistics",
        {
            "schema": "datalab.result_snapshot.statistics",
            "schema_version": 1,
            "family": "statistics",
            "mode": "weighted_sigma",
            "metric_rows": [
                {"key": "mean", "label_key": "statistics.metric.mean", "value": "10.5"},
                {"key": "std", "label_key": "statistics.metric.std", "value": "2.0"},
                {"key": "median", "label_key": "statistics.metric.median", "value": "n/a"},
            ],
            "diagnostic_rows": [],
            "row_flags": [
                {
                    "key": "outlier.line-2",
                    "label_key": "statistics.row_flag.outlier",
                    "value": "normal",
                }
            ],
            "source": {"row_count": 3, "batch_count": 1},
            "compatibility": {"rendered_caches_authoritative": False},
        },
    )
    right = _history_snapshot(
        "statistics",
        {
            "schema": "datalab.result_snapshot.statistics",
            "schema_version": 1,
            "family": "statistics",
            "mode": "weighted_sigma",
            "metric_rows": [
                {"key": "mean", "label_key": "statistics.metric.mean", "value": "13.0"},
                {"key": "median", "label_key": "statistics.metric.median", "value": "11.0"},
                {"key": "trimmed_mean", "label_key": "statistics.metric.trimmed_mean", "value": "12.0"},
            ],
            "diagnostic_rows": [],
            "row_flags": [
                {
                    "key": "outlier.line-2",
                    "label_key": "statistics.row_flag.outlier",
                    "value": "outlier",
                }
            ],
            "source": {"row_count": 4, "batch_count": 1},
            "markdown": "mean = 999999",
        },
    )

    result = build_history_comparison(left, right, left_label="Baseline", right_label="Current")

    assert result["schema"] == "datalab.history.compare.v1"
    assert result["comparison_mode"] == "same_family"
    rows = {row["key"]: row for row in result["rows"]}
    assert rows["delta.statistics.metric.mean.value"]["value"] == "2.5"
    assert "Baseline=10.5; Current=13.0" == rows["delta.statistics.metric.mean.value"]["source"]
    diagnostic_keys = {row["key"] for row in result["diagnostics"]}
    assert "statistics.metric.std.missing" in diagnostic_keys
    assert "statistics.metric.trimmed_mean.missing" in diagnostic_keys
    assert "statistics.metric.median.value.non_numeric" in diagnostic_keys
    metadata = {row["key"]: row for row in result["metadata_rows"]}
    assert metadata["metadata.source.row_count"]["value"] == "4"
    assert metadata["metadata.statistics.row_flag.outlier.line-2.value"]["value"] == "outlier"
    _assert_no_json_floats(result)


def test_statistics_history_comparison_aligns_multi_column_rows_by_column_source() -> None:
    left = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "A", "value": "1.0"},
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "B", "value": "10.0"},
        ],
        source={"value_columns": ["A", "B"], "column_count": 2},
    )
    right = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "B", "value": "13.0"},
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "A", "value": "1.5"},
        ],
        source={"value_columns": ["B", "A"], "column_count": 2},
    )

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    rows = {row["key"]: row for row in result["rows"]}
    assert rows["delta.statistics.metric.A.mean.value"]["value"] == "0.5"
    assert rows["delta.statistics.metric.B.mean.value"]["value"] == "3.0"
    assert "statistics.metric.mean#2.missing" not in {row["key"] for row in result["diagnostics"]}
    _assert_no_json_floats(result)


def test_statistics_bootstrap_history_comparison_reports_ci_overlap() -> None:
    left = _direct_snapshot(
        "statistics",
        mode="bootstrap_confidence_intervals",
        metric_rows=[
            {"key": "bootstrap_ci_lower", "label_key": "statistics.bootstrap.ci_lower", "source": "A", "value": "1.0"},
            {"key": "bootstrap_ci_upper", "label_key": "statistics.bootstrap.ci_upper", "source": "A", "value": "3.0"},
            {"key": "bootstrap_ci_lower", "label_key": "statistics.bootstrap.ci_lower", "source": "B", "value": "10.0"},
            {"key": "bootstrap_ci_upper", "label_key": "statistics.bootstrap.ci_upper", "source": "B", "value": "11.0"},
        ],
        source={"target_statistic": "mean", "resample_count": 100, "seeded": True},
    )
    right = _direct_snapshot(
        "statistics",
        mode="bootstrap_confidence_intervals",
        metric_rows=[
            {"key": "bootstrap_ci_lower", "label_key": "statistics.bootstrap.ci_lower", "source": "A", "value": "2.0"},
            {"key": "bootstrap_ci_upper", "label_key": "statistics.bootstrap.ci_upper", "source": "A", "value": "4.0"},
            {"key": "bootstrap_ci_lower", "label_key": "statistics.bootstrap.ci_lower", "source": "B", "value": "12.0"},
            {"key": "bootstrap_ci_upper", "label_key": "statistics.bootstrap.ci_upper", "source": "B", "value": "13.0"},
        ],
        source={"target_statistic": "mean", "resample_count": 100, "seeded": True},
    )

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    rows = {row["key"]: row for row in result["rows"]}
    assert rows["statistics.bootstrap_ci.source_QQ.overlap"]["value"] == "overlap"
    assert rows["statistics.bootstrap_ci.source_QQ.overlap"]["uncertainty"] == "1.0"
    assert rows["statistics.bootstrap_ci.source_Qg.overlap"]["value"] == "disjoint"
    assert "Old=[1.0, 3.0]; New=[2.0, 4.0]" == rows["statistics.bootstrap_ci.source_QQ.overlap"]["source"]
    assert result["budget_rows"] == []
    diagnostic_keys = {row["key"] for row in result["diagnostics"]}
    assert "history.compare.budget.left.budget.statistics.bootstrap.diagnostic_only" in diagnostic_keys
    assert "history.compare.budget.right.budget.statistics.bootstrap.diagnostic_only" in diagnostic_keys
    _assert_no_json_floats(result)


def test_statistics_hypothesis_history_comparison_reports_metric_and_metadata_context() -> None:
    left = _direct_snapshot(
        "statistics",
        mode="hypothesis_tests",
        metric_rows=[
            {"key": "statistic", "label_key": "statistics.hypothesis.statistic", "value": "2.0"},
            {"key": "p_value", "label_key": "statistics.hypothesis.p_value", "value": "0.05"},
            {"key": "alpha", "label_key": "statistics.hypothesis.alpha", "value": "0.05"},
        ],
        diagnostic_rows=[],
        source={
            "row_count": 5,
            "test_kind": "one_sample_t",
            "alternative": "two_sided",
            "alpha": "0.05",
            "backend": "mpmath",
            "value_columns": ["A"],
        },
    )
    right = _direct_snapshot(
        "statistics",
        mode="hypothesis_tests",
        metric_rows=[
            {"key": "statistic", "label_key": "statistics.hypothesis.statistic", "value": "3.5"},
            {"key": "p_value", "label_key": "statistics.hypothesis.p_value", "value": "0.01"},
            {"key": "alpha", "label_key": "statistics.hypothesis.alpha", "value": "0.01"},
        ],
        diagnostic_rows=[],
        source={
            "row_count": 5,
            "test_kind": "welch_t",
            "alternative": "greater",
            "alpha": "0.01",
            "backend": "scipy",
            "value_columns": ["A", "B"],
        },
    )

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    rows = {row["key"]: row for row in result["rows"]}
    metadata = {row["key"]: row for row in result["metadata_rows"]}
    diagnostics = {row["key"] for row in result["diagnostics"]}
    assert rows["delta.statistics.metric.p_value.value"]["value"] == "-0.04"
    assert metadata["metadata.source.test_kind"]["value"] == "welch_t"
    assert metadata["metadata.source.backend"]["value"] == "scipy"
    assert metadata["metadata.source.value_columns"]["value"] == "['A', 'B']"
    assert result["budget_rows"] == []
    assert "history.compare.budget.left.budget.statistics.hypothesis.diagnostic_only" in diagnostics
    assert "history.compare.budget.right.budget.statistics.hypothesis.diagnostic_only" in diagnostics
    _assert_no_json_floats(result)


def test_statistics_time_series_history_comparison_reports_option_and_final_point_deltas() -> None:
    left = _time_series_snapshot(window_size=2)
    right = _time_series_snapshot(window_size=3)

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    rows = {row["key"]: row for row in result["rows"]}
    metadata = {row["key"]: row for row in result["metadata_rows"]}
    diagnostics = {row["key"] for row in result["diagnostics"]}
    assert rows["delta.statistics.time_series.final.source_QQ_column_MQ.value"]["value"] == "-0.5"
    assert rows["delta.statistics.time_series.final.source_QQ_column_Mg.value"]["value"] == "-5.0"
    assert len([key for key in rows if key.startswith("delta.statistics.time_series.final.source_QQ_")]) == 2
    assert "metadata.source.window" in metadata
    assert result["budget_rows"] == []
    assert "history.compare.budget.left.budget.statistics.time_series.diagnostic_only" in diagnostics
    assert "history.compare.budget.right.budget.statistics.time_series.diagnostic_only" in diagnostics
    _assert_no_json_floats(result)


def test_statistics_time_series_history_comparison_preserves_high_precision_final_delta() -> None:
    left = _time_series_snapshot_from_values(
        ["1", "1." + ("0" * 99) + "1"],
        precision_digits=120,
    )
    right = _time_series_snapshot_from_values(
        ["1", "1." + ("0" * 99) + "3"],
        precision_digits=120,
    )

    result = build_history_comparison(left, right, left_label="Left", right_label="Right")

    rows = {row["key"]: row for row in result["rows"]}
    value = rows["delta.statistics.time_series.final.source_QQ_column_MQ.value"]["value"]
    assert "e-100" in value
    assert not value.startswith("0")
    _assert_no_json_floats(result)


def test_statistics_metric_row_index_avoids_hash_suffix_collisions() -> None:
    left = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "metric", "label_key": "statistics.metric", "value": "1"},
            {"key": "metric", "label_key": "statistics.metric", "value": "10"},
            {"key": "metric#2", "label_key": "statistics.metric.hash", "value": "100"},
        ],
    )
    right = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "metric", "label_key": "statistics.metric", "value": "2"},
            {"key": "metric", "label_key": "statistics.metric", "value": "20"},
            {"key": "metric#2", "label_key": "statistics.metric.hash", "value": "200"},
        ],
    )

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    rows = {row["key"]: row for row in result["rows"]}
    assert rows["delta.statistics.metric.metric.value"]["value"] == "1.0"
    assert rows["delta.statistics.metric.metric#2.value"]["value"] == "10.0"
    assert rows["delta.statistics.metric.metric#2#2.value"]["value"] == "100.0"
    _assert_no_json_floats(result)


def test_history_budget_comparison_uses_injective_source_tokens() -> None:
    left = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "a/b", "label_key": "statistics.metric.a_slash_b", "value": "1"},
            {"key": "a b", "label_key": "statistics.metric.a_space_b", "value": "10"},
        ],
    )
    right = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "a/b", "label_key": "statistics.metric.a_slash_b", "value": "2"},
            {"key": "a b", "label_key": "statistics.metric.a_space_b", "value": "20"},
        ],
    )

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    budget_rows = {row["key"]: row for row in result["budget_rows"]}
    assert sorted(row["value"] for row in budget_rows.values()) == ["1.0", "10.0"]
    assert len(budget_rows) == 2
    _assert_no_json_floats(result)


def test_history_budget_comparison_keeps_duplicate_metric_keys_with_distinct_sources() -> None:
    left = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "A", "value": "1"},
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "B", "value": "10"},
        ],
    )
    right = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "A", "value": "2"},
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "B", "value": "20"},
        ],
    )

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    budget_rows = [row for row in result["budget_rows"] if row["key"].startswith("delta.budget.statistics.metric.")]
    assert sorted(row["value"] for row in budget_rows) == ["1.0", "10.0"]
    assert len(budget_rows) == 2
    _assert_no_json_floats(result)


def test_history_budget_comparison_source_identity_is_delimiter_safe() -> None:
    left = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "A|row=1", "value": "1"},
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "A", "row_index": 1, "value": "10"},
        ],
    )
    right = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "A|row=1", "value": "2"},
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "A", "row_index": 1, "value": "20"},
        ],
    )

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    budget_rows = [row for row in result["budget_rows"] if row["key"].startswith("delta.budget.statistics.metric.")]
    assert sorted(row["value"] for row in budget_rows) == ["1.0", "10.0"]
    assert len(budget_rows) == 2
    _assert_no_json_floats(result)


def test_history_budget_comparison_reports_one_sided_optional_field_as_missing() -> None:
    left = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "A", "value": "1"},
        ],
    )
    right = _direct_snapshot(
        "statistics",
        metric_rows=[
            {
                "key": "mean",
                "label_key": "statistics.metric.mean",
                "source": "A",
                "value": "2",
                "uncertainty": "0.1",
            },
        ],
    )

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    budget_rows = {row["key"]: row for row in result["budget_rows"]}
    missing = next(row for key, row in budget_rows.items() if key.endswith(".uncertainty.missing"))
    assert "missing on left" in missing["value"]
    assert not any(key.endswith(".uncertainty.non_numeric") for key in budget_rows)
    _assert_no_json_floats(result)


def test_history_budget_comparison_identifies_non_numeric_side() -> None:
    left = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "A", "value": "n/a"},
        ],
    )
    right = _direct_snapshot(
        "statistics",
        metric_rows=[
            {"key": "mean", "label_key": "statistics.metric.mean", "source": "A", "value": "2"},
        ],
    )

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    budget_rows = {row["key"]: row for row in result["budget_rows"]}
    non_numeric = next(row for key, row in budget_rows.items() if key.endswith(".value.non_numeric"))
    assert "on left" in non_numeric["value"]
    assert "on right" not in non_numeric["value"]
    _assert_no_json_floats(result)


def test_statistics_bootstrap_history_comparison_separates_source_and_row_index_keys() -> None:
    left = _direct_snapshot(
        "statistics",
        mode="bootstrap_confidence_intervals",
        metric_rows=[
            {"key": "bootstrap_ci_lower", "label_key": "statistics.bootstrap.ci_lower", "source": "A.1", "value": "1.0"},
            {"key": "bootstrap_ci_upper", "label_key": "statistics.bootstrap.ci_upper", "source": "A.1", "value": "2.0"},
            {
                "key": "bootstrap_ci_lower",
                "label_key": "statistics.bootstrap.ci_lower",
                "source": "A",
                "row_index": "1",
                "value": "10.0",
            },
            {
                "key": "bootstrap_ci_upper",
                "label_key": "statistics.bootstrap.ci_upper",
                "source": "A",
                "row_index": "1",
                "value": "11.0",
            },
        ],
    )
    right = _direct_snapshot(
        "statistics",
        mode="bootstrap_confidence_intervals",
        metric_rows=[
            {"key": "bootstrap_ci_lower", "label_key": "statistics.bootstrap.ci_lower", "source": "A.1", "value": "1.5"},
            {"key": "bootstrap_ci_upper", "label_key": "statistics.bootstrap.ci_upper", "source": "A.1", "value": "2.5"},
            {
                "key": "bootstrap_ci_lower",
                "label_key": "statistics.bootstrap.ci_lower",
                "source": "A",
                "row_index": "1",
                "value": "12.0",
            },
            {
                "key": "bootstrap_ci_upper",
                "label_key": "statistics.bootstrap.ci_upper",
                "source": "A",
                "row_index": "1",
                "value": "13.0",
            },
        ],
    )

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    rows = {row["key"]: row for row in result["rows"]}
    assert rows["statistics.bootstrap_ci.source_QS4x.overlap"]["value"] == "overlap"
    assert rows["statistics.bootstrap_ci.source_QQ_row_MQ.overlap"]["value"] == "disjoint"
    assert len([key for key in rows if key.startswith("statistics.bootstrap_ci.source_Q")]) == 2
    _assert_no_json_floats(result)


def test_statistics_bootstrap_history_comparison_uses_injective_interval_tokens() -> None:
    left = _direct_snapshot(
        "statistics",
        mode="bootstrap_confidence_intervals",
        metric_rows=[
            {
                "key": "bootstrap_ci_lower",
                "label_key": "statistics.bootstrap.ci_lower",
                "source": "A.row.1",
                "value": "1.0",
            },
            {
                "key": "bootstrap_ci_upper",
                "label_key": "statistics.bootstrap.ci_upper",
                "source": "A.row.1",
                "value": "2.0",
            },
            {
                "key": "bootstrap_ci_lower",
                "label_key": "statistics.bootstrap.ci_lower",
                "source": "A",
                "row_index": "1",
                "value": "10.0",
            },
            {
                "key": "bootstrap_ci_upper",
                "label_key": "statistics.bootstrap.ci_upper",
                "source": "A",
                "row_index": "1",
                "value": "11.0",
            },
        ],
    )
    right = _direct_snapshot(
        "statistics",
        mode="bootstrap_confidence_intervals",
        metric_rows=[
            {
                "key": "bootstrap_ci_lower",
                "label_key": "statistics.bootstrap.ci_lower",
                "source": "A.row.1",
                "value": "1.5",
            },
            {
                "key": "bootstrap_ci_upper",
                "label_key": "statistics.bootstrap.ci_upper",
                "source": "A.row.1",
                "value": "2.5",
            },
            {
                "key": "bootstrap_ci_lower",
                "label_key": "statistics.bootstrap.ci_lower",
                "source": "A",
                "row_index": "1",
                "value": "12.0",
            },
            {
                "key": "bootstrap_ci_upper",
                "label_key": "statistics.bootstrap.ci_upper",
                "source": "A",
                "row_index": "1",
                "value": "13.0",
            },
        ],
    )

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    rows = {row["key"]: row for row in result["rows"]}
    assert rows["statistics.bootstrap_ci.source_QS5yb3cuMQ.overlap"]["value"] == "overlap"
    assert rows["statistics.bootstrap_ci.source_QQ_row_MQ.overlap"]["value"] == "disjoint"
    assert len([key for key in rows if key.startswith("statistics.bootstrap_ci.")]) == 2
    _assert_no_json_floats(result)


def test_statistics_bootstrap_history_comparison_preserves_ci_precision_beyond_eighty_digits() -> None:
    near_one_1 = "1." + ("0" * 99) + "1"
    near_one_2 = "1." + ("0" * 99) + "2"
    near_one_3 = "1." + ("0" * 99) + "3"
    left = _direct_snapshot(
        "statistics",
        mode="bootstrap_confidence_intervals",
        metric_rows=[
            {"key": "bootstrap_ci_lower", "label_key": "statistics.bootstrap.ci_lower", "source": "A", "value": "1"},
            {
                "key": "bootstrap_ci_upper",
                "label_key": "statistics.bootstrap.ci_upper",
                "source": "A",
                "value": near_one_1,
            },
        ],
        precision={"compute_digits": 120},
    )
    right = _direct_snapshot(
        "statistics",
        mode="bootstrap_confidence_intervals",
        metric_rows=[
            {
                "key": "bootstrap_ci_lower",
                "label_key": "statistics.bootstrap.ci_lower",
                "source": "A",
                "value": near_one_2,
            },
            {
                "key": "bootstrap_ci_upper",
                "label_key": "statistics.bootstrap.ci_upper",
                "source": "A",
                "value": near_one_3,
            },
        ],
        precision={"compute_digits": 120},
    )

    result = build_history_comparison(left, right, left_label="Left", right_label="Right")

    row = {row["key"]: row for row in result["rows"]}["statistics.bootstrap_ci.source_QQ.overlap"]
    assert row["value"] == "disjoint"
    assert near_one_1 in row["source"]
    assert near_one_2 in row["source"]
    _assert_no_json_floats(result)


def test_history_comparison_preserves_high_precision_delta_text() -> None:
    left = _direct_snapshot(
        "statistics",
        metric_rows=[
            {
                "key": "mean",
                "label_key": "statistics.metric.mean",
                "value": "1.000000000000000000000000000000",
            }
        ],
    )
    right = _direct_snapshot(
        "statistics",
        metric_rows=[
            {
                "key": "mean",
                "label_key": "statistics.metric.mean",
                "value": "1.000000000000000000000000000123",
            }
        ],
    )

    result = build_history_comparison(left, right)

    rows = {row["key"]: row for row in result["rows"]}
    assert rows["delta.statistics.metric.mean.value"]["value"] == "1.23e-28"
    _assert_no_json_floats(result)


def test_fitting_comparison_matches_candidates_without_recommendation_language() -> None:
    left = _direct_snapshot(
        "fitting_comparison",
        comparison_rows=[
            {"candidate_id": "linear", "status": "success", "chi2": "9", "rmse": "3", "r2": "0.8"},
            {"candidate_id": "quadratic", "status": "success", "chi2": "4", "rmse": None, "r2": "0.9"},
        ],
        entries=[
            {
                "candidate_id": "linear",
                "status": "success",
                "fit_result": {
                    "params": {"a": "1.0", "b": "2.0"},
                    "covariance": [["1", "0"], ["0", "1"]],
                    "details": {"covariance_warning": "ill-conditioned"},
                },
            }
        ],
        source={"candidate_count": 2},
    )
    right = _direct_snapshot(
        "fitting_comparison",
        comparison_rows=[
            {"candidate_id": "linear", "status": "success", "chi2": "4", "rmse": "2", "r2": "0.85"},
            {"candidate_id": "cubic", "status": "success", "chi2": "2", "rmse": "1", "r2": "0.95"},
        ],
        entries=[
            {
                "candidate_id": "linear",
                "status": "success",
                "fit_result": {
                    "params": {"a": "1.5", "b": "2.0"},
                    "covariance": [["1"]],
                    "details": {"covariance_warning": ""},
                },
            }
        ],
        source={"candidate_count": 2},
    )

    result = build_history_comparison(left, right)

    rows = {row["key"]: row for row in result["rows"]}
    assert rows["delta.fitting_comparison.linear.chi2"]["value"] == "-5.0"
    assert rows["delta.fitting_comparison.linear.rmse"]["value"] == "-1.0"
    assert rows["delta.fitting_comparison.linear.r2"]["value"] == "0.05"
    assert rows["delta.fitting_comparison.linear.parameter.a"]["value"] == "0.5"
    diagnostic_keys = {row["key"] for row in result["diagnostics"]}
    assert "fitting_comparison.candidate.quadratic.missing" in diagnostic_keys
    assert "fitting_comparison.candidate.cubic.missing" in diagnostic_keys
    metadata = {row["key"]: row for row in result["metadata_rows"]}
    assert metadata["metadata.candidate.linear.covariance_shape"]["value"] == "1x1"
    assert metadata["metadata.candidate.linear.covariance_warning"]["value"] == ""
    assert "best" not in str(result).lower()
    assert "winner" not in str(result).lower()
    assert "recommendation" not in str(result).lower()
    _assert_no_json_floats(result)


def test_root_solving_comparison_reports_metric_delta_and_mismatches() -> None:
    left = _direct_snapshot(
        "root_solving",
        mode="single",
        metric_rows=[
            {"key": "root.1.value", "label_key": "root.metric.value", "value": "2.0"},
        ],
        diagnostic_rows=[
            {"key": "classification.1", "label_key": "root.diagnostic.classification", "value": "bracketed"},
        ],
        source={"row_count": 1, "roots_count": 1},
    )
    right = _direct_snapshot(
        "root_solving",
        mode="batch",
        metric_rows=[
            {"key": "root.1.value", "label_key": "root.metric.value", "value": "2.25"},
        ],
        diagnostic_rows=[
            {"key": "classification.1", "label_key": "root.diagnostic.classification", "value": "unclassified"},
        ],
        source={"row_count": 1, "roots_count": 1},
    )

    result = build_history_comparison(left, right)

    rows = {row["key"]: row for row in result["rows"]}
    assert rows["delta.root_solving.metric.root.1.value.value"]["value"] == "0.25"
    diagnostic_keys = {row["key"] for row in result["diagnostics"]}
    assert "root_solving.mode_mismatch" in diagnostic_keys
    metadata = {row["key"]: row for row in result["metadata_rows"]}
    assert metadata["metadata.mode"]["value"] == "batch"
    assert metadata["metadata.root_solving.classification.1.value"]["value"] == "unclassified"


def test_uncertainty_comparison_handles_result_and_contribution_percent_deltas() -> None:
    left = _direct_snapshot(
        "uncertainty",
        metric_rows=[
            {
                "key": "result_value.1",
                "label_key": "uncertainty.metric.result_value",
                "value": "3.0",
                "uncertainty": "0.20",
                "row_index": 1,
            }
        ],
        diagnostic_rows=[
            {
                "key": "contribution_percent.x",
                "label_key": "uncertainty.diagnostic.contribution_percent",
                "value": "25%",
            },
            {
                "key": "comparison.1.relative_std_difference",
                "label_key": "uncertainty.diagnostic.comparison.relative_std_difference",
                "value": "0.1",
            },
            {
                "key": "propagation.method",
                "label_key": "uncertainty.diagnostic.propagation.method",
                "value": "taylor",
            },
        ],
        source={"row_count": 1},
    )
    right = _direct_snapshot(
        "uncertainty",
        metric_rows=[
            {
                "key": "result_value.1",
                "label_key": "uncertainty.metric.result_value",
                "value": "4.5",
                "uncertainty": "0.25",
                "row_index": 1,
            }
        ],
        diagnostic_rows=[
            {
                "key": "contribution_percent.x",
                "label_key": "uncertainty.diagnostic.contribution_percent",
                "value": "40%",
            },
            {
                "key": "comparison.1.relative_std_difference",
                "label_key": "uncertainty.diagnostic.comparison.relative_std_difference",
                "value": "0.3",
            },
            {
                "key": "propagation.method",
                "label_key": "uncertainty.diagnostic.propagation.method",
                "value": "monte_carlo",
            },
        ],
        source={"row_count": 1},
    )

    result = build_history_comparison(left, right)

    rows = {row["key"]: row for row in result["rows"]}
    assert rows["delta.uncertainty.result.result_value.1.value"]["value"] == "1.5"
    assert rows["delta.uncertainty.result.result_value.1.uncertainty"]["value"] == "0.05"
    assert rows["delta.uncertainty.diagnostic.contribution_percent.x.value"]["value"] == "15.0"
    assert rows["delta.uncertainty.diagnostic.comparison.1.relative_std_difference.value"]["value"] == "0.2"
    metadata = {row["key"]: row for row in result["metadata_rows"]}
    assert metadata["metadata.diagnostic.propagation.method.value"]["value"] == "monte_carlo"


def test_uncertainty_comparison_reports_unit_metadata_changes() -> None:
    left = _direct_snapshot(
        "uncertainty",
        metric_rows=[
            {
                "key": "result_value.1",
                "label_key": "uncertainty.metric.result_value",
                "value": "3.0",
                "uncertainty": "0.20",
                "row_index": 1,
            }
        ],
        diagnostic_rows=[],
        source={"row_count": 1},
    )
    right = _direct_snapshot(
        "uncertainty",
        metric_rows=[
            {
                "key": "result_value.1",
                "label_key": "uncertainty.metric.result_value",
                "value": "3.0",
                "uncertainty": "0.20",
                "row_index": 1,
            }
        ],
        diagnostic_rows=[],
        source={"row_count": 1},
    )
    left["units"] = {
        "schema": "datalab.units.annotations.v1",
        "schema_version": 1,
        "enabled": True,
        "mode": "display_only",
        "inputs": {"x": {"unit": "m"}},
        "constants": {"g": {"unit": "m/s^2"}},
        "parameters": {},
        "outputs": {"result": {"unit": "m"}},
    }
    right["units"] = {
        "schema": "datalab.units.annotations.v1",
        "schema_version": 1,
        "enabled": True,
        "mode": "validate_expression",
        "inputs": {"x": {"unit": "cm"}},
        "constants": {"g": {"unit": "m/s^2"}},
        "parameters": {},
        "outputs": {"result": {"unit": "cm"}},
    }

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    metadata = {row["key"]: row for row in result["metadata_rows"]}
    assert metadata["metadata.units.mode"]["value"] == "validate_expression"
    assert metadata["metadata.units.inputs"]["value"] == "x=cm"
    assert metadata["metadata.units.outputs"]["source"] == "Old=result=m; New=result=cm"
    assert "metadata.units.constants" not in metadata
    _assert_no_json_floats(result)


@pytest.mark.parametrize("family", ["statistics", "root_solving"])
def test_non_error_family_history_comparison_reports_unit_metadata_changes(family: str) -> None:
    left = _direct_snapshot(
        family,
        metric_rows=[{"key": "result", "label_key": f"{family}.metric.result", "value": "1.0"}],
        source={"row_count": 1},
    )
    right = _direct_snapshot(
        family,
        metric_rows=[{"key": "result", "label_key": f"{family}.metric.result", "value": "1.0"}],
        source={"row_count": 1},
    )
    left["units"] = {
        "schema": "datalab.units.annotations.v1",
        "schema_version": 1,
        "enabled": True,
        "mode": "display_only",
        "inputs": {"A": {"unit": "m"}},
        "constants": {},
        "parameters": {},
        "outputs": {"result": {"unit": "m"}},
    }
    right["units"] = {
        "schema": "datalab.units.annotations.v1",
        "schema_version": 1,
        "enabled": True,
        "mode": "display_only",
        "inputs": {"A": {"unit": "cm"}},
        "constants": {},
        "parameters": {},
        "outputs": {"result": {"unit": "cm"}},
    }

    result = build_history_comparison(left, right, left_label="Old", right_label="New")

    metadata = {row["key"]: row for row in result["metadata_rows"]}
    assert metadata["metadata.units.inputs"]["source"] == "Old=A=m; New=A=cm"
    assert metadata["metadata.units.outputs"]["value"] == "result=cm"
    _assert_no_json_floats(result)


def test_history_comparison_includes_budget_row_deltas() -> None:
    left = _direct_snapshot(
        "uncertainty",
        diagnostic_rows=[
            {
                "key": "contribution_percent.x",
                "label_key": "uncertainty.diagnostic.contribution_percent",
                "value": "25",
            },
        ],
    )
    right = _direct_snapshot(
        "uncertainty",
        diagnostic_rows=[
            {
                "key": "contribution_percent.x",
                "label_key": "uncertainty.diagnostic.contribution_percent",
                "value": "40",
            },
        ],
    )

    result = build_history_comparison(left, right, left_label="Earlier", right_label="Current")

    budget_rows = {row["key"]: row for row in result["budget_rows"]}
    delta = next(row for key, row in budget_rows.items() if key.endswith(".percent"))
    assert delta["value"] == "15.0"
    assert delta["source"] == "Earlier=25; Current=40"
    assert delta["method"] == "right_minus_left"
    _assert_no_json_floats(result)


def test_cross_family_comparison_returns_metadata_and_budget_unavailable() -> None:
    left = _direct_snapshot("statistics", metric_rows=[], source={"row_count": 2})
    right = _direct_snapshot("uncertainty", metric_rows=[], source={"row_count": 2})

    result = build_history_comparison(left, right)

    assert result["comparison_mode"] == "cross_family_metadata_only"
    assert result["rows"] == []
    diagnostic_keys = {row["key"] for row in result["diagnostics"]}
    assert "history.compare.cross_family_unavailable" in diagnostic_keys
    assert "history.compare.budget_rows_unavailable" in diagnostic_keys
    assert result["budget_rows"] == []
    assert {row["key"] for row in result["metadata_rows"]} >= {
        "metadata.family",
        "metadata.source.row_count",
    }


def test_unsupported_same_family_fails_closed() -> None:
    left = {
        "schema": "datalab.result_snapshot.future",
        "schema_version": 1,
        "family": "future",
        "mode": "x",
        "metric_rows": [{"key": "value", "value": "1"}],
    }
    right = {
        "schema": "datalab.result_snapshot.future",
        "schema_version": 1,
        "family": "future",
        "mode": "x",
        "metric_rows": [{"key": "value", "value": "2"}],
    }

    result = build_history_comparison(left, right)

    assert result["comparison_mode"] == "unavailable"
    assert result["rows"] == []
    diagnostics = {row["key"]: row for row in result["diagnostics"]}
    assert diagnostics["history.compare.unsupported_family"]["severity"] == "error"


def test_malformed_and_float_snapshots_fail_closed_without_raising() -> None:
    result = build_history_comparison(
        {"family": "statistics", "result": {"family": "statistics", "metric_rows": [{"key": "mean", "value": 1.25}]}},
        {"family": "statistics", "result": {"family": "statistics", "metric_rows": []}},
    )

    assert result["comparison_mode"] == "unavailable"
    assert result["rows"] == []
    assert result["diagnostics"][0]["severity"] == "error"
    _assert_no_json_floats(result)


def test_malformed_result_and_row_containers_emit_error_diagnostics() -> None:
    bad_result = build_history_comparison(
        {"family": "statistics", "result": []},
        {"family": "statistics", "result": {"family": "statistics", "metric_rows": []}},
    )

    assert bad_result["comparison_mode"] == "unavailable"
    assert bad_result["diagnostics"][0]["severity"] == "error"

    bad_left_rows = _direct_snapshot("statistics")
    bad_left_rows["metric_rows"] = {"key": "mean", "value": "1"}
    bad_right_rows = _direct_snapshot("statistics")
    bad_right_rows["metric_rows"] = ["not-a-row"]
    bad_rows = build_history_comparison(bad_left_rows, bad_right_rows)

    assert bad_rows["comparison_mode"] == "same_family"
    diagnostics = {row["key"]: row for row in bad_rows["diagnostics"]}
    assert diagnostics["history.compare.schema.left.metric_rows.invalid"]["severity"] == "error"
    assert diagnostics["history.compare.schema.right.metric_rows.0.invalid"]["severity"] == "error"


def test_unsupported_snapshot_schema_fails_closed_before_scientific_deltas() -> None:
    left = _direct_snapshot(
        "statistics",
        metric_rows=[{"key": "mean", "label_key": "statistics.metric.mean", "value": "1"}],
    )
    right = _direct_snapshot(
        "statistics",
        metric_rows=[{"key": "mean", "label_key": "statistics.metric.mean", "value": "2"}],
    )
    left["schema"] = "other.schema"
    right["schema_version"] = 99

    result = build_history_comparison(left, right)

    assert result["comparison_mode"] == "unavailable"
    assert result["rows"] == []
    diagnostics = {row["key"]: row for row in result["diagnostics"]}
    assert diagnostics["history.compare.schema.left.unsupported"]["severity"] == "error"
    assert diagnostics["history.compare.schema.right.version_unsupported"]["severity"] == "error"


def test_fitting_entry_malformed_required_fields_emit_schema_diagnostics() -> None:
    left = _direct_snapshot(
        "fitting_comparison",
        comparison_rows=[
            {"candidate_id": "linear", "status": "success", "chi2": "1"},
        ],
        entries=[
            {
                "candidate_id": "linear",
                "status": "success",
                "fit_result": {"params": ["not-a-map"], "covariance": "bad"},
            }
        ],
    )
    right = _direct_snapshot(
        "fitting_comparison",
        comparison_rows=[
            {"candidate_id": "linear", "status": "success", "chi2": "2"},
        ],
        entries=[
            {
                "candidate_id": "linear",
                "status": "success",
                "fit_result": {"params": {"a": "1"}, "covariance": [["1"]]},
            }
        ],
    )

    result = build_history_comparison(left, right)

    diagnostics = {row["key"]: row for row in result["diagnostics"]}
    assert (
        diagnostics["history.compare.schema.left.entries.linear.fit_result.params.invalid"]["severity"]
        == "error"
    )
    assert (
        diagnostics["history.compare.schema.left.entries.linear.fit_result.covariance.invalid"]["severity"]
        == "error"
    )


def test_history_compare_core_has_no_ui_or_report_dependencies() -> None:
    source = Path("datalab_core/history_compare.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".", 1)[0])

    assert imported.isdisjoint({"app_desktop", "app_web", "datalab_latex", "PySide6"})


def _history_snapshot(family: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "datalab.history.entry.v1",
        "snapshot_version": 1,
        "family": family,
        "kind": family,
        "language": "en",
        "status": "succeeded",
        "input_signature": {
            "current_mode": family,
            "workspace_hash": "w",
            "data_hash": "d",
            "constants_hash": "c",
            "formula_model": {},
            "options": {},
        },
        "result": result,
    }


def _direct_snapshot(
    family: str,
    *,
    mode: str = "selected",
    metric_rows: list[dict[str, Any]] | None = None,
    diagnostic_rows: list[dict[str, Any]] | None = None,
    comparison_rows: list[dict[str, Any]] | None = None,
    entries: list[dict[str, Any]] | None = None,
    source: dict[str, Any] | None = None,
    precision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "schema": f"datalab.result_snapshot.{family}",
        "schema_version": 1,
        "family": family,
        "mode": mode,
        "source": source or {},
    }
    if metric_rows is not None:
        snapshot["metric_rows"] = metric_rows
    if diagnostic_rows is not None:
        snapshot["diagnostic_rows"] = diagnostic_rows
    if comparison_rows is not None:
        snapshot["comparison_rows"] = comparison_rows
    if entries is not None:
        snapshot["entries"] = entries
    if precision is not None:
        snapshot["precision"] = precision
    return snapshot


def _time_series_snapshot(*, window_size: int) -> dict[str, Any]:
    return _time_series_snapshot_from_values(
        ["1", "2", "3"],
        window_size=window_size,
        precision_digits=30,
        second_values=["10", "20", "30"],
    )


def _time_series_snapshot_from_values(
    values: list[str],
    *,
    precision_digits: int,
    window_size: int = 1,
    second_values: list[str] | None = None,
) -> dict[str, Any]:
    from datalab_core.statistics import build_statistics_result_snapshot
    from datalab_core.statistics_time_series import TIME_SERIES_RESULT_CACHE_KIND, run_statistics_time_series

    with precision_guard(precision_digits):
        first_series = [mp.mpf(value) for value in values]
        second_series = [mp.mpf(value) for value in second_values] if second_values is not None else None
    payload_a = run_statistics_time_series(
        values=first_series,
        source_row_ids=[f"r{index + 1}" for index in range(len(values))],
        precision_digits=precision_digits,
        inputs={
            "series_method": "rolling_mean",
            "window_size": window_size,
            "min_periods": 1,
            "alignment": "right",
        },
        value_column="A",
        column_index=1,
    )
    payload = dict(payload_a)
    payload["value_columns"] = ["A"]
    payload["columns"] = [payload_a["columns"][0]]
    if second_series is not None:
        payload_b = run_statistics_time_series(
            values=second_series,
            source_row_ids=[f"r{index + 1}" for index in range(len(second_series))],
            precision_digits=precision_digits,
            inputs={
                "series_method": "rolling_mean",
                "window_size": window_size,
                "min_periods": 1,
                "alignment": "right",
            },
            value_column="A",
            column_index=2,
        )
        payload["value_columns"] = ["A", "A"]
        payload["columns"] = [payload_a["columns"][0], payload_b["columns"][0]]
    snapshot = build_statistics_result_snapshot(
        TIME_SERIES_RESULT_CACHE_KIND,
        payload,
        precision={"compute_digits": precision_digits, "display_digits": 10},
    )
    assert snapshot is not None
    return snapshot


def _assert_no_json_floats(value: Any) -> None:
    if isinstance(value, float):
        pytest.fail(f"JSON float leaked: {value!r}")
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_json_floats(item)
    if isinstance(value, list):
        for item in value:
            _assert_no_json_floats(item)
