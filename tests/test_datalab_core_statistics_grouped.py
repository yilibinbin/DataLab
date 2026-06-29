from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import mpmath as mp
import pytest

from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
from datalab_core.results import ResultStatus
from datalab_core.statistics import build_statistics_result_snapshot, render_statistics_snapshot_outputs, run_statistics
from datalab_core.history_compare import build_history_comparison
from datalab_core.statistics_grouped import (
    GROUPED_PAYLOAD_SCHEMA,
    GROUPED_RESULT_CACHE_KIND,
    GROUPED_WORKFLOW_MODE,
    statistics_grouped_mean_overview_spec_from_payload,
    validate_statistics_grouped_payload,
    validate_statistics_grouped_snapshot,
)
from datalab_latex.latex_tables_statistics_grouped import generate_statistics_grouped_latex
from shared.plotting import render_statistics_grouped_mean_overview_from_spec


def test_grouped_statistics_runs_per_group_and_value_column() -> None:
    envelope = run_statistics(
        _grouped_request(
            rows=(
                ("control", "1", "10"),
                ("treated", "2", "20"),
                ("control", "3", "30"),
            ),
            value_columns=("A", "B"),
        )
    )

    assert envelope.status is ResultStatus.SUCCEEDED
    payload = envelope.payload
    assert payload["schema"] == GROUPED_PAYLOAD_SCHEMA
    assert payload["workflow_mode"] == GROUPED_WORKFLOW_MODE
    assert payload["group_order"] == ["control", "treated"]

    control = payload["groups"][0]
    assert control["group"] == "control"
    assert control["group_source_row_ids"] == ["1", "3"]
    control_a = control["columns"][0]
    control_b = control["columns"][1]
    assert control_a["value_column"] == "A"
    assert control_a["row_count"] == 2
    assert control_a["included_source_row_ids"] == ["1", "3"]
    assert control_a["result"]["mean"] == "2.0"
    assert control_b["result"]["mean"] == "20.0"

    treated = payload["groups"][1]
    assert treated["group"] == "treated"
    assert treated["columns"][0]["result"]["mean"] == "2.0"


def test_grouped_statistics_preserves_text_groups_before_scalar_value_parsing() -> None:
    envelope = run_statistics(
        _grouped_request(
            rows=(("alpha", "1.25"), ("beta", "2.25")),
            value_columns=("A",),
        )
    )

    assert envelope.status is ResultStatus.SUCCEEDED
    assert envelope.payload["group_order"] == ["alpha", "beta"]


def test_grouped_statistics_snapshot_units_add_metric_unit_columns() -> None:
    request = _grouped_request(
        rows=(("control", "1"), ("control", "3")),
        value_columns=("A",),
    )
    request = ComputeJobRequest(
        mode=request.mode,
        inputs={
            **request.inputs,
            "units": {
                "enabled": True,
                "mode": "display_only",
                "outputs": {"mean": {"unit": "kg"}},
            },
        },
        options=request.options,
        request_id="grouped-units",
    )
    envelope = run_statistics(request)
    assert envelope.status is ResultStatus.SUCCEEDED
    snapshot = build_statistics_result_snapshot(GROUPED_RESULT_CACHE_KIND, envelope.payload)
    assert snapshot is not None

    rendered = render_statistics_snapshot_outputs(snapshot)

    assert rendered is not None
    text, csv_rows, headers = rendered
    assert "Value unit" in text
    assert headers == ["group", "column", "batch", "metric", "value", "uncertainty", "value_unit", "uncertainty_unit"]
    mean_row = next(row for row in csv_rows if row["metric"] == "mean")
    assert mean_row["value_unit"] == "kg"


def test_grouped_statistics_blank_group_and_value_cells_emit_diagnostics() -> None:
    envelope = run_statistics(
        _grouped_request(
            rows=(
                ("", "1"),
                ("control", ""),
                ("control", "2"),
            ),
            value_columns=("A",),
        )
    )

    payload = envelope.payload
    assert payload["group_order"] == ["control"]
    assert {item["code"] for item in payload["diagnostics"]} >= {"blank_group", "blank_value"}
    control_a = payload["groups"][0]["columns"][0]
    assert control_a["input_row_count"] == 2
    assert control_a["row_count"] == 1
    assert control_a["included_source_row_ids"] == ["3"]
    assert control_a["skipped_source_row_ids"] == ["2"]


def test_grouped_statistics_uses_embedded_uncertainties_when_no_sigma_column() -> None:
    envelope = run_statistics(
        _grouped_request(
            rows=(("g", "1.0(1)"), ("g", "2.0(2)")),
            value_columns=("A",),
            stats_mode="weighted_sigma",
        )
    )

    result = envelope.payload["groups"][0]["columns"][0]["result"]
    assert result["dropped"] == 0
    assert result["zero_sigma_anchor"] is False
    assert mp.almosteq(mp.mpf(result["mean"]), mp.mpf("1.2"))


def test_grouped_statistics_explicit_sigma_column_overrides_value_uncertainty() -> None:
    envelope = run_statistics(
        _grouped_request(
            headers=("Group", "A", "Sigma"),
            rows=(("g", "1.0(9)", "0.1"), ("g", "2.0(9)", "0.1")),
            value_columns=("A",),
            sigma_column="Sigma",
            stats_mode="weighted_sigma",
        )
    )

    result = envelope.payload["groups"][0]["columns"][0]["result"]
    assert result["dropped"] == 0
    assert mp.almosteq(mp.mpf(result["mean"]), mp.mpf("1.5"))


def test_grouped_statistics_preserves_high_precision_raw_numeric_strings() -> None:
    precise_a = "0.123456789012345678901234567890123456789"
    precise_b = "0.123456789012345678901234567890123456781"
    envelope = run_statistics(
        _grouped_request(
            rows=(("g", precise_a), ("g", precise_b)),
            value_columns=("A",),
            precision=60,
        )
    )

    result = envelope.payload["groups"][0]["columns"][0]["result"]
    expected = (mp.mpf(precise_a) + mp.mpf(precise_b)) / 2
    assert mp.almosteq(mp.mpf(result["mean"]), expected, rel_eps=mp.mpf("1e-55"))


def test_grouped_statistics_propagates_trim_fraction_to_descriptive_statistics() -> None:
    envelope = run_statistics(
        _grouped_request(
            rows=(("g", "1"), ("g", "2"), ("g", "3"), ("g", "100")),
            value_columns=("A",),
            stats_mode="descriptive",
            trim_fraction="0.25",
        )
    )

    result = envelope.payload["groups"][0]["columns"][0]["result"]
    assert result["trimmed_mean"] == "2.5"


def test_grouped_statistics_allows_standard_descriptive_nan_sentinels() -> None:
    envelope = run_statistics(
        _grouped_request(
            rows=(("g", "1"),),
            value_columns=("A",),
            stats_mode="descriptive",
        )
    )

    result = envelope.payload["groups"][0]["columns"][0]["result"]
    assert result["std_mean"] == "nan"
    validate_statistics_grouped_payload(envelope.payload)


def test_grouped_statistics_snapshot_renders_text_and_long_form_csv() -> None:
    payload = run_statistics(
        _grouped_request(
            rows=(
                ("control", "1", "10"),
                ("treated", "2", "20"),
                ("control", "3", "30"),
            ),
            value_columns=("A", "B"),
        )
    ).payload

    snapshot = build_statistics_result_snapshot(GROUPED_RESULT_CACHE_KIND, payload)
    assert snapshot is not None
    validate_statistics_grouped_snapshot(snapshot)
    assert snapshot["mode"] == GROUPED_WORKFLOW_MODE
    assert snapshot["source"]["group_column"] == "Group"
    assert snapshot["source"]["value_columns"] == ["A", "B"]
    assert snapshot["source"]["group_order"] == ["control", "treated"]

    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, headers = rendered
    assert "Grouped statistics" in text
    assert "Group 1: control" in text
    assert "std_mean |" not in text
    assert "Mean | 2.0 | 1.0" in text
    assert headers == ["group", "column", "batch", "metric", "value", "uncertainty"]
    assert {
        "group": "control",
        "column": "A",
        "batch": 1,
        "metric": "mean",
        "value": "2.0",
        "uncertainty": "1.0",
    } in csv_rows


def test_grouped_statistics_render_does_not_duplicate_standard_warnings() -> None:
    payload = run_statistics(
        _grouped_request(
            rows=(("g", "1"),),
            value_columns=("A",),
            stats_mode="descriptive",
        )
    ).payload
    snapshot = build_statistics_result_snapshot(GROUPED_RESULT_CACHE_KIND, payload)
    assert snapshot is not None

    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, _headers = rendered
    warning_text = "Mean confidence interval requires n>=2"

    assert text.count(warning_text) == 1
    assert sum(1 for row in csv_rows if warning_text in str(row["value"])) == 1


def test_grouped_statistics_render_preserves_outlier_reason_text() -> None:
    payload = run_statistics(
        _grouped_request(
            headers=("Group", "A", "Sigma"),
            rows=(("g", "0", "1"), ("g", "100", "1")),
            value_columns=("A",),
            sigma_column="Sigma",
        )
    ).payload
    snapshot = build_statistics_result_snapshot(GROUPED_RESULT_CACHE_KIND, payload)
    assert snapshot is not None

    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, _headers = rendered

    assert "metric sigma" in text
    assert any(row["metric"].startswith("outlier.") and "metric sigma" in row["uncertainty"] for row in csv_rows)


def test_grouped_statistics_snapshot_validator_rejects_source_drift() -> None:
    payload = run_statistics(
        _grouped_request(rows=(("g", "1"), ("g", "2")), value_columns=("A",))
    ).payload
    snapshot = build_statistics_result_snapshot(GROUPED_RESULT_CACHE_KIND, payload)
    assert snapshot is not None
    tampered = deepcopy(snapshot)
    tampered["source"]["group_column"] = "Other"

    with pytest.raises(ValueError, match="group_column"):
        validate_statistics_grouped_snapshot(tampered)


def test_grouped_statistics_snapshot_validator_rejects_groups_projection_drift() -> None:
    payload = run_statistics(
        _grouped_request(rows=(("g", "1"), ("g", "2")), value_columns=("A",))
    ).payload
    snapshot = build_statistics_result_snapshot(GROUPED_RESULT_CACHE_KIND, payload)
    assert snapshot is not None
    tampered = deepcopy(snapshot)
    tampered["groups"][0]["group"] = "other"

    with pytest.raises(ValueError, match="groups"):
        validate_statistics_grouped_snapshot(tampered)


def test_grouped_statistics_history_compare_aligns_reordered_groups_by_label() -> None:
    left_payload = run_statistics(
        _grouped_request(
            rows=(("control", "1"), ("treated", "20"), ("control", "3")),
            value_columns=("A",),
        )
    ).payload
    right_payload = run_statistics(
        _grouped_request(
            rows=(("treated", "20"), ("control", "4"), ("control", "6")),
            value_columns=("A",),
        )
    ).payload
    left_snapshot = build_statistics_result_snapshot(GROUPED_RESULT_CACHE_KIND, left_payload)
    right_snapshot = build_statistics_result_snapshot(GROUPED_RESULT_CACHE_KIND, right_payload)
    assert left_snapshot is not None
    assert right_snapshot is not None

    comparison = build_history_comparison(left_snapshot, right_snapshot)
    rows = comparison["rows"]
    mean_rows = [
        row
        for row in rows
        if row["label_key"] == "history.compare.statistics.grouped_metric_delta"
        and row["source"] == "Left=2.0; Right=5.0"
    ]

    assert mean_rows
    assert mean_rows[0]["value"] == "3.0"
    assert not [
        row
        for row in rows
        if row["label_key"] == "history.compare.statistics.grouped_metric_delta"
        and row["source"] == "Left=2.0; Right=20.0"
    ]


def test_grouped_statistics_latex_uses_shared_dcolumn_format_and_escapes_labels(tmp_path: Path) -> None:
    payload = run_statistics(
        _grouped_request(
            headers=("Group", "A&B", "Sigma"),
            rows=(
                ("control_1", "1.0(1)", "0.1"),
                ("control_1", "3.0(1)", "0.1"),
                ("treated", "5.0(2)", "0.2"),
            ),
            value_columns=("A&B",),
            sigma_column="Sigma",
            stats_mode="weighted_sigma",
        )
    ).payload
    tex_path = tmp_path / "statistics-grouped.tex"

    tex = generate_statistics_grouped_latex(
        payload,
        tex_path,
        use_dcolumn=True,
        digits=12,
        uncertainty_digits=1,
        latex_group_size=3,
    )

    assert tex_path.read_text(encoding="utf-8") == tex
    assert "\\usepackage{dcolumn}" in tex
    assert "\\newcolumntype{d}[1]{D{.}{.}{#1}}" in tex
    assert "S[table-format=" not in tex
    assert "control\\_1" in tex
    assert "A\\&B" in tex
    assert "Mean &" in tex
    assert "Std. error &" in tex


def test_grouped_statistics_latex_can_use_siunitx_columns() -> None:
    payload = run_statistics(
        _grouped_request(
            rows=(("control", "1"), ("treated", "2"), ("control", "3")),
            value_columns=("A",),
        )
    ).payload

    tex = generate_statistics_grouped_latex(payload, use_dcolumn=False, latex_group_size=0)

    assert "\\usepackage{dcolumn}" not in tex
    assert "S[table-format=" in tex
    assert "Grouped statistics" in tex


def test_grouped_statistics_latex_text_only_payload_uses_text_value_column() -> None:
    payload = run_statistics(
        _grouped_request(
            rows=(("g", ""),),
            value_columns=("A",),
        )
    ).payload

    tex = generate_statistics_grouped_latex(payload, use_dcolumn=True)

    assert "\\begin{tabular}{l l l l}" in tex
    assert "\\multicolumn{1}{l}{No numeric values.}" in tex
    assert "Blank value cell skipped" in tex


def test_grouped_statistics_latex_renders_units_in_text_column() -> None:
    payload = run_statistics(
        _grouped_request(
            rows=(("control", "1"), ("control", "3")),
            value_columns=("A",),
        )
    ).payload

    tex = generate_statistics_grouped_latex(
        payload,
        units={
            "enabled": True,
            "mode": "display_only",
            "outputs": {"mean": {"unit": "kg"}},
        },
    )

    assert "Group & Column & Metric & Unit &" in tex
    assert "Mean & kg &" in tex


def test_grouped_statistics_latex_cjk_diagnostic_enables_cjk_and_preserves_falsy_labels() -> None:
    payload = run_statistics(
        _grouped_request(
            rows=(("g", "1"), ("g", "2")),
            value_columns=("A",),
        )
    ).payload
    tampered = deepcopy(payload)
    tampered["diagnostics"] = [
        {
            "severity": "warning",
            "code": "cjk_warning",
            "message": "中文诊断",
            "group": 0,
            "column": False,
        }
    ]

    tex = generate_statistics_grouped_latex(tampered)

    assert "\\usepackage{xeCJK}" in tex
    assert "0 & False & Diagnostic" in tex
    assert "中文诊断" in tex


def test_grouped_statistics_mean_overview_plot_renders_png_bytes() -> None:
    payload = run_statistics(
        _grouped_request(
            rows=(
                ("control", "1", "10"),
                ("treated", "2", "20"),
                ("control", "3", "30"),
                ("treated", "6", "60"),
            ),
            value_columns=("A", "B"),
        )
    ).payload

    spec = statistics_grouped_mean_overview_spec_from_payload(payload)
    assert spec is not None
    assert spec.plot_key == "statistics.grouped_mean_overview"
    assert spec.labels == ("control / A", "control / B", "treated / A", "treated / B")
    png = render_statistics_grouped_mean_overview_from_spec(spec)

    assert png is not None
    assert png.startswith(b"\x89PNG")


def test_grouped_statistics_mean_overview_suppresses_missing_means() -> None:
    payload = run_statistics(
        _grouped_request(rows=(("g", "1"),), value_columns=("A",), stats_mode="descriptive")
    ).payload
    tampered = deepcopy(payload)
    tampered["groups"][0]["columns"][0]["result"]["mean"] = "nan"

    assert statistics_grouped_mean_overview_spec_from_payload(tampered) is None


def test_grouped_statistics_validator_rejects_json_floats_in_embedded_result() -> None:
    payload = run_statistics(
        _grouped_request(rows=(("g", "1"), ("g", "2")), value_columns=("A",))
    ).payload
    tampered = deepcopy(payload)
    tampered["groups"][0]["columns"][0]["result"]["mean"] = 1.5

    with pytest.raises(TypeError, match="JSON floats"):
        validate_statistics_grouped_payload(tampered)


def test_grouped_statistics_validator_rejects_invalid_numeric_metric_strings() -> None:
    payload = run_statistics(
        _grouped_request(rows=(("g", "1"), ("g", "2")), value_columns=("A",))
    ).payload
    tampered = deepcopy(payload)
    tampered["groups"][0]["columns"][0]["result"]["mean"] = "not-a-number"

    with pytest.raises(ValueError, match="valid numeric string"):
        validate_statistics_grouped_payload(tampered)


def test_grouped_statistics_validator_rejects_malformed_analysis_rows() -> None:
    payload = run_statistics(
        _grouped_request(rows=(("g", "1"), ("g", "2")), value_columns=("A",))
    ).payload
    tampered = deepcopy(payload)
    tampered["groups"][0]["columns"][0]["result"]["analysis_rows"] = [{"key": ""}]

    with pytest.raises(ValueError, match="key"):
        validate_statistics_grouped_payload(tampered)


def test_grouped_statistics_validator_rejects_non_string_warning_codes() -> None:
    payload = run_statistics(
        _grouped_request(rows=(("g", "1"),), value_columns=("A",))
    ).payload
    tampered = deepcopy(payload)
    tampered["groups"][0]["columns"][0]["result"]["warning_codes"] = [1]

    with pytest.raises(TypeError, match="warning_codes"):
        validate_statistics_grouped_payload(tampered)


def test_grouped_statistics_validator_rejects_malformed_standard_metadata_types() -> None:
    payload = run_statistics(
        _grouped_request(rows=(("g", "1"), ("g", "2")), value_columns=("A",))
    ).payload

    bad_precision = deepcopy(payload)
    bad_precision["groups"][0]["columns"][0]["result"]["precision_used"] = "40"
    with pytest.raises(TypeError, match="precision_used"):
        validate_statistics_grouped_payload(bad_precision)

    bad_zero_sigma = deepcopy(payload)
    bad_zero_sigma["groups"][0]["columns"][0]["result"]["zero_sigma_anchor"] = "false"
    with pytest.raises(TypeError, match="zero_sigma_anchor"):
        validate_statistics_grouped_payload(bad_zero_sigma)


def test_grouped_statistics_validator_rejects_malformed_outlier_flags() -> None:
    payload = run_statistics(
        _grouped_request(rows=(("g", "1"), ("g", "100")), value_columns=("A",))
    ).payload
    tampered = deepcopy(payload)
    tampered["groups"][0]["columns"][0]["result"]["outlier_flags"] = [{"source_row_id": "2"}]

    with pytest.raises(ValueError, match="missing keys"):
        validate_statistics_grouped_payload(tampered)


def test_grouped_statistics_validator_rejects_dropped_group_row_ids() -> None:
    payload = run_statistics(
        _grouped_request(rows=(("g", "1"), ("g", "")), value_columns=("A",))
    ).payload
    tampered = deepcopy(payload)
    tampered["groups"][0]["columns"][0]["skipped_source_row_ids"] = []

    with pytest.raises(ValueError, match="included/skipped row IDs must match"):
        validate_statistics_grouped_payload(tampered)


def test_grouped_statistics_rejects_malformed_numeric_cells() -> None:
    with pytest.raises(ValueError, match="not a valid numeric"):
        run_statistics(
            _grouped_request(
                rows=(("g", "1"), ("g", "not-a-number")),
                value_columns=("A",),
            )
        )


def _grouped_request(
    *,
    rows: tuple[tuple[str, ...], ...],
    value_columns: tuple[str, ...],
    headers: tuple[str, ...] = ("Group", "A", "B"),
    sigma_column: str = "",
    stats_mode: str = "mean",
    trim_fraction: str | None = None,
    precision: int = 40,
) -> ComputeJobRequest:
    inputs: dict[str, object] = {
        "workflow_mode": GROUPED_WORKFLOW_MODE,
        "headers": headers,
        "rows": rows,
        "group_column": "Group",
        "value_columns": value_columns,
        "sigma_column": sigma_column,
        "stats_mode": stats_mode,
        "use_sample": True,
        "use_weighted_variance": True,
        "source_row_ids": tuple(str(index) for index in range(1, len(rows) + 1)),
    }
    if trim_fraction is not None:
        inputs["trim_fraction"] = trim_fraction
    return ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs=inputs,
        options=JobOptions(precision_digits=precision, uncertainty_digits=1),
        request_id="grouped-statistics",
    )
