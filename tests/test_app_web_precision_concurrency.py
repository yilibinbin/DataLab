from __future__ import annotations

import csv
import io
import json
import re
import threading
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from mpmath import mp

from app_desktop.window_statistics_mixin import WindowStatisticsMixin

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


def _valid_error_distribution_summary() -> dict[str, object]:
    return {
        "schema": "datalab.monte_carlo_distribution_summary",
        "schema_version": 1,
        "requested_sample_count": 100,
        "evaluated_sample_count": 100,
        "accepted_sample_count": 100,
        "rejected_sample_count": 0,
        "finite_sample_count": 100,
        "mean": "1.0",
        "std": "0.2",
        "histogram": {"bin_edges": ["0.0", "1.0", "2.0"], "counts": [50, 50]},
        "percentiles": {"2.5": "0.1", "50": "1.0", "97.5": "1.9"},
    }


_CURRENT_STATISTICS_FOUNDATION_KEYS = {
    "method",
    "row_count",
    "mean",
    "trimmed_mean",
    "mean_ci_lower",
    "mean_ci_upper",
    "mean_ci_margin",
    "mean_ci_confidence_level",
    "mean_ci_method",
    "mean_sample_se_for_ci",
    "weighted_se_known_sigma",
    "mean_ci_dof",
    "mean_ci_critical_value",
    "std_mean",
    "std",
    "variance",
    "min",
    "max",
    "count",
    "median",
    "q1",
    "q3",
    "iqr",
    "mad",
    "skewness",
    "excess_kurtosis",
    "effective_n",
    "weighted_chi_square",
    "weighted_consistency_dof",
    "weighted_reduced_chi_square",
    "birge_ratio",
    "dropped",
    "zero_sigma_anchor",
    "outlier.sigma.1",
    "outlier.sigma.2",
    "outlier.sigma.3",
    "warning.zero_sigma_anchor",
}

_DESKTOP_CSV_KEY_MAP = {
    "method": "method",
    "row_count": "rows",
    "mean": "mean",
    "trimmed_mean": "trimmed_mean",
    "mean_ci_lower": "mean_ci_lower",
    "mean_ci_upper": "mean_ci_upper",
    "mean_ci_margin": "mean_ci_margin",
    "mean_ci_confidence_level": "mean_ci_confidence_level",
    "mean_ci_method": "mean_ci_method",
    "mean_sample_se_for_ci": "mean_sample_se_for_ci",
    "weighted_se_known_sigma": "weighted_se_known_sigma",
    "mean_ci_dof": "mean_ci_dof",
    "mean_ci_critical_value": "mean_ci_critical_value",
    "std": "std",
    "variance": "variance",
    "min": "min",
    "max": "max",
    "count": "count",
    "median": "median",
    "q1": "q1",
    "q3": "q3",
    "iqr": "iqr",
    "mad": "mad",
    "skewness": "skewness",
    "excess_kurtosis": "excess_kurtosis",
    "effective_n": "effective_n",
    "weighted_chi_square": "weighted_chi_square",
    "weighted_consistency_dof": "weighted_consistency_dof",
    "weighted_reduced_chi_square": "weighted_reduced_chi_square",
    "birge_ratio": "birge_ratio",
    "dropped": "dropped",
    "zero_sigma_anchor": "zero_sigma_anchor",
    "outlier.sigma.1": "outlier.sigma.1",
    "outlier.sigma.2": "outlier.sigma.2",
    "outlier.sigma.3": "outlier.sigma.3",
}

_WEB_CSV_KEY_MAP = {
    "method": "method",
    "row_count": "rows",
    "mean": "mean",
    "trimmed_mean": "trimmed_mean",
    "mean_ci_lower": "mean_ci_lower",
    "mean_ci_upper": "mean_ci_upper",
    "mean_ci_margin": "mean_ci_margin",
    "mean_ci_confidence_level": "mean_ci_confidence_level",
    "mean_ci_method": "mean_ci_method",
    "mean_sample_se_for_ci": "mean_sample_se_for_ci",
    "weighted_se_known_sigma": "weighted_se_known_sigma",
    "mean_ci_dof": "mean_ci_dof",
    "mean_ci_critical_value": "mean_ci_critical_value",
    "std": "std",
    "variance": "variance",
    "min": "min",
    "max": "max",
    "count": "count",
    "median": "median",
    "q1": "q1",
    "q3": "q3",
    "iqr": "iqr",
    "mad": "mad",
    "skewness": "skewness",
    "excess_kurtosis": "excess_kurtosis",
    "effective_n": "effective_n",
    "weighted_chi_square": "weighted_chi_square",
    "weighted_consistency_dof": "weighted_consistency_dof",
    "weighted_reduced_chi_square": "weighted_reduced_chi_square",
    "birge_ratio": "birge_ratio",
    "dropped": "dropped",
    "zero_sigma_anchor": "zero_sigma_anchor",
    "outlier.sigma.1": "outlier.sigma.1",
    "outlier.sigma.2": "outlier.sigma.2",
    "outlier.sigma.3": "outlier.sigma.3",
}


class _StatisticsFormatter(WindowStatisticsMixin):

    def _tr(self, _zh: str, en: str) -> str:
        return en

    def _format_display_value(self, value: object) -> str:
        try:
            return mp.nstr(mp.mpf(value), 12)
        except Exception:
            return str(value)

    def _format_precision_value(self, value: object) -> str:
        return self._format_display_value(value)

    def _format_uncertainty_value(self, value: object, uncertainty: object) -> str:
        return f"{self._format_display_value(value)} ± {self._format_display_value(uncertainty)}"


def _csv_metric_keys(rows: list[dict[str, object]]) -> set[str]:
    return {str(row.get("metric", "")) for row in rows}


def _csv_text_metric_keys(csv_data: str | None) -> set[str]:
    if not csv_data:
        return set()
    return {line.split(",", 1)[0] for line in csv_data.splitlines()[1:] if line.strip()}


def _csv_text_rows(csv_data: str | None) -> list[dict[str, str]]:
    if not csv_data:
        return []
    return list(csv.DictReader(io.StringIO(csv_data)))


def _statistics_calc_job(
    *,
    values: list[str],
    sigmas: list[str | None],
    stats_mode: str,
    precision: int = 60,
    trim_fraction: str | None = None,
) -> Any:
    from app_desktop.workers_core import CalcJob

    rows = [(mp.mpf(value),) for value in values]
    sigma_rows = [(None if sigma is None else mp.mpf(sigma),) for sigma in sigmas]
    return CalcJob(
        mode="statistics",
        data_path=None,
        manual_content="",
        manual_constants="",
        constants_file_path=None,
        options=SimpleNamespace(mp_precision=precision, warnings=[]),
        caption=None,
        generate_latex=False,
        output_path="",
        use_dcolumn=False,
        verbose=False,
        render_plots=False,
        lang="en",
        stats_value_col="A",
        stats_mode=stats_mode,
        stats_sample=True,
        stats_weighted_variance=True,
        stats_trim_fraction=trim_fraction,
        dataset=(["A"], rows, sigma_rows),
        latex_digits=16,
        segments=[(0, len(rows))],
        uncertainty_digits=2,
    )


def test_statistics_public_csv_method_row_uses_method_label_across_surfaces() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        run_statistics,
        statistics_csv_rows_from_result,
        statistics_payload_to_compute_result,
    )
    from datalab_core.statistics_compute import compute_statistics

    import app_web.logic.statistics as stats_logic

    values = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3")]
    sigmas = [mp.mpf("0.1"), mp.mpf("0.2"), mp.mpf("0.3")]
    core_result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={
                "values": [str(value) for value in values],
                "sigmas": [str(sigma) for sigma in sigmas],
                "stats_mode": "weighted_sigma",
            },
            options=JobOptions(precision_digits=60),
            request_id="stats-method-label-csv-compat",
        )
    )
    core_roundtrip = statistics_payload_to_compute_result(core_result.payload, core_result.warnings)
    semantic_rows = analysis_rows_from_json(core_result.payload["analysis_rows"])
    method_label = str(core_roundtrip["method_label"])
    assert {row.key: row for row in semantic_rows}["method"].value == "weighted_sigma"

    legacy_result = compute_statistics(values, sigmas, "weighted_sigma")
    legacy_rows = statistics_csv_rows_from_result(legacy_result, row_count=3, include_batch=False)
    core_rows = statistics_csv_rows_from_result(core_roundtrip, row_count=3, include_batch=False)
    desktop_rows = _StatisticsFormatter()._build_stats_csv_rows(core_roundtrip, batch_idx=1, row_count=3)
    web_result = stats_logic._run_statistics(
        "A sigma\n1 0.1\n2 0.2\n3 0.3\n",
        {
            "stats_mode": "weighted_sigma",
            "stats_mp_precision": "60",
            "stats_use_sample": "on",
            "stats_use_weighted_variance": "on",
        },
        lang="en",
    )
    web_rows = _csv_text_rows(web_result.csv_data)

    method_values = {
        "legacy": next(row["value"] for row in legacy_rows if row["metric"] == "method"),
        "core_roundtrip": next(row["value"] for row in core_rows if row["metric"] == "method"),
        "desktop": next(row["value"] for row in desktop_rows if row["metric"] == "method"),
        "web": next(row["value"] for row in web_rows if row["metric"] == "method"),
    }
    assert method_values == {
        "legacy": method_label,
        "core_roundtrip": method_label,
        "desktop": method_label,
        "web": method_label,
    }
    assert method_label == "Weighted mean (sample)"
    assert "weighted_sigma" not in set(method_values.values())
    assert [row["metric"] for row in desktop_rows][:2] == ["method", "mean"]
    assert [row["metric"] for row in web_rows][:2] == ["method", "mean"]
    assert "rows" in [row["metric"] for row in desktop_rows]
    assert "rows" in [row["metric"] for row in web_rows]


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
        calls["source_row_ids"] = list(request.inputs["source_row_ids"])  # type: ignore[index]
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
    assert calls["source_row_ids"] == ["1", "2", "3"]
    assert calls["headers"] == ("A",)
    assert calls["value_col"] == "A"
    assert calls["precision_digits"] == 80
    assert result.stats_mode == "weighted_sigma"
    assert result.mp_precision == 80
    assert result.result["method_label"] == "Weighted mean (sample)"
    assert "v_min" in result.result
    assert "v_max" in result.result
    assert "min" not in result.result
    assert "max" not in result.result
    assert result.result["source_row_ids"] == ("1", "2", "3")
    assert result.csv_data and "mean" in result.csv_data
    assert "min" in result.csv_data
    assert "max" in result.csv_data
    assert result.raw_csv_data and "A_sigma" in result.raw_csv_data


def test_web_statistics_generate_plots_returns_gallery(monkeypatch) -> None:
    import app_web.logic.statistics as stats_logic

    captured: dict[str, object] = {}

    def fake_render_statistics_plots(values, sigmas, stats_result, *, lang):
        captured["values"] = list(values)
        captured["sigmas"] = list(sigmas or [])
        captured["mean"] = stats_result.get("mean")
        captured["lang"] = lang
        return [b"\x89PNG\r\n\x1a\nseries", b"\x89PNG\r\n\x1a\nhist"]

    monkeypatch.setattr(stats_logic, "_render_statistics_plots", fake_render_statistics_plots)

    result = stats_logic._run_statistics(
        "A sigma\n1 0.1\n2 0.2\n3 0.3\n",
        {
            "stats_mode": "weighted_sigma",
            "stats_generate_plots": "on",
            "stats_use_sample": "on",
            "stats_use_weighted_variance": "on",
        },
        lang="en",
    )

    assert captured["values"] == [mp.mpf("1"), mp.mpf("2"), mp.mpf("3")]
    assert captured["sigmas"] == [mp.mpf("0.1"), mp.mpf("0.2"), mp.mpf("0.3")]
    assert abs(mp.mpf(captured["mean"]) - mp.mpf("1.3469387755102040816326530612244897959")) < mp.mpf("1e-12")
    assert captured["lang"] == "en"
    assert result.plot_b64_list == ["iVBORw0KGgpzZXJpZXM=", "iVBORw0KGgpoaXN0"]
    assert result.plot_b64 == result.plot_b64_list[0]
    assert "\\begin" in result.latex_text


def test_web_statistics_two_column_zero_sigma_reaches_zero_anchor() -> None:
    import app_web.logic.statistics as stats_logic

    result = stats_logic._run_statistics(
        "A sigma\n"
        "1.25 0\n"
        "2.50 0.1\n",
        {
            "stats_mode": "weighted_sigma",
            "stats_mp_precision": "60",
            "stats_use_sample": "on",
            "stats_use_weighted_variance": "on",
        },
        lang="en",
    )

    assert result.result["zero_sigma_anchor"] is True
    assert result.result["method_label"] == "Weighted mean (σ=0 anchor)"
    assert any("infinite weight" in warning for warning in result.warnings)
    assert result.csv_data is not None
    assert "zero_sigma_anchor,True," in result.csv_data


def test_web_statistics_embedded_zero_sigma_reaches_zero_anchor() -> None:
    import app_web.logic.statistics as stats_logic

    result = stats_logic._run_statistics(
        "A\n"
        "1.25(0)\n"
        "2.50(10)\n",
        {
            "stats_mode": "weighted_sigma",
            "stats_mp_precision": "60",
            "stats_use_sample": "on",
            "stats_use_weighted_variance": "on",
        },
        lang="en",
    )

    assert result.result["zero_sigma_anchor"] is True
    assert result.result["method_label"] == "Weighted mean (σ=0 anchor)"
    assert any("infinite weight" in warning for warning in result.warnings)
    assert result.csv_data is not None
    assert "zero_sigma_anchor,True," in result.csv_data


@pytest.mark.parametrize(
    ("sigma_text", "message"),
    [
        ("-0.1", "Negative uncertainty"),
        ("nan", "not finite"),
        ("inf", "not finite"),
    ],
)
def test_web_statistics_two_column_invalid_sigma_fails_loudly(sigma_text: str, message: str) -> None:
    import app_web.logic.statistics as stats_logic

    with pytest.raises(ValueError, match=message):
        stats_logic._run_statistics(
            f"A sigma\n1.25 {sigma_text}\n2.50 0.1\n",
            {
                "stats_mode": "weighted_sigma",
                "stats_mp_precision": "60",
                "stats_use_sample": "on",
                "stats_use_weighted_variance": "on",
            },
            lang="en",
        )


def test_web_statistics_descriptive_mode_routes_core_and_exports_rows(monkeypatch):
    from datalab_core.statistics import build_statistics_requests as real_build_statistics_requests

    import app_web.logic.statistics as stats_logic

    captured: dict[str, object] = {}

    def fake_build_statistics_requests(**kwargs):
        captured["stats_mode"] = kwargs["stats_mode"]
        captured["use_sample"] = kwargs["use_sample"]
        return real_build_statistics_requests(**kwargs)

    monkeypatch.setattr(stats_logic, "build_statistics_requests", fake_build_statistics_requests, raising=False)

    result = stats_logic._run_statistics(
        "A\n1\n2\n3\n4\n",
        {
            "stats_mode": "descriptive",
            "stats_mp_precision": "70",
            "stats_use_sample": "on",
        },
        lang="en",
    )

    assert captured == {"stats_mode": "descriptive", "use_sample": True}
    assert result.stats_mode == "descriptive"
    assert result.result["method_label"] == "Descriptive statistics (sample)"
    assert result.result["median"] == "2.5"
    assert result.csv_data is not None
    assert "median,2.5," in result.csv_data
    assert "variance," in result.csv_data
    assert "Median" in result.latex_text
    assert "Excess kurtosis" in result.latex_text


def test_web_statistics_descriptive_trimmed_mean_routes_and_renders(monkeypatch):
    from app_web.server import create_app
    from datalab_core.statistics import build_statistics_requests as real_build_statistics_requests

    import app_web.logic.statistics as stats_logic

    captured: dict[str, object] = {}

    def fake_build_statistics_requests(**kwargs):
        captured["trim_fraction"] = kwargs["trim_fraction"]
        return real_build_statistics_requests(**kwargs)

    monkeypatch.setattr(stats_logic, "build_statistics_requests", fake_build_statistics_requests, raising=False)

    result = stats_logic._run_statistics(
        "A\n1\n2\n3\n4\n100\n",
        {
            "stats_mode": "descriptive",
            "stats_mp_precision": "70",
            "stats_use_sample": "on",
            "stats_trim_fraction": "0.2",
        },
        lang="en",
    )

    assert captured == {"trim_fraction": "0.2"}
    assert result.result["trimmed_mean"] == "3.0"
    assert "trimmed_mean,3.0," in (result.csv_data or "")
    assert "Trimmed mean" in result.latex_text

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    response = client.post(
        "/stats",
        data={
            "csrf_token": _csrf_token(client),
            "stats_data_text": "A\n1\n2\n3\n4\n100\n",
            "stats_mode": "descriptive",
            "stats_mp_precision": "70",
            "stats_use_sample": "on",
            "stats_trim_fraction": "0.2",
        },
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-i18n="stats.metricTrimmedMean"' in html
    assert "3.0" in html


def test_web_statistics_descriptive_singleton_surfaces_core_warnings_in_bundle_and_html():
    from app_web.logic import statistics as stats_logic
    from app_web.server import create_app

    bundle = stats_logic._run_statistics(
        "A\n7\n",
        {
            "stats_mode": "descriptive",
            "stats_mp_precision": "60",
            "stats_use_sample": "on",
        },
        lang="en",
    )

    assert bundle.warnings
    assert any("Sample descriptive statistics require n>=2" in warning for warning in bundle.warnings)
    assert any("Zero variance" in warning for warning in bundle.warnings)

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    response = client.post(
        "/stats",
        data={
            "csrf_token": _csrf_token(client),
            "stats_data_text": "A\n7\n",
            "stats_mode": "descriptive",
            "stats_mp_precision": "60",
            "stats_use_sample": "on",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Sample descriptive statistics require n&gt;=2" in html
    assert "statistics.warning.descriptive" not in html


def test_web_statistics_weighted_metrics_render_in_html_and_export_csv() -> None:
    from app_web.server import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    response = client.post(
        "/stats",
        data={
            "csrf_token": _csrf_token(client),
            "stats_data_text": "A sigma\n1 1\n2 1\n4 2\n",
            "stats_mode": "weighted_sigma",
            "stats_mp_precision": "60",
            "stats_use_sample": "on",
            "stats_use_weighted_variance": "on",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-i18n="stats.metricWeightedChiSquare"' in html
    assert 'data-i18n="stats.metricWeightedConsistencyDof"' in html
    assert 'data-i18n="stats.metricWeightedReducedChiSquare"' in html
    assert 'data-i18n="stats.metricBirgeRatio"' in html
    assert "const serverStatsCsvData = " in html
    assert "weighted_chi_square" in html
    assert "weighted_consistency_dof" in html
    assert "birge_ratio" in html


def test_web_statistics_zero_sigma_anchor_renders_in_html() -> None:
    from app_web.server import create_app

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    response = client.post(
        "/stats",
        data={
            "csrf_token": _csrf_token(client),
            "stats_data_text": "A\n1.25(0)\n2.50(10)\n",
            "stats_mode": "weighted_sigma",
            "stats_mp_precision": "60",
            "stats_use_sample": "on",
            "stats_use_weighted_variance": "on",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-i18n="stats.metricZeroSigmaAnchor"' in html
    assert "zero_sigma_anchor" in html
    assert "weighted_chi_square" not in html


def test_desktop_statistics_text_renders_descriptive_warning_text_not_message_key() -> None:
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import run_statistics, statistics_payload_to_compute_result

    result = SessionService(handlers={JobMode.STATISTICS: run_statistics}).submit(
        ComputeJobRequest(
            mode=JobMode.STATISTICS,
            inputs={"values": ["7"], "stats_mode": "descriptive", "use_sample": True},
            options=JobOptions(precision_digits=60),
            request_id="desktop-descriptive-warning-text",
        )
    )
    legacy = statistics_payload_to_compute_result(result.payload, result.warnings)
    text, csv_rows = _StatisticsFormatter()._format_statistics_display(legacy, "A", 1)
    warning_rows = [row for row in analysis_rows_from_json(result.payload["analysis_rows"]) if row.severity == "warning"]

    assert warning_rows
    assert all(row.message_key and str(row.message_key).startswith("statistics.warning.") for row in warning_rows)
    assert "Warnings:" in text
    assert "Sample descriptive statistics require n>=2" in text
    assert "statistics.warning.descriptive" not in text
    assert any("Sample descriptive statistics require n>=2" in str(row["value"]) for row in csv_rows)


def test_desktop_statistics_text_resolves_message_key_only_warning_rows() -> None:
    from datalab_core.results import AnalysisRow

    result = {
        "mode": "descriptive",
        "mean": mp.mpf("7"),
        "std_mean": mp.nan,
        "std": mp.nan,
        "variance": mp.nan,
        "v_min": mp.mpf("7"),
        "v_max": mp.mpf("7"),
        "method_label": "Descriptive statistics (sample)",
        "analysis_rows": [
            AnalysisRow(
                key="warning.descriptive_zero_variance",
                label_key="statistics.warning",
                severity="warning",
                message_key="statistics.warning.descriptive_zero_variance",
                render_group="diagnostic",
            ).to_json()
        ],
    }

    text, _csv_rows = _StatisticsFormatter()._format_statistics_display(result, "A", 1)

    assert "Zero variance; skewness and kurtosis are unavailable." in text
    assert "statistics.warning.descriptive_zero_variance" not in text


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


def test_statistics_analysis_row_mode_condition_coverage_invariant() -> None:
    from app_desktop.workers_core import _execute_calc_job
    from datalab_core.jobs import ComputeJobRequest, JobMode, JobOptions
    from datalab_core.results import ResultStatus, analysis_rows_from_json
    from datalab_core.session import SessionService
    from datalab_core.statistics import (
        run_statistics,
        statistics_csv_rows_from_result,
        statistics_payload_to_compute_result,
    )

    import app_web.logic.statistics as stats_logic

    unweighted_ci_keys = {
        "mean_ci_lower",
        "mean_ci_upper",
        "mean_ci_margin",
        "mean_ci_confidence_level",
        "mean_ci_method",
        "mean_sample_se_for_ci",
        "mean_ci_dof",
        "mean_ci_critical_value",
    }
    weighted_ci_keys = {
        "mean_ci_lower",
        "mean_ci_upper",
        "mean_ci_margin",
        "mean_ci_confidence_level",
        "mean_ci_method",
        "weighted_se_known_sigma",
        "mean_ci_critical_value",
    }
    scenarios = [
        {
            "name": "arithmetic",
            "values": ["1", "2", "3"],
            "sigmas": [None, None, None],
            "mode": "mean_sample",
            "analysis_keys": {"method", "row_count", "mean", "std_mean", "std", "min", "max"}
            | unweighted_ci_keys,
            "surface_keys": {"method", "row_count", "mean", "std_mean", "std", "min", "max"}
            | unweighted_ci_keys,
            "web_data": "A\n1\n2\n3\n",
        },
        {
            "name": "weighted_normal",
            "values": ["1", "2", "3"],
            "sigmas": ["0.1", "0.2", "0.3"],
            "mode": "weighted_sigma",
            "analysis_keys": {
                "method",
                "row_count",
                "mean",
                "std_mean",
                "std",
                "min",
                "max",
                "effective_n",
                "weighted_chi_square",
                "weighted_consistency_dof",
                "weighted_reduced_chi_square",
                "birge_ratio",
                "outlier.sigma.1",
                "outlier.sigma.2",
                "outlier.sigma.3",
            } | weighted_ci_keys,
            "surface_keys": {
                "method",
                "row_count",
                "mean",
                "std_mean",
                "std",
                "min",
                "max",
                "effective_n",
                "weighted_chi_square",
                "weighted_consistency_dof",
                "weighted_reduced_chi_square",
                "birge_ratio",
                "outlier.sigma.1",
                "outlier.sigma.2",
                "outlier.sigma.3",
            } | weighted_ci_keys,
            "web_data": "A sigma\n1 0.1\n2 0.2\n3 0.3\n",
        },
        {
            "name": "descriptive",
            "values": ["1", "2", "3", "4"],
            "sigmas": [None, None, None, None],
            "mode": "descriptive",
            "analysis_keys": {
                "method",
                "row_count",
                "count",
                "mean",
                "std_mean",
                "std",
                "variance",
                "min",
                "max",
                "median",
                "q1",
                "q3",
                "iqr",
                "mad",
                "skewness",
                "excess_kurtosis",
            } | unweighted_ci_keys,
            "surface_keys": {
                "method",
                "row_count",
                "count",
                "mean",
                "std_mean",
                "std",
                "variance",
                "min",
                "max",
                "median",
                "q1",
                "q3",
                "iqr",
                "mad",
                "skewness",
                "excess_kurtosis",
            } | unweighted_ci_keys,
            "web_data": "A\n1\n2\n3\n4\n",
        },
        {
            "name": "descriptive_trimmed",
            "values": ["1", "2", "3", "4", "5"],
            "sigmas": [None, None, None, None, None],
            "mode": "descriptive",
            "trim_fraction": "0.2",
            "analysis_keys": {
                "method",
                "row_count",
                "count",
                "mean",
                "trimmed_mean",
                "std_mean",
                "std",
                "variance",
                "min",
                "max",
                "median",
                "q1",
                "q3",
                "iqr",
                "mad",
                "skewness",
                "excess_kurtosis",
            } | unweighted_ci_keys,
            "surface_keys": {
                "method",
                "row_count",
                "count",
                "mean",
                "trimmed_mean",
                "std_mean",
                "std",
                "variance",
                "min",
                "max",
                "median",
                "q1",
                "q3",
                "iqr",
                "mad",
                "skewness",
                "excess_kurtosis",
            } | unweighted_ci_keys,
            "web_data": "A\n1\n2\n3\n4\n5\n",
        },
        {
            "name": "weighted_zero_sigma_anchor",
            "values": ["1.25", "2.5"],
            "sigmas": ["0", "0.1"],
            "mode": "weighted_sigma",
            "analysis_keys": {
                "method",
                "row_count",
                "mean",
                "std_mean",
                "std",
                "min",
                "max",
                "effective_n",
                "zero_sigma_anchor",
                "outlier.sigma.1",
                "warning.zero_sigma_anchor",
            },
            "surface_keys": {
                "method",
                "row_count",
                "mean",
                "std_mean",
                "std",
                "min",
                "max",
                "effective_n",
                "zero_sigma_anchor",
                "outlier.sigma.1",
            },
            "web_data": None,
        },
        {
            "name": "weighted_dropped_rows",
            "values": ["-999", "1.25", "2.5", "999"],
            "sigmas": [None, "0.1", "0.2", None],
            "mode": "weighted_sigma",
            "analysis_keys": {
                "method",
                "row_count",
                "mean",
                "std_mean",
                "std",
                "min",
                "max",
                "effective_n",
                "dropped",
                "weighted_chi_square",
                "weighted_consistency_dof",
                "weighted_reduced_chi_square",
                "birge_ratio",
                "outlier.sigma.1",
            } | weighted_ci_keys,
            "surface_keys": {
                "method",
                "row_count",
                "mean",
                "std_mean",
                "std",
                "min",
                "max",
                "effective_n",
                "dropped",
                "weighted_chi_square",
                "weighted_consistency_dof",
                "weighted_reduced_chi_square",
                "birge_ratio",
                "outlier.sigma.1",
            } | weighted_ci_keys,
            "web_data": "A sigma\n-999\n1.25 0.1\n2.5 0.2\n999\n",
        },
    ]
    formatter = _StatisticsFormatter()
    service = SessionService(handlers={JobMode.STATISTICS: run_statistics})

    for scenario in scenarios:
        values = list(scenario["values"])
        sigmas = list(scenario["sigmas"])
        mode = str(scenario["mode"])
        core_result = service.submit(
            ComputeJobRequest(
                mode=JobMode.STATISTICS,
                inputs={
                    "values": values,
                    "sigmas": sigmas,
                    "stats_mode": mode,
                    **(
                        {"trim_fraction": str(scenario["trim_fraction"])}
                        if scenario.get("trim_fraction") is not None
                        else {}
                    ),
                },
                options=JobOptions(precision_digits=60),
                request_id=f"invariant-{scenario['name']}",
            )
        )

        assert core_result.status is ResultStatus.SUCCEEDED
        analysis_rows = analysis_rows_from_json(core_result.payload["analysis_rows"])
        analysis_keys = {row.key for row in analysis_rows}
        assert analysis_keys <= _CURRENT_STATISTICS_FOUNDATION_KEYS
        assert scenario["analysis_keys"] <= analysis_keys
        assert "v_min" not in core_result.payload
        assert "v_max" not in core_result.payload
        assert {"min", "max"} <= set(core_result.payload)

        legacy = statistics_payload_to_compute_result(core_result.payload, core_result.warnings)
        assert {"v_min", "v_max"} <= set(legacy)
        assert "min" not in legacy
        assert "max" not in legacy
        if "warning.zero_sigma_anchor" in analysis_keys:
            assert core_result.warnings
            assert legacy["warnings"] == list(core_result.warnings)

        direct_text, direct_csv_rows = formatter._format_statistics_display(
            legacy,
            "A",
            len(values),
        )
        shared_desktop_rows = statistics_csv_rows_from_result(
            legacy,
            row_count=len(values),
            batch=1,
            include_batch=True,
        )
        assert direct_csv_rows == shared_desktop_rows
        direct_keys = _csv_metric_keys(direct_csv_rows)
        batch_result = _execute_calc_job(
            _statistics_calc_job(
                values=values,
                sigmas=sigmas,
                stats_mode=mode,
                trim_fraction=str(scenario["trim_fraction"])
                if scenario.get("trim_fraction") is not None
                else None,
            )
        )
        batch = batch_result.payload["batches"][0]
        batch_text, batch_csv_rows = formatter._format_statistics_batches_display([batch], "A")
        batch_keys = _csv_metric_keys(batch_csv_rows)

        for semantic_key in scenario["surface_keys"]:
            if semantic_key == "std_mean":
                assert "Std. error" in direct_text
                assert "Std. error" in batch_text
                continue
            csv_key = _DESKTOP_CSV_KEY_MAP[semantic_key]
            assert csv_key in direct_keys
            assert csv_key in batch_keys

        web_data = scenario["web_data"]
        if web_data is None:
            continue
        web_result = stats_logic._run_statistics(
            str(web_data),
            {
                "stats_mode": mode,
                "stats_mp_precision": "60",
                "stats_use_sample": "on",
                "stats_use_weighted_variance": "on",
                **(
                    {"stats_trim_fraction": str(scenario["trim_fraction"])}
                    if scenario.get("trim_fraction") is not None
                    else {}
                ),
            },
            lang="en",
        )
        shared_web_rows = statistics_csv_rows_from_result(
            legacy,
            row_count=len(values),
            include_batch=False,
            precision_digits=60,
        )
        web_csv_rows = _csv_text_rows(web_result.csv_data)
        assert [row["metric"] for row in web_csv_rows] == [
            str(row["metric"]) for row in shared_web_rows
        ]
        assert [row["value"] for row in web_csv_rows] == [
            str(row["value"]) for row in shared_web_rows
        ]
        assert [row["uncertainty"] for row in web_csv_rows] == [
            str(row["uncertainty"]) for row in shared_web_rows
        ]
        web_keys = _csv_text_metric_keys(web_result.csv_data)
        for semantic_key in scenario["surface_keys"]:
            if semantic_key == "std_mean":
                mean_rows = [line for line in (web_result.csv_data or "").splitlines() if line.startswith("mean,")]
                assert mean_rows and "," in mean_rows[0]
                continue
            csv_key = _WEB_CSV_KEY_MAP.get(semantic_key)
            if csv_key is not None:
                assert csv_key in web_keys
        if "dropped" in scenario["surface_keys"]:
            assert web_result.warnings


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


def test_web_error_propagation_active_units_fail_closed_before_evaluation(monkeypatch):
    import app_web.logic.error_propagation as error_logic

    def fail_if_called(**_kwargs):
        raise AssertionError("active Web units must fail before request construction")

    monkeypatch.setattr(error_logic, "build_uncertainty_request", fail_if_called, raising=False)

    with pytest.raises(ValueError, match="unit_evaluation_unsupported_on_web"):
        error_logic._run_error_propagation(
            "A\n1.0(1)\n",
            "",
            {
                "error_formula": "A",
                "error_units_enabled": "on",
                "error_units_mode": "validate_expression",
            },
            lang="en",
        )


def test_web_error_propagation_display_only_units_remain_inert(monkeypatch):
    import app_web.logic.error_propagation as error_logic

    result = error_logic._run_error_propagation(
        "A\n1.0(1)\n",
        "",
        {
            "error_formula": "A",
            "error_units_enabled": "on",
            "error_units_mode": "display_only",
            "error_units_config": (
                '{"schema":"datalab.units.annotations.v1","schema_version":1,'
                '"enabled":true,"mode":"display_only","inputs":{"A":{"unit":"m"}},'
                '"outputs":{"result":{"unit":"m"}}}'
            ),
        },
        lang="en",
    )

    assert result.formatted_rows[0]["value"].startswith("1")


def test_web_error_propagation_monte_carlo_plots_collect_distribution_gallery(monkeypatch):
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus

    import app_web.logic.error_propagation as error_logic

    captured: dict[str, object] = {}

    class FakeService:
        def submit(self, request):
            captured["collect"] = request.inputs["collect_monte_carlo_distribution"]
            return ResultEnvelope(
                kind=ResultKind.TABLE,
                status=ResultStatus.SUCCEEDED,
                payload={
                    "headers": ["x"],
                    "formula": "x",
                    "segments": [[0, 1]],
                    "precision_used": 50,
                    "propagation": {
                        "method": "monte_carlo",
                        "order": 1,
                        "mc_samples": 100,
                        "mc_seed": 7,
                    },
                    "results": [
                        {
                            "value": "1.0",
                            "uncertainty": "0.2",
                            "contributions": {"x": "0.04"},
                            "monte_carlo_distribution": _valid_error_distribution_summary(),
                        }
                    ],
                },
            )

    monkeypatch.setattr(error_logic, "create_core_session_service", lambda: FakeService(), raising=False)
    monkeypatch.setattr(error_logic, "_render_error_latex", lambda *_args, **_kwargs: "ERROR_LATEX")
    monkeypatch.setattr(error_logic, "_render_contribution_plot", lambda *_args, **_kwargs: b"web-contrib")

    def fake_render_distribution(summary, *, lang, row_index):
        captured["summary"] = summary
        captured["lang"] = lang
        captured["row_index"] = row_index
        return b"web-dist"

    monkeypatch.setattr(error_logic, "_render_monte_carlo_distribution_plot", fake_render_distribution)

    result = error_logic._run_error_propagation(
        "x\n1.0(1)\n",
        "",
        {
            "error_formula": "x",
            "error_result_digits": "2",
            "error_generate_plots": "on",
            "error_propagation_method": "monte_carlo",
            "error_propagation_order": "1",
            "error_mc_samples": "100",
            "error_mc_seed": "7",
        },
        lang="en",
    )

    assert captured["collect"] is True
    assert captured["summary"]["schema"] == "datalab.monte_carlo_distribution_summary"
    assert captured["summary"]["finite_sample_count"] == 100
    assert captured["summary"]["histogram"]["counts"] == [50, 50]
    assert captured["lang"] == "en"
    assert captured["row_index"] == 1
    assert result.plot_b64_list == ["d2ViLWNvbnRyaWI=", "d2ViLWRpc3Q="]
    assert result.plot_b64 == result.plot_b64_list[0]


def test_web_error_propagation_taylor_plots_do_not_collect_distribution(monkeypatch):
    from datalab_core.results import ResultEnvelope, ResultKind, ResultStatus

    import app_web.logic.error_propagation as error_logic

    captured: dict[str, object] = {}

    class FakeService:
        def submit(self, request):
            captured["collect"] = request.inputs["collect_monte_carlo_distribution"]
            return ResultEnvelope(
                kind=ResultKind.TABLE,
                status=ResultStatus.SUCCEEDED,
                payload={
                    "headers": ["x"],
                    "formula": "x",
                    "segments": [[0, 1]],
                    "precision_used": 50,
                    "propagation": {
                        "method": "taylor",
                        "order": 1,
                        "mc_samples": None,
                        "mc_seed": None,
                    },
                    "results": [{"value": "1.0", "uncertainty": "0.1", "contributions": {}}],
                },
            )

    def fail_distribution_render(*_args, **_kwargs):
        raise AssertionError("Taylor plot run should not render distribution plots")

    monkeypatch.setattr(error_logic, "create_core_session_service", lambda: FakeService(), raising=False)
    monkeypatch.setattr(error_logic, "_render_error_latex", lambda *_args, **_kwargs: "ERROR_LATEX")
    monkeypatch.setattr(error_logic, "_render_contribution_plot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(error_logic, "_render_monte_carlo_distribution_plot", fail_distribution_render)

    result = error_logic._run_error_propagation(
        "x\n1.0(1)\n",
        "",
        {
            "error_formula": "x",
            "error_result_digits": "2",
            "error_generate_plots": "on",
            "error_propagation_method": "taylor",
            "error_propagation_order": "1",
        },
        lang="en",
    )

    assert captured["collect"] is False
    assert result.plot_b64 is None
    assert result.plot_b64_list is None


def test_web_error_route_renders_plot_gallery(monkeypatch):
    from app_web.blueprints import pages
    from app_web.server import create_app

    def fake_run(_data_text, _constants_text, _form, *, lang):
        assert lang
        return SimpleNamespace(
            mp_precision=50,
            formatted_rows=[{"index": 1, "value": "1.0", "uncertainty": "0.1", "latex": "1.0(1)"}],
            warnings=[],
            csv_data=None,
            plot_b64="Q09OVFJJQg==",
            plot_b64_list=["Q09OVFJJQg==", "RElTVA=="],
            latex_text="ERROR_LATEX",
            pdf_b64=None,
        )

    monkeypatch.setattr(pages, "_run_error_propagation", fake_run)

    app = create_app()
    app.config["TESTING"] = True
    client = app.test_client()
    response = client.post(
        "/error",
        data={
            "csrf_token": _csrf_token(client),
            "uncert_data_text": "x\n1.0(1)\n",
            "error_formula": "x",
        },
    )

    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "data:image/png;base64,Q09OVFJJQg==" in html
    assert "data:image/png;base64,RElTVA==" in html


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


def test_run_fit_parses_high_precision_input_inside_precision_guard() -> None:
    # P0-1 regression: web fitting must parse the data table INSIDE the precision
    # guard. If parsing happens at the ambient mp.dps (e.g. 15 left by a prior job),
    # high-precision input columns are silently truncated before the fit ever runs.
    import app_web.logic.fitting as fit_logic

    # A well-conditioned line, but the first x carries a digit at the 1e-24 place
    # (representable only at dps>=24). We assert the PARSED x-column keeps that
    # precision through to the result bundle; parsing at ambient dps=15 rounds it to 1.0.
    hi = "1.000000000000000000000001"
    data = f"x y\n{hi} 3\n2 5\n3 7\n4 9\n5 11\n"

    original = mp.dps
    mp.dps = 15  # simulate a fresh/leaked worker at the default precision
    try:
        result = fit_logic._run_fit(
            data,
            {
                "fit_mode": "polynomial",
                "fit_poly_degree": "1",
                "fit_mp_precision": "80",
                "fit_result_digits": "2",
            },
        )
    finally:
        mp.dps = original

    # The parsed x-column value must survive at full precision, not rounded to ~15 digits.
    with mp.workdps(80):
        got = result.x[0]
        expected = mp.mpf(hi)
        assert mp.fabs(got - expected) < mp.mpf("1e-30"), (
            f"x[0] parsed as {got!r}; high-precision input truncated (parse outside precision guard)"
        )
