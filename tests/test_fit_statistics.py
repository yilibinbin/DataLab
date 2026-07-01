from __future__ import annotations

import mpmath as mp
import pytest

import fitting.auto_models as auto_models
import fitting.implicit_model as implicit_model
from fitting.constraints import build_parameter_state
from fitting.statistics import FitStatistics, compute_fit_statistics


def test_compute_fit_statistics_empty_input_contract() -> None:
    stats = compute_fit_statistics([], [], None, free_param_count=2)

    assert stats.dof == -2
    for value in (stats.chi2, stats.reduced_chi2, stats.r2, stats.rmse, stats.aic, stats.bic):
        assert mp.isnan(value)


def test_compute_fit_statistics_unweighted_nonempty_values() -> None:
    stats = compute_fit_statistics(
        [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")],
        [mp.mpf("0.5"), mp.mpf("-0.25"), mp.mpf("0.75")],
        None,
        free_param_count=1,
    )

    assert stats.dof == 2
    assert stats.chi2 == mp.mpf("0.875")
    assert stats.reduced_chi2 == mp.mpf("0.4375")
    assert stats.rmse == mp.sqrt(mp.mpf("0.875") / 3)
    assert mp.almosteq(stats.r2, mp.mpf("1") - mp.mpf("0.875") / mp.mpf("8"))
    assert not mp.isnan(stats.aic)
    assert not mp.isnan(stats.bic)


def test_compute_fit_statistics_weighted_nonempty_values() -> None:
    stats = compute_fit_statistics(
        [mp.mpf("1"), mp.mpf("3"), mp.mpf("5")],
        [mp.mpf("0.5"), mp.mpf("-0.25"), mp.mpf("0.75")],
        [mp.mpf("2"), mp.mpf("1"), mp.mpf("3")],
        free_param_count=1,
    )

    assert stats.dof == 2
    assert stats.chi2 == mp.mpf("2.25")
    assert stats.reduced_chi2 == mp.mpf("1.125")
    assert stats.rmse == mp.sqrt(mp.mpf("2.25") / 6)
    assert not mp.isnan(stats.aic)
    assert not mp.isnan(stats.bic)


def test_compute_fit_statistics_dof_guard_and_constant_target_r2() -> None:
    stats = compute_fit_statistics(
        [mp.mpf("2"), mp.mpf("2")],
        [mp.mpf("0"), mp.mpf("0")],
        None,
        free_param_count=1,
    )

    assert stats.dof == 1
    assert stats.r2 == mp.mpf("1")

    no_dof = compute_fit_statistics(
        [mp.mpf("2"), mp.mpf("2")],
        [mp.mpf("1"), mp.mpf("-1")],
        None,
        free_param_count=2,
    )
    assert no_dof.dof == 0
    assert no_dof.chi2 == mp.mpf("2")
    assert mp.isnan(no_dof.reduced_chi2)
    assert mp.isnan(no_dof.r2)
    assert mp.isnan(no_dof.aic)
    assert mp.isnan(no_dof.bic)

    bad_constant = compute_fit_statistics(
        [mp.mpf("2"), mp.mpf("2"), mp.mpf("2")],
        [mp.mpf("1"), mp.mpf("0"), mp.mpf("-1")],
        None,
        free_param_count=1,
    )
    assert bad_constant.dof == 2
    assert mp.isnan(bad_constant.r2)


def test_compute_fit_statistics_validates_lengths_and_weights() -> None:
    with pytest.raises(ValueError, match="Residual count"):
        compute_fit_statistics([mp.mpf("1")], [], None, free_param_count=1)

    with pytest.raises(ValueError, match="Weight count"):
        compute_fit_statistics([mp.mpf("1")], [mp.mpf("0")], [], free_param_count=1)

    with pytest.raises(ValueError, match="Weights must be positive"):
        compute_fit_statistics(
            [mp.mpf("1")],
            [mp.mpf("0")],
            [mp.mpf("-1")],
            free_param_count=1,
            validate_weights=True,
        )

    with pytest.raises(ValueError, match="Weights must be positive"):
        compute_fit_statistics(
            [mp.mpf("1")],
            [mp.mpf("0")],
            [mp.inf],
            free_param_count=1,
            validate_weights=True,
        )


def test_auto_linear_model_uses_shared_fit_statistics(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = FitStatistics(
        chi2=mp.mpf("101"),
        reduced_chi2=mp.mpf("202"),
        r2=mp.mpf("0.303"),
        rmse=mp.mpf("0.404"),
        aic=mp.mpf("505"),
        bic=mp.mpf("606"),
        dof=3,
    )
    calls = []

    def fake_compute_fit_statistics(targets, residuals, weights, *, free_param_count, validate_weights=False):
        calls.append(
            {
                "targets": list(targets),
                "residuals": list(residuals),
                "weights": weights,
                "free_param_count": free_param_count,
                "validate_weights": validate_weights,
            }
        )
        return sentinel

    monkeypatch.setattr(auto_models, "compute_fit_statistics", fake_compute_fit_statistics)

    model = auto_models.AUTO_MODEL_MAP["M1"]
    result = auto_models.fit_linear_model(
        model,
        [mp.mpf(i) for i in range(5)],
        [mp.mpf(2 * i + 1) for i in range(5)],
        precision=50,
    )

    assert calls
    assert calls[0]["targets"] == [mp.mpf(2 * i + 1) for i in range(5)]
    assert calls[0]["free_param_count"] == 2
    assert calls[0]["validate_weights"] is False
    assert result.chi2 == sentinel.chi2
    assert result.reduced_chi2 == sentinel.reduced_chi2
    assert result.aic == sentinel.aic
    assert result.bic == sentinel.bic
    assert result.r2 == sentinel.r2
    assert result.rmse == sentinel.rmse
    assert all(mp.almosteq(residual, mp.mpf("0")) for residual in result.residuals)
    assert [len(row) for row in result.covariance] == [2, 2]


def test_observed_implicit_linear_model_uses_shared_fit_statistics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sentinel = FitStatistics(
        chi2=mp.mpf("707"),
        reduced_chi2=mp.mpf("808"),
        r2=mp.mpf("0.909"),
        rmse=mp.mpf("1.010"),
        aic=mp.mpf("111"),
        bic=mp.mpf("212"),
        dof=3,
    )
    calls = []

    def fake_compute_fit_statistics(targets, residuals, weights, *, free_param_count, validate_weights=False):
        calls.append(
            {
                "targets": list(targets),
                "residuals": list(residuals),
                "weights": weights,
                "free_param_count": free_param_count,
                "validate_weights": validate_weights,
            }
        )
        return sentinel

    monkeypatch.setattr(implicit_model, "compute_fit_statistics", fake_compute_fit_statistics)

    definition = implicit_model.ImplicitModelDefinition(
        x_variables=("x",),
        implicit_variable="u",
        equation="a + b*x",
        output_expression="u",
        parameters=("a", "b"),
    )
    parameter_state = build_parameter_state({}, ["a", "b"])
    xs = [mp.mpf(i) for i in range(5)]
    targets = [mp.mpf(2 * i + 1) for i in range(5)]
    result = implicit_model._solve_observed_linear_least_squares(
        definition=definition,
        parameter_state=parameter_state,
        targets=targets,
        offsets=[mp.mpf("0") for _ in xs],
        basis_rows=[[mp.mpf("1"), x] for x in xs],
        weights=None,
        data_sigmas=None,
    )

    assert calls
    assert calls[0]["targets"] == targets
    assert calls[0]["free_param_count"] == 2
    assert calls[0]["validate_weights"] is False
    assert result.chi2 == sentinel.chi2
    assert result.reduced_chi2 == sentinel.reduced_chi2
    assert result.aic == sentinel.aic
    assert result.bic == sentinel.bic
    assert result.r2 == sentinel.r2
    assert result.rmse == sentinel.rmse
    assert result.details["dof"] == sentinel.dof
    assert all(mp.almosteq(residual, mp.mpf("0")) for residual in result.residuals)
    assert [len(row) for row in result.covariance] == [2, 2]
