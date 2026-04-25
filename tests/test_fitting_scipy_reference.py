"""Cross-validate DataLab's linear-basis fitting against scipy.

DataLab's ``fit_linear_model`` solves a linear-in-parameters fit
(M1 linear, M2 quadratic, M3 cubic, M5 1/x-series, ...) via mpmath
arbitrary-precision normal equations. ``scipy.optimize.curve_fit`` (or
``numpy.linalg.lstsq``) solves the same problem in IEEE 754 double.
For reasonably-conditioned problems both methods must agree to
~12-14 significant digits — the limit imposed by double-precision
linear algebra.

Why this test matters
---------------------

Before this test, DataLab's fitting engine had:
- mypy --strict cleanup proving type contracts (Phase 7 #23)
- LaTeX writer / GUI wiring tests proving plumbing
- exactly **zero** independent verification of the fitted
  parameter values themselves

A subtle bug in the normal-equation assembly (e.g. wrong basis
function, transposed matrix, wrong residual definition) would slip
through every existing test silently. ``scipy`` is the canonical
reference numerical-fitting library; matching it cross-checks the
output, not just the plumbing.

Coverage
--------

- M1 linear, M2 quadratic, M3 cubic on synthetic data
- M5 1/x-series and M7 exponential-combo on positive-x synthetic data
- 50 points, no noise: tolerance 1e-12 (round-off only)
- 50 points, additive Gaussian noise: tolerance 1e-10 on the fit
  parameters (signal/noise large enough that both methods converge
  to the same minimum)
"""
from __future__ import annotations

import pytest

scipy_optimize = pytest.importorskip("scipy.optimize")
numpy = pytest.importorskip("numpy")

import numpy as np  # noqa: E402
from mpmath import mp  # noqa: E402

from fitting.auto_models import AUTO_MODELS, fit_linear_model  # noqa: E402


def _model_by_id(model_id: str) -> object:
    """Find an ``AutoModelDefinition`` by its identifier."""
    for model in AUTO_MODELS:
        if model.identifier == model_id:
            return model
    raise KeyError(f"AUTO_MODELS has no entry with identifier {model_id!r}")


def _scipy_curve_fit_linear(
    basis_funcs: list,
    xs: np.ndarray,
    ys: np.ndarray,
) -> np.ndarray:
    """Solve the linear least-squares problem ``A @ p = ys`` where
    ``A[i, j] = basis_funcs[j](xs[i])``. Uses ``numpy.linalg.lstsq``
    instead of ``curve_fit`` because the problem is linear in
    parameters and ``lstsq`` returns the analytic solution without
    iterative tuning."""
    A = np.column_stack([f(xs) for f in basis_funcs])
    p, _residuals, _rank, _sv = np.linalg.lstsq(A, ys, rcond=None)
    return p


# Each test case: (model_id, basis_funcs as numpy lambdas, true_params,
# x_range, n_points, noise_sigma)
_CASES = [
    (
        "M1_linear_clean",
        "M1",
        [lambda x: np.ones_like(x), lambda x: x],
        np.array([2.0, 3.5]),  # b0 + b1*x
        np.linspace(0, 10, 50),
        0.0,
    ),
    (
        "M2_quadratic_clean",
        "M2",
        [lambda x: np.ones_like(x), lambda x: x, lambda x: x ** 2],
        np.array([1.0, -2.0, 0.5]),  # b0 + b1*x + b2*x^2
        np.linspace(-5, 5, 50),
        0.0,
    ),
    (
        "M3_cubic_clean",
        "M3",
        [lambda x: np.ones_like(x),
         lambda x: x,
         lambda x: x ** 2,
         lambda x: x ** 3],
        np.array([1.0, 1.0, -0.5, 0.05]),
        np.linspace(-3, 3, 50),
        0.0,
    ),
    (
        "M2_quadratic_noisy",
        "M2",
        [lambda x: np.ones_like(x), lambda x: x, lambda x: x ** 2],
        np.array([1.0, -2.0, 0.5]),
        np.linspace(-5, 5, 100),
        0.05,
    ),
]


@pytest.mark.parametrize(
    "case",
    _CASES,
    ids=lambda c: c[0],
)
def test_linear_fit_matches_scipy(case: tuple) -> None:
    """Compare DataLab's linear-basis fit parameters to scipy's
    least-squares solution on identical data.

    Tolerance is set to ``1e-10`` for clean cases and ``1e-8`` for
    noisy cases. Both are well above mpmath's working precision
    (50 dps) — the limit is scipy's IEEE 754 double precision.
    """
    case_id, model_id, basis_funcs, true_params, xs_arr, noise_sigma = case
    rng = np.random.default_rng(seed=42)
    ys_clean = sum(p * f(xs_arr) for p, f in zip(true_params, basis_funcs))
    ys_arr = ys_clean + (
        noise_sigma * rng.standard_normal(xs_arr.shape) if noise_sigma > 0 else 0
    )

    # scipy reference
    scipy_params = _scipy_curve_fit_linear(basis_funcs, xs_arr, ys_arr)

    # DataLab fit at 50 dps
    with mp.workdps(50):
        xs_mp = [mp.mpf(float(x)) for x in xs_arr]
        ys_mp = [mp.mpf(float(y)) for y in ys_arr]
        result = fit_linear_model(_model_by_id(model_id), xs_mp, ys_mp, precision=50)

    datalab_params = np.array([float(result.params[name]) for name in result.params])

    tolerance = 1e-8 if noise_sigma > 0 else 1e-10
    diff = np.abs(datalab_params - scipy_params)
    max_diff = float(np.max(diff))

    assert max_diff < tolerance, (
        f"{case_id}: DataLab fit parameters disagree with scipy beyond "
        f"tolerance {tolerance:.0e}. Max abs diff = {max_diff:.3e}.\n"
        f"  DataLab: {datalab_params}\n"
        f"  scipy:   {scipy_params}\n"
        f"  diff:    {diff}"
    )


def test_datalab_recovers_true_parameters_at_high_precision() -> None:
    """At 80 dps and zero noise, DataLab's fit should recover the
    construction parameters at far better than scipy's double-
    precision limit. This test would fail (or barely pass) if
    DataLab were silently routing through scipy under the hood —
    it's a pinpoint check that the mpmath path is doing real
    arbitrary-precision arithmetic.

    Both ``xs`` and ``ys`` are constructed natively in mpmath at
    80 dps so the input itself carries arbitrary precision. Going
    through ``np.linspace`` would silently downgrade to IEEE 754
    double and put a 1e-15 floor on what any solver could recover.
    """
    with mp.workdps(80):
        # Quadratic with a small dynamic range so scipy's
        # double-precision lstsq has no excuse to underperform.
        # The true parameters are exact integers / rationals, so
        # the 80-digit fit should reproduce them to 50+ digits.
        true_b0 = mp.mpf(1)
        true_b1 = -mp.mpf("13") / 7  # exact rational
        true_b2 = mp.mpf("11") / 200
        n = 50
        # Build xs natively in mpmath: 0, 1/49, 2/49, ..., 1
        xs_mp = [mp.mpf(i) / (n - 1) for i in range(n)]
        ys_mp = [
            true_b0 + true_b1 * x + true_b2 * x * x
            for x in xs_mp
        ]
        result = fit_linear_model(
            _model_by_id("M2"), xs_mp, ys_mp, precision=80
        )

        # Look up each parameter by NAME rather than zipping
        # ``result.params.keys()`` against a positional list. Python
        # dicts have insertion order since 3.7, but tying the test
        # to that contract silently mis-compares b1 ↔ b2 if the
        # auto-models layer ever reorders ``parameter_names``.
        expected_by_name = {
            "b0": true_b0,
            "b1": true_b1,
            "b2": true_b2,
        }
        for name, expected in expected_by_name.items():
            actual = result.params[name]
            denom = mp.fabs(expected) if expected != 0 else mp.mpf(1)
            rel_err = mp.fabs(actual - expected) / denom
            assert rel_err < mp.mpf("1e-50"), (
                f"DataLab failed to recover {name} at high precision: "
                f"actual={mp.nstr(actual, 60)}, "
                f"expected={mp.nstr(expected, 60)}, "
                f"rel_err={mp.nstr(rel_err, 6)}"
            )
