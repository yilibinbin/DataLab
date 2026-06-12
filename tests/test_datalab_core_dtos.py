from __future__ import annotations

import threading
import time
from dataclasses import FrozenInstanceError, asdict
from decimal import Decimal

import pytest


def test_core_job_request_is_frozen_and_string_only() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions

    request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "data_text": "A\n1.0000000000000000001",
            "constants": {"A": "1.23"},
            "columns": ["A"],
            "enabled": True,
            "missing": None,
        },
        options=JobOptions(precision_digits=80, uncertainty_digits=2),
    )

    assert request.mode is JobMode.STATISTICS
    assert request.inputs["data_text"].endswith("0001")
    assert asdict(request.options) == {
        "precision_digits": 80,
        "uncertainty_digits": 2,
        "parallel": {},
    }
    with pytest.raises(FrozenInstanceError):
        request.mode = JobMode.FITTING  # type: ignore[misc]


@pytest.mark.parametrize(
    "bad_inputs",
    [
        {"x": 1.0},
        {"nested": {"x": 1.0}},
        {"rows": ["1.0", 2.0]},
        {"rows": ({"x": 2.0},)},
        {1.0: "x"},
    ],
)
def test_core_job_request_rejects_float_inputs(bad_inputs: object) -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        ComputeJobRequest(mode=JobMode.EXTRAPOLATION, inputs=bad_inputs)


@pytest.mark.parametrize(
    "bad_inputs",
    [
        {"values": {1.0}},
        {"value": Decimal("1.0")},
        {"value": complex(1, 0)},
    ],
)
def test_core_job_request_rejects_non_json_safe_inputs(bad_inputs: object) -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode

    with pytest.raises(TypeError, match="Unsupported payload type"):
        ComputeJobRequest(mode=JobMode.EXTRAPOLATION, inputs=bad_inputs)


def test_numeric_payload_string_preserves_high_precision_mpf_and_rejects_float() -> None:
    from mpmath import mp

    from datalab_core.numeric_payload import numeric_to_payload_string
    from shared.precision import precision_guard

    with precision_guard(80):
        value = mp.mpf("0.123456789012345678901234567890123456789")
        text = numeric_to_payload_string(value, field_name="value", digit_hint=80)

    assert text.startswith("0.123456789012345678901234567890123456789")
    with pytest.raises(TypeError, match="JSON floats are not allowed at value"):
        numeric_to_payload_string(1.0, field_name="value", digit_hint=80)
    with pytest.raises(TypeError, match="value must be numeric, not boolean"):
        numeric_to_payload_string(True, field_name="value", digit_hint=80)


def test_request_digit_hint_rejects_non_integer_precision_and_clamps_positive_floor() -> None:
    from datalab_core.numeric_payload import request_digit_hint

    assert request_digit_hint(None) == 50
    assert request_digit_hint(0) == 1
    assert request_digit_hint(-5) == 1
    assert request_digit_hint(80) == 80
    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        request_digit_hint(80.0)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="precision_digits must be an integer"):
        request_digit_hint(True)  # type: ignore[arg-type]


def test_numeric_payload_tree_normalizes_nested_values_without_json_floats() -> None:
    from mpmath import mp

    from datalab_core.numeric_payload import numeric_payload_tree
    from shared.precision import precision_guard

    with precision_guard(80):
        value = mp.mpf("1.0000000000000000000000000000000000001")
        payload = numeric_payload_tree(
            {
                "alpha": value,
                "nested": ["2", 3, None, True, {"beta": value}],
            },
            field_name="method_options",
            digit_hint=80,
        )

    assert payload == {
        "alpha": "1.0000000000000000000000000000000000001",
        "nested": [
            "2",
            "3",
            None,
            True,
            {"beta": "1.0000000000000000000000000000000000001"},
        ],
    }
    with pytest.raises(TypeError, match=r"method_options\.nested\[1\]"):
        numeric_payload_tree(
            {"nested": ["1", 2.0]},
            field_name="method_options",
            digit_hint=80,
        )


def test_optional_numeric_payload_string_handles_blank_and_absolute_values() -> None:
    from datalab_core.numeric_payload import optional_numeric_to_payload_string

    assert (
        optional_numeric_to_payload_string(
            " -1.25 ",
            field_name="sigma",
            digit_hint=50,
            absolute=True,
        )
        == "1.25"
    )
    assert (
        optional_numeric_to_payload_string(
            "",
            field_name="sigma",
            digit_hint=50,
            absolute=True,
        )
        is None
    )
    with pytest.raises(TypeError, match="JSON floats are not allowed at sigma"):
        optional_numeric_to_payload_string(
            0.5,
            field_name="sigma",
            digit_hint=50,
            absolute=True,
        )


@pytest.mark.parametrize(
    "bad_option",
    [
        {"precision_digits": 1.5},
        {"uncertainty_digits": 2.5},
        {"parallel": {"workers": 1.0}},
    ],
)
def test_core_job_options_reject_float_values(bad_option: dict[str, object]) -> None:
    from datalab_core.jobs import JobOptions

    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        JobOptions(**bad_option)


def test_core_job_options_parallel_must_be_mapping() -> None:
    from datalab_core.jobs import JobOptions

    with pytest.raises(TypeError, match="options.parallel must be a mapping"):
        JobOptions(parallel=["workers"])  # type: ignore[arg-type]


def test_core_job_request_copies_nested_inputs() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode

    source = {"constants": {"A": "1.23"}, "rows": ["1", "2"]}
    request = ComputeJobRequest(mode=JobMode.STATISTICS, inputs=source)

    source["constants"]["A"] = "9.99"  # type: ignore[index]
    source["rows"].append("3")  # type: ignore[union-attr]

    assert request.inputs == {"constants": {"A": "1.23"}, "rows": ["1", "2"]}


def test_core_job_request_payload_containers_are_immutable_and_asdict_safe() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions

    request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={"constants": {"A": "1.23"}, "rows": ("1", "2")},
        options=JobOptions(parallel={"workers": "auto"}),
    )

    assert request.inputs == {"constants": {"A": "1.23"}, "rows": ["1", "2"]}
    assert asdict(request) == {
        "mode": JobMode.STATISTICS,
        "inputs": {"constants": {"A": "1.23"}, "rows": ["1", "2"]},
        "options": {
            "precision_digits": None,
            "uncertainty_digits": None,
            "parallel": {"workers": "auto"},
        },
        "request_id": "",
    }
    with pytest.raises(TypeError):
        request.inputs["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        request.inputs["constants"]["A"] = "9.99"  # type: ignore[index]
    with pytest.raises(AttributeError):
        request.inputs["rows"].append("3")  # type: ignore[attr-defined]
    assert request.inputs["rows"][0:1] == ["1"]
    with pytest.raises(AttributeError):
        request.inputs["rows"][0:1].append("3")  # type: ignore[attr-defined]


def test_core_dtos_are_hashable_when_payloads_are_hashable_json() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus

    request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={"constants": {"A": "1.23"}, "rows": ("1", "2")},
        options=JobOptions(parallel={"workers": "auto"}),
    )
    result = ResultEnvelope(
        kind=ResultKind.TEXT,
        status=ResultStatus.SUCCEEDED,
        payload={"rows": ("1", "2")},
    )

    assert {request: "request"}[request] == "request"
    assert {result: "result"}[result] == "result"


def test_core_result_envelope_preserves_result_payload_strings() -> None:
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus

    result = ResultEnvelope(
        kind=ResultKind.TABLE,
        status=ResultStatus.SUCCEEDED,
        payload={"value": "1.0000000000000000001", "rows": [{"sigma": "0.01"}]},
        logs=("started", "finished"),
    )

    assert result.payload["value"].endswith("0001")
    assert result.logs == ("started", "finished")
    with pytest.raises(TypeError):
        result.payload["value"] = "2"  # type: ignore[index]
    with pytest.raises(AttributeError):
        result.payload["rows"].append({"sigma": "0.02"})  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match="JSON floats are not allowed"):
        ResultEnvelope(
            kind=ResultKind.TABLE,
            status=ResultStatus.SUCCEEDED,
            payload={"value": 1.0},
        )


def test_core_job_request_normalizes_string_mode() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode

    request = ComputeJobRequest(mode="statistics", inputs={"data_text": "A\n1"})  # type: ignore[arg-type]

    assert request.mode is JobMode.STATISTICS


def test_core_job_request_rejects_unknown_mode() -> None:
    from datalab_core.jobs import ComputeJobRequest

    with pytest.raises(ValueError, match="Unsupported job mode"):
        ComputeJobRequest(mode="made_up", inputs={})  # type: ignore[arg-type]


def test_core_result_envelope_rejects_non_string_logs_and_warnings() -> None:
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus

    with pytest.raises(TypeError, match="logs must be a sequence of strings"):
        ResultEnvelope(kind=ResultKind.TEXT, status=ResultStatus.FAILED, logs="error")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="warnings must be a sequence of strings"):
        ResultEnvelope(kind=ResultKind.TEXT, status=ResultStatus.FAILED, warnings="warning")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="logs\\[0\\] must be a string"):
        ResultEnvelope(kind=ResultKind.TEXT, status=ResultStatus.FAILED, logs=(1,))  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="warnings\\[0\\] must be a string"):
        ResultEnvelope(kind=ResultKind.TEXT, status=ResultStatus.FAILED, warnings=(1,))  # type: ignore[arg-type]


def test_core_session_returns_unsupported_failure_envelope() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultKind, ResultStatus
    from datalab_core.session import SessionService

    request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={"data_text": "A\n1"},
        request_id="req-1",
    )
    service = SessionService()

    result = service.submit(request)

    assert result.kind is ResultKind.TEXT
    assert result.status is ResultStatus.FAILED
    assert result.payload == {
        "error_code": "unsupported_mode",
        "message": "No core handler is registered for mode: statistics.",
        "mode": "statistics",
        "request_id": "req-1",
    }
    assert service.last_result is result
    assert service.active_request_id is None


def test_core_service_factory_registers_statistics_uncertainty_and_extrapolation_handlers() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus
    from datalab_core.service_factory import create_core_session_service

    service = create_core_session_service()
    stats_request = ComputeJobRequest(
        mode=JobMode.STATISTICS,
        inputs={
            "values": ("1.0000000000000000001", "2.0000000000000000002"),
            "sigmas": (None, None),
            "stats_mode": "mean",
            "use_sample": True,
            "use_weighted_variance": True,
        },
        options=JobOptions(precision_digits=80, uncertainty_digits=2),
        request_id="stats-factory",
    )

    result = service.submit(stats_request)

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["mean"].startswith("1.50000000000000000015")

    uncertainty_request = ComputeJobRequest(
        mode=JobMode.UNCERTAINTY,
        inputs={
            "headers": ["A"],
            "values": [["2.0000000000000000001"]],
            "uncertainties": [["0.1"]],
            "constants": {"C": {"value": "3", "uncertainty": "0.2"}},
            "formula": "A + C",
            "propagation": {
                "method": "taylor",
                "order": 1,
                "mc_samples": None,
                "mc_seed": None,
            },
            "segments": [[0, 1]],
        },
        options=JobOptions(precision_digits=80, uncertainty_digits=2),
        request_id="uncertainty-factory",
    )

    uncertainty_result = service.submit(uncertainty_request)

    assert uncertainty_result.status is ResultStatus.SUCCEEDED
    assert uncertainty_result.payload["results"][0]["value"].startswith("5.0000000000000000001")

    extrapolation_request = ComputeJobRequest(
        mode=JobMode.EXTRAPOLATION,
        inputs={
            "headers": ["A", "B", "C"],
            "rows": [["1", "1.5", "1.75"]],
            "method": "quadratic",
            "method_options": {},
            "segments": [[0, 1]],
        },
        options=JobOptions(precision_digits=80, uncertainty_digits=2),
        request_id="extrapolation-factory",
    )

    extrapolation_result = service.submit(extrapolation_request)

    assert extrapolation_result.status is ResultStatus.SUCCEEDED
    assert extrapolation_result.payload["results"][0]["value"] == "1.875"

    fitting_request = ComputeJobRequest(
        mode=JobMode.FITTING,
        inputs={
            "model_type": "polynomial",
            "headers": ["x", "y"],
            "data_rows": [["0", "1"], ["1", "3"], ["2", "5"], ["3", "7"]],
            "sigma_rows": [[None, None], [None, None], [None, None], [None, None]],
            "x_series": ["0", "1", "2", "3"],
            "y_series": ["1", "3", "5", "7"],
            "sigma_series": [None, None, None, None],
            "weights": None,
            "variable_map": {"x": "x"},
            "variable_data": {"x": ["0", "1", "2", "3"]},
            "target_series": ["1", "3", "5", "7"],
            "target_column": "y",
            "model_expr": "",
            "parameter_config": {},
            "parameter_names": [],
            "template_expr": None,
            "template_params": {},
            "poly_degree": 1,
            "inverse_min": 1,
            "inverse_max": 3,
            "pade_m": 1,
            "pade_n": 1,
            "auto_identifier": None,
            "weighted": False,
            "label": "service-polynomial",
            "is_multidim": False,
            "implicit_definition": None,
            "timeout_seconds": None,
            "custom_constants": {},
        },
        options=JobOptions(precision_digits=80, uncertainty_digits=2),
        request_id="fitting-factory",
    )

    fitting_result = service.submit(fitting_request)

    assert fitting_result.status is ResultStatus.SUCCEEDED
    assert fitting_result.payload["model_type"] == "polynomial"
    import mpmath as mp

    assert mp.almosteq(
        mp.mpf(fitting_result.payload["fit_result"]["params"]["b0"]),
        mp.mpf("1"),
        abs_eps=mp.mpf("1e-40"),
    )
    assert mp.almosteq(
        mp.mpf(fitting_result.payload["fit_result"]["params"]["b1"]),
        mp.mpf("2"),
        abs_eps=mp.mpf("1e-40"),
    )

    root_request = ComputeJobRequest(
        mode=JobMode.ROOT_SOLVING,
        inputs={
            "equations": ["x^2 - A"],
            "unknown_rows": [{"name": "x", "initial": "2", "lower": "0", "upper": "10", "source": "manual"}],
            "data_headers": ["A"],
            "data_rows": [["4"]],
            "constants_enabled": False,
            "constants_rows": [],
            "constants_view": "table",
            "constants_text": "",
            "mode": "scalar",
            "scan_config": {},
            "uncertainty_options": {"method": "taylor", "taylor_order": 1},
            "display_digits": 12,
        },
        options=JobOptions(precision_digits=50, uncertainty_digits=2),
        request_id="root-factory",
    )

    root_result = service.submit(root_request)

    assert root_result.status is ResultStatus.SUCCEEDED
    assert root_result.payload["row_count"] == 1
    assert root_result.payload["roots_count"] >= 1


def test_core_service_factory_forwards_cancellation_checker() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.service_factory import create_core_session_service

    service = create_core_session_service(cancellation_checker=lambda: True)
    result = service.submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": ("1", "2"),
                "sigmas": (None, None),
                "stats_mode": "mean",
                "use_sample": True,
                "use_weighted_variance": True,
            },
            request_id="factory-cancel",
        )
    )

    assert result.status is ResultStatus.CANCELLED
    assert result.payload["error_code"] == "cancelled"


def test_core_service_factory_exposes_only_currently_migrated_handlers() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.service_factory import (
        MIGRATED_CORE_MODES,
        create_core_session_service,
        default_core_handlers,
    )

    handlers = default_core_handlers()

    assert MIGRATED_CORE_MODES == (
        JobMode.STATISTICS,
        JobMode.UNCERTAINTY,
        JobMode.EXTRAPOLATION,
        JobMode.FITTING,
        JobMode.ROOT_SOLVING,
    )
    assert tuple(handlers) == MIGRATED_CORE_MODES

    service = create_core_session_service()
    for mode in JobMode:
        if mode in MIGRATED_CORE_MODES:
            continue

        result = service.submit(ComputeJobRequest(mode=mode, inputs={}, request_id=f"{mode.value}-boundary"))

        assert result.status is ResultStatus.FAILED
        assert result.payload["error_code"] == "unsupported_mode"
        assert result.payload["mode"] == mode.value
        assert result.payload["request_id"] == f"{mode.value}-boundary"


def test_core_session_dispatches_registered_handler() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus
    from datalab_core.session import SessionService

    def _handler(request: ComputeJobRequest) -> ResultEnvelope:
        assert request.inputs == {"value": "1.0000000000000000001"}
        return ResultEnvelope(
            kind=ResultKind.TABLE,
            status=ResultStatus.SUCCEEDED,
            payload={"value": request.inputs["value"]},
        )

    service = SessionService(handlers={JobMode.STATISTICS: _handler})
    result = service.submit(
        ComputeJobRequest(mode=JobMode.STATISTICS, inputs={"value": "1.0000000000000000001"})
    )

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["value"] == "1.0000000000000000001"
    assert service.last_result is result


def test_core_session_handlers_registry_is_live_after_construction() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus
    from datalab_core.session import SessionService

    def _handler(_request: ComputeJobRequest) -> ResultEnvelope:
        return ResultEnvelope(kind=ResultKind.TEXT, status=ResultStatus.SUCCEEDED, payload={"value": "live"})

    service = SessionService()
    service.handlers[JobMode.STATISTICS] = _handler

    result = service.submit(ComputeJobRequest(mode=JobMode.STATISTICS, inputs={}))

    assert result.status is ResultStatus.SUCCEEDED
    assert result.payload["value"] == "live"


def test_core_session_wraps_handler_exceptions_as_failure_envelope() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService

    def _handler(_request: ComputeJobRequest):
        raise RuntimeError("boom")

    service = SessionService(handlers={JobMode.STATISTICS: _handler})
    result = service.submit(ComputeJobRequest(mode=JobMode.STATISTICS, inputs={}, request_id="req-2"))

    assert result.status is ResultStatus.FAILED
    assert result.payload == {
        "error_code": "handler_exception",
        "error_type": "RuntimeError",
        "message": "boom",
        "mode": "statistics",
        "request_id": "req-2",
    }


def test_core_session_blocks_reentrant_submissions() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus
    from datalab_core.session import SessionCallbacks, SessionService

    nested_result: ResultEnvelope | None = None
    events: list[str] = []
    service = SessionService()

    def _handler(_request: ComputeJobRequest) -> ResultEnvelope:
        nonlocal nested_result
        service.callbacks = SessionCallbacks(on_result=lambda _result, _request: events.append("busy-callback"))
        nested_result = service.submit(ComputeJobRequest(mode=JobMode.UNCERTAINTY, inputs={}, request_id="nested"))
        service.callbacks = SessionCallbacks()
        return ResultEnvelope(kind=ResultKind.TEXT, status=ResultStatus.SUCCEEDED, payload={"ok": True})

    service.register_handler(JobMode.STATISTICS, _handler)
    result = service.submit(ComputeJobRequest(mode=JobMode.STATISTICS, inputs={}, request_id="outer"))

    assert result.status is ResultStatus.SUCCEEDED
    assert nested_result is not None
    assert nested_result.status is ResultStatus.FAILED
    assert nested_result.payload["error_code"] == "busy"
    assert nested_result.payload["active_request_id"] == "outer"
    assert service.last_result is result
    assert events == []


def test_core_session_invalid_handler_result_is_failure_envelope() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionService

    service = SessionService(handlers={JobMode.STATISTICS: lambda _request: None})  # type: ignore[dict-item]

    result = service.submit(ComputeJobRequest(mode=JobMode.STATISTICS, inputs={}, request_id="bad-result"))

    assert result.status is ResultStatus.FAILED
    assert result.payload == {
        "error_code": "invalid_handler_result",
        "message": "Core handler did not return a ResultEnvelope.",
        "mode": "statistics",
        "request_id": "bad-result",
        "result_type": "NoneType",
    }


def test_core_session_register_handler_validates_handler_and_mode() -> None:
    from datalab_core.jobs import JobMode
    from datalab_core.session import SessionService

    service = SessionService()

    with pytest.raises(TypeError, match="handler must be callable"):
        service.register_handler(JobMode.STATISTICS, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="Unsupported job mode"):
        service.register_handler("made_up", lambda _request: None)  # type: ignore[arg-type]


def test_core_session_callback_exceptions_are_fail_fast_but_reset_active_state() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus
    from datalab_core.session import SessionCallbacks, SessionService

    handler_calls = 0

    def _status(_status, _request):
        raise RuntimeError("callback boom")

    def _handler(_request: ComputeJobRequest) -> ResultEnvelope:
        nonlocal handler_calls
        handler_calls += 1
        return ResultEnvelope(kind=ResultKind.TEXT, status=ResultStatus.SUCCEEDED)

    service = SessionService(
        handlers={JobMode.STATISTICS: _handler},
        callbacks=SessionCallbacks(on_status=_status),
    )

    with pytest.raises(RuntimeError, match="callback boom"):
        service.submit(ComputeJobRequest(mode=JobMode.STATISTICS, inputs={}, request_id="req"))

    assert service.active_request_id is None
    assert service.status.value == "idle"
    assert handler_calls == 0


def test_core_session_result_callback_exception_preserves_result_and_original_error() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus
    from datalab_core.session import SessionCallbacks, SessionService, SessionStatus

    events: list[str] = []

    def _handler(_request: ComputeJobRequest) -> ResultEnvelope:
        return ResultEnvelope(kind=ResultKind.TEXT, status=ResultStatus.SUCCEEDED, payload={"ok": True})

    def _status(status: SessionStatus, _request: ComputeJobRequest | None) -> None:
        events.append(status.value)
        if status is SessionStatus.IDLE:
            raise RuntimeError("idle should not mask")

    def _result(_result: ResultEnvelope, _request: ComputeJobRequest) -> None:
        raise RuntimeError("result failed")

    service = SessionService(
        handlers={JobMode.STATISTICS: _handler},
        callbacks=SessionCallbacks(on_status=_status, on_result=_result),
    )

    with pytest.raises(RuntimeError, match="result failed"):
        service.submit(ComputeJobRequest(mode=JobMode.STATISTICS, inputs={}, request_id="req-result"))

    assert events == ["running", "idle"]
    assert service.active_request_id is None
    assert service.last_result is not None
    assert service.last_result.status is ResultStatus.SUCCEEDED


def test_core_session_failure_callback_exception_preserves_failure_result() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultStatus
    from datalab_core.session import SessionCallbacks, SessionService

    def _failure(_result, _request) -> None:
        raise RuntimeError("failure callback failed")

    service = SessionService(callbacks=SessionCallbacks(on_failure=_failure))

    with pytest.raises(RuntimeError, match="failure callback failed"):
        service.submit(ComputeJobRequest(mode=JobMode.STATISTICS, inputs={}, request_id="req-failure"))

    assert service.active_request_id is None
    assert service.last_result is not None
    assert service.last_result.status is ResultStatus.FAILED


def test_core_session_emits_status_result_or_failure_callbacks() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus
    from datalab_core.session import SessionCallbacks, SessionService, SessionStatus

    events: list[tuple[str, str, str, str]] = []

    def _status(status: SessionStatus, request: ComputeJobRequest | None) -> None:
        events.append(("status", status.value, request.request_id if request else "", ""))

    def _result(result: ResultEnvelope, request: ComputeJobRequest) -> None:
        events.append(("result", result.status.value, request.request_id, result.payload.get("value", "")))

    def _failure(result: ResultEnvelope, request: ComputeJobRequest) -> None:
        events.append(("failure", result.status.value, request.request_id, result.payload["error_code"]))

    def _handler(_request: ComputeJobRequest) -> ResultEnvelope:
        return ResultEnvelope(
            kind=ResultKind.TEXT,
            status=ResultStatus.SUCCEEDED,
            payload={"value": "ok"},
        )

    service = SessionService(
        handlers={JobMode.STATISTICS: _handler},
        callbacks=SessionCallbacks(on_status=_status, on_result=_result, on_failure=_failure),
    )
    service.submit(ComputeJobRequest(mode=JobMode.STATISTICS, inputs={}, request_id="success"))
    service.submit(ComputeJobRequest(mode=JobMode.ROOT_SOLVING, inputs={}, request_id="unsupported"))

    assert events == [
        ("status", "running", "success", ""),
        ("result", "succeeded", "success", "ok"),
        ("status", "idle", "", ""),
        ("status", "running", "unsupported", ""),
        ("failure", "failed", "unsupported", "unsupported_mode"),
        ("status", "idle", "", ""),
    ]


def test_core_session_cancel_active_request_returns_cancelled_envelope() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultEnvelope, ResultStatus
    from datalab_core.session import (
        SessionCallbacks,
        SessionService,
        cancellation_requested,
        check_cancelled,
    )

    started = threading.Event()
    results: list[ResultEnvelope] = []
    events: list[tuple[str, str, str]] = []

    def _failure(result: ResultEnvelope, request: ComputeJobRequest) -> None:
        events.append(("failure", result.status.value, request.request_id))

    def _handler(_request: ComputeJobRequest) -> ResultEnvelope:
        started.set()
        deadline = time.monotonic() + 2
        while not cancellation_requested():
            if time.monotonic() > deadline:
                raise AssertionError("Timed out waiting for cancellation.")
            time.sleep(0.001)
        check_cancelled()
        raise AssertionError("Cancellation checkpoint should have raised.")

    service = SessionService(
        handlers={JobMode.STATISTICS: _handler},
        callbacks=SessionCallbacks(on_failure=_failure),
    )
    request = ComputeJobRequest(mode=JobMode.STATISTICS, inputs={}, request_id="req-cancel")

    def _submit() -> None:
        results.append(service.submit(request))

    thread = threading.Thread(target=_submit)
    thread.start()
    assert started.wait(timeout=1)

    assert service.cancel("other-request") is False
    assert service.cancel("req-cancel") is True
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert len(results) == 1
    assert results[0].status is ResultStatus.CANCELLED
    assert results[0].payload == {
        "error_code": "cancelled",
        "message": "Core job was cancelled.",
        "mode": "statistics",
        "request_id": "req-cancel",
    }
    assert events == [("failure", "cancelled", "req-cancel")]
    assert service.active_request_id is None


def test_core_session_external_cancellation_checker_is_observed_by_checkpoints() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus
    from datalab_core.session import SessionService, check_cancelled

    def _handler(_request: ComputeJobRequest) -> ResultEnvelope:
        check_cancelled()
        return ResultEnvelope(kind=ResultKind.TEXT, status=ResultStatus.SUCCEEDED)

    service = SessionService(
        handlers={JobMode.STATISTICS: _handler},
        cancellation_checker=lambda: True,
    )
    result = service.submit(ComputeJobRequest(mode=JobMode.STATISTICS, inputs={}, request_id="external"))

    assert result.status is ResultStatus.CANCELLED
    assert result.payload["error_code"] == "cancelled"
    assert service.cancel() is False
    with pytest.raises(TypeError, match="request_id must be a string or None"):
        service.cancel(1)  # type: ignore[arg-type]
