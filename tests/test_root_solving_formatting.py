from __future__ import annotations

import mpmath as mp

from root_solving import render_root_result
from root_solving.formatting import render_root_batch_result
from root_solving.models import RootBatchResult, RootBatchRowResult, RootResult, RootValue


def test_render_root_with_uncertainty_to_markdown_and_csv() -> None:
    result = RootResult(
        roots=(RootValue("x", mp.mpf("2.3456789"), uncertainty=mp.mpf("0.001234567")),),
        backend="mpmath",
        mode="scalar",
        residual_norm=mp.mpf("1e-20"),
    )

    markdown, csv_rows, csv_headers = render_root_result(result, display_digits=6, uncertainty_digits=2)

    assert csv_headers == ["name", "value", "uncertainty", "display_value", "backend", "mode", "residual_norm"]
    assert csv_rows == [
        {
            "name": "x",
            "value": "2.34568",
            "uncertainty": "0.00123457",
            "display_value": "2.3457(12)",
            "backend": "mpmath",
            "mode": "scalar",
            "residual_norm": "1.0e-20",
        }
    ]
    assert markdown == "\n".join(
        [
            "| name | value | backend | mode | residual_norm |",
            "| --- | --- | --- | --- | --- |",
            "| x | 2.3457(12) | mpmath | scalar | 1.0e-20 |",
        ]
    )


def test_render_root_without_uncertainty_leaves_empty_uncertainty_fields() -> None:
    result = RootResult(
        roots=(RootValue("x", mp.mpf("123456789.0")),),
        backend="scipy",
        mode="scalar",
        residual_norm=mp.mpf("0"),
    )

    markdown, csv_rows, _ = render_root_result(result, display_digits=5)

    assert csv_rows[0]["value"] == "1.2346e+8"
    assert csv_rows[0]["uncertainty"] == ""
    assert csv_rows[0]["display_value"] == "1.2346e+8"
    assert "| x | 1.2346e+8 | scipy | scalar | 0.0 |" in markdown


def test_render_root_with_missing_value_falls_back_to_empty_display() -> None:
    result = RootResult(
        roots=(RootValue("x", None, uncertainty=mp.mpf("0.1")),),
        backend="mpmath",
        mode="scalar",
    )

    markdown, csv_rows, _ = render_root_result(result, display_digits=5)

    assert csv_rows[0]["value"] == ""
    assert csv_rows[0]["display_value"] == ""
    assert "| x |  | mpmath | scalar |  |" in markdown


def test_render_uncertainty_scientific_display_uses_plain_exponent() -> None:
    result = RootResult(
        roots=(RootValue("x", mp.mpf("123456789.0"), uncertainty=mp.mpf("120000")),),
        backend="mpmath",
        mode="scalar",
    )

    markdown, csv_rows, _ = render_root_result(result, display_digits=5, uncertainty_digits=2)

    assert csv_rows[0]["display_value"] == "1.2346(12)e+8"
    assert r"\text" not in markdown
    assert "1.2346(12)e+8" in markdown


def test_render_root_uncertainty_digits_controls_compact_display() -> None:
    result = RootResult(
        roots=(RootValue("x", mp.mpf("2.3456789"), uncertainty=mp.mpf("0.001234567")),),
        backend="mpmath",
        mode="scalar",
    )

    one_digit, one_rows, _ = render_root_result(result, display_digits=8, uncertainty_digits=1)
    three_digits, three_rows, _ = render_root_result(result, display_digits=8, uncertainty_digits=3)

    assert one_rows[0]["display_value"] != three_rows[0]["display_value"]
    assert one_rows[0]["display_value"] in one_digit
    assert three_rows[0]["display_value"] in three_digits


def test_render_complex_polynomial_roots_as_a_plus_b_i_without_uncertainty() -> None:
    result = RootResult(
        roots=(
            RootValue("x1", mp.mpc("0", "1")),
            RootValue("x2", complex(0, -1)),
        ),
        backend="mpmath",
        mode="polynomial",
        residual_norm=mp.mpf("2.5e-30"),
    )

    markdown, csv_rows, _ = render_root_result(result, display_digits=4)

    assert csv_rows == [
        {
            "name": "x1",
            "value": "0.0 + 1.0 i",
            "uncertainty": "",
            "display_value": "0.0 + 1.0 i",
            "backend": "mpmath",
            "mode": "polynomial",
            "residual_norm": "2.5e-30",
        },
        {
            "name": "x2",
            "value": "0.0 - 1.0 i",
            "uncertainty": "",
            "display_value": "0.0 - 1.0 i",
            "backend": "mpmath",
            "mode": "polynomial",
            "residual_norm": "2.5e-30",
        },
    ]
    assert "| x1 | 0.0 + 1.0 i | mpmath | polynomial | 2.5e-30 |" in markdown
    assert "| x2 | 0.0 - 1.0 i | mpmath | polynomial | 2.5e-30 |" in markdown


def test_render_warnings_below_result_table() -> None:
    result = RootResult(
        roots=(RootValue("x", mp.mpf("2.0")),),
        backend="mpmath",
        mode="scalar",
        residual_norm=mp.mpf("1e-12"),
        warnings=("Jacobian is ill-conditioned.", "SciPy validation failed; used mpmath fallback."),
    )

    markdown, _, _ = render_root_result(result, display_digits=3)

    table, warnings = markdown.split("\n\n", maxsplit=1)
    assert table.endswith("| x | 2.0 | mpmath | scalar | 1.0e-12 |")
    assert warnings == "\n".join(
        [
            "Warnings:",
            "- Jacobian is ill-conditioned.",
            "- SciPy validation failed; used mpmath fallback.",
        ]
    )


def test_render_root_result_includes_uncertainty_method_details_without_csv_columns() -> None:
    result = RootResult(
        roots=(RootValue("x", mp.mpf("2.0"), uncertainty=mp.mpf("0.05")),),
        backend="mpmath",
        mode="scalar",
        residual_norm=mp.mpf("1e-20"),
        details={
            "uncertainty_method": "monte_carlo",
            "monte_carlo_samples": 2000,
            "monte_carlo_failures": 0,
        },
    )

    markdown, csv_rows, csv_headers = render_root_result(result, display_digits=6)

    assert csv_headers == ["name", "value", "uncertainty", "display_value", "backend", "mode", "residual_norm"]
    assert "uncertainty_method" not in csv_rows[0]
    assert "Details:" in markdown
    assert "- uncertainty method: monte_carlo" in markdown
    assert "- monte carlo samples: 2000" in markdown
    assert "- monte carlo failures: 0" in markdown


def test_render_scan_multiple_flattens_roots_to_csv_rows() -> None:
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={"A": "4"},
                result=RootResult(
                    roots=(RootValue("x", mp.mpf("-2")), RootValue("x", mp.mpf("2"))),
                    backend="scipy",
                    mode="scan_multiple",
                ),
            ),
        ),
        headers=("A",),
    )

    markdown, csv_rows, headers = render_root_batch_result(batch, display_digits=8)

    assert "input_row_index" in headers
    assert "root_index" in headers
    assert "A" in headers
    assert len(csv_rows) == 2
    assert csv_rows[0]["input_row_index"] == "0"
    assert csv_rows[0]["root_index"] == "0"
    assert csv_rows[0]["A"] == "4"
    assert csv_rows[0]["value"] == "-2.0"
    assert csv_rows[1]["root_index"] == "1"
    assert csv_rows[1]["value"] == "2.0"
    assert "| input_row_index |" in markdown


def test_render_batch_result_includes_uncertainty_method_details_without_csv_columns() -> None:
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                result=RootResult(
                    roots=(RootValue("x", mp.mpf("2"), uncertainty=mp.mpf("0.05")),),
                    backend="mpmath",
                    mode="scalar",
                    details={
                        "uncertainty_method": "monte_carlo",
                        "monte_carlo_samples": 2000,
                        "monte_carlo_failures": 0,
                    },
                ),
            ),
        ),
    )

    markdown, csv_rows, headers = render_root_batch_result(batch, display_digits=8)

    assert "uncertainty_method" not in headers
    assert "uncertainty_method" not in csv_rows[0]
    assert "Details:" in markdown
    assert "- uncertainty method: monte_carlo" in markdown
    assert "- monte carlo samples: 2000" in markdown
    assert "- monte carlo failures: 0" in markdown


def test_render_batch_result_aggregates_monte_carlo_detail_counters() -> None:
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                result=RootResult(
                    roots=(RootValue("x", mp.mpf("2"), uncertainty=mp.mpf("0.05")),),
                    backend="mpmath",
                    mode="scalar",
                    details={
                        "uncertainty_method": "monte_carlo",
                        "monte_carlo_failures": 1,
                        "monte_carlo_valid_samples": 1999,
                    },
                ),
            ),
            RootBatchRowResult(
                row_index=1,
                result=RootResult(
                    roots=(RootValue("x", mp.mpf("3"), uncertainty=mp.mpf("0.04")),),
                    backend="mpmath",
                    mode="scalar",
                    details={
                        "uncertainty_method": "linear",
                        "monte_carlo_failures": 2,
                        "monte_carlo_valid_samples": 1998,
                        "monte_carlo_first_failure": "row 2 sample failed",
                    },
                ),
            ),
        ),
    )

    markdown, _csv_rows, _headers = render_root_batch_result(batch, display_digits=8)

    assert "- uncertainty method: mixed" in markdown
    assert "- monte carlo failures: 3" in markdown
    assert "- monte carlo valid samples: 3997" in markdown
    assert "- monte carlo first failure: row 2 sample failed" in markdown


def test_render_root_result_localizes_details_to_chinese() -> None:
    result = RootResult(
        roots=(RootValue("x", mp.mpf("2"), uncertainty=mp.mpf("0.05")),),
        backend="mpmath",
        mode="scalar",
        details={"uncertainty_method": "taylor", "monte_carlo_failures": 0},
    )

    markdown, _, _ = render_root_result(result, display_digits=8, language="zh")

    assert "详情:" in markdown
    assert "- 不确定度方法: 泰勒" in markdown
    assert "- 蒙特卡洛失败数: 0" in markdown
    assert "Details:" not in markdown
    assert "uncertainty method" not in markdown


def test_render_row_failure_as_one_csv_row() -> None:
    batch = RootBatchResult(
        rows=(RootBatchRowResult(row_index=2, source_values={"A": "bad"}, failure="failed"),),
        headers=("A",),
    )

    markdown, csv_rows, headers = render_root_batch_result(batch, display_digits=8)

    assert "failure" in headers
    assert csv_rows == [
        {
            "input_row_index": "2",
            "root_index": "",
            "A": "bad",
            "name": "",
            "value": "",
            "uncertainty": "",
            "display_value": "",
            "backend": "",
            "mode": "",
            "residual_norm": "",
            "failure": "failed",
        }
    ]
    assert "| 2 |  | bad |  |  |  |  |  | failed |" in markdown


def test_render_batch_disambiguates_source_headers_that_match_result_columns() -> None:
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={"name": "sample", "failure": "input-ok"},
                result=RootResult(
                    roots=(RootValue("x", mp.mpf("2")),),
                    backend="scipy",
                    mode="scalar",
                ),
            ),
        ),
        headers=("name", "failure"),
    )

    markdown, csv_rows, headers = render_root_batch_result(batch, display_digits=8)

    assert "input_name" in headers
    assert "input_failure" in headers
    assert csv_rows[0]["input_name"] == "sample"
    assert csv_rows[0]["input_failure"] == "input-ok"
    assert csv_rows[0]["name"] == "x"
    assert csv_rows[0]["failure"] == ""
    assert "| input_row_index | root_index | input_name | input_failure | name |" in markdown
