from __future__ import annotations

from mpmath import mp

from fitting import build_model_specification, build_parameter_state, fit_custom_model


def test_fit_custom_model_recovers_exact_linear_parameters():
    with mp.workdps(80):
        expr = "a*x + b"
        model = build_model_specification(expr, ["x"], ["a", "b"])
        state = build_parameter_state(
            {
                "a": {"initial": mp.mpf("1.0")},
                "b": {"initial": mp.mpf("0.0")},
            },
            ["a", "b"],
        )

        x_data = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
        a_true = mp.mpf("2")
        b_true = mp.mpf("1")
        y_data = [a_true * x + b_true for x in x_data]

        result = fit_custom_model(
            model,
            state,
            variable_data={"x": x_data},
            target_data=y_data,
            precision=80,
            weights=None,
            data_sigmas=None,
        )

        assert mp.almosteq(result.params["a"], a_true, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))
        assert mp.almosteq(result.params["b"], b_true, rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))
        assert all(mp.almosteq(r, mp.mpf("0"), abs_eps=mp.mpf("1e-40")) for r in result.residuals)

        cov = result.covariance
        assert len(cov) == 2
        assert len(cov[0]) == 2
        assert len(cov[1]) == 2
        assert mp.almosteq(cov[0][1], cov[1][0], rel_eps=mp.mpf("1e-40"), abs_eps=mp.mpf("1e-40"))
        assert cov[0][0] >= 0
        assert cov[1][1] >= 0


def test_fit_custom_model_systematic_uncertainty_branch_runs():
    with mp.workdps(80):
        expr = "a*x + b"
        model = build_model_specification(expr, ["x"], ["a", "b"])
        state = build_parameter_state(
            {
                "a": {"initial": mp.mpf("1.0")},
                "b": {"initial": mp.mpf("0.0")},
            },
            ["a", "b"],
        )

        x_data = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
        y_data = [mp.mpf("2") * x + mp.mpf("1") for x in x_data]
        sigmas = [mp.mpf("0.1")] * len(y_data)

        result = fit_custom_model(
            model,
            state,
            variable_data={"x": x_data},
            target_data=y_data,
            precision=80,
            weights=None,
            data_sigmas=sigmas,
        )

        # Should compute sys errors via ±σ refits (non-zero in general for linear models with perturbations).
        assert "a" in result.param_errors_sys
        assert "b" in result.param_errors_sys
        assert result.param_errors_sys["a"] > 0
        assert result.param_errors_sys["b"] > 0


def test_fit_custom_model_weighted_branch_skips_systematic_uncertainty():
    with mp.workdps(80):
        expr = "a*x + b"
        model = build_model_specification(expr, ["x"], ["a", "b"])
        state = build_parameter_state(
            {
                "a": {"initial": mp.mpf("1.0")},
                "b": {"initial": mp.mpf("0.0")},
            },
            ["a", "b"],
        )

        x_data = [mp.mpf(v) for v in ["0", "1", "2", "3"]]
        y_data = [mp.mpf("2") * x + mp.mpf("1") for x in x_data]
        sigmas = [mp.mpf("0.1")] * len(y_data)
        weights = [mp.mpf("1") / (s * s) for s in sigmas]

        result = fit_custom_model(
            model,
            state,
            variable_data={"x": x_data},
            target_data=y_data,
            precision=80,
            weights=weights,
            data_sigmas=sigmas,
        )

        # When weights are provided, the implementation deliberately avoids double-counting by not adding sys errors.
        assert result.param_errors_sys.get("a", mp.mpf("0")) == 0
        assert result.param_errors_sys.get("b", mp.mpf("0")) == 0
