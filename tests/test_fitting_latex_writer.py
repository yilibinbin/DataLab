from __future__ import annotations

import mpmath as mp

from app_desktop import fitting_latex_writer as writer
from fitting.diagnostics import attach_fit_diagnostics
from fitting.hp_fitter import FitResult


def _sample_fit_result() -> FitResult:
    return FitResult(
        params={"A": mp.mpf("1.5")},
        param_errors={"A": mp.mpf("0.1")},
        chi2=mp.mpf("1.0"),
        reduced_chi2=mp.mpf("1.0"),
        aic=mp.mpf("1.0"),
        bic=mp.mpf("1.0"),
        r2=mp.mpf("0.9"),
        rmse=mp.mpf("0.01"),
        residuals=[mp.mpf("0.0")],
        fitted_curve=[mp.mpf("0.0")],
        covariance=[[mp.mpf("0.01")]],
        param_errors_total={"A": mp.mpf("0.1")},
    )


def test_build_fit_latex_preamble_includes_expected_packages():
    # native_group_width True (default) → the app probed the engine as capable, so
    # digit-group-size is emitted UNGUARDED (the probe replaces the old \@ifpackagelater
    # date heuristic). group-minimum-digits gates WHEN grouping kicks in.
    text = "\n".join(writer.build_fit_latex_preamble(use_dcolumn=False, digits=16, latex_group_size=4))
    assert "\\usepackage{siunitx}" in text
    assert "digit-group-size = 4" in text
    assert "@ifpackagelater" not in text
    assert "group-minimum-digits = 4" in text
    assert "\\usepackage{dcolumn}" not in text

    # native_group_width False (bundled Tectonic can't vary the width) → never emit
    # digit-group-size; the writer pre-groups the cells app-side instead.
    text_bundled = "\n".join(
        writer.build_fit_latex_preamble(
            use_dcolumn=False, digits=16, latex_group_size=4, native_group_width=False
        )
    )
    assert "digit-group-size" not in text_bundled
    assert "@ifpackagelater" not in text_bundled

    text_dcolumn = "\n".join(writer.build_fit_latex_preamble(use_dcolumn=True, digits=16, latex_group_size=4))
    assert "\\usepackage{dcolumn}" in text_dcolumn
    assert "\\newcolumntype{d}[1]{D{.}{.}{#1}}" in text_dcolumn
    # dcolumn branch: no grouping at all
    assert "digit-group-size" not in text_dcolumn


def test_group_size_zero_disables_fitting_grouping():
    # F1 (dual-model review): the UI says group size 0 = 不分组. The preamble previously
    # coerced 0→1 (max(1,..)) so grouping stayed ON. It must now emit the "no grouping" body.
    text = "\n".join(writer.build_fit_latex_preamble(use_dcolumn=False, digits=16, latex_group_size=0))
    assert "group-digits = false" in text
    assert "digit-group-size" not in text
    assert "group-minimum-digits" not in text


def test_build_fit_latex_block_generates_siunitx_column_spec():
    fit_result = _sample_fit_result()
    lines = writer.build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf("1.0"), mp.mpf("2.0"))],
        sigma_rows=[(None, None)],
        fit_result=fit_result,
        expression="A*x",
        substituted="1.5*x",
        image_path=None,
        use_dcolumn=False,
        digits=6,
        latex_group_size=3,
        batch_index=None,
        target_column="y",
        variable_pairs=[("x", "x")],
        caption_text="Fit results",
        default_uncertainty_digits=1,
        cleaned_substituted="1.5*x",
    )

    assert any("Model: $" in line for line in lines)
    assert any("With params: $" in line for line in lines)
    assert any(line.startswith("Param A &") for line in lines)
    assert any("\\begin{tabular}{l S[table-format=" in line for line in lines)


def test_build_fit_latex_block_adds_text_only_unit_column_when_units_present():
    fit_result = _sample_fit_result()
    lines = writer.build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf("1.0"), mp.mpf("2.0"))],
        sigma_rows=[(None, None)],
        fit_result=fit_result,
        expression="A*x",
        substituted="1.5*x",
        image_path=None,
        use_dcolumn=True,
        digits=6,
        latex_group_size=3,
        batch_index=None,
        target_column="y",
        variable_pairs=[("x", "x")],
        caption_text="Fit results",
        default_uncertainty_digits=1,
        cleaned_substituted="1.5*x",
        units={
            "parameters": {"A": {"unit": "m/s"}},
            "outputs": {"y": {"unit": "J"}},
        },
    )

    text = "\n".join(lines)
    assert "\\begin{tabular}{l l d{" in text
    assert "Entry & Unit & \\multicolumn{1}{c}{Value}" in text
    assert "(x=1.0) & J &" in text
    assert "Param A & m/s &" in text
    assert "RMSE & J &" in text


def test_build_fit_latex_block_generates_dcolumn_column_spec_and_batch_header():
    fit_result = _sample_fit_result()
    lines = writer.build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf("1.0"), mp.mpf("2.0"))],
        sigma_rows=[(None, None)],
        fit_result=fit_result,
        expression="A*x",
        substituted="1.5*x",
        image_path=None,
        use_dcolumn=True,
        digits=6,
        latex_group_size=3,
        batch_index=3,
        target_column="y",
        variable_pairs=[("x", "x")],
        caption_text="Fit results",
        default_uncertainty_digits=1,
        cleaned_substituted="1.5*x",
    )

    assert any("\\subsection*{Fit Results: Batch 3}" in line for line in lines)
    assert any("\\begin{tabular}{l d{" in line for line in lines)


def test_build_fit_latex_block_adds_stat_sys_rows_when_present():
    fit_result = _sample_fit_result()
    fit_result.param_errors_stat = {"A": mp.mpf("0.08")}
    fit_result.param_errors_sys = {"A": mp.mpf("0.05")}

    lines = writer.build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf("1.0"), mp.mpf("2.0"))],
        sigma_rows=[(None, None)],
        fit_result=fit_result,
        expression="A*x",
        substituted="1.5*x",
        image_path=None,
        use_dcolumn=False,
        digits=6,
        latex_group_size=3,
        batch_index=None,
        target_column="y",
        variable_pairs=[("x", "x")],
        caption_text="Fit results",
        default_uncertainty_digits=1,
        cleaned_substituted="1.5*x",
    )

    assert any(line.startswith("A stat &") for line in lines)
    assert any(line.startswith("A sys &") for line in lines)


def test_build_fit_latex_block_reads_sentinel_metrics_from_fit_result():
    fit_result = _sample_fit_result()
    fit_result.chi2 = mp.mpf("101")
    fit_result.reduced_chi2 = mp.mpf("202")
    fit_result.aic = mp.mpf("303")
    fit_result.bic = mp.mpf("404")
    fit_result.r2 = mp.mpf("0.505")
    fit_result.rmse = mp.mpf("0.606")

    lines = writer.build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf("1.0"), mp.mpf("2.0"))],
        sigma_rows=[(None, None)],
        fit_result=fit_result,
        expression="A*x",
        substituted="1.5*x",
        image_path=None,
        use_dcolumn=False,
        digits=6,
        latex_group_size=3,
        batch_index=None,
        target_column="y",
        variable_pairs=[("x", "x")],
        caption_text="Fit results",
        default_uncertainty_digits=1,
        cleaned_substituted="1.5*x",
    )

    text = "\n".join(lines)
    for value in ("101", "202", "303", "404", "0.505", "0.606"):
        assert value in text


def test_build_fit_latex_block_includes_attached_diagnostics():
    fit_result = FitResult(
        params={"A": mp.mpf("1"), "B": mp.mpf("2")},
        param_errors={"A": mp.mpf("2"), "B": mp.mpf("3")},
        chi2=mp.mpf("4.6051701859880913680359829093687284152022029772575"),
        reduced_chi2=mp.mpf("2.3025850929940456840179914546843642076011011014886288"),
        aic=mp.mpf("1.0"),
        bic=mp.mpf("1.0"),
        r2=mp.mpf("0.9"),
        rmse=mp.mpf("2"),
        residuals=[mp.mpf("1"), mp.mpf("-2")],
        fitted_curve=[mp.mpf("0"), mp.mpf("0")],
        covariance=[[mp.mpf("4"), mp.mpf("6")], [mp.mpf("6"), mp.mpf("9")]],
        param_errors_stat={"A": mp.mpf("2"), "B": mp.mpf("3")},
        param_errors_total={"A": mp.mpf("2"), "B": mp.mpf("3")},
        details={"dof": 2, "covariance_parameters": ["A", "B"]},
    )
    attach_fit_diagnostics(fit_result, sigma_series=[mp.mpf("2"), mp.mpf("4")])

    lines = writer.build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf("1.0"), mp.mpf("2.0"))],
        sigma_rows=[(None, None)],
        fit_result=fit_result,
        expression="A*x + B",
        substituted="1*x + 2",
        image_path=None,
        use_dcolumn=False,
        digits=6,
        latex_group_size=3,
        batch_index=None,
        target_column="y",
        variable_pairs=[("x", "x")],
        caption_text="Fit results",
        default_uncertainty_digits=1,
        cleaned_substituted="1*x + 2",
    )

    text = "\n".join(lines)
    assert "$\\chi^2$ p-value" in text
    assert "Max standardized residual" in text
    assert "Corr A,B" in text
    assert "Sigma-standardized residual 1" in text


def test_build_fit_latex_block_handles_nonfinite_diagnostics():
    fit_result = FitResult(
        params={"A": mp.mpf("1"), "B": mp.mpf("2")},
        param_errors={"A": mp.mpf("0"), "B": mp.mpf("3")},
        chi2=mp.mpf("1"),
        reduced_chi2=mp.mpf("0"),
        aic=mp.mpf("0"),
        bic=mp.mpf("0"),
        r2=mp.mpf("1"),
        rmse=mp.mpf("0"),
        residuals=[mp.mpf("0"), mp.mpf("0")],
        fitted_curve=[mp.mpf("0"), mp.mpf("0")],
        covariance=[[mp.nan, mp.nan], [mp.nan, mp.mpf("9")]],
        param_errors_stat={"A": mp.mpf("0"), "B": mp.mpf("3")},
        param_errors_total={"A": mp.mpf("0"), "B": mp.mpf("3")},
        details={"dof": 0, "covariance_parameters": ["A", "B"]},
    )
    attach_fit_diagnostics(fit_result)

    lines = writer.build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf("1.0"), mp.mpf("2.0"))],
        sigma_rows=[(None, None)],
        fit_result=fit_result,
        expression="A*x + B",
        substituted="1*x + 2",
        image_path=None,
        use_dcolumn=True,
        digits=6,
        latex_group_size=3,
        batch_index=None,
        target_column="y",
        variable_pairs=[("x", "x")],
        caption_text="Fit results",
        default_uncertainty_digits=1,
        cleaned_substituted="1*x + 2",
    )

    text = "\n".join(lines)
    assert "$\\chi^2$ p-value" in text
    assert "Corr A,A" in text
    assert r"\multicolumn{1}{c}{Unavailable}" in text


def test_build_fit_latex_block_tolerates_invalid_x_sigma_objects():
    fit_result = _sample_fit_result()
    lines = writer.build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf("1.0"), mp.mpf("2.0"))],
        sigma_rows=[("not-a-number", None)],
        fit_result=fit_result,
        expression="A*x",
        substituted="1.5*x",
        image_path=None,
        use_dcolumn=False,
        digits=6,
        latex_group_size=3,
        batch_index=None,
        target_column="y",
        variable_pairs=[("x", "x")],
        caption_text="Fit results",
        default_uncertainty_digits=1,
        cleaned_substituted="1.5*x",
    )

    assert any(line.startswith("(x=1.0) &") for line in lines)


def test_fit_latex_block_does_not_emit_automatic_fit_rankings():
    fit_result = _sample_fit_result()
    fit_result.details.update(
        {
            "optimizer_backend": "mpmath",
            "scipy_safety_passed": False,
            "seed_variants_tried": 1,
            "seed_variants_succeeded": 1,
        }
    )
    lines = writer.build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf("1.0"), mp.mpf("2.0"))],
        sigma_rows=[(None, None)],
        fit_result=fit_result,
        expression="A*x",
        substituted="1.5*x",
        image_path=None,
        use_dcolumn=False,
        digits=6,
        latex_group_size=3,
        batch_index=None,
        target_column="y",
        variable_pairs=[("x", "x")],
        caption_text="Fit results",
        default_uncertainty_digits=1,
        cleaned_substituted="1.5*x",
    )

    text = "\n".join(lines).lower()
    assert "solver:" in text
    assert "sciPy".lower() in text
    assert "automatic" not in text
    assert "auto-fit" not in text
    assert "ranking" not in text
    assert "best model" not in text
