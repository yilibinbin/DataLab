"""P1-3: MCMC posterior refinement is reachable through datalab_core.run_fitting
(so web/CLI get it, not just the desktop worker).

Coverage matches desktop: refinement runs for models that carry a live evaluator
(polynomial / inverse_power auto-models) and self-skips for custom/pade/
power_limit. These tests pin that contract and the serialization safety of the
attached diagnostics.
"""

from __future__ import annotations

import json

import pytest

# emcee is optional; the whole feature self-skips without it, so gate the tests.
pytest.importorskip("emcee")


def _polynomial_request(refine: bool):
    from datalab_core.fitting import build_fitting_request

    # Well-conditioned line y = 2x + 1 so the posterior is sane and the MCMC
    # pre-flight log-probabilities are finite.
    return build_fitting_request(
        model_type="polynomial",
        headers=("x", "y"),
        data_rows=(
            ("0", "1.0"),
            ("1", "3.0"),
            ("2", "5.0"),
            ("3", "7.0"),
            ("4", "9.0"),
        ),
        variable_map={"x": "x"},
        target_column="y",
        poly_degree=1,
        refine_with_mcmc=refine,
        precision_digits=50,
        request_id="fit-poly-mcmc",
    )


def test_run_fitting_polynomial_with_mcmc_attaches_refinement() -> None:
    from datalab_core.fitting import run_fitting
    from datalab_core.results import ResultStatus

    result = run_fitting(_polynomial_request(refine=True))

    assert result.status is ResultStatus.SUCCEEDED
    details = result.payload["fit_result"]["details"]
    assert "mcmc_refinement" in details, "MCMC refinement not attached in core"
    refinement = details["mcmc_refinement"]
    for key in ("medians", "lo_ci", "hi_ci", "acceptance_fraction"):
        assert key in refinement, f"missing {key} in mcmc_refinement"


def test_run_fitting_without_flag_has_no_mcmc() -> None:
    from datalab_core.fitting import run_fitting
    from datalab_core.results import ResultStatus

    result = run_fitting(_polynomial_request(refine=False))

    assert result.status is ResultStatus.SUCCEEDED
    details = result.payload["fit_result"]["details"]
    assert "mcmc_refinement" not in details


def test_run_fitting_custom_with_mcmc_self_skips() -> None:
    # A custom model has no live evaluator in details, so refinement must skip
    # gracefully (no crash, no mcmc_refinement) — the documented limitation.
    from datalab_core.fitting import build_fitting_request, run_fitting
    from datalab_core.results import ResultStatus

    request = build_fitting_request(
        model_type="custom",
        headers=("x", "y"),
        data_rows=(("0", "1.0"), ("1", "3.0"), ("2", "5.0"), ("3", "7.0")),
        variable_map={"x": "x"},
        target_column="y",
        model_expr="a*x + b",
        parameter_names=("a", "b"),
        refine_with_mcmc=True,
        precision_digits=50,
        request_id="fit-custom-mcmc",
    )

    result = run_fitting(request)

    assert result.status is ResultStatus.SUCCEEDED
    details = result.payload["fit_result"]["details"]
    assert "mcmc_refinement" not in details


def test_mcmc_refinement_payload_is_json_serializable() -> None:
    # The attached diagnostics (and any corner plot) must survive the fit-result
    # serializer — no raw bytes. The corner plot is stored base64, not bytes.
    import copy

    from datalab_core.fitting import run_fitting

    result = run_fitting(_polynomial_request(refine=True))
    details = result.payload["fit_result"]["details"]
    assert "mcmc_refinement" in details
    # The payload is stored as the core's immutable FrozenJsonDict; deep-copying
    # unwraps it to plain dict/list, which is the JSON-safe representation the
    # frontends serialize. It must round-trip with no raw bytes.
    plain = copy.deepcopy(dict(result.payload["fit_result"]))
    json.dumps(plain)
    if "mcmc_corner_png_b64" in details:
        assert isinstance(details["mcmc_corner_png_b64"], str)
