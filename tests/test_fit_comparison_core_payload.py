from __future__ import annotations

import inspect
from collections.abc import Sequence
from typing import Any

import mpmath as mp
import pytest

from fitting.hp_fitter import FitResult


def _fit_result(*, chi2: str, reduced_chi2: str, aic: str, bic: str, rmse: str, r2: str) -> FitResult:
    return FitResult(
        params={"a": mp.mpf("1")},
        param_errors={"a": mp.mpf("0.1")},
        chi2=mp.mpf(chi2),
        reduced_chi2=mp.mpf(reduced_chi2),
        aic=mp.mpf(aic),
        bic=mp.mpf(bic),
        r2=mp.mpf(r2),
        rmse=mp.mpf(rmse),
        residuals=[mp.mpf("999")],
        fitted_curve=[mp.mpf("-999")],
        covariance=[[mp.mpf("1")]],
        details={"diagnostic_warnings": ["sentinel warning"]},
    )


def test_build_fitting_comparison_request_normalizes_json_safe_payload() -> None:
    from datalab_core.fitting_comparison import build_fitting_comparison_request
    from datalab_core.jobs import JobMode

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", mp.mpf("3")), ("2", "5")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
            {"candidate_id": "quad", "label": "Quadratic", "model_type": "polynomial", "poly_degree": 2},
        ),
        precision_digits=70,
        request_id="fit-comparison-core",
    )

    assert request.mode is JobMode.FITTING
    assert request.request_id == "fit-comparison-core"
    assert request.options.precision_digits == 70
    assert request.inputs["comparison"] is True
    assert request.inputs["headers"] == ["x", "y"]
    assert request.inputs["data_rows"] == [["0", "1"], ["1", "3.0"], ["2", "5"]]
    assert request.inputs["target_series"] == ["1", "3.0", "5"]
    assert request.inputs["comparison_candidates"] == [
        {
            "candidate_id": "linear",
            "label": "Linear",
            "model_type": "polynomial",
            "model_expr": "",
            "parameter_config": {},
            "parameter_names": [],
            "poly_degree": 1,
            "inverse_min": 1,
            "inverse_max": 3,
            "pade_m": 1,
            "pade_n": 1,
            "custom_constants": {},
        },
        {
            "candidate_id": "quad",
            "label": "Quadratic",
            "model_type": "polynomial",
            "model_expr": "",
            "parameter_config": {},
            "parameter_names": [],
            "poly_degree": 2,
            "inverse_min": 1,
            "inverse_max": 3,
            "pade_m": 1,
            "pade_n": 1,
            "custom_constants": {},
        },
    ]


def test_run_fitting_comparison_returns_rows_and_serialized_fit_results() -> None:
    from datalab_core.fitting_comparison import (
        build_fitting_comparison_request,
        fitting_comparison_payload_to_fit_results,
        run_fitting_comparison,
    )
    from datalab_core.results import ResultStatus

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "3"), ("2", "5"), ("3", "7")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
            {
                "candidate_id": "custom",
                "label": "Custom",
                "model_type": "custom",
                "model_expr": "a*x+b",
                "parameter_config": {"a": {"initial": "1"}, "b": {"initial": "0"}},
                "parameter_names": ("a", "b"),
            },
        ),
        precision_digits=80,
    )

    envelope = run_fitting_comparison(request)

    assert envelope.status is ResultStatus.SUCCEEDED
    assert envelope.payload["comparison"] is True
    assert envelope.payload["candidate_count"] == 2
    assert [row["candidate_id"] for row in envelope.payload["rows"]] == ["linear", "custom"]
    assert [row["status"] for row in envelope.payload["rows"]] == ["success", "success"]
    assert "best_model" not in envelope.payload
    assert "winner" not in envelope.payload
    entries = envelope.payload["entries"]
    assert entries[0]["fit_result"]
    assert entries[1]["fit_result"]
    fits = fitting_comparison_payload_to_fit_results(envelope.payload)
    assert set(fits) == {"linear", "custom"}
    assert mp.almosteq(fits["linear"].params["b0"], mp.mpf("1"), abs_eps=mp.mpf("1e-40"))
    assert mp.almosteq(fits["linear"].params["b1"], mp.mpf("2"), abs_eps=mp.mpf("1e-40"))


def test_run_fitting_comparison_serializes_at_requested_precision_under_low_ambient_dps() -> None:
    # Regression: mp.dps is process-global. Serialization (serialize_fitting_comparison_result
    # -> mp.nstr(mp.mpf(value), n=keep_digits)) must run at the request's precision, not the
    # ambient mp.dps left by a prior job. A non-terminating slope (1/3) exposes truncation.
    from datalab_core.fitting_comparison import (
        build_fitting_comparison_request,
        run_fitting_comparison,
    )
    from datalab_core.results import ResultStatus

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        # y = x/3 -> the linear-fit slope b1 is 1/3 = 0.3333... (non-terminating)
        data_rows=(("0", "0"), ("3", "1"), ("6", "2"), ("9", "3")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
        ),
        precision_digits=60,
    )

    previous_dps = mp.mp.dps
    mp.mp.dps = 15  # simulate a fresh/leaked worker thread at the default precision
    try:
        envelope = run_fitting_comparison(request)
    finally:
        restored_dps = mp.mp.dps
        mp.mp.dps = previous_dps

    assert envelope.status is ResultStatus.SUCCEEDED
    # The guard must restore the ambient dps on exit (no leak).
    assert restored_dps == 15

    entry = envelope.payload["entries"][0]
    serialized = entry["fit_result"]
    # The slope b1 == 1/3 (non-terminating). It must be serialized correctly to the
    # requested precision, not re-rounded to ~15 digits under the ambient dps. Compare
    # the round-tripped value to 1/3 at high precision: ~16-digit truncation would
    # leave an error around 1e-16, far above the 1e-40 tolerance below.
    with mp.workdps(80):
        b1_value = mp.mpf(str(serialized["params"]["b1"]))
        one_third = mp.mpf(1) / mp.mpf(3)
        assert mp.almosteq(b1_value, one_third, abs_eps=mp.mpf("1e-40")), (
            f"b1 serialized as {serialized['params']['b1']!r}; "
            "precision guard missing around serialization (truncated to ambient dps)"
        )


def test_fitting_comparison_payload_formatter_accepts_result_envelope_payload() -> None:
    from datalab_core.fitting_comparison import build_fitting_comparison_request, run_fitting_comparison
    from fitting.comparison_formatting import build_comparison_table_rows_from_payload

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "3"), ("2", "5"), ("3", "7")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
        ),
        precision_digits=60,
    )

    envelope = run_fitting_comparison(request)
    rows = build_comparison_table_rows_from_payload(envelope.payload)

    assert rows[0]["candidate_id"] == "linear"
    assert rows[0]["status"] == "success"
    assert rows[0]["chi2"]


def test_fitting_comparison_snapshot_round_trips_rows_without_winner_language() -> None:
    from datalab_core.fitting_comparison import (
        build_fitting_comparison_request,
        build_fitting_comparison_result_snapshot,
        render_fitting_comparison_snapshot_outputs,
        run_fitting_comparison,
    )
    from fitting.comparison_formatting import COMPARISON_TABLE_HEADERS

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "3"), ("2", "5"), ("3", "7")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
            {"candidate_id": "quadratic", "label": "Quadratic", "model_type": "polynomial", "poly_degree": 2},
        ),
        precision_digits=60,
    )
    envelope = run_fitting_comparison(request)

    snapshot = build_fitting_comparison_result_snapshot(
        "fitting_comparison",
        envelope.payload,
        overview_state="complete",
        plot_metadata=({"path": "attachments/plots/plot-001.png", "role": "primary"},),
        precision={"compute_digits": 60, "uncertainty_digits": 1},
    )

    assert snapshot is not None
    assert snapshot["schema"] == "datalab.result_snapshot.fitting_comparison"
    assert snapshot["schema_version"] == 1
    assert snapshot["family"] == "fitting_comparison"
    assert snapshot["mode"] == "selected"
    assert snapshot["source"]["candidate_count"] == 2
    assert snapshot["source"]["successful_count"] == 2
    assert [row["candidate_id"] for row in snapshot["comparison_rows"]] == ["linear", "quadratic"]
    assert "best_model" not in snapshot
    assert "winner" not in snapshot
    assert snapshot["compatibility"]["rendered_caches_authoritative"] is False
    assert snapshot["compatibility"]["result_cache_kind"] == "fitting_comparison"

    outputs = render_fitting_comparison_snapshot_outputs(snapshot)
    assert outputs is not None
    text, csv_rows, headers = outputs
    assert headers == COMPARISON_TABLE_HEADERS
    assert "Selected Fit Comparison" in text
    assert "Linear | success" in text
    assert "winner" not in text.lower()
    assert [row["candidate_id"] for row in csv_rows] == ["linear", "quadratic"]


def test_fitting_comparison_snapshot_rejects_non_comparison_kind() -> None:
    from datalab_core.fitting_comparison import (
        build_fitting_comparison_request,
        build_fitting_comparison_result_snapshot,
        run_fitting_comparison,
    )

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "3"), ("2", "5"), ("3", "7")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
        ),
        precision_digits=60,
    )
    envelope = run_fitting_comparison(request)

    assert build_fitting_comparison_result_snapshot("fit_single", envelope.payload) is None


def test_fitting_comparison_snapshot_fail_closed_for_non_json_rows() -> None:
    from datalab_core.fitting_comparison import build_fitting_comparison_result_snapshot

    payload = {
        "comparison": True,
        "rows": [
            {
                "candidate_id": "bad",
                "order": 1,
                "model_label": "Bad",
                "status": "success",
                "free_parameter_count": object(),
                "chi2": "1",
                "reduced_chi2": "1",
                "aic": "1",
                "bic": "1",
                "rmse": "1",
                "r2": "1",
                "warnings": [],
                "error": None,
            }
        ],
        "entries": [],
    }

    assert build_fitting_comparison_result_snapshot("fitting_comparison", payload) is None


def test_run_fitting_comparison_keeps_candidate_failures_as_rows() -> None:
    from datalab_core.fitting_comparison import build_fitting_comparison_request, run_fitting_comparison

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "2"), ("2", "3")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {
                "candidate_id": "bad-inverse",
                "label": "Bad inverse",
                "model_type": "inverse_power",
                "inverse_min": 1,
                "inverse_max": 2,
            },
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
        ),
        precision_digits=60,
    )

    envelope = run_fitting_comparison(request)

    rows = envelope.payload["rows"]
    assert [row["candidate_id"] for row in rows] == ["bad-inverse", "linear"]
    assert rows[0]["status"] == "failed"
    assert rows[0]["error"]
    assert rows[0]["chi2"] is None
    assert rows[1]["status"] == "success"


def test_run_fitting_comparison_keeps_candidate_construction_failures_as_rows() -> None:
    from datalab_core.fitting_comparison import build_fitting_comparison_request, run_fitting_comparison

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "3"), ("2", "5"), ("3", "7")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {
                "candidate_id": "bad-poly",
                "label": "Bad polynomial",
                "model_type": "polynomial",
                "poly_degree": 0,
            },
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
        ),
        precision_digits=60,
    )

    envelope = run_fitting_comparison(request)

    rows = envelope.payload["rows"]
    assert [row["candidate_id"] for row in rows] == ["bad-poly", "linear"]
    assert rows[0]["status"] == "failed"
    assert rows[0]["error"]
    assert rows[1]["status"] == "success"
    assert envelope.payload["entries"][0]["fit_result"] is None
    assert envelope.payload["entries"][1]["fit_result"]


def test_build_request_defers_candidate_metadata_failures_to_result_rows() -> None:
    from datalab_core.fitting_comparison import build_fitting_comparison_request, run_fitting_comparison

    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "3"), ("2", "5"), ("3", "7")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=(
            {
                "candidate_id": "bad-free-count",
                "label": "Bad free count",
                "model_type": "polynomial",
                "free_parameter_count": -1,
            },
            {
                "candidate_id": "bad-type",
                "label": "Bad type",
                "model_type": "not-a-fit-model",
            },
            {"candidate_id": "linear", "label": "Linear", "model_type": "polynomial", "poly_degree": 1},
        ),
        precision_digits=60,
    )

    envelope = run_fitting_comparison(request)

    rows = envelope.payload["rows"]
    assert [row["candidate_id"] for row in rows] == ["bad-free-count", "bad-type", "linear"]
    assert [row["status"] for row in rows] == ["failed", "failed", "success"]
    assert rows[0]["error"]
    assert rows[1]["error"]
    assert rows[2]["chi2"] is not None


def test_run_fitting_comparison_serializes_sentinel_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import datalab_core.fitting_comparison as core_comparison
    from datalab_core.fitting_comparison import (
        build_fitting_comparison_request,
        run_fitting_comparison,
    )
    from fitting.model_comparison import (
        FitComparisonCandidate,
        FitComparisonEntry,
        FitComparisonResult,
        FitComparisonRow,
    )

    sentinel = _fit_result(
        chi2="123456789",
        reduced_chi2="987654321",
        aic="-12345.5",
        bic="67890.25",
        rmse="0.0000001234",
        r2="-42.5",
    )

    def fake_compare(
        candidates: Sequence[FitComparisonCandidate],
        **_kwargs: Any,
    ) -> FitComparisonResult:
        return FitComparisonResult(
            entries=[
                FitComparisonEntry(
                    candidate_id=candidates[0].candidate_id,
                    order=1,
                    label=candidates[0].label,
                    candidate=candidates[0],
                    fit_result=sentinel,
                )
            ],
            rows=[
                FitComparisonRow(
                    candidate_id=candidates[0].candidate_id,
                    order=1,
                    model_label=candidates[0].label,
                    status="success",
                    free_parameter_count=1,
                    chi2=sentinel.chi2,
                    reduced_chi2=sentinel.reduced_chi2,
                    aic=sentinel.aic,
                    bic=sentinel.bic,
                    rmse=sentinel.rmse,
                    r2=sentinel.r2,
                    warnings=("sentinel warning",),
                )
            ],
        )

    monkeypatch.setattr(core_comparison, "compare_selected_fits", fake_compare)
    request = build_fitting_comparison_request(
        headers=("x", "y"),
        data_rows=(("0", "1"), ("1", "2")),
        variable_map={"x": "x"},
        target_column="y",
        candidates=({"candidate_id": "sentinel", "label": "Sentinel", "model_type": "polynomial"},),
        precision_digits=50,
    )

    envelope = run_fitting_comparison(request)
    row = envelope.payload["rows"][0]

    assert row["chi2"] == "123456789.0"
    assert row["reduced_chi2"] == "987654321.0"
    assert row["aic"] == "-12345.5"
    assert row["bic"] == "67890.25"
    assert mp.mpf(row["rmse"]) == sentinel.rmse
    assert row["r2"] == "-42.5"
    assert envelope.payload["entries"][0]["fit_result"]["chi2"] == "123456789.0"


def test_fitting_comparison_core_does_not_import_auto_fit_selection() -> None:
    import datalab_core.fitting_comparison as core_comparison

    source = inspect.getsource(core_comparison)
    assert "auto_fit_dataset" not in source
    assert "_sequence_model" not in source
    assert "AUTO_MODELS" not in source
    assert "best_model" not in source
