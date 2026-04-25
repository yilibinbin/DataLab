DataLab numerical-validation ground truth (Mathematica reference)
=================================================================

This directory holds Mathematica-computed reference values that the
numerical-validation tests compare against. The goal is independent
verification: DataLab's mpmath answers must agree with Mathematica's
arbitrary-precision answers to a documented number of significant
digits, otherwise the test fails loudly.

Layout
------

Each subdirectory covers one functional area of DataLab:

- ``special_functions/`` — Sin, Cos, Erf, Gamma, Zeta, BesselJ,
  Hyp1f1, Hyp2f1, etc. (the whitelist in
  ``datalab_latex/expression_engine.py``).
- ``extrapolation/`` — Richardson, Wynn-epsilon, Shanks, Levin-u
  applied to series whose limits Mathematica can compute exactly
  (zeta values, log(2), pi, ...).
- ``error_propagation/`` — Taylor 1st and 2nd order error propagation
  on small symbolic expressions whose partial derivatives Mathematica
  evaluates symbolically.
- ``statistics/`` — Weighted means, weighted std, chi^2 test
  statistics on small reference samples.

Each subdirectory contains exactly two files:

- ``generate.wls`` — A Wolfram Language script that prints the
  ground-truth JSON to stdout. Re-running it regenerates
  ``ground_truth.json`` byte-for-byte.
- ``ground_truth.json`` — The committed reference data. Tests load
  this; they do **not** call wolframscript at test time, so the
  test suite runs without Mathematica.

JSON shape
----------

::

    {
      "metadata": {
        "generator": "<script path>",
        "mathematica_version": "...",
        "precision_digits": 50,
        "description": "<one-line area description>"
      },
      "cases": [
        {
          "id": "Sin[1]",
          "function": "Sin",
          "args": [1],
          "value": "0.84147098480789650665250232163029899962256306079837...",
          "context": "trig"
        },
        ...
      ]
    }

The ``value`` field is always a decimal string; the test loads it
as ``mp.mpf(s)`` and compares to DataLab's output via
``mp.almosteq(actual, expected, rel_eps=1e-30, abs_eps=1e-30)``.

Regenerating
------------

Requires ``wolframscript`` on PATH (Mathematica >= 13.0 recommended)::

    cd tests/fixtures/mathematica_reference
    bash generate_all.sh

The script writes the JSON files in place. Commit them along with any
schema or precision changes.

If wolframscript is unavailable, the existing ``ground_truth.json``
files are sufficient for running the test suite — only regeneration
needs Mathematica.
