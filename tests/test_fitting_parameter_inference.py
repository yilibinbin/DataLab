from __future__ import annotations

from fitting import infer_parameter_names


def test_infer_parameter_names_ignores_safe_eval_function_names():
    expr = "P*Ln[x] + Gamma[x] + Erf[x] + Zeta[2] + BesselJ[0, x] + Pi + E"
    names = infer_parameter_names(expr, ["x"], ["P"])
    assert names == ["P"]


def test_infer_parameter_names_collects_unknown_identifiers_as_parameters():
    expr = "A + B*x + C*Exp[-x] + D*Ln[x]"
    names = infer_parameter_names(expr, ["x"], [])
    assert names == ["A", "B", "C", "D"]
