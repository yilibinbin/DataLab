from __future__ import annotations

import json
import re
import threading
from dataclasses import replace
from types import SimpleNamespace

import pytest
from mpmath import mp

pytest.importorskip("flask")


def _parse_sse_stream(body: bytes) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    text = body.decode("utf-8")
    for frame in text.split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        event = "message"
        data_lines: list[str] = []
        for line in frame.splitlines():
            if line.startswith("event:"):
                event = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
        data_text = "\n".join(data_lines)
        data = json.loads(data_text) if data_text else None
        events.append({"event": event, "data": data, "raw": frame})
    return events


def _csrf_token(client) -> str:
    from app_web.security import generate_csrf_token

    token = generate_csrf_token()
    with client.session_transaction() as session:
        session["csrf_token"] = token
    return token


def test_web_post_and_sse_use_the_same_mpmath_serial_lock():
    import app_web.security as security
    from app_web import _security_shim
    from app_web.blueprints import sse

    assert _security_shim.mpmath_lock is security._mpmath_lock
    assert sse._MP_SERIAL_LOCK is security._mpmath_lock


def test_mpmath_synchronized_post_logic_blocks_on_shared_lock():
    import app_web.security as security
    from app_web.logic.statistics import _run_statistics

    started = threading.Event()
    finished = threading.Event()
    errors: list[BaseException] = []

    def target() -> None:
        started.set()
        try:
            _run_statistics("A\n1\n2\n3", {"stats_mp_precision": "40"})
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            finished.set()

    security._mpmath_lock.acquire()
    try:
        thread = threading.Thread(target=target)
        thread.start()
        assert started.wait(1)
        assert not finished.wait(0.15), "decorated POST logic bypassed the shared lock"
    finally:
        security._mpmath_lock.release()

    thread.join(5)
    assert finished.is_set(), "decorated POST logic did not finish after lock release"
    assert errors == []


def test_web_stats_post_restores_global_mpmath_precision():
    from app_web.server import create_app

    original = mp.dps
    try:
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        mp.dps = 29
        response = client.post(
            "/stats",
            data={
                "csrf_token": _csrf_token(client),
                "stats_data_text": "A\n1\n2\n3",
                "stats_mp_precision": "71",
            },
        )
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "<section class=\"results\">" in html
        assert re.search(r"mp\.dps:\s*71\b", html)
        assert mp.dps == 29
    finally:
        mp.dps = original


def test_web_statistics_logic_uses_core_request_builder_and_handler(monkeypatch):
    from datalab_core.statistics import build_statistics_requests as real_build_statistics_requests
    from datalab_core.statistics import run_statistics as real_run_statistics

    import app_web.logic.statistics as stats_logic

    calls: dict[str, object] = {"build": 0, "run": 0, "request_ids": [], "submit": 0, "submit_request_ids": []}

    def fake_build_statistics_requests(**kwargs):
        calls["build"] = int(calls["build"]) + 1
        calls["headers"] = tuple(kwargs["headers"])
        calls["value_col"] = kwargs["value_col"]
        calls["precision_digits"] = kwargs["precision_digits"]
        return real_build_statistics_requests(**kwargs)

    def fake_run_statistics(request):
        calls["run"] = int(calls["run"]) + 1
        calls["request_ids"].append(request.request_id)  # type: ignore[union-attr]
        return real_run_statistics(request)

    class FakeService:
        def submit(self, request):
            calls["submit"] = int(calls["submit"]) + 1
            calls["submit_request_ids"].append(request.request_id)  # type: ignore[union-attr]
            return fake_run_statistics(request)

    def fake_create_core_session_service():
        calls["factory"] = int(calls.get("factory", 0)) + 1
        return FakeService()

    monkeypatch.setattr(stats_logic, "build_statistics_requests", fake_build_statistics_requests, raising=False)
    monkeypatch.setattr(stats_logic, "run_statistics", fake_run_statistics, raising=False)
    monkeypatch.setattr(stats_logic, "create_core_session_service", fake_create_core_session_service, raising=False)

    result = stats_logic._run_statistics(
        "A sigma\n"
        "1.0000000000000000001 0.1\n"
        "2.0000000000000000002 0.2\n"
        "3.0000000000000000003 0.3\n",
        {
            "stats_mode": "weighted_sigma",
            "stats_mp_precision": "80",
            "stats_use_sample": "on",
            "stats_use_weighted_variance": "on",
        },
        lang="en",
    )

    assert calls["build"] == 1
    assert calls["factory"] == 1
    assert calls["submit"] == 1
    assert calls["submit_request_ids"] == ["web-statistics-1"]
    assert calls["run"] == 1
    assert calls["request_ids"] == ["web-statistics-1"]
    assert calls["headers"] == ("A",)
    assert calls["value_col"] == "A"
    assert calls["precision_digits"] == 80
    assert result.stats_mode == "weighted_sigma"
    assert result.mp_precision == 80
    assert result.result["method_label"] == "Weighted mean (sample)"
    assert result.csv_data and "mean" in result.csv_data
    assert result.raw_csv_data and "A_sigma" in result.raw_csv_data
    assert "\\begin" in result.latex_text


def test_web_statistics_multicolumn_input_projects_to_value_and_sigma_only(monkeypatch):
    from datalab_core.statistics import build_statistics_requests as real_build_statistics_requests

    import app_web.logic.statistics as stats_logic

    captured: dict[str, object] = {}

    def fake_build_statistics_requests(**kwargs):
        captured["headers"] = tuple(kwargs["headers"])
        captured["rows"] = tuple(tuple(row) for row in kwargs["rows"])
        captured["sigma_rows"] = tuple(tuple(row) for row in kwargs["sigma_rows"])
        captured["value_col"] = kwargs["value_col"]
        return real_build_statistics_requests(**kwargs)

    monkeypatch.setattr(stats_logic, "build_statistics_requests", fake_build_statistics_requests, raising=False)

    result = stats_logic._run_statistics(
        "A sigma ignored\n"
        "1.0000000000000000001 0.1 99\n"
        "2.0000000000000000002 0.2 88\n"
        "3.0000000000000000003 0.3 77\n",
        {
            "stats_mode": "weighted_sigma",
            "stats_mp_precision": "80",
            "stats_use_sample": "on",
            "stats_use_weighted_variance": "on",
        },
        lang="en",
    )

    assert captured["headers"] == ("A",)
    assert captured["value_col"] == "A"
    assert [mp.nstr(row[0], 30) for row in captured["rows"]] == [
        "1.0000000000000000001",
        "2.0000000000000000002",
        "3.0000000000000000003",
    ]
    assert [mp.nstr(row[0], 30) for row in captured["sigma_rows"]] == ["0.1", "0.2", "0.3"]
    assert result.headers == ["A"]
    assert result.raw_csv_data
    assert result.raw_csv_data.splitlines()[0] == "index,A,A_sigma"
    assert "ignored" not in result.raw_csv_data
    assert "sigma_sigma" not in result.raw_csv_data


def test_web_extrapolation_logic_uses_core_request_builder_and_handler(monkeypatch):
    from datalab_core.extrapolation import build_extrapolation_request as real_build_extrapolation_request
    from datalab_core.extrapolation import run_extrapolation as real_run_extrapolation

    import app_web.logic.extrapolation as extrap_logic

    calls: dict[str, object] = {"build": 0, "run": 0, "request_ids": [], "submit": 0, "submit_request_ids": []}

    def fake_build_extrapolation_request(**kwargs):
        calls["build"] = int(calls["build"]) + 1
        calls["headers"] = tuple(kwargs["headers"])
        calls["method"] = kwargs["method"]
        calls["method_options"] = kwargs["method_options"]
        calls["precision_digits"] = kwargs["precision_digits"]
        return real_build_extrapolation_request(**kwargs)

    def fake_run_extrapolation(request):
        calls["run"] = int(calls["run"]) + 1
        calls["request_ids"].append(request.request_id)  # type: ignore[union-attr]
        return real_run_extrapolation(request)

    class FakeService:
        def submit(self, request):
            calls["submit"] = int(calls["submit"]) + 1
            calls["submit_request_ids"].append(request.request_id)  # type: ignore[union-attr]
            return fake_run_extrapolation(request)

    def fake_create_core_session_service():
        calls["factory"] = int(calls.get("factory", 0)) + 1
        return FakeService()

    monkeypatch.setattr(extrap_logic, "build_extrapolation_request", fake_build_extrapolation_request, raising=False)
    monkeypatch.setattr(extrap_logic, "run_extrapolation", fake_run_extrapolation, raising=False)
    monkeypatch.setattr(extrap_logic, "create_core_session_service", fake_create_core_session_service, raising=False)

    result = extrap_logic._run_extrapolation(
        "A B C\n"
        "1.0000000000000000001 1.5 1.75\n",
        {
            "method": "quadratic",
            "mp_precision": "80",
            "result_digits": "2",
            "reference_column": "B",
        },
        lang="en",
    )

    assert calls["build"] == 1
    assert calls["factory"] == 1
    assert calls["submit"] == 1
    assert calls["submit_request_ids"] == ["web-extrapolation"]
    assert calls["run"] == 1
    assert calls["request_ids"] == ["web-extrapolation"]
    assert calls["headers"] == ("A", "B", "C")
    assert calls["method"] == "quadratic"
    assert calls["method_options"]["uncertainty_column"] == "B"
    assert calls["precision_digits"] == 80
    assert result.method == "quadratic"
    assert result.mp_precision == 80
    assert result.formatted_rows
    assert "\\begin" in result.latex_text


def test_web_error_propagation_logic_uses_core_request_builder_and_handler(monkeypatch):
    from datalab_core.uncertainty import build_uncertainty_request as real_build_uncertainty_request
    from datalab_core.uncertainty import run_uncertainty as real_run_uncertainty

    import app_web.logic.error_propagation as error_logic

    calls: dict[str, object] = {"build": 0, "run": 0, "request_ids": [], "submit": 0, "submit_request_ids": []}

    def fake_build_uncertainty_request(**kwargs):
        calls["build"] = int(calls["build"]) + 1
        calls["headers"] = tuple(kwargs["headers"])
        calls["formula"] = kwargs["formula"]
        calls["constants"] = kwargs["constants"]
        calls["propagation_method"] = kwargs["propagation_method"]
        calls["propagation_order"] = kwargs["propagation_order"]
        calls["precision_digits"] = kwargs["precision_digits"]
        return real_build_uncertainty_request(**kwargs)

    def fake_run_uncertainty(request):
        calls["run"] = int(calls["run"]) + 1
        calls["request_ids"].append(request.request_id)  # type: ignore[union-attr]
        return real_run_uncertainty(request)

    class FakeService:
        def submit(self, request):
            calls["submit"] = int(calls["submit"]) + 1
            calls["submit_request_ids"].append(request.request_id)  # type: ignore[union-attr]
            return fake_run_uncertainty(request)

    def fake_create_core_session_service():
        calls["factory"] = int(calls.get("factory", 0)) + 1
        return FakeService()

    monkeypatch.setattr(error_logic, "build_uncertainty_request", fake_build_uncertainty_request, raising=False)
    monkeypatch.setattr(error_logic, "run_uncertainty", fake_run_uncertainty, raising=False)
    monkeypatch.setattr(error_logic, "create_core_session_service", fake_create_core_session_service, raising=False)

    result = error_logic._run_error_propagation(
        "A B\n"
        "1.0000000000000000001(1) 2.0(2)\n",
        "C 3.0(3)\n",
        {
            "error_formula": "A + C",
            "error_mp_precision": "80",
            "error_result_digits": "2",
            "error_constants_enabled": "on",
            "error_propagation_method": "taylor",
            "error_propagation_order": "1",
        },
        lang="en",
    )

    assert calls["build"] == 1
    assert calls["factory"] == 1
    assert calls["submit"] == 1
    assert calls["submit_request_ids"] == ["web-uncertainty"]
    assert calls["run"] == 1
    assert calls["request_ids"] == ["web-uncertainty"]
    assert calls["headers"] == ("A", "B")
    assert calls["formula"] == "A + C"
    assert set(calls["constants"]) == {"C"}
    assert calls["propagation_method"] == "taylor"
    assert calls["propagation_order"] == 1
    assert calls["precision_digits"] == 80
    assert result.formatted_rows
    assert result.mp_precision == 80
    assert "\\begin" in result.latex_text


def test_web_fitting_logic_uses_core_request_builder_and_handler(monkeypatch):
    from datalab_core.fitting import build_fitting_request as real_build_fitting_request
    from datalab_core.fitting import run_fitting as real_run_fitting

    import app_web.logic.fitting as fit_logic

    calls: dict[str, object] = {"build": 0, "run": 0, "request_ids": [], "submit": 0, "submit_request_ids": []}

    def fake_build_fitting_request(**kwargs):
        calls["build"] = int(calls["build"]) + 1
        calls["model_type"] = kwargs["model_type"]
        calls["headers"] = tuple(kwargs["headers"])
        calls["variable_map"] = dict(kwargs["variable_map"])
        calls["target_column"] = kwargs["target_column"]
        calls["poly_degree"] = kwargs["poly_degree"]
        calls["weighted"] = kwargs["weighted"]
        calls["precision_digits"] = kwargs["precision_digits"]
        return real_build_fitting_request(**kwargs)

    def fake_run_fitting(request):
        calls["run"] = int(calls["run"]) + 1
        calls["request_ids"].append(request.request_id)  # type: ignore[union-attr]
        return real_run_fitting(request)

    class FakeService:
        def submit(self, request):
            calls["submit"] = int(calls["submit"]) + 1
            calls["submit_request_ids"].append(request.request_id)  # type: ignore[union-attr]
            return fake_run_fitting(request)

    def fake_create_core_session_service():
        calls["factory"] = int(calls.get("factory", 0)) + 1
        return FakeService()

    monkeypatch.setattr(fit_logic, "build_fitting_request", fake_build_fitting_request, raising=False)
    monkeypatch.setattr(fit_logic, "run_fitting", fake_run_fitting, raising=False)
    monkeypatch.setattr(fit_logic, "create_core_session_service", fake_create_core_session_service, raising=False)

    result = fit_logic._run_fit(
        "x y\n"
        "0 1\n"
        "1 3\n"
        "2 5\n"
        "3 7\n",
        {
            "fit_mode": "polynomial",
            "fit_poly_degree": "1",
            "fit_mp_precision": "80",
            "fit_result_digits": "2",
        },
    )

    assert calls["build"] == 1
    assert calls["factory"] == 1
    assert calls["submit"] == 1
    assert calls["submit_request_ids"] == ["web-fitting"]
    assert calls["run"] == 1
    assert calls["request_ids"] == ["web-fitting"]
    assert calls["model_type"] == "polynomial"
    assert calls["headers"] == ("x", "y")
    assert calls["variable_map"] == {"x": "x"}
    assert calls["target_column"] == "y"
    assert calls["poly_degree"] == 1
    assert calls["weighted"] is False
    assert calls["precision_digits"] == 80
    assert result.best_label
    assert result.params
    assert result.metrics
    assert result.mp_precision == 80
    assert "\\begin" in result.latex_text


def test_web_statistics_core_failure_without_payload_uses_default_message(monkeypatch):
    from datalab_core.results import ResultStatus

    import app_web.logic.statistics as stats_logic

    class FakeService:
        def submit(self, request):  # noqa: ARG002 - fake service boundary.
            return SimpleNamespace(status=ResultStatus.FAILED, payload=None, warnings=())

    monkeypatch.setattr(stats_logic, "create_core_session_service", lambda: FakeService(), raising=False)

    with pytest.raises(ValueError, match=r"^Statistics failed\.$"):
        stats_logic._run_statistics(
            "A\n1\n2\n3\n",
            {
                "stats_mode": "mean_sample",
                "stats_mp_precision": "80",
            },
            lang="en",
        )


def test_web_extrapolation_core_failure_without_payload_uses_default_message(monkeypatch):
    from datalab_core.results import ResultStatus

    import app_web.logic.extrapolation as extrap_logic

    class FakeService:
        def submit(self, request):  # noqa: ARG002 - fake service boundary.
            return SimpleNamespace(status=ResultStatus.FAILED, payload=None, warnings=())

    monkeypatch.setattr(extrap_logic, "create_core_session_service", lambda: FakeService(), raising=False)

    with pytest.raises(ValueError, match=r"^Extrapolation failed\.$"):
        extrap_logic._run_extrapolation(
            "A B C\n1 2 3\n",
            {
                "method": "quadratic",
                "mp_precision": "80",
            },
            lang="en",
        )


def test_web_fitting_core_failure_without_payload_uses_default_message(monkeypatch):
    from datalab_core.results import ResultStatus

    import app_web.logic.fitting as fit_logic

    class FakeService:
        def submit(self, request):  # noqa: ARG002 - fake service boundary.
            return SimpleNamespace(status=ResultStatus.FAILED, payload=None, warnings=())

    monkeypatch.setattr(fit_logic, "create_core_session_service", lambda: FakeService(), raising=False)

    with pytest.raises(ValueError, match=r"^Fitting failed\.$"):
        fit_logic._run_fit(
            "x y\n0 1\n1 3\n2 5\n3 7\n",
            {
                "fit_mode": "polynomial",
                "fit_poly_degree": "1",
                "fit_mp_precision": "80",
            },
        )


def test_web_fitting_merges_payload_and_envelope_warnings(monkeypatch):
    from datalab_core.fitting import run_fitting as real_run_fitting

    import app_web.logic.fitting as fit_logic

    class FakeService:
        def submit(self, request):
            result = real_run_fitting(request)
            return replace(
                result,
                payload={**result.payload, "warnings": ["payload warning"]},
                warnings=("envelope warning",),
            )

    monkeypatch.setattr(fit_logic, "create_core_session_service", lambda: FakeService(), raising=False)

    result = fit_logic._run_fit(
        "x y\n0 1\n1 3\n2 5\n3 7\n",
        {
            "fit_mode": "polynomial",
            "fit_poly_degree": "1",
            "fit_mp_precision": "80",
        },
    )

    assert result.warnings == ["payload warning", "envelope warning"]


def test_web_statistics_formats_result_inside_selected_precision_guard(monkeypatch):
    import app_web.logic.statistics as stats_logic

    observed_dps: list[int] = []
    real_formatter = stats_logic.format_result_with_uncertainty_latex

    def spy_formatter(value, uncertainty, digits):
        observed_dps.append(mp.dps)
        return real_formatter(value, uncertainty, digits)

    monkeypatch.setattr(stats_logic, "format_result_with_uncertainty_latex", spy_formatter)

    previous = mp.dps
    mp.dps = 17
    try:
        stats_logic._run_statistics(
            "A\n"
            "1.0000000000000000001\n"
            "2.0000000000000000002\n"
            "3.0000000000000000003\n",
            {
                "stats_mode": "mean_sample",
                "stats_mp_precision": "80",
                "stats_uncertainty_digits": "2",
            },
            lang="en",
        )
        assert observed_dps == [80]
        assert mp.dps == 17
    finally:
        mp.dps = previous


def test_web_integer_option_parser_keeps_decimal_integer_text_exact():
    from app_web.logic.common import _parse_int

    assert _parse_int("80") == 80
    assert _parse_int("80.0") == 80
    assert _parse_int("1e2") == 100
    assert _parse_int("9007199254740993.0") == 9007199254740993


@pytest.mark.parametrize("text", ["1.5", "nan", "inf", "-inf"])
def test_web_integer_option_parser_rejects_non_integral_decimal_text(text):
    from app_web.logic.common import _parse_int

    with pytest.raises(ValueError, match="Failed to parse integer"):
        _parse_int(text)


def test_web_sse_preserves_high_precision_query_strings_until_locked_mpf_conversion(
    monkeypatch,
):
    from app_web.blueprints import sse
    from app_web.server import create_app

    high_precision_x = "1.0000000000000000000000000000001"
    observed: dict[str, object] = {}
    real_materialise = sse._materialise_mpf_pairs

    def spy_materialise(xs_str, ys_str, precision):
        observed["xs_str"] = list(xs_str)
        observed["ys_str"] = list(ys_str)
        observed["precision"] = precision
        observed["mp_dps_inside"] = mp.dps
        return real_materialise(xs_str, ys_str, precision)

    monkeypatch.setattr(sse, "_materialise_mpf_pairs", spy_materialise)

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    response = client.get(
        "/api/fit/stream?"
        f"x={high_precision_x},2,3,4&y=2,4,6,8&model=polynomial&precision=73"
    )

    assert response.status_code == 200
    events = _parse_sse_stream(response.data)
    assert any(event["event"] == "result" for event in events)
    assert observed["xs_str"] == [high_precision_x, "2", "3", "4"]
    assert observed["ys_str"] == ["2", "4", "6", "8"]
    assert observed["precision"] == 73
    assert observed["mp_dps_inside"] == 73


def test_web_sse_fit_stream_restores_global_mpmath_precision():
    from app_web.server import create_app

    original = mp.dps
    mp.dps = 31
    try:
        app = create_app()
        app.config["TESTING"] = True
        client = app.test_client()
        response = client.get(
            "/api/fit/stream?x=1,2,3,4&y=2,4,6,8&model=polynomial&precision=73"
        )
        assert response.status_code == 200
        events = _parse_sse_stream(response.data)
        assert any(
            event["event"] == "started"
            and isinstance(event["data"], dict)
            and event["data"].get("precision") == 73
            for event in events
        )
        assert any(event["event"] == "result" for event in events)
        assert mp.dps == 31
    finally:
        mp.dps = original


def test_web_sse_fit_stream_uses_core_request_builder_and_handler(monkeypatch):
    from datalab_core.fitting import build_fitting_request as real_build_fitting_request
    from datalab_core.fitting import run_fitting as real_run_fitting

    from app_web.blueprints import sse

    calls: dict[str, object] = {"build": 0, "run": 0, "request_ids": [], "submit": 0, "submit_request_ids": []}

    def fake_build_fitting_request(**kwargs):
        calls["build"] = int(calls["build"]) + 1
        calls["model_type"] = kwargs["model_type"]
        calls["headers"] = tuple(kwargs["headers"])
        calls["variable_map"] = dict(kwargs["variable_map"])
        calls["target_column"] = kwargs["target_column"]
        calls["poly_degree"] = kwargs["poly_degree"]
        calls["precision_digits"] = kwargs["precision_digits"]
        return real_build_fitting_request(**kwargs)

    def fake_run_fitting(request):
        calls["run"] = int(calls["run"]) + 1
        calls["request_ids"].append(request.request_id)  # type: ignore[union-attr]
        return real_run_fitting(request)

    class FakeService:
        def submit(self, request):
            calls["submit"] = int(calls["submit"]) + 1
            calls["submit_request_ids"].append(request.request_id)  # type: ignore[union-attr]
            return fake_run_fitting(request)

    def fake_create_core_session_service():
        calls["factory"] = int(calls.get("factory", 0)) + 1
        return FakeService()

    monkeypatch.setattr(sse, "build_fitting_request", fake_build_fitting_request, raising=False)
    monkeypatch.setattr(sse, "run_fitting", fake_run_fitting, raising=False)
    monkeypatch.setattr(sse, "create_core_session_service", fake_create_core_session_service, raising=False)

    events = list(sse._single_fit_events(["0", "1", "2", "3"], ["1", "3", "5", "7"], "polynomial", 80))

    assert calls["build"] == 1
    assert calls["factory"] == 1
    assert calls["submit"] == 1
    assert calls["submit_request_ids"] == ["web-sse-fit-polynomial"]
    assert calls["run"] == 1
    assert calls["request_ids"] == ["web-sse-fit-polynomial"]
    assert calls["model_type"] == "polynomial"
    assert calls["headers"] == ("x", "y")
    assert calls["variable_map"] == {"x": "x"}
    assert calls["target_column"] == "y"
    assert calls["poly_degree"] == 1
    assert calls["precision_digits"] == 80
    assert [event_name for event_name, _payload in events] == ["started", "progress", "result"]
    result = events[-1][1]
    assert result["model"] == "polynomial"
    assert result["params"]["b0"] == pytest.approx(1.0)
    assert result["params"]["b1"] == pytest.approx(2.0)
