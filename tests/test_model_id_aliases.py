"""``fitting.auto_models.MODEL_ID_ALIASES`` coverage + correctness.

Pins the invariant: every identifier in ``AUTO_MODELS`` must be
addressable via at least one friendly alias, so users who don't
memorise ``M1``..``M8`` can still reference every built-in model
from the CLI or the SSE endpoint.
"""

from __future__ import annotations


def test_every_auto_model_identifier_has_a_friendly_alias():
    """Coverage: MODEL_ID_ALIASES's values must include every
    AUTO_MODELS identifier. Regression-guards the completeness
    flagged by the Phase B depth review."""
    from fitting.auto_models import AUTO_MODELS, MODEL_ID_ALIASES

    aliased_ids = set(MODEL_ID_ALIASES.values())
    all_ids = {d.identifier for d in AUTO_MODELS}
    missing = all_ids - aliased_ids
    assert not missing, (
        f"MODEL_ID_ALIASES does not cover identifier(s): {sorted(missing)}. "
        "Add a friendly alias in fitting/auto_models.py so users can "
        "select this model from the CLI / SSE endpoint."
    )


def test_resolve_model_identifier_passes_through_canonical_ids():
    """``M1`` stays ``M1`` — aliases only rewrite friendly names."""
    from fitting.auto_models import AUTO_MODELS, resolve_model_identifier

    for d in AUTO_MODELS:
        assert resolve_model_identifier(d.identifier) == d.identifier


def test_resolve_model_identifier_handles_none_and_empty():
    from fitting.auto_models import resolve_model_identifier

    # The annotation says ``str`` but defensive coercion is
    # documented in the body — confirm it doesn't crash.
    assert resolve_model_identifier("") == ""
    assert resolve_model_identifier(None) == ""  # type: ignore[arg-type]


def test_resolve_model_identifier_is_case_insensitive_for_aliases():
    from fitting.auto_models import resolve_model_identifier

    assert resolve_model_identifier("linear") == "M1"
    assert resolve_model_identifier("LINEAR") == "M1"
    assert resolve_model_identifier("Linear") == "M1"


def test_resolve_model_identifier_preserves_unknown_strings():
    """Unknown strings pass through so the SSE endpoint can emit
    its own 'unknown model' error with the exact input echoed back."""
    from fitting.auto_models import resolve_model_identifier

    assert resolve_model_identifier("frobnicate") == "frobnicate"
    assert resolve_model_identifier("M99") == "M99"


def test_all_aliases_point_to_real_identifiers():
    """Dangling alias detection: every value in MODEL_ID_ALIASES
    must be a real AUTO_MODELS identifier. A typo like
    'exp_basis': 'M7C' (non-existent) would silently fail lookups
    with 'unknown model M7C'."""
    from fitting.auto_models import AUTO_MODELS, MODEL_ID_ALIASES

    all_ids = {d.identifier for d in AUTO_MODELS}
    dangling = {
        alias: target
        for alias, target in MODEL_ID_ALIASES.items()
        if target not in all_ids
    }
    assert not dangling, (
        f"MODEL_ID_ALIASES has dangling targets: {dangling}. "
        "Every alias value must match an AUTO_MODELS identifier."
    )
