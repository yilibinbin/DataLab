from __future__ import annotations

import time

import mpmath as mp


D8_ROWS = [
    ("4", "-0.01161947382", "0.00000000002"),
    ("5", "-0.01182004861", "0.00000000004"),
    ("6", "-0.01192302789", "0.00000000003"),
    ("7", "-0.01198312684", "0.00000000003"),
    ("8", "-0.01202134197", "0.00000000004"),
    ("9", "-0.01204718702", "0.00000000006"),
    ("10", "-0.01206549920", "0.00000000006"),
    ("11", "-0.01207895610", "0.00000000008"),
    ("12", "-0.0120891399", "0.0000000001"),
    ("13", "-0.0120970357", "0.0000000001"),
    ("14", "-0.0121032829", "0.0000000002"),
    ("15", "-0.0121083122", "0.0000000002"),
    ("16", "-0.0121124215", "0.0000000003"),
    ("17", "-0.0121158233", "0.0000000003"),
    ("18", "-0.0121186716", "0.0000000004"),
    ("19", "-0.0121210809", "0.0000000004"),
    ("20", "-0.0121231371", "0.0000000005"),
    ("21", "-0.0121249065", "0.0000000006"),
    ("22", "-0.0121264402", "0.0000000006"),
    ("23", "-0.0121277787", "0.0000000007"),
    ("24", "-0.0121289539", "0.0000000008"),
    ("25", "-0.012129992", "0.000000001"),
    ("26", "-0.012130913", "0.000000001"),
    ("27", "-0.012131734", "0.000000001"),
    ("28", "-0.012132469", "0.000000001"),
    ("29", "-0.012133131", "0.000000001"),
    ("30", "-0.012133729", "0.000000002"),
    ("31", "-0.012134269", "0.000000002"),
    ("32", "-0.012134761", "0.000000002"),
    ("33", "-0.012135210", "0.000000003"),
    ("34", "-0.012135623", "0.000000006"),
    ("35", "-0.01213599", "0.00000001"),
    ("36", "-0.01213634", "0.00000006"),
    ("37", "-0.0121366", "0.0000008"),
    ("38", "-0.01215", "0.00005"),
]


def test_observed_implicit_d8_weighted_fit_finishes_quickly():
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    problem = ModelProblem(
        model_type="self_consistent",
        expression="delta",
        variables=("n",),
        parameter_config={
            "d0": {"initial": "-0.01213"},
            "d2": {"initial": "0.0"},
            "d4": {"initial": "0.0"},
            "d6": {"initial": "0.0"},
            "d8": {"initial": "0.0"},
        },
        implicit_definition=ImplicitModelDefinition(
            x_variables=("n",),
            implicit_variable="delta",
            equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4 + d6/(n-delta)^6 + d8/(n-delta)^8",
            output_expression="delta",
            parameters=("d0", "d2", "d4", "d6", "d8"),
        ),
    )
    n = [mp.mpf(row[0]) for row in D8_ROWS]
    delta = [mp.mpf(row[1]) for row in D8_ROWS]
    weights = [1 / (mp.mpf(row[2]) ** 2) for row in D8_ROWS]

    start = time.perf_counter()
    result = FitRunner().fit(problem, {"n": n}, delta, precision=80, weights=weights)

    assert time.perf_counter() - start < 1.0
    assert result.details["implicit_strategy"] == "observed_linear"
    assert result.details["optimizer_backend"] in {"mpmath_qr", "scipy_least_squares"}
    assert set(result.params) == {"d0", "d2", "d4", "d6", "d8"}
