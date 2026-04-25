# DataLab Numerical Validation

This document describes the numerical-correctness verification
infrastructure that proves DataLab's scientific computations agree
with independent reference implementations to documented precision.

## Why this matters

DataLab implements high-precision (mpmath) versions of:
- Sequence-acceleration extrapolation (Richardson, Wynn-eps, Shanks,
  Levin-u)
- Power-law extrapolation
- Linear-basis curve fitting (M1 linear, M2 quadratic, M3 cubic, ...)
- Symbolic Taylor 1st/2nd-order error propagation
- Weighted statistics (mean, sample/population variance, std)
- Special-function evaluation (~30 functions: Sin, Erf, Gamma, Zeta,
  Hyp2f1, BesselJ, ...) via the safe expression engine

A bug in any of these — wrong basis selection, transposed matrix,
flipped sign in a partial derivative, IEEE 754 truncation in a
"high-precision" path — would propagate silently into the final
LaTeX/plot output. Type-check tests, GUI-wiring tests, and
"function returns a number" smoke tests cannot catch this. The
**numerical validation test suite** described here cross-checks
DataLab's outputs against two independent reference systems.

## Reference systems

Two complementary references:

1. **Mathematica (wolframscript)** — for mathematics where
   Mathematica computes the exact answer at arbitrary precision:
   special-function values, sequence-acceleration limits, symbolic
   Taylor error propagation, exact-rational statistics.

2. **scipy** — for problems where IEEE 754 double precision is
   sufficient and Mathematica overhead isn't justified, primarily
   linear-basis least-squares fitting against
   ``numpy.linalg.lstsq``.

Mathematica is preferred where applicable because it computes at
arbitrary precision; scipy provides an IEEE-754-bounded second
opinion that catches accidental algorithmic regressions independent
of which CAS we trust.

## Test files

| File | Reference | Cases | What it validates |
|------|-----------|-------|-------------------|
| ``tests/test_special_functions_mathematica_reference.py`` | Mathematica | 39 + 1 drift guard | Every whitelisted special function (Sin, Erf, Gamma, Zeta, Hyp1f1, BesselJ, Airy, ...) at one or more representative arguments, agreement to 1e-30. The drift-guard test fails if a function is added to the engine whitelist without a matching fixture entry. |
| ``tests/test_extrapolation_mathematica_reference.py`` | Mathematica | 7 | Richardson on monotone series (zeta values); Wynn-eps/Shanks/Levin-u on alternating/geometric series (Leibniz, alternating-harmonic, geometric-half); power-law inversion against constructed E_inf+A·x^(-p) data. |
| ``tests/test_error_propagation_mathematica_reference.py`` | Mathematica | 10 | Taylor 1st-order propagation on linear/product/quotient/quadratic/transcendental compositions. Mathematica computes ∂f/∂x_i symbolically and assembles σ_y exactly; agreement to 1e-30. |
| ``tests/test_statistics_mathematica_reference.py`` | Mathematica | 7 | Sample/population mean+std on small int/rational data; weighted-mean with Kish-style effective-DOF variance. |
| ``tests/test_fitting_scipy_reference.py`` | scipy | 5 | DataLab vs ``numpy.linalg.lstsq`` on M1/M2/M3 with clean and noisy data; one high-precision test that constructs xs natively in mpmath and checks DataLab recovers integer/rational params to 1e-50. |
| ``tests/test_extrapolation_high_precision_convergence.py`` | Closed-form limits | 9 | Each accelerator achieves its expected high-precision convergence rate at large N (Richardson 1e-45 at N=60; Wynn 1e-50 at N=15; Levin-u 1e-23 at N=20). Catches double-precision regressions that the existing 1e-2 tolerance test would miss. |

**Total: 78 cross-validation tests** (39 special-function + 1 drift guard + 7 extrapolation + 10 error propagation + 7 statistics + 5 scipy fit + 9 high-precision convergence).

## Tolerance philosophy

Each tolerance is set deliberately, not copied from a template:

- **1e-30 (Mathematica cases)** — well below the 50-digit precision
  Mathematica generates at, with a safety margin against the
  comparison itself introducing rounding. A regression must drop the
  output to ≤30 significant digits to fail.

- **1e-10 (scipy linear fits, clean data)** — close to scipy's
  IEEE 754 double-precision floor. A regression must push DataLab's
  output more than ~5 orders of magnitude away from scipy to fail.

- **Per-method tolerance for accelerators** — calibrated to each
  algorithm's intrinsic 10/15/30-term convergence rate, then
  loosened by 1 order of magnitude. See the comments in
  ``test_extrapolation_high_precision_convergence.py`` for the
  empirical-measurement methodology.

## Mathematica fixtures

Mathematica reference values are committed as JSON under
``tests/fixtures/mathematica_reference/<area>/ground_truth.json``.

Each subdirectory has two files:
- ``generate.wls`` — Wolfram Language script that prints the
  ground-truth JSON to stdout. Re-running it regenerates the JSON
  byte-for-byte.
- ``ground_truth.json`` — the committed reference data; tests read
  this. Tests do **not** call wolframscript at runtime.

### Regenerating

Requires ``wolframscript`` on PATH (Mathematica ≥ 13.0 recommended)::

    cd tests/fixtures/mathematica_reference
    bash generate_all.sh

The script writes the JSON files in place. Commit them whenever you
change a ``generate.wls`` (e.g. add a new test case).

If wolframscript isn't available, the existing committed JSON is
sufficient for running the test suite — only regeneration needs
Mathematica.

### Pitfalls observed during fixture authoring

These are documented in the .wls files but worth noting in one
place because they're common gotchas:

1. **Variable-name shadowing in `Module`**: a loop variable named
   ``v`` collides with a Module local of the same name, so
   ``D[expr, v]`` differentiates against the wrong symbol. Always
   pick distinct names (we use ``var`` for the loop).

2. **Mathematica reserved symbols**: ``I`` (imaginary unit), ``E``
   (Euler's number), ``Pi`` are protected. Using ``I`` as a current
   variable in Ohm's law silently produces complex-number results.
   Rename to ``Iv``, ``Ek``, etc.

3. **Decimal literals lose precision before RealDigits**: a fixture
   input like ``"3.14"`` becomes a machine-precision real with only
   ~17 base-10 digits, after which ``RealDigits[..., 50]`` returns
   33 ``Indeterminate`` digits. Always write rationals
   (``"314/100"``) or integers in fixtures and let Mathematica's
   exact-arithmetic layer carry full precision until the final
   ``N[..., 50]`` numericalisation.

4. **mpmath default dps truncates fixture strings**: the test
   loader must do ``with mp.workdps(80): expected = mp.mpf(s)`` —
   constructing ``mp.mpf("0.84147...50digits")`` outside the dps
   context truncates to ~17 digits.

## scipy fitting tests

scipy is a hard dependency only for the fitting tests; both
``scipy.optimize`` and ``numpy`` are gated by
``pytest.importorskip``, so a CI runner without them simply skips
those tests rather than failing collection. ``scipy>=1.16`` is
recommended; older versions should also work.

The fitting tests build the same data with both numpy lambdas (for
scipy) and mpmath constructions (for DataLab), then compare the
fitted parameters. The clean-data tolerance is ``1e-10`` (well
above scipy's ``1e-15`` IEEE 754 floor); the noisy-data tolerance
is ``1e-8``.

The ``test_datalab_recovers_true_parameters_at_high_precision``
test bypasses scipy and constructs ``xs`` natively in mpmath at 80
dps, then asserts DataLab's fit recovers the integer/rational
construction parameters to 1e-50. A test failure here means
DataLab's "high-precision" path is silently truncating to double
somewhere — a load-bearing claim of the project.

## Adding new validation cases

### Special functions

If you add a function to
``datalab_latex/expression_engine.py:_ALLOWED_FUNCTIONS``:

1. Add a case to
   ``tests/fixtures/mathematica_reference/special_functions/generate.wls``.
2. Run ``wolframscript -file generate.wls > ground_truth.json``.
3. Run ``pytest tests/test_special_functions_mathematica_reference.py``.

The ``test_fixture_covers_every_whitelisted_function`` drift guard
will fail loudly if you forget step 1.

### Extrapolation methods

If you add a new accelerator method or change the tolerances:

1. Edit the ``methods`` list in
   ``tests/fixtures/mathematica_reference/extrapolation/generate.wls``
   to declare which series the new method should handle.
2. Add a tolerance row to ``_METHOD_TOLERANCE`` in
   ``tests/test_extrapolation_mathematica_reference.py``.
3. Re-run ``wolframscript`` and ``pytest``.

### New error-propagation expressions

Add a case to ``error_propagation/generate.wls``. The script
computes the symbolic ∂f/∂x_i automatically, so you only need
to supply the formula (in DataLab's Mathematica-style syntax),
the variable list, and the (values, sigmas) maps.

### New scipy fit cases

Append a tuple to ``_CASES`` in
``tests/test_fitting_scipy_reference.py``. Each tuple specifies
the model identifier, the basis functions as numpy lambdas, the
true parameters, the x range, and the noise level.

## Continuous integration

These tests run as part of the standard ``pytest`` invocation —
they are NOT marked ``slow`` and complete in under 5 seconds total.
They DO require:
- ``mpmath`` (already a hard dep)
- ``scipy`` and ``numpy`` for the fitting tests (gated by
  ``importorskip``)
- ``wolframscript`` only for *regenerating* fixtures, not for
  running tests against committed JSON
