"""Round-2 review regressions: R2-3 (statistics double-wrap) + R2-4 (desktop writer NaN).

R2-3: _parse_stats_data's 'uncertainty is not finite' bilingual ValueError used to be
raised inside the two-column parse try and re-wrapped by its except Exception,
yielding a doubled '汉语 / English / 汉语 / English' message (CR-1 pattern).

R2-4: the desktop fit LaTeX writer feeds FitResult.param_errors_total into
format_value_for_latex_file; a self_consistent fit with degenerate covariance
(NaN sigmas, e.g. an unused parameter) used to crash LaTeX export with a raw
'cannot convert inf or nan to int' in both siunitx and dcolumn modes.
"""

from __future__ import annotations

import pytest
from mpmath import mp

from app_web.logic.statistics import _parse_stats_data
from fitting import FitRunner, ImplicitModelDefinition, ModelProblem


def test_stats_nonfinite_sigma_gives_single_bilingual_message() -> None:
    with pytest.raises(ValueError) as exc_info:
        _parse_stats_data("v s\n1.0 nan\n")
    assert str(exc_info.value).count(" / ") == 1


def _degenerate_self_consistent_fit():
    definition = ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a*x",
        output_expression="u + 1",
        parameters=("z", "a"),  # z never appears in the equation → NaN sigmas
    )
    problem = ModelProblem(
        model_type="self_consistent",
        expression="u + 1",
        variables=("x",),
        parameter_config={"z": {"initial": "1"}},
        implicit_definition=definition,
    )
    return FitRunner().fit(
        problem,
        {"x": [mp.mpf(1), mp.mpf(2), mp.mpf(3)]},
        [mp.mpf(3), mp.mpf(5), mp.mpf(7)],
        precision=50,
    )


@pytest.mark.parametrize("use_dcolumn", [False, True])
def test_desktop_fit_latex_block_survives_nan_sigmas(use_dcolumn: bool) -> None:
    fit_result = _degenerate_self_consistent_fit()
    assert any(not mp.isfinite(v) for v in fit_result.param_errors_total.values())

    from app_desktop.fitting_latex_writer import build_fit_latex_block

    lines = build_fit_latex_block(
        headers=["x", "y"],
        rows=[(mp.mpf(1), mp.mpf(3)), (mp.mpf(2), mp.mpf(5)), (mp.mpf(3), mp.mpf(7))],
        sigma_rows=[],
        fit_result=fit_result,
        expression="u + 1",
        substituted="",
        image_path=None,
        use_dcolumn=use_dcolumn,
        digits=6,
        target_column="y",
    )
    assert lines  # produced a table instead of raising
    text = "\n".join(lines)
    # The recovered parameter values are present; the NaN sigmas degraded gracefully.
    assert "Param a" in text and "Param z" in text
