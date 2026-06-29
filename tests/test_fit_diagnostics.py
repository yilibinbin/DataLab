from __future__ import annotations

import mpmath as mp

from fitting.diagnostics import (
    attach_fit_diagnostics,
    chi_square_p_value,
    fit_diagnostic_warnings,
    fit_diagnostics,
    parameter_correlation_matrix,
    standardized_residuals,
)
from fitting.diagnostic_formatting import (
    build_fitting_diagnostic_csv_rows,
    build_fitting_diagnostic_latex_entries,
    fitting_diagnostic_view,
    safe_latex_diagnostic_value,
)
from fitting.hp_fitter import FitResult


def _fit_result(
    *,
    residuals: list[mp.mpf] | None = None,
    rmse: mp.mpf = mp.mpf("1"),
    covariance: list[list[mp.mpf]] | None = None,
    stat_errors: dict[str, mp.mpf] | None = None,
    details: dict[str, object] | None = None,
) -> FitResult:
    params = {"a": mp.mpf("1"), "b": mp.mpf("2")}
    return FitResult(
        params=params,
        param_errors=stat_errors or {"a": mp.mpf("0"), "b": mp.mpf("0")},
        chi2=mp.mpf("4.6051701859880913680359829093687284152022029772575"),
        reduced_chi2=mp.mpf("2.3025850929940456840179914546843642076011014886288"),
        aic=mp.mpf("0"),
        bic=mp.mpf("0"),
        r2=mp.mpf("1"),
        rmse=rmse,
        residuals=residuals or [mp.mpf("1"), mp.mpf("-2")],
        fitted_curve=[],
        covariance=covariance or [[mp.mpf("4"), mp.mpf("10")], [mp.mpf("10"), mp.mpf("9")]],
        param_errors_stat=stat_errors or {"a": mp.mpf("2"), "b": mp.mpf("3")},
        param_errors_sys={},
        param_errors_total=stat_errors or {"a": mp.mpf("2"), "b": mp.mpf("3")},
        details=details or {"dof": 2, "covariance_parameters": ["a", "b"]},
    )


def test_chi_square_p_value_uses_upper_tail_survival_probability() -> None:
    assert chi_square_p_value(mp.mpf("0"), 2) == mp.mpf("1")

    p_value = chi_square_p_value(
        mp.mpf("4.6051701859880913680359829093687284152022029772575"),
        2,
        precision=80,
    )

    assert mp.almosteq(p_value, mp.mpf("0.1"), rel_eps=mp.mpf("1e-14"))


def test_chi_square_p_value_invalid_inputs_return_nan() -> None:
    for chi2, dof in ((mp.inf, 2), (mp.mpf("-1"), 2), (mp.mpf("1"), 0)):
        assert mp.isnan(chi_square_p_value(chi2, dof))


def test_parameter_correlation_bounds_diagonal_and_warns_for_invalid_cells() -> None:
    fit = _fit_result(
        covariance=[
            [mp.mpf("4"), mp.mpf("10")],
            [mp.nan, mp.mpf("9")],
        ],
        stat_errors={"a": mp.mpf("2"), "b": mp.mpf("3")},
    )

    correlation, warnings = parameter_correlation_matrix(fit)

    matrix = correlation["matrix"]
    assert matrix[0][0] == mp.mpf("1")
    assert matrix[0][1] == mp.mpf("1")
    assert mp.isnan(matrix[1][0])
    assert matrix[1][1] == mp.mpf("1")
    assert any("a,b" in warning or "b,a" in warning for warning in warnings)


def test_parameter_correlation_zero_error_produces_nan_warning() -> None:
    fit = _fit_result(stat_errors={"a": mp.mpf("0"), "b": mp.mpf("3")})

    correlation, warnings = parameter_correlation_matrix(fit)

    assert mp.isnan(correlation["matrix"][0][0])
    assert mp.isnan(correlation["matrix"][0][1])
    assert warnings


def test_standardized_residuals_use_sigma_weight_or_rmse_paths() -> None:
    fit = _fit_result(residuals=[mp.mpf("1"), mp.mpf("-2")], rmse=mp.mpf("2"))

    sigma_result, sigma_warnings = standardized_residuals(
        fit,
        sigma_series=[mp.mpf("2"), mp.mpf("4")],
    )
    assert sigma_result["method"] == "sigma"
    assert sigma_result["values"] == [mp.mpf("0.5"), mp.mpf("-0.5")]
    assert sigma_result["max_abs"] == mp.mpf("0.5")
    assert not sigma_warnings

    weight_result, _ = standardized_residuals(
        fit,
        weights=[mp.mpf("4"), mp.mpf("9")],
    )
    assert weight_result["method"] == "weight"
    assert weight_result["values"] == [mp.mpf("2"), mp.mpf("-6")]
    assert weight_result["max_abs"] == mp.mpf("6")

    normalized_result, _ = standardized_residuals(fit)
    assert normalized_result["method"] == "normalized"
    assert normalized_result["label"] == "Normalized residual"
    assert normalized_result["values"] == [mp.mpf("0.5"), mp.mpf("-1")]


def test_attach_fit_diagnostics_stores_json_safe_serializable_shape() -> None:
    fit = _fit_result()

    warnings = attach_fit_diagnostics(
        fit,
        sigma_series=[mp.mpf("2"), mp.mpf("4")],
        precision=80,
    )

    diagnostics = fit_diagnostics(fit)
    assert mp.almosteq(diagnostics["chi_square_p_value"], mp.mpf("0.1"), rel_eps=mp.mpf("1e-14"))
    assert diagnostics["parameter_correlation"]["parameters"] == ["a", "b"]
    assert diagnostics["residuals"]["method"] == "sigma"
    assert warnings == ()


def test_attach_fit_diagnostics_replaces_stale_warning_state() -> None:
    fit = _fit_result(stat_errors={"a": mp.mpf("0"), "b": mp.mpf("3")})

    first_warnings = attach_fit_diagnostics(fit)
    assert first_warnings
    assert fit_diagnostic_warnings(fit)

    fit.param_errors = {"a": mp.mpf("2"), "b": mp.mpf("3")}
    fit.param_errors_stat = {"a": mp.mpf("2"), "b": mp.mpf("3")}
    fit.param_errors_total = {"a": mp.mpf("2"), "b": mp.mpf("3")}
    second_warnings = attach_fit_diagnostics(fit, sigma_series=[mp.mpf("2"), mp.mpf("4")])

    assert second_warnings == ()
    assert fit_diagnostic_warnings(fit) == ()
    assert "diagnostic_warnings" not in fit.details


def test_shared_diagnostic_formatters_build_csv_and_latex_rows() -> None:
    fit = _fit_result(covariance=[[mp.mpf("4"), mp.mpf("6")], [mp.mpf("6"), mp.mpf("9")]])
    attach_fit_diagnostics(fit, sigma_series=[mp.mpf("2"), mp.mpf("4")])

    view = fitting_diagnostic_view(fit)
    csv_rows = build_fitting_diagnostic_csv_rows(
        fit,
        batch=3,
        format_value=lambda value: mp.nstr(value, 8),
    )
    latex_entries, latex_warnings = build_fitting_diagnostic_latex_entries(
        fit,
        format_value=lambda value: f"LATEX({mp.nstr(value, 8)})",
        escape_text=lambda text: text.replace("_", r"\_"),
    )

    assert [metric.key for metric in view.metrics] == [
        "chi_square_p_value",
        "max_standardized_residual",
    ]
    by_name = {str(row["name"]): row for row in csv_rows}
    assert by_name["chi_square_p_value"]["section"] == "metric"
    assert by_name["max_standardized_residual"]["note"] == "Sigma-standardized residual"
    assert by_name["corr[a,b]"]["section"] == "correlation"
    assert by_name["standardized_residual[1]"]["section"] == "residual_diagnostic"
    assert ("Corr a,b", "LATEX(1.0)") in latex_entries
    assert ("Sigma-standardized residual 1", "LATEX(0.5)") in latex_entries
    assert not latex_warnings


def test_shared_latex_diagnostic_formatter_handles_nonfinite_values() -> None:
    assert safe_latex_diagnostic_value(mp.nan, lambda value: "SHOULD_NOT_CALL") == r"\multicolumn{1}{c}{Unavailable}"
    assert safe_latex_diagnostic_value(mp.inf, lambda value: "SHOULD_NOT_CALL") == r"\multicolumn{1}{c}{Unavailable}"

    fit = _fit_result(stat_errors={"a": mp.mpf("0"), "b": mp.mpf("3")}, details={"dof": 0, "covariance_parameters": ["a", "b"]})
    attach_fit_diagnostics(fit)
    latex_entries, latex_warnings = build_fitting_diagnostic_latex_entries(
        fit,
        format_value=lambda value: f"FINITE({value})",
    )

    assert ("$\\chi^2$ p-value", r"\multicolumn{1}{c}{Unavailable}") in latex_entries
    assert ("Corr a,a", r"\multicolumn{1}{c}{Unavailable}") in latex_entries
    assert latex_warnings


def test_core_fitting_payload_serializes_attached_diagnostics() -> None:
    from datalab_core.fitting import build_fitting_request, fitting_payload_to_fit_result, run_fitting
    from datalab_core.results import ResultStatus

    request = build_fitting_request(
        model_type="polynomial",
        headers=("x", "y", "sigma"),
        data_rows=(
            (mp.mpf("0"), mp.mpf("1.0"), mp.mpf("1")),
            (mp.mpf("1"), mp.mpf("3.2"), mp.mpf("1")),
            (mp.mpf("2"), mp.mpf("4.8"), mp.mpf("1")),
            (mp.mpf("3"), mp.mpf("7.1"), mp.mpf("1")),
        ),
        variable_map={"x": "x"},
        target_column="y",
        sigma_series=(mp.mpf("1"), mp.mpf("1"), mp.mpf("1"), mp.mpf("1")),
        weighted=True,
        poly_degree=1,
        precision_digits=80,
        request_id="fit-diagnostics-core",
    )

    envelope = run_fitting(request)
    fit_result = fitting_payload_to_fit_result(envelope.payload["fit_result"])
    diagnostics = fit_diagnostics(fit_result)

    assert envelope.status is ResultStatus.SUCCEEDED
    assert "chi_square_p_value" in diagnostics
    assert diagnostics["residuals"]["method"] == "sigma"
    assert len(diagnostics["residuals"]["values"]) == 4
    assert diagnostics["parameter_correlation"]["parameters"] == ["b0", "b1"]
