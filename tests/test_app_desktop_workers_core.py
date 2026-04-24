from __future__ import annotations

import mpmath as mp

from data_extrapolation_latex_latest import ExtrapolationOptions

from app_desktop.workers_core import (
    AutoFitJob,
    CalcJob,
    FitJob,
    _execute_auto_fit_job,
    _execute_calc_job,
    _execute_fit_job_payload,
)


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
