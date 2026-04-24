"""R10 C5 regression: AutoModel M5 (1/x series) must require positive x.

Without requires_positive_x=True, calling auto_fit on data containing 0 causes
an opaque QR-decomposition failure instead of a clean bilingual pre-fit error.
"""

from __future__ import annotations

import pytest

from fitting.auto_models import AUTO_MODELS, fit_linear_model


def _get_model(identifier: str):
    for m in AUTO_MODELS:
        if m.identifier == identifier:
            return m
    raise AssertionError(f"Model {identifier} not found")


def test_m5_definition_has_requires_positive_x():
    """The definition flag must be set, matching M4/M4B/M6/M8."""
    m5 = _get_model("M5")
    assert m5.requires_positive_x is True, (
        "M5 (1/x series) must declare requires_positive_x=True; basis 1/x is "
        "undefined at x=0 and ill-conditioned near zero."
    )


def test_m5_fit_rejects_zero_x_with_bilingual_error():
    """Running M5 against data with x=0 must raise a clean bilingual ValueError."""
    m5 = _get_model("M5")
    with pytest.raises(ValueError) as excinfo:
        fit_linear_model(
            definition=m5,
            x_data=[0.0, 1.0, 2.0, 3.0],
            y_data=[1.0, 1.0, 0.5, 0.25],
            precision=50,
        )
    msg = str(excinfo.value)
    assert " / " in msg, f"Error must be bilingual, got: {msg!r}"


def test_m5_fit_accepts_positive_x():
    """Sanity: with all x>0, M5 must still succeed."""
    m5 = _get_model("M5")
    result = fit_linear_model(
        definition=m5,
        x_data=[1.0, 2.0, 3.0, 4.0, 5.0],
        y_data=[1.0, 0.5, 0.33, 0.25, 0.2],
        precision=50,
    )
    assert result is not None
    assert "A" in result.params
