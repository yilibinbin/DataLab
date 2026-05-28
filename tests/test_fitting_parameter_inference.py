from __future__ import annotations

import pytest

from fitting import infer_parameter_names
from fitting.model_parser import build_model_specification


def test_infer_parameter_names_ignores_safe_eval_function_names():
    expr = "P*Ln[x] + Gamma[x] + Erf[x] + Zeta[2] + BesselJ[0, x] + Pi + E"
    names = infer_parameter_names(expr, ["x"], ["P"])
    assert names == ["P"]


def test_infer_parameter_names_collects_unknown_identifiers_as_parameters():
    expr = "A + B*x + C*Exp[-x] + D*Ln[x]"
    names = infer_parameter_names(expr, ["x"], [])
    assert names == ["A", "B", "C", "D"]


def test_infer_parameter_names_excludes_variables_constants_and_functions():
    assert infer_parameter_names(
        "A*x + B + K + Sin[x]",
        variables=["x"],
        constants=["K"],
    ) == ["A", "B"]


def test_infer_parameter_names_shared_by_custom_and_implicit():
    custom = infer_parameter_names("A*x + B + K", variables=["x"], constants=["K"])
    implicit = infer_parameter_names(
        "d0 + d2/(n-delta)^2 + K",
        variables=["n", "delta"],
        constants=["K"],
    )
    assert custom == ["A", "B"]
    assert implicit == ["d0", "d2"]


@pytest.mark.parametrize("constants", [{"Pi": "3"}, {"Sin": "2"}])
def test_build_model_specification_rejects_reserved_constant_names(constants):
    with pytest.raises(ValueError, match="Reserved|保留"):
        build_model_specification("A*x + K", ["x"], ["A"], constants=constants)
