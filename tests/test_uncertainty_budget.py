from __future__ import annotations

from typing import Any, cast

import pytest


def test_uncertainty_budget_extracts_uncertainty_contribution_rows_without_json_floats() -> None:
    from datalab_core.uncertainty_budget import budget_rows_to_json, extract_uncertainty_budget

    snapshot = {
        "schema": "datalab.result_snapshot.uncertainty",
        "schema_version": 1,
        "family": "uncertainty",
        "metric_rows": [],
        "diagnostic_rows": [
            _row("contribution.1.A", "uncertainty.diagnostic.contribution_variance", value="0.01", row_index=1),
            _row("contribution_total.A", "uncertainty.diagnostic.contribution_total_variance", value="0.03"),
            _row("contribution_percent.A", "uncertainty.diagnostic.contribution_percent", value="75"),
            _row(
                "contribution_cumulative_percent.A",
                "uncertainty.diagnostic.contribution_cumulative_percent",
                value="75",
            ),
        ],
        "row_flags": [],
    }

    result = extract_uncertainty_budget(snapshot, source_snapshot_id="u1")

    rows_by_category = {row.category: row for row in result.rows}
    assert rows_by_category["uncertainty.contribution_variance"].value == "0.01"
    assert rows_by_category["uncertainty.contribution_total_variance"].value == "0.03"
    assert rows_by_category["uncertainty.contribution_percent"].percent == "75"
    assert rows_by_category["uncertainty.contribution_percent"].value is None
    assert rows_by_category["uncertainty.contribution_cumulative_percent"].cumulative_percent == "75"
    assert result.diagnostics == ()

    payload = budget_rows_to_json(result.rows)
    assert not _contains_float(payload)
    assert not any("analysis_rows" in row for row in payload)


def test_uncertainty_budget_treats_units_as_provenance_not_contributions() -> None:
    from datalab_core.uncertainty_budget import extract_uncertainty_budget

    snapshot = {
        "schema": "datalab.result_snapshot.uncertainty",
        "schema_version": 1,
        "family": "uncertainty",
        "metric_rows": [_row("result_value.1", "uncertainty.metric.result_value", value="2.0", uncertainty="0.1")],
        "diagnostic_rows": [],
        "row_flags": [],
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
    }

    result = extract_uncertainty_budget(snapshot, source_snapshot_id="u1")

    assert [row.category for row in result.rows] == ["uncertainty.metric"]
    assert result.rows[0].source_key and result.rows[0].source_key.startswith("analysis_row:v1:")
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].key == "budget.uncertainty.units.provenance"
    assert result.diagnostics[0].severity == "info"


def test_uncertainty_budget_reports_mode_and_compatibility_only_unit_provenance() -> None:
    from datalab_core.uncertainty_budget import extract_uncertainty_budget

    base_snapshot = {
        "schema": "datalab.result_snapshot.uncertainty",
        "schema_version": 1,
        "family": "uncertainty",
        "metric_rows": [],
        "diagnostic_rows": [],
        "row_flags": [],
    }
    mode_only = {
        **base_snapshot,
        "units": {
            "schema": "datalab.units.annotations.v1",
            "schema_version": 1,
            "enabled": False,
            "mode": "validate_expression",
            "inputs": {},
            "constants": {},
            "parameters": {},
            "outputs": {},
        },
    }
    compatibility_only = {
        **base_snapshot,
        "units": {
            "schema": "datalab.units.annotations.v1",
            "schema_version": 1,
            "enabled": False,
            "mode": "display_only",
            "inputs": {},
            "constants": {},
            "parameters": {},
            "outputs": {},
            "compatibility": {"quantity_space": "length"},
        },
    }

    mode_result = extract_uncertainty_budget(mode_only, source_snapshot_id="mode-only")
    compatibility_result = extract_uncertainty_budget(compatibility_only, source_snapshot_id="compat-only")

    assert mode_result.diagnostics[0].key == "budget.uncertainty.units.provenance"
    assert compatibility_result.diagnostics[0].key == "budget.uncertainty.units.provenance"


def test_uncertainty_budget_extracts_statistics_context_and_flags() -> None:
    from datalab_core.uncertainty_budget import extract_uncertainty_budget

    snapshot = {
        "schema": "datalab.result_snapshot.statistics",
        "schema_version": 1,
        "family": "statistics",
        "metric_rows": [
            _row("mean_ci_lower", "statistics.metric.mean_ci_lower", value="1.0"),
            _row("weighted_reduced_chi_square", "statistics.metric.weighted_reduced_chi_square", value="0.8"),
        ],
        "diagnostic_rows": [],
        "row_flags": [
            _row(
                "outlier.sigma.1",
                "statistics.flag.outlier.sigma",
                value="9.2",
                row_index="line-7",
                render_group="row_flag",
                message_key="statistics.flag.outlier",
            )
        ],
    }

    result = extract_uncertainty_budget(snapshot, source_snapshot_id="stats1")

    assert {row.label_key for row in result.rows} >= {
        "statistics.metric.mean_ci_lower",
        "statistics.metric.weighted_reduced_chi_square",
        "statistics.flag.outlier.sigma",
    }
    outlier = next(row for row in result.rows if row.label_key == "statistics.flag.outlier.sigma")
    assert outlier.category == "statistics.row_flag"
    assert outlier.source_row_id == "line-7"
    assert outlier.notes == ("statistics.flag.outlier",)
    assert result.diagnostics == ()


def test_uncertainty_budget_treats_statistics_bootstrap_as_diagnostics_only() -> None:
    from datalab_core.uncertainty_budget import extract_uncertainty_budget

    snapshot = {
        "schema": "datalab.result_snapshot.statistics",
        "schema_version": 1,
        "family": "statistics",
        "mode": "bootstrap_confidence_intervals",
        "metric_rows": [
            _row("bootstrap_ci_lower", "statistics.bootstrap.ci_lower", value="1.0"),
            _row("bootstrap_ci_upper", "statistics.bootstrap.ci_upper", value="2.0"),
        ],
        "diagnostic_rows": [],
        "row_flags": [],
    }

    result = extract_uncertainty_budget(snapshot, source_snapshot_id="boot1")

    assert result.rows == ()
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].key == "budget.statistics.bootstrap.diagnostic_only"
    assert result.diagnostics[0].severity == "info"


def test_uncertainty_budget_treats_statistics_hypothesis_as_diagnostics_only() -> None:
    from datalab_core.uncertainty_budget import extract_uncertainty_budget

    snapshot = {
        "schema": "datalab.result_snapshot.statistics",
        "schema_version": 1,
        "family": "statistics",
        "mode": "hypothesis_tests",
        "metric_rows": [
            _row("statistic", "statistics.hypothesis.statistic", value="2.5"),
            _row("p_value", "statistics.hypothesis.p_value", value="0.04"),
            _row("reject_null", "statistics.hypothesis.reject_null", value="true"),
        ],
        "diagnostic_rows": [],
        "row_flags": [],
    }

    result = extract_uncertainty_budget(snapshot, source_snapshot_id="hyp1")

    assert result.rows == ()
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].key == "budget.statistics.hypothesis.diagnostic_only"
    assert result.diagnostics[0].severity == "info"


def test_uncertainty_budget_treats_statistics_time_series_as_diagnostics_only() -> None:
    from datalab_core.uncertainty_budget import extract_uncertainty_budget

    snapshot = {
        "schema": "datalab.result_snapshot.statistics",
        "schema_version": 1,
        "family": "statistics",
        "mode": "time_series_rolling",
        "metric_rows": [],
        "diagnostic_rows": [_row("insufficient_window", "statistics.time_series.diagnostic", value="warning")],
        "row_flags": [],
    }

    result = extract_uncertainty_budget(snapshot, source_snapshot_id="ts1")

    assert result.rows == ()
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].key == "budget.statistics.time_series.diagnostic_only"
    assert result.diagnostics[0].severity == "info"


def test_uncertainty_budget_extracts_root_diagnostic_rows() -> None:
    from datalab_core.uncertainty_budget import extract_uncertainty_budget

    snapshot = {
        "schema": "datalab.result_snapshot.root_solving",
        "schema_version": 1,
        "family": "root_solving",
        "metric_rows": [_row("roots_count", "root_solving.metric.roots_count", value=2)],
        "diagnostic_rows": [
            _row("jacobian_condition.0", "root_solving.diagnostic.jacobian_condition", value="12.5", row_index=0),
            _row("classification_tags.0.0", "root_solving.diagnostic.classification_tags", value="boundary"),
        ],
        "row_flags": [],
    }

    result = extract_uncertainty_budget(snapshot, source_snapshot_id="roots1")

    rows_by_label = {row.label_key: row for row in result.rows}
    assert rows_by_label["root_solving.metric.roots_count"].category == "root_solving.metric"
    assert rows_by_label["root_solving.diagnostic.jacobian_condition"].category == "root_solving.diagnostic"
    assert rows_by_label["root_solving.diagnostic.jacobian_condition"].source_row_id == "0"
    assert rows_by_label["root_solving.diagnostic.classification_tags"].value == "boundary"
    assert result.diagnostics == ()


def test_uncertainty_budget_extracts_fitting_comparison_candidates_and_covariance() -> None:
    from datalab_core.uncertainty_budget import extract_uncertainty_budget

    snapshot = {
        "schema": "datalab.result_snapshot.fitting_comparison",
        "schema_version": 1,
        "family": "fitting_comparison",
        "comparison_rows": [
            {"candidate_id": "linear", "status": "success", "chi2": "1.2", "warnings": ""},
            {"candidate_id": "bad", "status": "failed", "chi2": None, "error": "singular matrix"},
        ],
        "entries": [
            {
                "candidate_id": "linear",
                "fit_result": {"covariance": [["1", "0"], ["0", "2"]]},
            }
        ],
    }

    result = extract_uncertainty_budget(snapshot, source_snapshot_id="fit1")

    rows_by_key = {row.source_key: row for row in result.rows}
    assert rows_by_key["linear"].category == "fitting_comparison.candidate"
    assert rows_by_key["linear"].value == "1.2"
    assert rows_by_key["bad"].severity == "warning"
    assert rows_by_key["bad"].notes == ("singular matrix",)
    assert rows_by_key["covariance.linear"].category == "fitting_comparison.covariance"
    assert rows_by_key["covariance.linear"].value == 2
    assert result.diagnostics == ()


def test_uncertainty_budget_fails_closed_for_unsupported_or_malformed_snapshots() -> None:
    from datalab_core.uncertainty_budget import extract_uncertainty_budget

    unsupported = extract_uncertainty_budget(
        {"schema": "future", "schema_version": 1, "family": "statistics"},
        source_snapshot_id="bad1",
    )
    assert unsupported.rows == ()
    assert unsupported.diagnostics[0].severity == "error"
    assert unsupported.diagnostics[0].key == "budget.snapshot.unsupported_schema"

    malformed = extract_uncertainty_budget(
        {
            "schema": "datalab.result_snapshot.statistics",
            "schema_version": 1,
            "family": "statistics",
            "metric_rows": [_row("mean", "statistics.metric.mean", value=1.25)],
            "diagnostic_rows": [],
            "row_flags": [],
        },
        source_snapshot_id="bad2",
    )
    assert malformed.rows == ()
    assert malformed.diagnostics[0].key == "budget.statistics.metric_rows.malformed"

    malformed_fitting = extract_uncertainty_budget(
        {
            "schema": "datalab.result_snapshot.fitting_comparison",
            "schema_version": 1,
            "family": "fitting_comparison",
            "comparison_rows": [{"candidate_id": "ok", "status": "success", "chi2": "1"}, "bad-row"],
            "entries": [],
        },
        source_snapshot_id="bad3",
    )
    assert malformed_fitting.rows == ()
    assert malformed_fitting.diagnostics[0].key == "budget.fitting_comparison.malformed_row"

    malformed_fitting_float = extract_uncertainty_budget(
        {
            "schema": "datalab.result_snapshot.fitting_comparison",
            "schema_version": 1,
            "family": "fitting_comparison",
            "comparison_rows": [{"candidate_id": "ok", "status": "success", "chi2": 1.25}],
            "entries": [],
        },
        source_snapshot_id="bad4",
    )
    assert malformed_fitting_float.rows == ()
    assert malformed_fitting_float.diagnostics[0].key == "budget.fitting_comparison.malformed_value"


def test_uncertainty_budget_row_rejects_json_float_values() -> None:
    from datalab_core.uncertainty_budget import UncertaintyBudgetRow

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        UncertaintyBudgetRow(
            family="statistics",
            result_id="r1",
            source_snapshot_id="s1",
            source_row_id=None,
            source_key="mean",
            category="statistics.metric",
            label_key="statistics.metric.mean",
            value=cast(Any, 1.25),
        )


def _row(
    key: str,
    label_key: str,
    *,
    value: object = None,
    uncertainty: object = None,
    row_index: object = None,
    render_group: str = "metric",
    message_key: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "key": key,
        "label_key": label_key,
        "severity": "info",
        "render_group": render_group,
    }
    if value is not None:
        row["value"] = value
    if uncertainty is not None:
        row["uncertainty"] = uncertainty
    if row_index is not None:
        row["row_index"] = row_index
    if message_key is not None:
        row["message_key"] = message_key
    return row


def _contains_float(value: Any) -> bool:
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(key) or _contains_float(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_contains_float(item) for item in value)
    return False
