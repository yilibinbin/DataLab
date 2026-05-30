from __future__ import annotations

# mypy: disable-error-code=untyped-decorator

from typing import Any

import mpmath as mp
import pytest


def _d8_rows() -> list[tuple[mp.mpf, mp.mpf, mp.mpf]]:
    raw = [
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
    return [(mp.mpf(n), mp.mpf(delta), mp.mpf(sigma)) for n, delta, sigma in raw]


def test_direct_delta_output_uses_observed_path_without_root_solves() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    rows = _d8_rows()
    n = [row[0] for row in rows]
    delta = [row[1] for row in rows]
    sigmas = [row[2] for row in rows]
    problem = ModelProblem(
        model_type="self_consistent",
        expression="delta",
        variables=("n",),
        parameter_config={
            "d0": {"initial": "-0.01213"},
            "d2": {"initial": "0"},
            "d4": {"initial": "0"},
            "d6": {"initial": "0"},
            "d8": {"initial": "0"},
        },
        implicit_definition=ImplicitModelDefinition(
            x_variables=("n",),
            implicit_variable="delta",
            equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4 + d6/(n-delta)^6 + d8/(n-delta)^8",
            output_expression="delta",
            parameters=("d0", "d2", "d4", "d6", "d8"),
        ),
    )

    result = FitRunner().fit(
        problem,
        {"n": n},
        delta,
        precision=80,
        weights=[1 / (sigma * sigma) for sigma in sigmas],
        data_sigmas=sigmas,
    )

    assert result.details["implicit_strategy"] == "observed_linear"
    assert result.details["optimizer_backend"] == "mpmath_qr"
    assert result.details["implicit_fast_path"] == "observed_implicit_linear"
    diagnostics = result.details["implicit_diagnostics"]
    assert isinstance(diagnostics, dict)
    assert diagnostics["points_solved"] == 0
    assert "uncertainty_note" in result.details
    assert all(
        mp.almosteq(residual, fit - target, rel_eps=mp.mpf("1e-24"), abs_eps=mp.mpf("1e-21"))
        for residual, fit, target in zip(result.residuals, result.fitted_curve, delta, strict=True)
    )
    assert all(mp.isfinite(result.params[name]) for name in ("d0", "d2", "d4", "d6", "d8"))


def _assert_error_maps_are_finite(result: Any, parameter_names: tuple[str, ...]) -> None:
    for mapping_name in ("param_errors_stat", "param_errors_sys", "param_errors_total", "param_errors"):
        mapping = getattr(result, mapping_name)
        assert set(mapping) == set(parameter_names)
        assert all(mp.isfinite(mapping[name]) for name in parameter_names)
    assert len(result.covariance) == len(parameter_names)
    assert all(len(row) == len(parameter_names) for row in result.covariance)
    assert all(mp.isfinite(value) for row in result.covariance for value in row)


def _assert_fit_statistics_are_finite(result: Any) -> None:
    for attr in ("chi2", "reduced_chi2", "aic", "bic", "r2", "rmse"):
        assert mp.isfinite(getattr(result, attr))


def _synthetic_quantum_defect_rows() -> tuple[list[mp.mpf], list[mp.mpf], dict[str, mp.mpf]]:
    true_params = {
        "d0": mp.mpf("-0.01214"),
        "d2": mp.mpf("0.0018"),
        "d4": mp.mpf("-0.00035"),
    }

    def solve_delta(n_value: mp.mpf) -> mp.mpf:
        delta = true_params["d0"]
        for _ in range(80):
            denom = n_value - delta
            next_delta = true_params["d0"] + true_params["d2"] / denom**2 + true_params["d4"] / denom**4
            if mp.fabs(next_delta - delta) < mp.mpf("1e-60"):
                return +next_delta
            delta = next_delta
        return +delta

    n_values = [mp.mpf(index) for index in range(5, 15)]
    return n_values, [solve_delta(n_value) for n_value in n_values], true_params


def _assert_recovers_synthetic_quantum_defect_params(result: Any, true_params: dict[str, mp.mpf]) -> None:
    assert mp.fabs(result.params["d0"] - true_params["d0"]) < mp.mpf("1e-28")
    assert mp.fabs(result.params["d2"] - true_params["d2"]) < mp.mpf("1e-26")
    assert mp.fabs(result.params["d4"] - true_params["d4"]) < mp.mpf("1e-24")


def test_synthetic_direct_delta_oracle_recovers_quantum_defect_parameters() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    with mp.workdps(90):
        n_values, delta_values, true_params = _synthetic_quantum_defect_rows()
        parameter_names = ("d0", "d2", "d4")
        problem = ModelProblem(
            model_type="self_consistent",
            expression="delta",
            variables=("n",),
            parameter_config={
                "d0": {"initial": "-0.0120"},
                "d2": {"initial": "0.001"},
                "d4": {"initial": "0"},
            },
            implicit_definition=ImplicitModelDefinition(
                x_variables=("n",),
                implicit_variable="delta",
                equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
                output_expression="delta",
                parameters=parameter_names,
            ),
        )

        result = FitRunner().fit(problem, {"n": n_values}, delta_values, precision=80)

        assert result.details["implicit_strategy"] == "observed_linear"
        assert result.details["optimizer_backend"] == "mpmath_qr"
        _assert_recovers_synthetic_quantum_defect_params(result, true_params)
        _assert_fit_statistics_are_finite(result)
        assert all(
            mp.almosteq(residual, fit - observed, rel_eps=mp.mpf("1e-30"), abs_eps=mp.mpf("1e-50"))
            for residual, fit, observed in zip(result.residuals, result.fitted_curve, delta_values, strict=True)
        )
        _assert_error_maps_are_finite(result, parameter_names)


@pytest.mark.slow
def test_synthetic_ionization_energy_oracle_recovers_quantum_defect_parameters() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    with mp.workdps(90):
        n_values, delta_values, true_params = _synthetic_quantum_defect_rows()
        r_const = mp.mpf("100")
        energy_values = [r_const / (n_value - delta) ** 2 for n_value, delta in zip(n_values, delta_values, strict=True)]
        parameter_names = ("d0", "d2", "d4")
        problem = ModelProblem(
            model_type="self_consistent",
            expression="R/(n-delta)^2",
            variables=("n",),
            parameter_config={
                "d0": {"initial": "-0.0120"},
                "d2": {"initial": "0.001"},
                "d4": {"initial": "0"},
            },
            implicit_definition=ImplicitModelDefinition(
                x_variables=("n",),
                implicit_variable="delta",
                equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
                output_expression="R/(n-delta)^2",
                parameters=parameter_names,
                constants={"R": str(r_const)},
            ),
        )

        result = FitRunner().fit(problem, {"n": n_values}, energy_values, precision=80)

        assert result.details["implicit_strategy"] in {
            "analytic_implicit_output_space",
            "general_implicit_numeric_finite_difference",
        }
        assert result.details.get("output_transform") is None
        _assert_recovers_synthetic_quantum_defect_params(result, true_params)
        _assert_fit_statistics_are_finite(result)
        assert all(
            mp.almosteq(residual, fit - observed, rel_eps=mp.mpf("1e-24"), abs_eps=mp.mpf("1e-36"))
            for residual, fit, observed in zip(result.residuals, result.fitted_curve, energy_values, strict=True)
        )
        _assert_error_maps_are_finite(result, parameter_names)


def test_direct_delta_uncertainty_modes_preserve_error_contracts() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    rows = _d8_rows()[:8]
    n = [row[0] for row in rows]
    delta = [row[1] for row in rows]
    sigmas = [row[2] for row in rows]
    parameter_names = ("d0", "d2", "d4")
    problem = ModelProblem(
        model_type="self_consistent",
        expression="delta",
        variables=("n",),
        parameter_config={
            "d0": {"initial": "-0.01213"},
            "d2": {"initial": "0"},
            "d4": {"initial": "0"},
        },
        implicit_definition=ImplicitModelDefinition(
            x_variables=("n",),
            implicit_variable="delta",
            equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
            output_expression="delta",
            parameters=parameter_names,
        ),
    )
    runner = FitRunner()

    no_sigma = runner.fit(problem, {"n": n}, delta, precision=50)
    weighted = runner.fit(
        problem,
        {"n": n},
        delta,
        precision=50,
        weights=[1 / (sigma * sigma) for sigma in sigmas],
        data_sigmas=sigmas,
    )
    unweighted = runner.fit(problem, {"n": n}, delta, precision=50, data_sigmas=sigmas)

    assert no_sigma.details["implicit_strategy"] == "observed_linear"
    assert weighted.details["implicit_strategy"] == "observed_linear"
    assert unweighted.details["implicit_strategy"] != "observed_linear"
    fallback_history = unweighted.details.get("fallback_history")
    assert isinstance(fallback_history, list)
    assert any(item.get("skipped") == "unweighted_data_sigmas" for item in fallback_history if isinstance(item, dict))
    for result in (no_sigma, weighted, unweighted):
        _assert_error_maps_are_finite(result, parameter_names)
        _assert_fit_statistics_are_finite(result)
        assert all(
            mp.almosteq(residual, fit - target, rel_eps=mp.mpf("1e-20"), abs_eps=mp.mpf("1e-22"))
            for residual, fit, target in zip(result.residuals, result.fitted_curve, delta, strict=True)
        )
    assert all(value == 0 for value in no_sigma.param_errors_sys.values())
    assert any(value > 0 for value in unweighted.param_errors_sys.values())


@pytest.mark.slow
def test_nonlinear_output_uses_output_space_backend_without_transforming_objective() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    rows = _d8_rows()[:12]
    n = [row[0] for row in rows]
    delta = [row[1] for row in rows]
    r_const = mp.mpf("100")
    energy = [r_const / (x - u) ** 2 for x, u in zip(n, delta, strict=True)]
    sigma_energy = [mp.fabs(2 * r_const / (x - u) ** 3) * s for x, u, s in rows]
    base_config = {
        "d0": {"initial": "-0.01213"},
        "d2": {"initial": "0"},
        "d4": {"initial": "0"},
    }
    energy_problem = ModelProblem(
        model_type="self_consistent",
        expression="R/(n-delta)^2",
        variables=("n",),
        parameter_config=base_config,
        implicit_definition=ImplicitModelDefinition(
            x_variables=("n",),
            implicit_variable="delta",
            equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
            output_expression="R/(n-delta)^2",
            parameters=("d0", "d2", "d4"),
            constants={"R": str(r_const)},
        ),
    )

    energy_result = FitRunner().fit(
        energy_problem,
        {"n": n},
        energy,
        precision=80,
        weights=[1 / s**2 for s in sigma_energy],
        data_sigmas=sigma_energy,
    )

    assert energy_result.details["implicit_strategy"] in {
        "analytic_implicit_output_space",
        "general_implicit_numeric_finite_difference",
    }
    assert energy_result.details.get("output_transform") is None
    assert all(
        mp.almosteq(residual, fit - target, rel_eps=mp.mpf("1e-20"), abs_eps=mp.mpf("1e-22"))
        for residual, fit, target in zip(energy_result.residuals, energy_result.fitted_curve, energy, strict=True)
    )
    assert all(mp.isfinite(value) for value in energy_result.params.values())
    _assert_fit_statistics_are_finite(energy_result)
    diagnostics = energy_result.details.get("implicit_diagnostics", {})
    assert isinstance(diagnostics, dict)
    assert int(diagnostics.get("points_solved", 10**9)) < len(n) * 500
    assert "seed_sources" in diagnostics or "seed_attempts" in diagnostics


@pytest.mark.slow
def test_ionization_energy_uncertainty_modes_preserve_output_space_errors() -> None:
    from fitting.implicit_model import ImplicitModelDefinition
    from fitting.problem import ModelProblem
    from fitting.runner import FitRunner

    rows = _d8_rows()[:6]
    n = [row[0] for row in rows]
    delta = [row[1] for row in rows]
    r_const = mp.mpf("100")
    energy = [r_const / (x - u) ** 2 for x, u in zip(n, delta, strict=True)]
    sigma_energy = [mp.fabs(2 * r_const / (x - u) ** 3) * s for x, u, s in rows]
    parameter_names = ("d0", "d2", "d4")
    problem = ModelProblem(
        model_type="self_consistent",
        expression="R/(n-delta)^2",
        variables=("n",),
        parameter_config={
            "d0": {"initial": "-0.01213"},
            "d2": {"initial": "0"},
            "d4": {"initial": "0"},
        },
        implicit_definition=ImplicitModelDefinition(
            x_variables=("n",),
            implicit_variable="delta",
            equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
            output_expression="R/(n-delta)^2",
            parameters=parameter_names,
            constants={"R": str(r_const)},
        ),
    )
    runner = FitRunner()

    no_sigma = runner.fit(problem, {"n": n}, energy, precision=50)
    weighted = runner.fit(
        problem,
        {"n": n},
        energy,
        precision=50,
        weights=[1 / (sigma * sigma) for sigma in sigma_energy],
        data_sigmas=sigma_energy,
    )
    unweighted = runner.fit(problem, {"n": n}, energy, precision=50, data_sigmas=sigma_energy)

    for result in (no_sigma, weighted, unweighted):
        assert result.details["implicit_strategy"] in {
            "analytic_implicit_output_space",
            "general_implicit_numeric_finite_difference",
        }
        assert result.details.get("output_transform") is None
        _assert_error_maps_are_finite(result, parameter_names)
        _assert_fit_statistics_are_finite(result)
        assert all(
            mp.almosteq(residual, fit - target, rel_eps=mp.mpf("1e-20"), abs_eps=mp.mpf("1e-22"))
            for residual, fit, target in zip(result.residuals, result.fitted_curve, energy, strict=True)
        )
    assert all(value == 0 for value in no_sigma.param_errors_sys.values())
    assert any(value > 0 for value in unweighted.param_errors_sys.values())


@pytest.mark.slow
def test_nonlinear_output_analytic_strategy_matches_forced_numeric_errors() -> None:
    from fitting.constraints import build_parameter_state
    from fitting.hp_fitter import fit_custom_model
    from fitting.implicit_model import ImplicitModelDefinition, build_implicit_model_specification

    rows = _d8_rows()[:12]
    n = [row[0] for row in rows]
    delta = [row[1] for row in rows]
    r_const = mp.mpf("100")
    energy = [r_const / (x - u) ** 2 for x, u in zip(n, delta, strict=True)]
    definition = ImplicitModelDefinition(
        x_variables=("n",),
        implicit_variable="delta",
        equation="d0 + d2/(n-delta)^2 + d4/(n-delta)^4",
        output_expression="R/(n-delta)^2",
        parameters=("d0", "d2", "d4"),
        constants={"R": str(r_const)},
    )
    state = build_parameter_state(
        {"d0": {"initial": "-0.01213"}, "d2": {"initial": "0"}, "d4": {"initial": "0"}},
        list(definition.parameters),
    )
    analytic = fit_custom_model(
        build_implicit_model_specification(definition, target_data=energy, use_analytic_derivatives=True),
        state,
        {"n": n},
        energy,
        precision=50,
    )
    numeric = fit_custom_model(
        build_implicit_model_specification(definition, target_data=energy, use_analytic_derivatives=False),
        state,
        {"n": n},
        energy,
        precision=50,
    )

    _assert_fit_statistics_are_finite(analytic)
    _assert_fit_statistics_are_finite(numeric)
    for name in definition.parameters:
        assert mp.almosteq(analytic.params[name], numeric.params[name], rel_eps=mp.mpf("1e-16"), abs_eps=mp.mpf("1e-24"))
        assert mp.almosteq(
            analytic.param_errors_total[name],
            numeric.param_errors_total[name],
            rel_eps=mp.mpf("1e-10"),
            abs_eps=mp.mpf("1e-20"),
        )
    for attr in ("chi2", "reduced_chi2", "aic", "bic", "r2", "rmse"):
        assert mp.almosteq(
            getattr(analytic, attr),
            getattr(numeric, attr),
            rel_eps=mp.mpf("1e-16"),
            abs_eps=mp.mpf("1e-24"),
        )
    for analytic_residual, numeric_residual in zip(analytic.residuals, numeric.residuals, strict=True):
        assert mp.almosteq(
            analytic_residual,
            numeric_residual,
            rel_eps=mp.mpf("1e-16"),
            abs_eps=mp.mpf("1e-24"),
        )
    for analytic_fit, numeric_fit in zip(analytic.fitted_curve, numeric.fitted_curve, strict=True):
        assert mp.almosteq(
            analytic_fit,
            numeric_fit,
            rel_eps=mp.mpf("1e-16"),
            abs_eps=mp.mpf("1e-24"),
        )
