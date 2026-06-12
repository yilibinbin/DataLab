from __future__ import annotations

import mpmath as mp
import pytest

from shared.precision import precision_guard


def test_core_statistics_request_builder_creates_string_batches_through_session() -> None:
    from datalab_core.jobs import JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService
    from datalab_core.statistics import build_statistics_requests, run_statistics

    batches = build_statistics_requests(
        headers=("A", "sigma"),
        rows=(
            ("1.0000000000000000001", "-0.10000000000000000001"),
            ("2.0000000000000000002", "0.2"),
            ("3.0000000000000000003", "0.3"),
        ),
        value_col="A",
        sigma_col="sigma",
        stats_mode="weighted_sigma",
        precision_digits=80,
        segments=((-5, 2), (2, 99), (3, 3)),
        request_id_prefix="stats-batch",
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

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(batches[0].request)

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["row_count"] == 2
    assert result.payload["mode"] == "weighted_sigma"


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
            segments=segment,
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
            precision_digits=precision_digits,
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


def test_core_statistics_request_builder_absolutizes_infinite_sigma_text() -> None:
    from datalab_core.statistics import build_statistics_requests

    batches = build_statistics_requests(
        headers=("A", "sigma"),
        rows=(("1", "-inf"), ("2", "+Infinity")),
        value_col="A",
        sigma_col="sigma",
    )

    assert list(batches[0].request.inputs["sigmas"]) == ["inf", "Infinity"]


def test_core_statistics_request_builder_absolutizes_sigma_rows() -> None:
    from datalab_core.statistics import build_statistics_requests

    batches = build_statistics_requests(
        headers=("A",),
        rows=(("1",), ("2",)),
        sigma_rows=(("-0.05",), (mp.mpf("-0.10"),)),
        value_col="A",
    )

    assert list(batches[0].request.inputs["sigmas"]) == ["0.05", "0.1"]


def test_core_statistics_request_builder_validates_columns_and_empty_segments() -> None:
    from datalab_core.statistics import build_statistics_requests

    with pytest.raises(ValueError, match="Column not found"):
        build_statistics_requests(headers=("A",), rows=((mp.mpf("1"),),), value_col="B")

    with pytest.raises(ValueError, match="at least one value"):
        build_statistics_requests(headers=("A",), rows=((mp.mpf("1"),),), value_col="A", segments=((1, 1),))


def test_core_statistics_handler_runs_arithmetic_mean_through_session() -> None:
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


def test_core_statistics_handler_reports_zero_sigma_anchor_in_payload() -> None:
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
    assert any("infinite weight" in warning for warning in result.warnings)


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


def test_core_statistics_handler_falls_back_when_total_weight_is_zero() -> None:
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

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mean"] == "2.0"
    assert result.payload["method_label"] == "Weighted mean (fallback to unweighted)"
    assert result.payload["effective_n"] == "2.0"
    assert any("fell back to arithmetic mean" in warning for warning in result.warnings)


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
