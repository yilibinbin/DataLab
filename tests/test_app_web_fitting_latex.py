from __future__ import annotations

import csv
import json
import shutil
from io import StringIO
from types import SimpleNamespace

import pytest
from mpmath import mp


def _sample_params() -> list[dict[str, object]]:
    return [
        {
            "name": "A",
            "value_raw": mp.mpf("1234.5"),
            "uncertainty_raw": mp.mpf("0.6"),
        }
    ]


def _sample_metrics() -> dict[str, object]:
    return {
        "chi2": "1.0",
        "reduced_chi2": "1.0",
        "aic": "0.0",
        "bic": "0.0",
        "r2": "0.9",
        "rmse": "0.1",
    }


def _render_fitting_latex(model_expression: object | None = None, *, use_dcolumn: bool = False) -> str:
    from app_web.logic.fitting import _generate_fitting_latex

    return _generate_fitting_latex(
        best_label="A*x + B",
        params=_sample_params(),
        metrics=_sample_metrics(),
        use_dcolumn=use_dcolumn,
        caption="Fitting",
        latex_precision=8,
        latex_group_size=3,
        uncertainty_digits=None,
        model_expression=model_expression,
    )


def test_generate_fitting_latex_adds_canonical_formula_and_keeps_model_label() -> None:
    tex = _render_fitting_latex("d0 + d2/(n-delta)^2")

    assert r"Model: \texttt{A*x + B}" in tex
    assert r"Formula: $d_{0} + \frac{d_{2}}{(n-\delta)^{2}}$" in tex
    assert tex.index("Model:") < tex.index("Formula:")


@pytest.mark.parametrize("model_expression", [None, "", "   ", "None", " None "])
def test_generate_fitting_latex_skips_empty_and_legacy_none_formula_values(model_expression: object | None) -> None:
    tex = _render_fitting_latex(model_expression)

    assert "Formula:" not in tex
    assert "$None$" not in tex
    assert "$$" not in tex


@pytest.mark.parametrize(
    ("model_expression", "expected", "forbidden"),
    [
        ("x\\", r"Formula: $x\backslash{}$", r"$x\$"),
        (r"\foo + x", r"Formula: $\backslash{}foo + x$", r"$\foo"),
        ("a_b_c", r"Formula: $a\_b\_c$", r"$a_b_c$"),
    ],
)
def test_generate_fitting_latex_uses_safe_literal_formula_fallback(
    model_expression: str,
    expected: str,
    forbidden: str,
) -> None:
    tex = _render_fitting_latex(model_expression)

    assert expected in tex
    assert forbidden not in tex


def test_generate_fitting_latex_literal_fallback_with_invalid_subscripts_compiles() -> None:
    from app_web.latex_security import compile_latex_safe

    engine = next((name for name in ("pdflatex", "xelatex", "lualatex") if shutil.which(name)), None)
    if not engine:
        pytest.skip("No TeX engine found (pdflatex/xelatex/lualatex).")

    tex = _render_fitting_latex("a_b_c")
    warnings: list[str] = []
    pdf = compile_latex_safe(tex, engine, warnings, "fitting")

    assert r"Formula: $a\_b\_c$" in tex
    assert pdf is not None, f"LaTeX compile failed: {warnings}"
    assert pdf.startswith(b"%PDF")


def test_generate_fitting_latex_literal_fallback_with_metacharacters_compiles() -> None:
    from app_web.latex_security import compile_latex_safe

    engine = next((name for name in ("pdflatex", "xelatex", "lualatex") if shutil.which(name)), None)
    if not engine:
        pytest.skip("No TeX engine found (pdflatex/xelatex/lualatex).")

    tex = _render_fitting_latex(r"x^ + y\ + a_b & c % d $ e # f ~g")
    warnings: list[str] = []
    pdf = compile_latex_safe(tex, engine, warnings, "fitting")

    assert r"Formula: $x\char`\^{} + y\backslash{} + a\_b \& c \% d \$ e \# f \sim{}g$" in tex
    assert pdf is not None, f"LaTeX compile failed: {warnings}"
    assert pdf.startswith(b"%PDF")


def test_generate_fitting_latex_preserves_dcolumn_numeric_formatting_with_formula() -> None:
    tex = _render_fitting_latex("d0 + d2/(n-delta)^2", use_dcolumn=True)

    assert r"\newcolumntype{d}[1]{D{.}{.}{#1}}" in tex
    assert r"\begin{tabular}{l d{2.10}}" in tex
    assert r"A & 1.234\,5(6)[\text{+3}] \\" in tex
    assert r"\begin{tabular}{l d{2.13}}" in tex
    assert r"$\chi^2$ & 1.000\,000\,00 \\" in tex


def test_run_fit_passes_raw_core_expression_to_latex_not_csv_string(monkeypatch) -> None:
    from datalab_core.fitting import run_fitting as real_run_fitting

    import app_web.logic.fitting as fit_logic

    class RawExpression:
        def __bool__(self) -> bool:
            return True

        def __str__(self) -> str:
            return "STRINGIFIED_FOR_CSV"

    raw_expression = RawExpression()
    calls: dict[str, object] = {}

    def fake_generate_fitting_latex(**kwargs):
        calls["model_expression"] = kwargs.get("model_expression", "missing")
        return "LATEX_FROM_FAKE"

    class FakeService:
        def submit(self, request):
            result = real_run_fitting(request)
            return SimpleNamespace(
                status=result.status,
                payload={**result.payload, "expression": raw_expression},
                warnings=result.warnings,
            )

    monkeypatch.setattr(fit_logic, "create_core_session_service", lambda: FakeService(), raising=False)
    monkeypatch.setattr(fit_logic, "_generate_fitting_latex", fake_generate_fitting_latex)

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

    assert calls["model_expression"] is raw_expression
    assert result.latex_text == "LATEX_FROM_FAKE"
    assert result.csv_data is not None
    assert "STRINGIFIED_FOR_CSV" in result.csv_data


def test_run_fit_does_not_fall_back_to_blank_model_expr_for_missing_core_expression(monkeypatch) -> None:
    from datalab_core.fitting import run_fitting as real_run_fitting

    import app_web.logic.fitting as fit_logic

    calls: dict[str, object] = {}

    def fake_generate_fitting_latex(**kwargs):
        calls["model_expression"] = kwargs.get("model_expression", "missing")
        return "LATEX_FROM_FAKE"

    class FakeService:
        def submit(self, request):
            result = real_run_fitting(request)
            payload = dict(result.payload)
            payload.pop("expression", None)
            return SimpleNamespace(status=result.status, payload=payload, warnings=result.warnings)

    monkeypatch.setattr(fit_logic, "create_core_session_service", lambda: FakeService(), raising=False)
    monkeypatch.setattr(fit_logic, "_generate_fitting_latex", fake_generate_fitting_latex)

    fit_logic._run_fit(
        "x y\n"
        "0 1\n"
        "1 3\n"
        "2 5\n"
        "3 7\n",
        {
            "fit_mode": "polynomial",
            "fit_poly_degree": "1",
            "fit_mp_precision": "80",
        },
    )

    assert calls["model_expression"] is None


def test_run_fit_uses_sentinel_fit_result_metrics(monkeypatch) -> None:
    from datalab_core.results import ResultStatus
    from fitting.hp_fitter import FitResult
    from shared.fitting_engine import serialize_fit_result

    import app_web.logic.fitting as fit_logic

    sentinel_result = FitResult(
        params={"A": mp.mpf("1.0")},
        param_errors={"A": mp.mpf("0.0")},
        chi2=mp.mpf("101"),
        reduced_chi2=mp.mpf("202"),
        aic=mp.mpf("303"),
        bic=mp.mpf("404"),
        r2=mp.mpf("0.505"),
        rmse=mp.mpf("0.606"),
        residuals=[mp.mpf("0.0")],
        fitted_curve=[mp.mpf("0.0")],
        covariance=[[mp.mpf("0.0")]],
        param_errors_stat={"A": mp.mpf("0.0")},
        param_errors_sys={"A": mp.mpf("0.0")},
        param_errors_total={"A": mp.mpf("0.0")},
    )

    class FakeService:
        def submit(self, request):
            return SimpleNamespace(
                status=ResultStatus.SUCCEEDED,
                payload={
                    "fit_result": serialize_fit_result(sentinel_result, 30),
                    "expression": "A*x",
                    "warnings": [],
                },
                warnings=[],
            )

    monkeypatch.setattr(fit_logic, "create_core_session_service", lambda: FakeService(), raising=False)

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

    assert result.metrics == {
        "chi2": fit_logic._format_number(mp.mpf("101"), 8),
        "reduced_chi2": fit_logic._format_number(mp.mpf("202"), 8),
        "aic": fit_logic._format_number(mp.mpf("303"), 8),
        "bic": fit_logic._format_number(mp.mpf("404"), 8),
        "r2": fit_logic._format_number(mp.mpf("0.505"), 8),
        "rmse": fit_logic._format_number(mp.mpf("0.606"), 8),
    }
    assert result.csv_data is not None
    csv_metrics = {
        row["name"]: mp.mpf(row["value"])
        for row in csv.DictReader(StringIO(result.csv_data))
        if row["section"] == "metric"
    }
    for metric, value in result.metrics.items():
        assert mp.almosteq(csv_metrics[metric], getattr(sentinel_result, metric))
        assert value in result.latex_text


def test_run_fit_surfaces_attached_diagnostics_in_metrics_csv_and_latex(monkeypatch) -> None:
    from datalab_core.results import ResultStatus
    from fitting.diagnostics import attach_fit_diagnostics
    from fitting.hp_fitter import FitResult
    from shared.fitting_engine import serialize_fit_result

    import app_web.logic.fitting as fit_logic

    fit_result = FitResult(
        params={"A": mp.mpf("1"), "B": mp.mpf("2")},
        param_errors={"A": mp.mpf("2"), "B": mp.mpf("3")},
        chi2=mp.mpf("4.6051701859880913680359829093687284152022029772575"),
        reduced_chi2=mp.mpf("2.3025850929940456840179914546843642076011014886288"),
        aic=mp.mpf("0"),
        bic=mp.mpf("0"),
        r2=mp.mpf("1"),
        rmse=mp.mpf("2"),
        residuals=[mp.mpf("1"), mp.mpf("-2")],
        fitted_curve=[mp.mpf("0"), mp.mpf("0")],
        covariance=[[mp.mpf("4"), mp.mpf("6")], [mp.mpf("6"), mp.mpf("9")]],
        param_errors_stat={"A": mp.mpf("2"), "B": mp.mpf("3")},
        param_errors_sys={},
        param_errors_total={"A": mp.mpf("2"), "B": mp.mpf("3")},
        details={"dof": 2, "covariance_parameters": ["A", "B"]},
    )
    attach_fit_diagnostics(fit_result, sigma_series=[mp.mpf("2"), mp.mpf("4")])

    class FakeService:
        def submit(self, request):
            return SimpleNamespace(
                status=ResultStatus.SUCCEEDED,
                payload={
                    "fit_result": serialize_fit_result(fit_result, 30),
                    "expression": "A*x + B",
                    "warnings": [],
                },
                warnings=[],
            )

    monkeypatch.setattr(fit_logic, "create_core_session_service", lambda: FakeService(), raising=False)

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

    assert mp.almosteq(mp.mpf(result.metrics["chi_square_p_value"]), mp.mpf("0.1"))
    assert result.metrics["max_standardized_residual"] == "0.5"
    assert "$\\chi^2$ p-value" in result.latex_text
    assert "Max standardized residual" in result.latex_text
    assert "Fitting Diagnostics" in result.latex_text
    assert "Corr A,B" in result.latex_text
    assert "Sigma-standardized residual 1" in result.latex_text
    assert result.diagnostic_correlations[1] == {
        "left": "A",
        "right": "B",
        "value": "1.0",
    }
    assert result.diagnostic_residuals[0] == {
        "index": 1,
        "value": "0.5",
        "label": "Sigma-standardized residual",
        "method": "sigma",
    }
    assert result.csv_data is not None
    csv_rows = list(csv.DictReader(StringIO(result.csv_data)))
    by_name = {row["name"]: row for row in csv_rows}
    assert by_name["chi_square_p_value"]["section"] == "metric"
    assert by_name["corr[A,B]"]["section"] == "correlation"
    assert by_name["standardized_residual[1]"]["note"] == "Sigma-standardized residual"


def test_run_fit_plot_routes_attached_diagnostics_to_shared_overview(monkeypatch) -> None:
    from datalab_core.results import ResultStatus
    from fitting.diagnostics import attach_fit_diagnostics
    from fitting.hp_fitter import FitResult
    from shared.fitting_engine import serialize_fit_result

    import app_web.logic.fitting as fit_logic

    fit_result = FitResult(
        params={"A": mp.mpf("1"), "B": mp.mpf("2")},
        param_errors={"A": mp.mpf("2"), "B": mp.mpf("3")},
        chi2=mp.mpf("4.6051701859880913680359829093687284152022029772575"),
        reduced_chi2=mp.mpf("2.3025850929940456840179914546843642076011014886288"),
        aic=mp.mpf("0"),
        bic=mp.mpf("0"),
        r2=mp.mpf("1"),
        rmse=mp.mpf("2"),
        residuals=[mp.mpf("1"), mp.mpf("-2")],
        fitted_curve=[mp.mpf("0"), mp.mpf("0")],
        covariance=[[mp.mpf("4"), mp.mpf("6")], [mp.mpf("6"), mp.mpf("9")]],
        param_errors_stat={"A": mp.mpf("2"), "B": mp.mpf("3")},
        param_errors_sys={},
        param_errors_total={"A": mp.mpf("2"), "B": mp.mpf("3")},
        details={"dof": 2, "covariance_parameters": ["A", "B"]},
    )
    attach_fit_diagnostics(fit_result, sigma_series=[mp.mpf("2"), mp.mpf("4")])

    class FakeService:
        def submit(self, request):
            return SimpleNamespace(
                status=ResultStatus.SUCCEEDED,
                payload={
                    "fit_result": serialize_fit_result(fit_result, 30),
                    "expression": "A*x + B",
                    "warnings": [],
                },
                warnings=[],
            )

    captured = {}

    def fake_render(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return b"\x89PNG\r\n\x1a\nweb-fit"

    monkeypatch.setattr(fit_logic, "create_core_session_service", lambda: FakeService(), raising=False)
    monkeypatch.setattr(fit_logic, "render_fitting_overview", fake_render)

    result = fit_logic._run_fit(
        "x y sigma\n"
        "0 1 2\n"
        "1 3 4\n",
        {
            "fit_mode": "polynomial",
            "fit_poly_degree": "1",
            "fit_mp_precision": "80",
            "fit_generate_plots": "1",
            "fit_use_weights": "1",
            "fit_sigma_col": "sigma",
        },
    )

    assert result.plot_b64 is not None
    assert captured["kwargs"]["diagnostics"]["parameter_correlation"]["parameters"] == ["A", "B"]
    assert captured["kwargs"]["covariance"] == [[mp.mpf("4"), mp.mpf("6")], [mp.mpf("6"), mp.mpf("9")]]


def test_run_fit_latex_handles_nonfinite_diagnostics(monkeypatch) -> None:
    from datalab_core.results import ResultStatus
    from fitting.diagnostics import attach_fit_diagnostics
    from fitting.hp_fitter import FitResult
    from shared.fitting_engine import serialize_fit_result

    import app_web.logic.fitting as fit_logic

    fit_result = FitResult(
        params={"A": mp.mpf("1"), "B": mp.mpf("2")},
        param_errors={"A": mp.mpf("0"), "B": mp.mpf("3")},
        chi2=mp.mpf("1"),
        reduced_chi2=mp.mpf("0"),
        aic=mp.mpf("0"),
        bic=mp.mpf("0"),
        r2=mp.mpf("1"),
        rmse=mp.mpf("0"),
        residuals=[mp.mpf("1"), mp.mpf("-1")],
        fitted_curve=[mp.mpf("0"), mp.mpf("0")],
        covariance=[[mp.nan, mp.nan], [mp.nan, mp.mpf("9")]],
        param_errors_stat={"A": mp.mpf("0"), "B": mp.mpf("3")},
        param_errors_sys={},
        param_errors_total={"A": mp.mpf("0"), "B": mp.mpf("3")},
        details={"dof": 0, "covariance_parameters": ["A", "B"]},
    )
    attach_fit_diagnostics(fit_result)

    class FakeService:
        def submit(self, request):
            return SimpleNamespace(
                status=ResultStatus.SUCCEEDED,
                payload={
                    "fit_result": serialize_fit_result(fit_result, 30),
                    "expression": "A*x + B",
                    "warnings": [],
                },
                warnings=[],
            )

    monkeypatch.setattr(fit_logic, "create_core_session_service", lambda: FakeService(), raising=False)

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
            "fit_use_dcolumn": "1",
        },
    )

    assert "Fitting Diagnostics" in result.latex_text
    assert "$\\chi^2$ p-value" in result.latex_text
    assert "Corr A,A" in result.latex_text
    assert "Normalized residual 1" in result.latex_text
    assert r"\multicolumn{1}{c}{Unavailable}" in result.latex_text


def test_run_fit_comparison_mode_returns_shared_summary_csv_and_latex() -> None:
    from app_web.logic.fitting import _run_fit
    from fitting.comparison_formatting import COMPARISON_TABLE_HEADERS

    result = _run_fit(
        "x y\n"
        "0 1\n"
        "1 3\n"
        "2 5\n"
        "3 7\n",
        {
            "fit_mode": "comparison",
            "fit_comparison_candidates": json.dumps(
                [
                    {
                        "candidate_id": "linear",
                        "label": "Linear",
                        "model_type": "polynomial",
                        "poly_degree": 1,
                    },
                    {
                        "candidate_id": "quadratic",
                        "label": "Quadratic",
                        "model_type": "polynomial",
                        "poly_degree": 2,
                    },
                ]
            ),
            "fit_mp_precision": "60",
            "fit_result_digits": "2",
            "fit_use_dcolumn": "1",
        },
    )

    assert result.best_label == "Selected fit comparison"
    assert result.params == []
    assert result.metrics == {}
    assert [row["candidate_id"] for row in result.comparison_rows] == ["linear", "quadratic"]
    assert result.plot_b64 is None
    assert "Selected Fit Comparison" in result.summary_text
    assert "Linear | success" in result.summary_text
    assert "Quadratic | success" in result.summary_text
    assert "winner" not in result.summary_text.lower()
    assert "best_model" not in result.summary_text
    assert result.csv_data is not None
    csv_rows = list(csv.DictReader(StringIO(result.csv_data)))
    assert csv_rows
    assert csv_rows[0].keys() == set(COMPARISON_TABLE_HEADERS)
    assert [row["candidate_id"] for row in csv_rows] == ["linear", "quadratic"]
    assert [row["status"] for row in csv_rows] == ["success", "success"]
    assert "Selected model comparison" in result.latex_text
    assert "Linear" in result.latex_text
    assert "Quadratic" in result.latex_text
    assert "winner" not in result.latex_text.lower()
    assert "best_model" not in result.latex_text


def test_run_fit_comparison_mode_requires_explicit_candidates() -> None:
    from app_web.logic.fitting import _run_fit

    with pytest.raises(ValueError, match="comparison candidates"):
        _run_fit(
            "x y\n"
            "0 1\n"
            "1 3\n",
            {
                "fit_mode": "comparison",
                "fit_mp_precision": "60",
            },
        )
