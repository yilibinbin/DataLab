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
