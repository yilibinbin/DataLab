from __future__ import annotations

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
    diagnostics = energy_result.details.get("implicit_diagnostics", {})
    assert isinstance(diagnostics, dict)
    assert int(diagnostics.get("points_solved", 10**9)) < len(n) * 500
    assert "seed_sources" in diagnostics or "seed_attempts" in diagnostics


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

    for name in definition.parameters:
        assert mp.almosteq(analytic.params[name], numeric.params[name], rel_eps=mp.mpf("1e-16"), abs_eps=mp.mpf("1e-24"))
        assert mp.almosteq(
            analytic.param_errors_total[name],
            numeric.param_errors_total[name],
            rel_eps=mp.mpf("1e-10"),
            abs_eps=mp.mpf("1e-20"),
        )
