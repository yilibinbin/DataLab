from __future__ import annotations

import shutil

import pytest
from mpmath import mp

from app_web.latex_security import compile_latex_safe
from data_extrapolation_latex_latest import (
    ExtrapolationOptions,
    apply_formula_to_data,
    generate_error_propagation_table,
    generate_latex_table,
    parse_uncertainty_format,
    process_data_string,
)
from statistics_utils import compute_statistics, generate_statistics_latex


def _pick_tex_engine() -> str | None:
    for engine in ("pdflatex", "xelatex", "lualatex"):
        if shutil.which(engine):
            return engine
    return None


def _pick_tex_engines() -> list[str]:
    return [
        engine
        for engine in ("pdflatex", "xelatex", "lualatex")
        if shutil.which(engine)
    ]


def _compile_or_fail(tex_text: str, engine: str, label: str) -> bytes:
    warnings: list[str] = []
    pdf = compile_latex_safe(tex_text, engine, warnings, label)
    assert pdf is not None, f"LaTeX compile failed ({label}): {warnings}"
    assert pdf.startswith(b"%PDF"), f"Unexpected PDF header for {label}"
    return pdf


def test_latex_compile_e2e(tmp_path):
    engine = _pick_tex_engine()
    if not engine:
        pytest.skip("No TeX engine found (pdflatex/xelatex/lualatex).")

    # Extrapolation LaTeX
    data_text = "A B C\n1 2 3\n2 3 4\n"
    opts = ExtrapolationOptions(mp_precision=60)
    headers, rows, results = process_data_string(data_text, verbose=False, options=opts)
    extrap_tex_path = tmp_path / "extrapolation.tex"
    generate_latex_table(
        headers,
        rows,
        results,
        str(extrap_tex_path),
        caption="Extrapolation",
        precision=10,
        verbose=False,
        use_dcolumn=False,
        latex_group_size=3,
    )
    _compile_or_fail(extrap_tex_path.read_text(encoding="utf-8"), engine, "extrapolation")

    # Error propagation LaTeX
    err_headers = ["x", "y"]
    parsed_data = [
        [
            parse_uncertainty_format("1.0(1)", lang="zh"),
            parse_uncertainty_format("2.0(2)", lang="zh"),
        ]
    ]
    err_results = apply_formula_to_data(
        err_headers,
        parsed_data,
        {},
        "x + y",
        verbose=False,
        return_components=True,
    )
    err_tex_path = tmp_path / "error_propagation.tex"
    generate_error_propagation_table(
        err_headers,
        parsed_data,
        err_results,
        {},
        "x + y",
        str(err_tex_path),
        caption="Error propagation",
        verbose=False,
        use_dcolumn=False,
        precision=10,
        latex_group_size=3,
    )
    _compile_or_fail(err_tex_path.read_text(encoding="utf-8"), engine, "error")

    # Statistics LaTeX
    values = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3")]
    sigmas = [mp.mpf("0.1"), mp.mpf("0.2"), mp.mpf("0.1")]
    stats_result = compute_statistics(values, sigmas, "weighted", use_sample=True, use_weighted_variance=True)
    data_rows = [(v,) for v in values]
    sigma_rows = [(s,) for s in sigmas]
    stats_tex_path = tmp_path / "statistics.tex"
    generate_statistics_latex(
        "X",
        data_rows,
        sigma_rows,
        stats_result,
        digits=10,
        tex_path=str(stats_tex_path),
        use_dcolumn=False,
        caption="Statistics",
        latex_group_size=3,
    )
    _compile_or_fail(stats_tex_path.read_text(encoding="utf-8"), engine, "statistics")

    # Fitting LaTeX (via web helper)
    from app_web.logic import _generate_fitting_latex

    fitting_tex_text = _generate_fitting_latex(
        best_label="A*x + B",
        params=[
            {"name": "A", "value_raw": mp.mpf("1.23"), "uncertainty_raw": mp.mpf("0.01")},
            {"name": "B", "value_raw": mp.mpf("0.5"), "uncertainty_raw": mp.mpf("0.02")},
        ],
        metrics={
            "chi2": "1.0",
            "reduced_chi2": "1.0",
            "aic": "0.0",
            "bic": "0.0",
            "r2": "0.9",
            "rmse": "0.1",
        },
        use_dcolumn=False,
        caption="Fitting",
        latex_precision=8,
        latex_group_size=3,
        uncertainty_digits=None,
    )
    _compile_or_fail(fitting_tex_text, engine, "fitting")


def test_statistics_latex_zero_sigma_diagnostics_compile_dcolumn_and_siunitx(tmp_path):
    engine = _pick_tex_engine()
    if not engine:
        pytest.skip("No TeX engine found (pdflatex/xelatex/lualatex).")

    values = [mp.mpf("1.25"), mp.mpf("2.5")]
    sigmas = [mp.mpf("0"), mp.mpf("0.1")]
    stats_result = compute_statistics(values, sigmas, "weighted_sigma", use_sample=True, use_weighted_variance=True)
    data_rows = [(value,) for value in values]
    sigma_rows = [(sigma,) for sigma in sigmas]

    for use_dcolumn in (False, True):
        tex_path = tmp_path / f"statistics-zero-sigma-{'dcolumn' if use_dcolumn else 'siunitx'}.tex"
        generate_statistics_latex(
            "X",
            data_rows,
            sigma_rows,
            stats_result,
            digits=10,
            tex_path=str(tex_path),
            use_dcolumn=use_dcolumn,
            caption="Statistics",
            latex_group_size=0,
        )
        tex_text = tex_path.read_text(encoding="utf-8")

        assert "Detected" in tex_text
        assert "statistics.warning.zero" not in tex_text
        _compile_or_fail(tex_text, engine, f"statistics-zero-sigma-{use_dcolumn}")


def test_statistics_latex_options_compile_with_all_discovered_local_engines(tmp_path):
    engines = _pick_tex_engines()
    if not engines:
        pytest.skip("No TeX engine found (pdflatex/xelatex/lualatex).")

    values = [mp.mpf("1.25"), mp.mpf("2.5")]
    sigmas = [mp.mpf("0"), mp.mpf("0.1")]
    stats_result = compute_statistics(
        values,
        sigmas,
        "weighted_sigma",
        use_sample=True,
        use_weighted_variance=True,
    )
    data_rows = [(value,) for value in values]
    sigma_rows = [(sigma,) for sigma in sigmas]

    for engine in engines:
        for use_dcolumn in (False, True):
            for latex_group_size in (0, 4):
                captions = ("English caption",)
                if engine == "xelatex":
                    captions = ("English caption", "中文标题")
                for caption in captions:
                    tex_path = tmp_path / (
                        f"statistics-{engine}-{use_dcolumn}-"
                        f"{latex_group_size}-{caption}.tex"
                    )
                    generate_statistics_latex(
                        "X",
                        data_rows,
                        sigma_rows,
                        stats_result,
                        digits=10,
                        tex_path=str(tex_path),
                        use_dcolumn=use_dcolumn,
                        caption=caption,
                        latex_group_size=latex_group_size,
                    )
                    tex_text = tex_path.read_text(encoding="utf-8")

                    if not use_dcolumn:
                        if latex_group_size == 0:
                            assert "group-digits = false" in tex_text
                        else:
                            assert (
                                f"group-minimum-digits = {latex_group_size}"
                                in tex_text
                            )
                    assert caption in tex_text
                    assert "Detected" in tex_text
                    assert "statistics.warning.zero" not in tex_text
                    _compile_or_fail(
                        tex_text,
                        engine,
                        f"statistics-options-{engine}-{use_dcolumn}-"
                        f"{latex_group_size}-{caption}",
                    )
