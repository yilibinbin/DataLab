from __future__ import annotations

import mpmath as mp

from app_desktop import fitting_latex_writer as writer
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
    text = "\n".join(writer.build_fit_latex_preamble(use_dcolumn=False, digits=16, latex_group_size=4))
    assert "\\usepackage{siunitx}" in text
    # ``digit-group-size`` is siunitx-v3 only; the helper wraps it in
    # an ``\@ifpackagelater`` guard pinned to siunitx 3.0's release
    # date (2020-02-08) so v2 installs fall back to the built-in
    # default rather than erroring out. The v2/v3-safe key that
    # gates WHEN grouping kicks in is ``group-minimum-digits``.
    assert "digit-group-size = 4" in text
    assert "@ifpackagelater" in text
    assert "group-minimum-digits = 4" in text
    assert "\\usepackage{dcolumn}" not in text

    text_dcolumn = "\n".join(writer.build_fit_latex_preamble(use_dcolumn=True, digits=16, latex_group_size=4))
    assert "\\usepackage{dcolumn}" in text_dcolumn
    assert "\\newcolumntype{d}[1]{D{.}{.}{#1}}" in text_dcolumn
    # dcolumn branch: no grouping at all
    assert "digit-group-size" not in text_dcolumn


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
