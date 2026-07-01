from __future__ import annotations

import pytest
from mpmath import mp


def _sample_rows() -> tuple[list[str], list[tuple[mp.mpf, ...]], list[tuple[mp.mpf, mp.mpf]]]:
    return (
        ["A", "B", "C"],
        [(mp.mpf("1"), mp.mpf("2"), mp.mpf("3"))],
        [(mp.mpf("4"), mp.mpf("0.1"))],
    )


def test_render_extrapolation_latex_adds_custom_formula_summary() -> None:
    from app_web.logic.extrapolation import _render_latex

    headers, rows, results = _sample_rows()
    tex = _render_latex(
        headers,
        rows,
        results,
        caption="Extrapolation",
        latex_precision=8,
        latex_group_size=3,
        use_dcolumn=False,
        result_digits=2,
        formula_summary="d0 + d2/(n-delta)^2",
    )

    expected = r"Formula: $d_{0} + \frac{d_{2}}{(n-\delta)^{2}}$"
    assert expected in tex
    assert tex.index(expected) < tex.index(r"\begin{table}")


def test_render_extrapolation_latex_skips_empty_custom_formula_summary() -> None:
    from app_web.logic.extrapolation import _render_latex

    headers, rows, results = _sample_rows()
    tex = _render_latex(
        headers,
        rows,
        results,
        caption=None,
        latex_precision=8,
        latex_group_size=3,
        use_dcolumn=False,
        result_digits=2,
        formula_summary="  ",
    )

    assert "Formula:" not in tex


def test_insert_extrapolation_formula_summary_requires_stable_anchor() -> None:
    from app_web.logic.extrapolation import _insert_formula_summary

    with pytest.raises(ValueError, match="formula summary"):
        _insert_formula_summary("\\documentclass{article}", "Formula: $x$")


def test_run_extrapolation_threads_custom_formula_to_latex(monkeypatch) -> None:
    import app_web.logic.extrapolation as extrap_logic

    captured: dict[str, object] = {}

    def fake_render_latex(*args: object, **kwargs: object) -> str:
        captured["formula_summary"] = kwargs.get("formula_summary", "missing")
        return "LATEX_FROM_FAKE"

    monkeypatch.setattr(extrap_logic, "_render_latex", fake_render_latex)

    formula = "(C - B)^2/(B - A) + C"
    result = extrap_logic._run_extrapolation(
        "A B C\n1 2 3\n2 3 4\n",
        {
            "method": "custom",
            "custom_formula": formula,
            "mp_precision": "60",
        },
        lang="en",
    )

    assert captured["formula_summary"] == formula
    assert result.latex_text == "LATEX_FROM_FAKE"


def test_run_extrapolation_does_not_thread_formula_for_non_custom_method(monkeypatch) -> None:
    import app_web.logic.extrapolation as extrap_logic

    captured: dict[str, object] = {}

    def fake_render_latex(*args: object, **kwargs: object) -> str:
        captured["formula_summary"] = kwargs.get("formula_summary", "missing")
        return "LATEX_FROM_FAKE"

    monkeypatch.setattr(extrap_logic, "_render_latex", fake_render_latex)

    extrap_logic._run_extrapolation(
        "A B C\n1 2 3\n2 3 4\n",
        {
            "method": "quadratic",
            "custom_formula": "(C - B)^2/(B - A) + C",
            "mp_precision": "60",
        },
        lang="en",
    )

    assert captured["formula_summary"] is None
