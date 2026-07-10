"""Web-fitting `self_consistent` (implicit) mode wiring tests (task B4).

Reuses the known-recovery model from
``tests/test_implicit_model.py::test_runner_uses_singleton_output_inversion_seed_for_parameter_initials``:
implicit equation ``a*x`` (independent of the implicit variable ``u``), output
expression ``u + 1``. With ``a=2`` this yields ``y = 2*x + 1``, so the dataset
``x=1,2,3 -> y=3,5,7`` recovers ``a=2`` exactly.
"""

from __future__ import annotations

import mpmath as mp
import pytest

from app_web.logic.fitting import _run_fit

_DATA_TEXT = "x y\n1 3\n2 5\n3 7\n"


def test_run_fit_self_consistent_recovers_known_parameter() -> None:
    result = _run_fit(
        _DATA_TEXT,
        {
            "fit_mode": "self_consistent",
            "fit_implicit_equation": "a*x",
            "fit_implicit_variable": "u",
            "fit_implicit_output": "u + 1",
            "fit_implicit_params": '{"a": {"initial": "1"}}',
            "fit_mp_precision": "50",
            "fit_result_digits": "6",
        },
    )

    assert result.params
    assert result.metrics
    param_by_name = {p["name"]: p for p in result.params}
    assert "a" in param_by_name
    assert mp.almosteq(mp.mpf(str(param_by_name["a"]["value_raw"])), mp.mpf("2"), rel_eps=mp.mpf("1e-10"))
    assert result.best_label == "自洽隐式模型 / Self-consistent"


def test_run_fit_self_consistent_requires_equation() -> None:
    with pytest.raises(ValueError) as exc_info:
        _run_fit(
            _DATA_TEXT,
            {
                "fit_mode": "self_consistent",
                "fit_implicit_equation": "",
                "fit_implicit_variable": "u",
                "fit_implicit_output": "u + 1",
                "fit_mp_precision": "50",
            },
        )
    assert " / " in str(exc_info.value)


def test_run_fit_self_consistent_requires_output_expression() -> None:
    with pytest.raises(ValueError) as exc_info:
        _run_fit(
            _DATA_TEXT,
            {
                "fit_mode": "self_consistent",
                "fit_implicit_equation": "a*x",
                "fit_implicit_variable": "u",
                "fit_implicit_output": "",
                "fit_mp_precision": "50",
            },
        )
    assert " / " in str(exc_info.value)


def test_run_fit_self_consistent_requires_valid_identifier_for_implicit_variable() -> None:
    with pytest.raises(ValueError) as exc_info:
        _run_fit(
            _DATA_TEXT,
            {
                "fit_mode": "self_consistent",
                "fit_implicit_equation": "a*x",
                "fit_implicit_variable": "1bad",
                "fit_implicit_output": "u + 1",
                "fit_mp_precision": "50",
            },
        )
    assert " / " in str(exc_info.value)


def test_run_fit_self_consistent_non_dict_params_gives_single_bilingual_message() -> None:
    """CR-1 regression: a non-dict params JSON must raise ONE clean bilingual message.

    Previously the non-dict check was raised inside the JSON-parse try/except, so it
    was caught and re-wrapped, producing a doubled '汉语 / English / 汉语 / English'
    string that breaks the locale layer's single ' / ' split.
    """
    with pytest.raises(ValueError) as exc_info:
        _run_fit(
            _DATA_TEXT,
            {
                "fit_mode": "self_consistent",
                "fit_implicit_equation": "a*x",
                "fit_implicit_variable": "u",
                "fit_implicit_output": "u + 1",
                "fit_implicit_params": "[1, 2]",  # valid JSON, but not an object
                "fit_mp_precision": "50",
            },
        )
    # Exactly one ' / ' separator — not a nested/doubled message.
    assert str(exc_info.value).count(" / ") == 1


def test_run_fit_self_consistent_unused_param_reports_na_instead_of_crashing() -> None:
    """CX-1 regression: an unused parameter yields a non-finite (undefined) uncertainty.

    The implicit solver still converges on the real parameter, but the covariance is
    rank-deficient, so uncertainties come back NaN. _collect_params must render those
    as 'N/A' rather than letting the siunitx formatter raise a raw, non-bilingual
    'cannot convert inf or nan to int' and 500-crash the whole fit response.
    """
    result = _run_fit(
        _DATA_TEXT,
        {
            "fit_mode": "self_consistent",
            "fit_implicit_equation": "a*x",
            "fit_implicit_variable": "u",
            "fit_implicit_output": "u + 1",
            "fit_implicit_params": '{"z": {"initial": "1"}}',  # z never appears in the equation
            "fit_mp_precision": "50",
            "fit_result_digits": "6",
        },
    )
    assert result.params  # did not crash
    by_name = {p["name"]: p for p in result.params}
    assert "z" in by_name and "a" in by_name
    # The unused parameter's uncertainty is undefined → reported as N/A, not a crash.
    assert by_name["z"]["uncertainty"] == "N/A"
    # The real parameter value is still recovered correctly (a = 2 for y = 2x + 1).
    assert mp.almosteq(mp.mpf(str(by_name["a"]["value_raw"])), mp.mpf("2"), rel_eps=mp.mpf("1e-10"))
    # Round-2 R2-2: the CSV export and text summary must agree with the table —
    # an undefined sigma is "N/A" on every surface, never a bare "nan".
    csv_param_lines = [ln for ln in (result.csv_data or "").splitlines() if ",parameter," in ln]
    assert csv_param_lines and all(",N/A," in ln and ",nan," not in ln for ln in csv_param_lines)
    assert "± N/A" in result.summary_text
    assert "± nan" not in result.summary_text


def test_run_fit_self_consistent_zero_dof_survives_nan_metrics() -> None:
    """Round-2 R2-1 regression: dof=0 (2 points, 2 params) makes reduced χ²/AIC/BIC NaN.

    The LaTeX metrics branch used to re-parse 'nan' and crash in
    format_value_for_latex_file, discarding the whole successful fit behind a
    generic compute-failed flash. Non-finite metrics must now render as
    parse-safe literal cells while params/CSV/plot survive.
    """
    result = _run_fit(
        "x y\n1 3\n2 5\n",  # 2 points, 2 inferred params (z unused + a) → dof = 0
        {
            "fit_mode": "self_consistent",
            "fit_implicit_equation": "a*x",
            "fit_implicit_variable": "u",
            "fit_implicit_output": "u + 1",
            "fit_implicit_params": '{"z": {"initial": "1"}}',
            "fit_mp_precision": "50",
            "fit_result_digits": "6",
        },
    )
    by_name = {p["name"]: p for p in result.params}
    assert mp.almosteq(mp.mpf(str(by_name["a"]["value_raw"])), mp.mpf("2"), rel_eps=mp.mpf("1e-10"))
    # NaN metrics render as parse-safe literal cells in the LaTeX metrics table.
    assert "\\multicolumn{1}{c}{nan}" in result.latex_text
