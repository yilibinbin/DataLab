from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
from datalab_core.results import ResultStatus
from datalab_core.statistics import build_statistics_result_snapshot
from datalab_core.statistics import render_statistics_snapshot_outputs
from datalab_core.statistics import run_statistics
from datalab_core.statistics_matrix import (
    MATRIX_PAYLOAD_SCHEMA,
    MATRIX_RESULT_CACHE_KIND,
    MATRIX_WORKFLOW_MODE,
    validate_statistics_matrix_payload,
    validate_statistics_matrix_snapshot,
)
from datalab_latex.latex_tables_statistics_matrix import generate_statistics_matrix_latex
from shared.plotting import render_correlation_heatmap_from_spec
from shared.plotting import statistics_matrix_correlation_heatmap_spec_from_payload


def test_statistics_matrix_listwise_sample_covariance_and_correlation() -> None:
    envelope = run_statistics(
        _matrix_request(
            rows=(("1", "2"), ("2", "4"), ("3", "6")),
            missing_policy="listwise",
            use_sample=True,
        )
    )

    assert envelope.status is ResultStatus.SUCCEEDED
    payload = envelope.payload
    assert payload["schema"] == MATRIX_PAYLOAD_SCHEMA
    assert payload["workflow_mode"] == MATRIX_WORKFLOW_MODE
    assert payload["row_count"] == 3
    assert payload["source_row_ids"] == ["1", "2", "3"]
    assert payload["matrices"]["covariance"]["values"] == [
        ["1.0000000000000000000000000000000", "2.0000000000000000000000000000000"],
        ["2.0000000000000000000000000000000", "4.0000000000000000000000000000000"],
    ]
    assert payload["matrices"]["correlation"]["values"] == [
        ["1", "1.0000000000000000000000000000000"],
        ["1.0000000000000000000000000000000", "1"],
    ]
    assert payload["correlation_metadata"]["budget_eligible"] is True


def test_statistics_matrix_payload_and_snapshot_preserve_display_only_units() -> None:
    base_request = _matrix_request(
        rows=(("1", "2"), ("2", "4"), ("3", "6")),
        missing_policy="listwise",
        use_sample=True,
    )
    request = ComputeJobRequest(
        mode=base_request.mode,
        inputs={
            **base_request.inputs,
            "units": {
                "enabled": True,
                "mode": "display_only",
                "inputs": {"A": {"unit": "m"}, "B": {"unit": "s"}},
                "outputs": {"covariance": {"unit": "m*s"}, "correlation": {"unit": "1"}},
            },
        },
        options=base_request.options,
        request_id="matrix-units",
    )

    envelope = run_statistics(request)

    assert envelope.status is ResultStatus.SUCCEEDED
    assert envelope.payload["units"]["inputs"] == {"A": {"unit": "m"}, "B": {"unit": "s"}}
    snapshot = build_statistics_result_snapshot(MATRIX_RESULT_CACHE_KIND, envelope.payload)
    assert snapshot is not None
    validate_statistics_matrix_snapshot(snapshot)
    assert snapshot["units"]["outputs"] == {"covariance": {"unit": "m*s"}, "correlation": {"unit": "1"}}
    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, headers = rendered
    assert "Unit: m*s" in text
    assert headers == ["matrix", "row_column", "column", "value", "count", "denominator", "unit"]
    covariance_rows = [row for row in csv_rows if row["matrix"] == "covariance"]
    correlation_rows = [row for row in csv_rows if row["matrix"] == "correlation"]
    assert covariance_rows and all(row["unit"] == "m*s" for row in covariance_rows)
    assert correlation_rows and all("unit" not in row for row in correlation_rows)


def test_statistics_matrix_pairwise_preserves_missing_cells_before_scalar_parsing() -> None:
    envelope = run_statistics(
        _matrix_request(
            rows=(("1", "10"), ("", "20"), ("3", "30")),
            missing_policy="pairwise",
            use_sample=False,
        )
    )

    assert envelope.status is ResultStatus.SUCCEEDED
    payload = envelope.payload
    assert payload["row_count"] == 3
    assert payload["matrices"]["covariance"]["counts"] == [[2, 2], [2, 3]]
    assert payload["matrices"]["covariance"]["denominators"] == [[2, 2], [2, 3]]
    assert payload["correlation_metadata"] == {
        "source": "statistics_covariance_correlation",
        "row_alignment": "pairwise",
        "weighted": False,
        "budget_eligible": False,
    }


def test_statistics_matrix_zero_variance_disables_budget_eligibility() -> None:
    envelope = run_statistics(
        _matrix_request(
            rows=(("1", "2"), ("1", "3"), ("1", "4")),
            missing_policy="listwise",
            use_sample=True,
        )
    )

    payload = envelope.payload
    assert payload["matrices"]["correlation"]["values"][0][0] is None
    assert payload["matrices"]["correlation"]["values"][0][1] is None
    assert payload["correlation_metadata"]["budget_eligible"] is False
    assert any(item["code"] == "zero_variance" for item in payload["diagnostics"])


def test_statistics_matrix_validator_rejects_json_floats_and_nonfinite_strings() -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "2"), ("2", "4"), ("3", "6")), missing_policy="listwise")
    ).payload

    tampered_float = deepcopy(payload)
    tampered_float["matrices"]["covariance"]["values"][0][0] = 1.0
    with pytest.raises(TypeError, match="JSON floats"):
        validate_statistics_matrix_payload(tampered_float)

    tampered_nonfinite = deepcopy(payload)
    tampered_nonfinite["matrices"]["correlation"]["values"][0][1] = "nan"
    with pytest.raises(ValueError, match="finite"):
        validate_statistics_matrix_payload(tampered_nonfinite)


def test_statistics_matrix_validator_requires_source_row_ids_for_pairwise_rows() -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "2"), ("", "3"), ("4", "5")), missing_policy="pairwise")
    ).payload
    tampered = deepcopy(payload)
    tampered["source_row_ids"] = ["1", "2"]

    with pytest.raises(ValueError, match="source_row_ids"):
        validate_statistics_matrix_payload(tampered)


def test_statistics_matrix_snapshot_renders_text_and_long_form_csv() -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "2"), ("2", "4"), ("3", "6")), missing_policy="listwise")
    ).payload

    snapshot = build_statistics_result_snapshot(MATRIX_RESULT_CACHE_KIND, payload)
    assert snapshot is not None
    validate_statistics_matrix_snapshot(snapshot)
    assert snapshot["mode"] == MATRIX_WORKFLOW_MODE
    assert snapshot["source"]["value_columns"] == ["A", "B"]
    assert snapshot["matrices"][0]["kind"] == "covariance"
    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, headers = rendered

    assert "Covariance/correlation matrix" in text
    assert "Missing data: listwise" in text
    assert headers == ["matrix", "row_column", "column", "value", "count", "denominator"]
    assert {
        "matrix": "covariance",
        "row_column": "A",
        "column": "B",
        "value": "2.0000000000000000000000000000000",
        "count": 3,
        "denominator": 2,
    } in csv_rows


def test_statistics_matrix_snapshot_validator_rejects_derived_source_drift() -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "2"), ("2", "4"), ("3", "6")), missing_policy="listwise")
    ).payload
    snapshot = build_statistics_result_snapshot(MATRIX_RESULT_CACHE_KIND, payload)
    assert snapshot is not None
    tampered = deepcopy(snapshot)
    tampered["source"]["missing_policy"] = "pairwise"

    with pytest.raises(ValueError, match="missing_policy"):
        validate_statistics_matrix_snapshot(tampered)


def test_statistics_matrix_snapshot_validator_rejects_matrix_projection_drift() -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "2"), ("2", "4"), ("3", "6")), missing_policy="listwise")
    ).payload
    snapshot = build_statistics_result_snapshot(MATRIX_RESULT_CACHE_KIND, payload)
    assert snapshot is not None
    tampered = deepcopy(snapshot)
    tampered["matrices"][0]["values"][0][0] = "999"

    with pytest.raises(ValueError, match="matrices"):
        validate_statistics_matrix_snapshot(tampered)


def test_statistics_matrix_latex_uses_dcolumn_and_null_safe_cells(tmp_path: Path) -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "2"), ("1", "3"), ("1", "4")), missing_policy="listwise")
    ).payload
    tex_path = tmp_path / "statistics-matrix.tex"

    tex = generate_statistics_matrix_latex(
        payload,
        tex_path,
        use_dcolumn=True,
        latex_group_size=3,
    )

    assert tex_path.read_text(encoding="utf-8") == tex
    assert "\\usepackage{dcolumn}" in tex
    assert "\\newcolumntype{d}[1]{D{.}{.}{#1}}" in tex
    assert "S[table-format=" not in tex
    assert "\\multicolumn{1}{c}{--}" in tex


def test_statistics_matrix_latex_can_use_siunitx_columns() -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "2"), ("2", "4"), ("3", "6")), missing_policy="listwise")
    ).payload

    tex = generate_statistics_matrix_latex(payload, use_dcolumn=False, latex_group_size=0)

    assert "\\usepackage{dcolumn}" not in tex
    # Column spec is now computed from the actual cell magnitudes (audit F13),
    # so assert a siunitx S column is used rather than a hardcoded table-format.
    assert "S[table-format=" in tex


def test_statistics_matrix_latex_handles_pairwise_payload_summary() -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "10"), ("", "20"), ("3", "30")), missing_policy="pairwise")
    ).payload

    tex = generate_statistics_matrix_latex(payload)

    assert r"Missing data: \texttt{pairwise}" in tex
    assert r"denominator: \texttt{sample}" in tex
    assert "rows: 3/3." in tex


def test_statistics_matrix_latex_renders_covariance_unit_as_text_only() -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "2"), ("2", "4"), ("3", "6")), missing_policy="listwise")
    ).payload

    tex = generate_statistics_matrix_latex(
        payload,
        units={
            "enabled": True,
            "mode": "display_only",
            "outputs": {"covariance": {"unit": "m*s"}, "correlation": {"unit": "1"}},
        },
    )

    assert r"Unit: \texttt{m*s}" in tex
    assert "Correlation" in tex
    assert r"Unit: \texttt{1}" not in tex


def test_statistics_matrix_correlation_heatmap_renders_for_complete_matrix() -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "2"), ("2", "4"), ("3", "6")), missing_policy="listwise")
    ).payload

    spec = statistics_matrix_correlation_heatmap_spec_from_payload(payload)
    assert spec is not None
    assert spec.plot_key == "statistics.correlation_heatmap"
    png = render_correlation_heatmap_from_spec(spec)

    assert png is not None
    assert png.startswith(b"\x89PNG")


def test_statistics_matrix_correlation_heatmap_suppresses_null_cells() -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "2"), ("1", "3"), ("1", "4")), missing_policy="listwise")
    ).payload

    assert statistics_matrix_correlation_heatmap_spec_from_payload(payload) is None


def test_statistics_matrix_validator_rejects_out_of_range_correlation() -> None:
    payload = run_statistics(
        _matrix_request(rows=(("1", "2"), ("2", "4"), ("3", "6")), missing_policy="listwise")
    ).payload
    tampered = deepcopy(payload)
    tampered["matrices"]["correlation"]["values"][0][1] = "1.01"
    tampered["matrices"]["correlation"]["values"][1][0] = "1.01"

    with pytest.raises(ValueError, match="within"):
        validate_statistics_matrix_payload(tampered)


def test_statistics_matrix_requires_two_distinct_columns() -> None:
    with pytest.raises(ValueError, match="at least two"):
        run_statistics(
            ComputeJobRequest(
                mode=JobMode.STATISTICS,
                inputs={
                    "workflow_mode": MATRIX_WORKFLOW_MODE,
                    "headers": ("A", "B"),
                    "rows": (("1", "2"),),
                    "value_columns": ("A",),
                },
                options=JobOptions(precision_digits=32, uncertainty_digits=1),
                request_id="matrix-invalid",
            )
        )


def test_statistics_standard_workflow_still_uses_scalar_values() -> None:
    envelope = run_statistics(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ("1", "2", "3"),
                "sigmas": (None, None, None),
                "stats_mode": "mean",
                "use_sample": True,
                "use_weighted_variance": True,
            },
            options=JobOptions(precision_digits=32, uncertainty_digits=1),
            request_id="standard-statistics",
        )
    )

    assert envelope.status is ResultStatus.SUCCEEDED
    assert envelope.payload["mean"] == "2.0"


def _matrix_request(
    *,
    rows: tuple[tuple[str, str], ...],
    missing_policy: str,
    use_sample: bool = True,
) -> ComputeJobRequest:
    return ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "workflow_mode": MATRIX_WORKFLOW_MODE,
            "headers": ("A", "B"),
            "rows": rows,
            "value_columns": ("A", "B"),
            "missing_policy": missing_policy,
            "use_sample": use_sample,
        },
        options=JobOptions(precision_digits=32, uncertainty_digits=1),
        request_id=f"matrix-{missing_policy}",
    )
