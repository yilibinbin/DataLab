from __future__ import annotations

from copy import deepcopy
from typing import Any

import mpmath as mp
import pytest


def _submit_hypothesis(inputs: dict[str, Any], *, precision_digits: int = 16):
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics

    return SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={"workflow_mode": "hypothesis_tests", "value_column": "A", **inputs},
            options=JobOptions(precision_digits=precision_digits),
            request_id="hypothesis-test",
        )
    )


def _run_hypothesis(inputs: dict[str, Any], *, precision_digits: int = 16) -> dict[str, Any]:
    from datalab_core.results import ResultStatus

    result = _submit_hypothesis(inputs, precision_digits=precision_digits)
    assert result.status is ResultStatus.SUCCEEDED
    return dict(result.payload)


def test_one_sample_t_low_precision_matches_scipy_reference() -> None:
    from scipy import stats

    payload = _run_hypothesis(
        {
            "test_kind": "one_sample_t",
            "values": ["2", "3", "4", "5", "6"],
            "source_row_ids": ["r1", "r2", "r3", "r4", "r5"],
            "mu0": "3",
            "alternative": "two_sided",
            "alpha": "0.05",
        },
        precision_digits=16,
    )

    assert payload["schema"] == "datalab.statistics.hypothesis_test.v1"
    assert payload["workflow_mode"] == "hypothesis_tests"
    assert payload["backend"] == "scipy"
    scipy_result = stats.ttest_1samp([2, 3, 4, 5, 6], popmean=3, alternative="two-sided")
    result = payload["result"]
    assert mp.almosteq(mp.mpf(str(result["statistic"])), mp.mpf(str(scipy_result.statistic)))
    assert mp.almosteq(mp.mpf(str(result["p_value"])), mp.mpf(str(scipy_result.pvalue)))
    assert result["degrees_of_freedom"] == "4.0"
    assert result["reject_null"] is False
    assert payload["inputs"]["source_row_ids"] == ["r1", "r2", "r3", "r4", "r5"]


def test_one_sample_t_high_precision_uses_mpmath_backend() -> None:
    payload = _run_hypothesis(
        {
            "test_kind": "one_sample_t",
            "values": ["2", "3", "4", "5", "6"],
            "mu0": "3",
            "alternative": "greater",
            "alpha": "0.05",
        },
        precision_digits=50,
    )

    assert payload["backend"] == "mpmath"
    p_value = mp.mpf(str(payload["result"]["p_value"]))
    assert mp.mpf("0") <= p_value <= mp.mpf("1")
    assert payload["result"]["reject_null"] is False
    effect_rows = {row["key"]: row["value"] for row in payload["result"]["effect_rows"]}
    assert effect_rows["mean"] == "4.0"
    assert effect_rows["mean_difference"] == "1.0"
    assert payload["inputs"]["source_row_ids"] == ["1", "2", "3", "4", "5"]


def test_sign_test_exact_p_values_and_tie_diagnostics() -> None:
    base_inputs = {
        "test_kind": "sign_test",
        "values": ["1", "2", "3", "-1", "0"],
        "m0": "0",
        "alpha": "0.05",
    }

    two_sided = _run_hypothesis({**base_inputs, "alternative": "two_sided"}, precision_digits=40)
    greater = _run_hypothesis({**base_inputs, "alternative": "greater"}, precision_digits=40)
    less = _run_hypothesis({**base_inputs, "alternative": "less"}, precision_digits=40)

    assert two_sided["backend"] == "mpmath"
    assert two_sided["inputs"]["sign_mode"] == "one_sample"
    assert two_sided["result"]["positive_count"] == 3
    assert two_sided["result"]["negative_count"] == 1
    assert two_sided["result"]["tie_count"] == 1
    assert two_sided["result"]["effective_n"] == 4
    assert mp.mpf(str(two_sided["result"]["p_value"])) == mp.mpf("0.625")
    assert mp.mpf(str(greater["result"]["p_value"])) == mp.mpf("0.3125")
    assert mp.mpf(str(less["result"]["p_value"])) == mp.mpf("0.9375")
    assert two_sided["diagnostics"][0]["code"] == "sign_test_ties_dropped"


def test_paired_t_low_precision_matches_scipy_reference() -> None:
    from scipy import stats

    values_a = [10, 12, 9, 11, 13]
    values_b = [8, 9, 10, 10, 12]
    payload = _run_hypothesis(
        {
            "test_kind": "paired_t",
            "values": [str(value) for value in values_a],
            "paired_values": [str(value) for value in values_b],
            "delta0": "0",
            "alternative": "greater",
            "value_column_b": "B",
        },
        precision_digits=16,
    )

    scipy_result = stats.ttest_rel(values_a, values_b, alternative="greater")
    result = payload["result"]
    assert payload["backend"] == "scipy"
    assert payload["inputs"]["value_columns"] == ["A", "B"]
    assert payload["inputs"]["source_row_ids"] == ["1", "2", "3", "4", "5"]
    assert payload["inputs"]["source_row_ids_b"] == ["1", "2", "3", "4", "5"]
    assert mp.almosteq(mp.mpf(str(result["statistic"])), mp.mpf(str(scipy_result.statistic)))
    assert mp.almosteq(mp.mpf(str(result["p_value"])), mp.mpf(str(scipy_result.pvalue)))
    assert result["degrees_of_freedom"] == "4.0"


def test_welch_t_low_precision_matches_scipy_reference_and_records_group_b_rows() -> None:
    from scipy import stats

    values_a = [1, 2, 3, 4]
    values_b = [2, 2, 5, 6, 7]
    payload = _run_hypothesis(
        {
            "test_kind": "welch_t",
            "values": [str(value) for value in values_a],
            "values_b": [str(value) for value in values_b],
            "source_row_ids": ["a1", "a2", "a3", "a4"],
            "source_row_ids_b": ["b1", "b2", "b3", "b4", "b5"],
            "delta0": "0",
            "alternative": "less",
            "value_column_b": "B",
        },
        precision_digits=16,
    )

    scipy_result = stats.ttest_ind(values_a, values_b, equal_var=False, alternative="less")
    result = payload["result"]
    assert payload["backend"] == "scipy"
    assert payload["inputs"]["source_row_ids"] == ["a1", "a2", "a3", "a4"]
    assert payload["inputs"]["source_row_ids_b"] == ["b1", "b2", "b3", "b4", "b5"]
    assert result["sample_size_a"] == 4
    assert result["sample_size_b"] == 5
    assert mp.almosteq(mp.mpf(str(result["statistic"])), mp.mpf(str(scipy_result.statistic)))
    assert mp.almosteq(mp.mpf(str(result["p_value"])), mp.mpf(str(scipy_result.pvalue)))


def test_welch_t_allows_one_zero_variance_group_when_standard_error_is_positive() -> None:
    payload = _run_hypothesis(
        {
            "test_kind": "welch_t",
            "values": ["2", "2", "2"],
            "values_b": ["1", "2", "4", "8"],
            "alternative": "greater",
        },
        precision_digits=50,
    )

    assert payload["backend"] == "mpmath"
    assert mp.mpf(str(payload["result"]["p_value"])) >= 0
    effect_rows = {row["key"]: row["value"] for row in payload["result"]["effect_rows"]}
    assert effect_rows["sample_variance_a"] == "0.0"


def test_chi_square_gof_matches_scipy_counts_and_high_precision_probabilities() -> None:
    from scipy import stats

    observed = [12, 18, 20]
    expected = [10, 20, 20]
    payload = _run_hypothesis(
        {
            "test_kind": "chi_square_gof",
            "values": [str(value) for value in observed],
            "expected_counts": [str(value) for value in expected],
            "alternative": "greater",
            "alpha": "0.05",
        },
        precision_digits=16,
    )

    scipy_result = stats.chisquare(observed, f_exp=expected)
    result = payload["result"]
    assert payload["backend"] == "scipy"
    assert result["statistic_name"] == "chi_square"
    assert result["degrees_of_freedom"] == "2.0"
    assert result["expected_source"] == "counts"
    assert mp.almosteq(mp.mpf(str(result["statistic"])), mp.mpf(str(scipy_result.statistic)))
    assert mp.almosteq(mp.mpf(str(result["p_value"])), mp.mpf(str(scipy_result.pvalue)))

    probability_payload = _run_hypothesis(
        {
            "test_kind": "chi_square_gof",
            "values": [str(value) for value in observed],
            "expected_probabilities": ["1", "2", "2"],
            "fitted_parameter_count": 1,
        },
        precision_digits=50,
    )
    probability_result = probability_payload["result"]
    assert probability_payload["backend"] == "mpmath"
    assert probability_result["expected_source"] == "probabilities"
    assert probability_result["probability_normalized"] is True
    assert probability_result["degrees_of_freedom"] == "1.0"
    assert mp.mpf(str(probability_result["p_value"])) >= 0

    small_expected_payload = _run_hypothesis(
        {
            "test_kind": "chi_square_gof",
            "values": ["1", "9"],
            "expected_probabilities": ["1", "9"],
        },
        precision_digits=50,
    )
    assert small_expected_payload["diagnostics"][0]["code"] == "chi_square_expected_count_lt_5"
    assert small_expected_payload["diagnostics"][0]["severity"] == "warning"


def test_hypothesis_snapshot_and_render_outputs_are_payload_authoritative() -> None:
    from datalab_core.statistics import build_statistics_result_snapshot, render_statistics_snapshot_outputs

    payload = _run_hypothesis(
        {
            "test_kind": "paired_t",
            "values": ["10", "12", "9", "11"],
            "paired_values": ["8", "9", "10", "10"],
            "source_row_ids": ["r1", "r2", "r3", "r4"],
            "source_row_ids_b": ["r1", "r2", "r3", "r4"],
            "delta0": "0",
            "alternative": "greater",
            "value_column_b": "B",
        },
        precision_digits=50,
    )

    tampered_payload = deepcopy(payload)
    tampered_payload["analysis_rows"] = []
    snapshot = build_statistics_result_snapshot(
        "statistics_hypothesis_test",
        tampered_payload,
        precision={"compute_digits": 50, "uncertainty_digits": 1},
    )

    assert snapshot is not None
    assert snapshot["mode"] == "hypothesis_tests"
    assert snapshot["hypothesis_test"]["result"]["statistic"] == payload["result"]["statistic"]
    assert snapshot["source"]["test_kind"] == "paired_t"
    assert snapshot["source"]["source_row_ids_b"] == ["r1", "r2", "r3", "r4"]
    assert {row["key"] for row in snapshot["metric_rows"]} >= {"statistic", "p_value", "reject_null"}

    rendered = render_statistics_snapshot_outputs(snapshot)
    assert rendered is not None
    text, csv_rows, headers = rendered
    assert headers == ["test", "metric", "value", "uncertainty", "note"]
    assert "=== Hypothesis Test ===" in text
    assert "paired_t" in text
    csv_by_metric = {str(row["metric"]): row for row in csv_rows}
    assert csv_by_metric["statistic"]["value"] == payload["result"]["statistic"]
    assert csv_by_metric["effect.mean_difference_minus_delta0"]["value"]


def test_hypothesis_snapshot_units_apply_only_to_scientific_rows() -> None:
    from datalab_core.statistics import build_statistics_result_snapshot, render_statistics_snapshot_outputs

    payload = _run_hypothesis(
        {
            "test_kind": "one_sample_t",
            "values": ["2", "3", "4", "5"],
            "mu0": "0",
            "alternative": "two_sided",
            "units": {
                "enabled": True,
                "mode": "display_only",
                "outputs": {"statistic": {"unit": "s"}},
            },
        },
        precision_digits=50,
    )
    snapshot = build_statistics_result_snapshot("statistics_hypothesis_test", payload)
    assert snapshot is not None

    rendered = render_statistics_snapshot_outputs(snapshot)

    assert rendered is not None
    text, csv_rows, headers = rendered
    assert headers == ["test", "metric", "value", "uncertainty", "note", "value_unit"]
    assert "Metric | Value | Unit | Note" in text
    by_metric = {str(row["metric"]): row for row in csv_rows}
    assert by_metric["statistic"]["value_unit"] == "s"
    assert by_metric["p_value"]["value_unit"] == ""
    assert by_metric["degrees_of_freedom"]["value_unit"] == ""


def test_hypothesis_snapshot_rejects_tampered_payload_and_source_metadata() -> None:
    from datalab_core.statistics import build_statistics_result_snapshot, render_statistics_snapshot_outputs

    payload = _run_hypothesis(
        {
            "test_kind": "chi_square_gof",
            "values": ["12", "18", "20"],
            "expected_counts": ["10", "20", "20"],
        },
        precision_digits=50,
    )
    float_payload = deepcopy(payload)
    float_payload["result"]["p_value"] = 0.5
    with pytest.raises(TypeError, match="JSON floats"):
        build_statistics_result_snapshot("statistics_hypothesis_test", float_payload)

    snapshot = build_statistics_result_snapshot("statistics_hypothesis_test", payload)
    assert snapshot is not None
    tampered_snapshot = deepcopy(snapshot)
    tampered_snapshot["source"]["test_kind"] = "one_sample_t"
    with pytest.raises(ValueError, match="test_kind"):
        render_statistics_snapshot_outputs(tampered_snapshot)

    for field, value, match in (
        ("value_columns", ["wrong"], "value_columns"),
        ("source_row_ids", ["row-1", "row-2", "row-3"], "source_row_ids"),
        ("row_count", 99, "row_count"),
    ):
        source_tampered = deepcopy(snapshot)
        source_tampered["source"][field] = value
        with pytest.raises(ValueError, match=match):
            render_statistics_snapshot_outputs(source_tampered)

    paired_payload = _run_hypothesis(
        {
            "test_kind": "paired_t",
            "values": ["10", "12", "9"],
            "paired_values": ["8", "9", "10"],
            "source_row_ids": ["r1", "r2", "r3"],
            "source_row_ids_b": ["r1", "r2", "r3"],
        },
        precision_digits=50,
    )
    paired_snapshot = build_statistics_result_snapshot("statistics_hypothesis_test", paired_payload)
    assert paired_snapshot is not None
    paired_tampered = deepcopy(paired_snapshot)
    paired_tampered["source"]["source_row_ids_b"] = ["r1", "r2", "other"]
    with pytest.raises(ValueError, match="source_row_ids_b"):
        render_statistics_snapshot_outputs(paired_tampered)


def test_hypothesis_latex_uses_semantic_snapshot_and_shared_number_formatting(tmp_path) -> None:
    from datalab_core.statistics import build_statistics_result_snapshot
    from statistics_utils import generate_statistics_hypothesis_latex

    payload = _run_hypothesis(
        {
            "test_kind": "chi_square_gof",
            "values": ["12", "18", "20"],
            "expected_counts": ["10", "20", "20"],
        },
        precision_digits=50,
    )
    snapshot = build_statistics_result_snapshot("statistics_hypothesis_test", payload)
    assert snapshot is not None

    tex_path = tmp_path / "hypothesis.tex"
    generate_statistics_hypothesis_latex(
        snapshot,
        str(tex_path),
        use_dcolumn=True,
        digits=20,
        uncertainty_digits=1,
        latex_group_size=3,
    )

    content = tex_path.read_text(encoding="utf-8")
    assert "\\usepackage{dcolumn}" in content
    assert "\\sisetup{" in content
    assert "Hypothesis Test" in content
    assert "chi\\_square\\_gof" in content
    assert "p\\_value" in content
    assert "\\multicolumn{1}{c}{Value}" in content
    assert "Metadata" in content
    assert "Backend & mpmath" in content
    assert "Precision digits & 50" in content
    assert "Alternative & greater" in content
    assert "Value columns & A, expected" in content
    assert "degrees\\_of\\_freedom & 2.0" in content


def test_hypothesis_latex_renders_units_only_for_supported_rows(tmp_path) -> None:
    from datalab_core.statistics import build_statistics_result_snapshot
    from statistics_utils import generate_statistics_hypothesis_latex

    payload = _run_hypothesis(
        {
            "test_kind": "one_sample_t",
            "values": ["2", "3", "4", "5"],
            "mu0": "0",
            "units": {
                "enabled": True,
                "mode": "display_only",
                "outputs": {"statistic": {"unit": "s"}},
            },
        },
        precision_digits=50,
    )
    snapshot = build_statistics_result_snapshot("statistics_hypothesis_test", payload)
    assert snapshot is not None

    tex_path = tmp_path / "hypothesis-units.tex"
    generate_statistics_hypothesis_latex(
        snapshot,
        str(tex_path),
        use_dcolumn=True,
        digits=20,
        uncertainty_digits=1,
    )

    content = tex_path.read_text(encoding="utf-8")
    assert "Metric & Unit &" in content
    assert "statistic & s &" in content
    assert "p\\_value &  &" in content


@pytest.mark.parametrize(
    ("inputs", "match"),
    [
        ({"test_kind": "one_sample_t", "values": ["1", "2"], "alpha": "1"}, "alpha"),
        ({"test_kind": "one_sample_t", "values": ["1"], "mu0": "0"}, "at least two"),
        ({"test_kind": "one_sample_t", "values": ["2", "2"], "mu0": "0"}, "variance"),
        ({"test_kind": "one_sample_t", "values": ["1", "nan"], "mu0": "0"}, "finite"),
        ({"test_kind": "sign_test", "values": ["0", "0"], "m0": "0"}, "non-tied"),
        ({"test_kind": "sign_test", "values": ["1", "-1"], "sign_mode": "paired"}, "one_sample"),
        (
            {"test_kind": "paired_t", "values": ["1", "2"], "paired_values": ["1"], "delta0": "0"},
            "equal-length",
        ),
        (
            {
                "test_kind": "paired_t",
                "values": ["1", "2"],
                "paired_values": ["1", "2"],
                "source_row_ids": ["r1", "r2"],
                "source_row_ids_b": ["r1", "r3"],
            },
            "source_row_ids",
        ),
        ({"test_kind": "welch_t", "values": ["1", "2"], "values_b": ["3"], "delta0": "0"}, "two values"),
        (
            {
                "test_kind": "chi_square_gof",
                "values": ["1.5", "2"],
                "expected_counts": ["1", "2.5"],
            },
            "integer",
        ),
        (
            {
                "test_kind": "chi_square_gof",
                "values": ["1", "2"],
                "expected_counts": ["0", "3"],
            },
            "zero",
        ),
        (
            {
                "test_kind": "chi_square_gof",
                "values": ["1", "2"],
                "expected_counts": ["1", "2"],
                "fitted_parameter_count": 1,
            },
            "degrees",
        ),
    ],
)
def test_hypothesis_invalid_inputs_fail_closed(inputs: dict[str, Any], match: str) -> None:
    from datalab_core.results import ResultStatus

    result = _submit_hypothesis(inputs, precision_digits=50)

    assert result.status is ResultStatus.FAILED
    assert match in str(result.payload["message"])


def test_hypothesis_payload_validator_rejects_json_floats_and_malformed_p_values() -> None:
    from datalab_core.statistics_hypothesis import validate_statistics_hypothesis_payload

    payload = _run_hypothesis(
        {
            "test_kind": "sign_test",
            "values": ["1", "-1", "2"],
            "m0": "0",
            "alternative": "greater",
        },
        precision_digits=40,
    )

    float_payload = deepcopy(payload)
    float_payload["result"]["p_value"] = 0.5
    with pytest.raises(TypeError, match="JSON floats"):
        validate_statistics_hypothesis_payload(float_payload)

    malformed_payload = deepcopy(payload)
    malformed_payload["result"]["p_value"] = "1.2"
    with pytest.raises(ValueError, match="p_value"):
        validate_statistics_hypothesis_payload(malformed_payload)

    mismatched_rows = deepcopy(payload)
    mismatched_rows["inputs"]["source_row_ids"] = ["only-one-row"]
    with pytest.raises(ValueError, match="source_row_ids"):
        validate_statistics_hypothesis_payload(mismatched_rows)

    missing_rows = deepcopy(payload)
    missing_rows["inputs"]["source_row_ids"] = []
    with pytest.raises(ValueError, match="source_row_ids"):
        validate_statistics_hypothesis_payload(missing_rows)

    high_precision_scipy = deepcopy(payload)
    high_precision_scipy["backend"] = "scipy"
    high_precision_scipy["precision_used"] = 50
    with pytest.raises(ValueError, match="scipy backend"):
        validate_statistics_hypothesis_payload(high_precision_scipy)

    bad_sign_backend = deepcopy(payload)
    bad_sign_backend["backend"] = "scipy"
    bad_sign_backend["precision_used"] = 16
    with pytest.raises(ValueError, match="sign_test"):
        validate_statistics_hypothesis_payload(bad_sign_backend)

    bad_sign_effective_n = deepcopy(payload)
    bad_sign_effective_n["result"]["effective_n"] = 0
    with pytest.raises(ValueError, match="effective_n"):
        validate_statistics_hypothesis_payload(bad_sign_effective_n)

    t_payload = _run_hypothesis(
        {
            "test_kind": "one_sample_t",
            "values": ["1", "2", "3"],
            "mu0": "0",
        },
        precision_digits=40,
    )
    bad_t_sample_size = deepcopy(t_payload)
    bad_t_sample_size["result"]["sample_size"] = 1
    with pytest.raises(ValueError, match="sample_size"):
        validate_statistics_hypothesis_payload(bad_t_sample_size)

    bad_t_df = deepcopy(t_payload)
    bad_t_df["result"]["degrees_of_freedom"] = "999"
    with pytest.raises(ValueError, match="degrees_of_freedom"):
        validate_statistics_hypothesis_payload(bad_t_df)

    welch_payload = _run_hypothesis(
        {
            "test_kind": "welch_t",
            "values": ["1", "2", "3"],
            "values_b": ["2", "3", "4"],
        },
        precision_digits=40,
    )
    bad_welch_source = deepcopy(welch_payload)
    bad_welch_source["inputs"]["source_row_ids_b"] = ["b1"]
    with pytest.raises(ValueError, match="source_row_ids_b"):
        validate_statistics_hypothesis_payload(bad_welch_source)

    paired_payload = _run_hypothesis(
        {
            "test_kind": "paired_t",
            "values": ["1", "2", "3"],
            "paired_values": ["1", "1", "1"],
        },
        precision_digits=40,
    )
    bad_paired_source = deepcopy(paired_payload)
    bad_paired_source["inputs"]["source_row_ids_b"] = ["1", "2", "shifted"]
    with pytest.raises(ValueError, match="source_row_ids_b"):
        validate_statistics_hypothesis_payload(bad_paired_source)

    chi_payload = _run_hypothesis(
        {
            "test_kind": "chi_square_gof",
            "values": ["10", "20", "30"],
            "expected_probabilities": ["1", "2", "3"],
        },
        precision_digits=40,
    )
    bad_chi_df = deepcopy(chi_payload)
    bad_chi_df["result"]["degrees_of_freedom"] = "99"
    with pytest.raises(ValueError, match="degrees_of_freedom"):
        validate_statistics_hypothesis_payload(bad_chi_df)

    bad_chi_source = deepcopy(chi_payload)
    bad_chi_source["inputs"]["expected_source"] = "counts"
    with pytest.raises(ValueError, match="expected_source"):
        validate_statistics_hypothesis_payload(bad_chi_source)

    stray_chi_field = deepcopy(t_payload)
    stray_chi_field["inputs"]["expected_source"] = "counts"
    with pytest.raises(ValueError, match="chi_square_gof"):
        validate_statistics_hypothesis_payload(stray_chi_field)

    bad_units = deepcopy(payload)
    bad_units["units"] = {"enabled": True, "mode": "active"}
    with pytest.raises(ValueError, match="statistics units only support display_only"):
        validate_statistics_hypothesis_payload(bad_units)
