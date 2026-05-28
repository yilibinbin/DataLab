from __future__ import annotations

from types import SimpleNamespace

import mpmath as mp
import pytest

from data_extrapolation_latex_latest import ExtrapolationOptions

import app_desktop.workers_core as workers_core
from app_desktop.workers_core import (
    AutoFitJob,
    CalcJob,
    FitJob,
    _execute_auto_fit_job,
    _execute_calc_job,
    _execute_fit_job_payload,
)
from fitting.hp_fitter import FitResult
from fitting.implicit_model import ImplicitModelDefinition, ImplicitSolveOptions


def test_execute_fit_job_payload_poly_recovers_linear_params():
    x_series = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
    y_series = [mp.mpf("2") * x + mp.mpf("1") for x in x_series]

    data_rows = list(zip(x_series, y_series))
    sigma_rows = [(None, None) for _ in data_rows]

    job = FitJob(
        model_type="poly",
        headers=["x", "y"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="y",
        model_expr="",
        parameter_config={},
        parameter_names=[],
        poly_degree=1,
        precision=80,
        weighted=False,
        label="unit-test",
    )

    payload = _execute_fit_job_payload(job)
    fit = payload.fit_result
    assert fit is not None
    assert mp.almosteq(fit.params["b0"], mp.mpf("1"), abs_eps=mp.mpf("1e-50"))
    assert mp.almosteq(fit.params["b1"], mp.mpf("2"), abs_eps=mp.mpf("1e-50"))


def test_execute_fit_job_payload_self_consistent_wires_definition_and_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    x_series = [mp.mpf(v) for v in ["0", "1", "2"]]
    y_series = [mp.mpf(v) for v in ["0.3", "0.4", "0.5"]]

    data_rows = list(zip(x_series, y_series))
    sigma_rows = [(None, None) for _ in data_rows]
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*Cos[u] + c*x",
        output_expression="u",
        parameters=("a", "b", "c"),
        constants={},
        solve_options=ImplicitSolveOptions(
            method="root",
            initial="0.3",
            tolerance="1e-36",
        ),
    )
    spec = SimpleNamespace(
        implicit_diagnostics=SimpleNamespace(
            points_solved=7,
            root_fallbacks=2,
            max_iterations_used=5,
            max_residual="1.0e-42",
        )
    )
    calls: dict[str, object] = {}

    def fake_build_implicit_model_specification(
        received_definition: ImplicitModelDefinition,
    ) -> object:
        calls["definition"] = received_definition
        return spec

    def fake_fit_custom_model(
        received_spec: object,
        state: object,
        variable_data: dict[str, list[mp.mpf]],
        target_series: list[mp.mpf],
        **kwargs: object,
    ) -> FitResult:
        calls["spec"] = received_spec
        calls["free_params"] = tuple(state.free_params)
        calls["variable_data"] = variable_data
        calls["target_series"] = target_series
        calls["kwargs"] = kwargs
        return FitResult(
            params={"a": mp.mpf("0.1"), "b": mp.mpf("0.2"), "c": mp.mpf("0.4")},
            param_errors={},
            chi2=mp.mpf("0"),
            reduced_chi2=mp.mpf("0"),
            aic=mp.mpf("0"),
            bic=mp.mpf("0"),
            r2=mp.mpf("1"),
            rmse=mp.mpf("0"),
            residuals=[],
            fitted_curve=list(target_series),
            covariance=[],
            details={},
        )

    monkeypatch.setattr(
        workers_core,
        "build_implicit_model_specification",
        fake_build_implicit_model_specification,
    )
    monkeypatch.setattr(workers_core, "fit_custom_model", fake_fit_custom_model)

    job = FitJob(
        model_type="self_consistent",
        headers=["x", "u"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        variable_map={"x": "x"},
        variable_data={"x": x_series},
        target_series=y_series,
        target_column="u",
        model_expr="",
        parameter_config={
            "a": {"initial": 0.1},
            "b": {"initial": 0.2},
            "c": {"initial": 0.4},
        },
        parameter_names=["a", "b", "c"],
        precision=30,
        weighted=False,
        label="self-consistent-test",
        implicit_definition=definition,
    )

    payload = _execute_fit_job_payload(job)
    fit = payload.fit_result

    assert calls["definition"] is definition
    assert calls["spec"] is spec
    assert calls["free_params"] == ("a", "b", "c")
    assert calls["variable_data"] == {"x": x_series}
    assert calls["target_series"] == y_series
    assert calls["kwargs"] == {
        "precision": 30,
        "weights": None,
        "data_sigmas": [None] * len(y_series),
    }
    assert {name: float(value) for name, value in fit.params.items()} == {
        "a": 0.1,
        "b": 0.2,
        "c": 0.4,
    }
    assert payload.expression == "u"
    details = fit.details
    assert details["implicit_variable"] == "u"
    assert details["equation"] == "a + b*Cos[u] + c*x"
    assert details["output_expression"] == "u"
    assert details["implicit_diagnostics"] == {
        "points_solved": 7,
        "root_fallbacks": 2,
        "max_iterations_used": 5,
        "max_residual": "1.0e-42",
    }


def test_execute_fit_job_payload_self_consistent_requires_definition() -> None:
    with pytest.raises(ValueError, match="requires an implicit definition"):
        _execute_fit_job_payload(
            FitJob(
                model_type="self_consistent",
                headers=["x", "u"],
                data_rows=[],
                sigma_rows=[],
                x_series=[],
                y_series=[],
                sigma_series=[],
                weights=None,
                variable_map={"x": "x"},
                variable_data={"x": []},
                target_series=[],
                target_column="u",
                model_expr="",
                parameter_config={"a": {"initial": 0.1}},
                parameter_names=["a"],
                precision=30,
                weighted=False,
                label="missing-definition-test",
            )
        )


def test_execute_auto_fit_job_selects_a_model() -> None:
    x_series = [mp.mpf(v) for v in ["0", "1", "2", "3", "4"]]
    y_series = [mp.mpf("2") * x + mp.mpf("1") for x in x_series]
    data_rows = list(zip(x_series, y_series))
    sigma_rows = [(None, None) for _ in data_rows]

    job = AutoFitJob(
        headers=["x", "y"],
        data_rows=data_rows,
        sigma_rows=sigma_rows,
        x_series=x_series,
        y_series=y_series,
        sigma_series=[None] * len(y_series),
        weights=None,
        precision=80,
        custom_entries=[],
        extra_models=[],
        verbose=False,
        render_plots=False,
    )
    summary = _execute_auto_fit_job(job)
    assert summary.best_model is not None
    best = summary.best()
    assert best is not None
    assert best.success is True


def test_execute_calc_job_extrapolation_returns_payload() -> None:
    with mp.workdps(80):
        limit = mp.mpf("1")
        amp = mp.mpf("0.5")
        terms = [limit + amp / mp.power(n, 2) for n in range(1, 9)]  # 8 columns
        headers = [f"S{idx}" for idx in range(1, len(terms) + 1)]
        data_text = " ".join(headers) + "\n" + " ".join(mp.nstr(v, 50) for v in terms) + "\n"

        opts = ExtrapolationOptions(method="richardson", mp_precision=80)
        job = CalcJob(
            mode="extrapolation",
            data_path=None,
            manual_content=data_text,
            manual_constants="",
            constants_file_path=None,
            options=opts,
            caption=None,
            generate_latex=False,
            output_path="",
            use_dcolumn=False,
            verbose=False,
            render_plots=False,
            lang="en",
            latex_digits=16,
            latex_group_size=3,
            uncertainty_digits=2,
        )

        result = _execute_calc_job(job)
        assert result.mode == "extrapolation"
        assert result.latex_path is None
        payload = result.payload
        assert payload["headers"] == headers
        assert len(payload["data_rows"]) == 1
        assert len(payload["results"]) == 1
        assert payload["precision_used"] == 80
        assert payload["render_plots"] is False
        assert "plots" not in payload

        res0 = payload["results"][0]
        assert mp.fabs(res0.value - limit) < mp.mpf("1e-2")
