from __future__ import annotations

import time

import mpmath as mp
from pytest import MonkeyPatch


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


def test_observed_implicit_d8_weighted_fit_finishes_quickly() -> None:
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
    assert result.details["optimizer_backend"] == "mpmath_qr"
    assert set(result.params) == {"d0", "d2", "d4", "d6", "d8"}


def test_affine_output_uses_exact_observed_fast_path_without_changing_statistics() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    with mp.workdps(80):
        n = [mp.mpf(row[0]) for row in D8_ROWS]
        delta = [mp.mpf(row[1]) for row in D8_ROWS]
        affine_y = [2 * value + 1 for value in delta]
        sigmas_delta = [mp.mpf(row[2]) for row in D8_ROWS]
        sigmas_affine = [2 * sigma for sigma in sigmas_delta]
        delta_weights = [1 / (sigma**2) for sigma in sigmas_delta]
        affine_weights = [1 / (sigma**2) for sigma in sigmas_affine]
    base_config = {
        "d0": {"initial": "-0.01213"},
        "d2": {"initial": "0.0"},
        "d4": {"initial": "0.0"},
        "d6": {"initial": "0.0"},
        "d8": {"initial": "0.0"},
    }
    equation = "d0 + d2/(n-delta)^2 + d4/(n-delta)^4 + d6/(n-delta)^6 + d8/(n-delta)^8"
    delta_definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation=equation,
        output_expression="delta",
        parameters=("d0", "d2", "d4", "d6", "d8"),
    )
    direct_problem = ModelProblem(
        model_type="self_consistent",
        expression="delta",
        variables=("n",),
        parameter_config=base_config,
        implicit_definition=delta_definition,
    )
    affine_problem = ModelProblem(
        model_type="self_consistent",
        expression="2*delta + 1",
        variables=("n",),
        parameter_config=base_config,
        implicit_definition=ImplicitModelDefinition(
            x_variables=("n",),
            implicit_variable="delta",
            equation=equation,
            output_expression="2*delta + 1",
            parameters=delta_definition.parameters,
        ),
    )

    runner = FitRunner()
    direct = runner.fit(direct_problem, {"n": n}, delta, precision=80, weights=delta_weights, data_sigmas=sigmas_delta)
    affine = runner.fit(
        affine_problem,
        {"n": n},
        affine_y,
        precision=80,
        weights=affine_weights,
        data_sigmas=sigmas_affine,
    )

    assert affine.details["implicit_strategy"] == "exact_affine_output_observed_linear"
    assert affine.details["optimizer_backend"] == "mpmath_qr"
    assert affine.details["output_space_remapped"] is True
    with mp.workdps(80):
        expected_affine_curve = [2 * value + 1 for value in direct.fitted_curve]
        max_curve_delta = max(
            mp.fabs(value - expected)
            for value, expected in zip(affine.fitted_curve, expected_affine_curve, strict=True)
        )
        assert max_curve_delta < mp.mpf("1e-24")
    with mp.workdps(80):
        max_residual_delta = max(
            mp.fabs(value - (fit - target))
            for value, fit, target in zip(affine.residuals, affine.fitted_curve, affine_y, strict=True)
        )
        assert max_residual_delta < mp.mpf("1e-24")
    for name, expected in direct.params.items():
        assert mp.almosteq(affine.params[name], expected, rel_eps=mp.mpf("1e-25"), abs_eps=mp.mpf("1e-30"))
        assert mp.almosteq(
            affine.param_errors_total[name],
            direct.param_errors_total[name],
            rel_eps=mp.mpf("1e-20"),
            abs_eps=mp.mpf("1e-30"),
        )
    for attr in ("chi2", "reduced_chi2", "aic", "bic", "r2"):
        assert mp.almosteq(getattr(affine, attr), getattr(direct, attr), rel_eps=mp.mpf("1e-20"), abs_eps=mp.mpf("1e-30"))
    with mp.workdps(80):
        assert mp.almosteq(affine.rmse, 2 * direct.rmse, rel_eps=mp.mpf("1e-20"), abs_eps=mp.mpf("1e-30"))


def test_affine_output_fast_path_matches_general_output_space_on_nonzero_residuals(
    monkeypatch: MonkeyPatch,
) -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4"), mp.mpf("5")]
    implicit_targets = [mp.mpf("0.15"), mp.mpf("0.41"), mp.mpf("0.62"), mp.mpf("0.81"), mp.mpf("1.08")]
    output_targets = [2 * value + 1 for value in implicit_targets]
    weights = [mp.mpf("1"), mp.mpf("2"), mp.mpf("1.5"), mp.mpf("3"), mp.mpf("2.5")]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="2*u + 1",
        variables=("x",),
        parameter_config={"a": {"initial": "0.1"}, "b": {"initial": "0.1"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression="2*u + 1",
            parameters=("a", "b"),
        ),
    )

    fast = FitRunner().fit(problem, {"x": xs}, output_targets, precision=80, weights=weights)
    monkeypatch.setattr("fitting.implicit_planner.detect_output_transform", lambda definition, **kwargs: None)
    general = FitRunner().fit(problem, {"x": xs}, output_targets, precision=80, weights=weights)

    assert fast.details["implicit_strategy"] == "exact_affine_output_observed_linear"
    for attr in ("chi2", "reduced_chi2", "aic", "bic", "r2", "rmse"):
        assert mp.almosteq(getattr(fast, attr), getattr(general, attr), rel_eps=mp.mpf("1e-18"), abs_eps=mp.mpf("1e-25"))
    for name in fast.params:
        assert mp.almosteq(fast.params[name], general.params[name], rel_eps=mp.mpf("1e-18"), abs_eps=mp.mpf("1e-25"))
        assert mp.almosteq(
            fast.param_errors_total[name],
            general.param_errors_total[name],
            rel_eps=mp.mpf("1e-12"),
            abs_eps=mp.mpf("1e-25"),
        )


def test_unweighted_affine_output_fast_path_matches_general_output_space(
    monkeypatch: MonkeyPatch,
) -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4"), mp.mpf("5")]
    implicit_targets = [mp.mpf("0.17"), mp.mpf("0.44"), mp.mpf("0.61"), mp.mpf("0.88"), mp.mpf("1.03")]
    output_targets = [mp.mpf("3.5") * value - mp.mpf("0.75") for value in implicit_targets]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="3.5*u - 0.75",
        variables=("x",),
        parameter_config={"a": {"initial": "0.1"}, "b": {"initial": "0.1"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a + b*x",
            output_expression="3.5*u - 0.75",
            parameters=("a", "b"),
        ),
    )

    fast = FitRunner().fit(problem, {"x": xs}, output_targets, precision=80)
    monkeypatch.setattr("fitting.implicit_planner.detect_output_transform", lambda definition, **kwargs: None)
    general = FitRunner().fit(problem, {"x": xs}, output_targets, precision=80)

    assert fast.details["implicit_strategy"] == "exact_affine_output_observed_linear"
    assert "weighted" not in fast.details
    for attr in ("chi2", "reduced_chi2", "aic", "bic", "r2", "rmse"):
        assert mp.almosteq(getattr(fast, attr), getattr(general, attr), rel_eps=mp.mpf("1e-18"), abs_eps=mp.mpf("1e-25"))
    for name in fast.params:
        assert mp.almosteq(fast.params[name], general.params[name], rel_eps=mp.mpf("1e-18"), abs_eps=mp.mpf("1e-25"))
        assert mp.almosteq(
            fast.param_errors_total[name],
            general.param_errors_total[name],
            rel_eps=mp.mpf("1e-12"),
            abs_eps=mp.mpf("1e-25"),
        )


def test_affine_output_skips_fast_path_for_unweighted_data_sigmas() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3")]
    us = [mp.mpf("0.2"), mp.mpf("0.4"), mp.mpf("0.6")]
    ys = [2 * value + 1 for value in us]
    sigmas = [mp.mpf("0.01"), mp.mpf("0.01"), mp.mpf("0.01")]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="2*u + 1",
        variables=("x",),
        parameter_config={"a": {"initial": "0.1"}, "b": {"initial": "0.1"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="a*x + b",
            output_expression="2*u + 1",
            parameters=("a", "b"),
        ),
    )

    result = FitRunner().fit(problem, {"x": xs}, ys, precision=80, data_sigmas=sigmas)

    assert result.details["implicit_strategy"] != "exact_affine_output_observed_linear"
    fallback_history = result.details.get("fallback_history", [])
    assert isinstance(fallback_history, list)
    assert any(
        item.get("skipped") == "unweighted_data_sigmas"
        for item in fallback_history
        if isinstance(item, dict)
    )


def test_affine_output_does_not_use_observed_nonlinear_residual_fast_path() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    xs = [mp.mpf("1"), mp.mpf("2"), mp.mpf("3"), mp.mpf("4")]
    ys = [mp.mpf("1.2"), mp.mpf("1.3"), mp.mpf("1.4"), mp.mpf("1.5")]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="2*u + 1",
        variables=("x",),
        parameter_config={"a": {"initial": "0.1"}, "b": {"initial": "0.1"}},
        implicit_definition=ImplicitModelDefinition(
            x_variables=("x",),
            implicit_variable="u",
            equation="Sin[a] + b*x",
            output_expression="2*u + 1",
            parameters=("a", "b"),
        ),
    )

    result = FitRunner().fit(problem, {"x": xs}, ys, precision=80)

    assert result.details["implicit_strategy"] != "exact_affine_output_observed_nonlinear"
    fallback_history = result.details.get("fallback_history", [])
    assert isinstance(fallback_history, list)
    assert any(
        item.get("from") == "exact_affine_output"
        for item in fallback_history
        if isinstance(item, dict)
    )
