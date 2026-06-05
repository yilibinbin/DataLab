"""``LogScaleSpinner`` — regression tests.

The widget is designed for fit-parameter entry where values span
many orders of magnitude. Tests pin:
- multiplicative step on wheel / arrow keys
- modifier-scaled steps (shift coarser, ctrl finer)
- bounds clamping
- scientific-notation display fidelity
- editing via keyboard triggers parse + clamp
- ``valueChanged`` signal emitted exactly once per effective change
- initial value / setValue round-trip
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from app_desktop.log_scale_spinner import LogScaleSpinner  # noqa: E402


@pytest.fixture(scope="module")
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_initial_value_and_getter(_app):
    spinner = LogScaleSpinner(value=1.5e-6)
    assert spinner.value() == pytest.approx(1.5e-6, rel=1e-12)


def test_setvalue_clamps_to_range(_app):
    spinner = LogScaleSpinner(
        value=1.0, min_positive=1e-10, max_value=1e10
    )
    spinner.setValue(1e20)
    assert spinner.value() == 1e10
    spinner.setValue(1e-20)
    assert spinner.value() == 1e-10


def test_setvalue_negative_becomes_positive(_app):
    """The widget is documented positive-only; negatives map to abs."""
    spinner = LogScaleSpinner(value=1.0, min_positive=1e-10)
    spinner.setValue(-42)
    assert spinner.value() == 42.0


def test_setvalue_zero_clamps_to_min(_app):
    spinner = LogScaleSpinner(value=1.0, min_positive=1e-10)
    spinner.setValue(0)
    assert spinner.value() == 1e-10


def test_step_up_multiplies_by_base(_app):
    spinner = LogScaleSpinner(value=100.0, base=1.1)
    captured = []
    spinner.valueChanged.connect(captured.append)
    spinner._step(+1)
    assert spinner.value() == pytest.approx(110.0, rel=1e-9)
    assert captured == [pytest.approx(110.0, rel=1e-9)]


def test_step_down_divides_by_base(_app):
    spinner = LogScaleSpinner(value=100.0, base=1.1)
    spinner._step(-1)
    assert spinner.value() == pytest.approx(100.0 / 1.1, rel=1e-9)


def test_step_with_shift_modifier_is_coarser(_app):
    """shift-click steps ~2x via DEFAULT_SHIFT_EXP ≈ 7.27."""
    spinner = LogScaleSpinner(value=100.0, base=1.1)
    spinner._step(+1, exp=LogScaleSpinner.DEFAULT_SHIFT_EXP)
    # Expect roughly 2x
    assert 190.0 < spinner.value() < 210.0


def test_step_with_ctrl_modifier_is_finer(_app):
    spinner = LogScaleSpinner(value=100.0, base=1.1)
    spinner._step(+1, exp=LogScaleSpinner.DEFAULT_CTRL_EXP)
    # Expect barely-above-100
    assert 100.5 < spinner.value() < 101.5


def test_value_changed_signal_fires_once_per_step(_app):
    spinner = LogScaleSpinner(value=1.0)
    captured = []
    spinner.valueChanged.connect(captured.append)
    spinner._step(+1)
    spinner._step(+1)
    spinner._step(+1)
    assert len(captured) == 3


def test_value_changed_not_emitted_when_step_hits_ceiling(_app):
    """Stepping up while already at max must not re-emit."""
    spinner = LogScaleSpinner(value=1e10, max_value=1e10)
    captured = []
    spinner.valueChanged.connect(captured.append)
    spinner._step(+1)
    assert captured == []


def test_edit_finished_parses_scientific_notation(_app):
    """User typing 1.5e-8 + Enter → widget updates + emits."""
    spinner = LogScaleSpinner(value=1.0)
    captured = []
    spinner.valueChanged.connect(captured.append)
    spinner._edit.setText("1.5e-8")
    spinner._on_edit_finished()
    assert spinner.value() == pytest.approx(1.5e-8, rel=1e-12)
    assert captured == [pytest.approx(1.5e-8, rel=1e-12)]


def test_edit_finished_parses_eu_decimal(_app):
    """Pasting '1,5' from EU-formatted source should work."""
    spinner = LogScaleSpinner(value=1.0)
    spinner._edit.setText("1,5")
    spinner._on_edit_finished()
    assert spinner.value() == pytest.approx(1.5, rel=1e-12)


def test_edit_finished_rejects_garbage(_app):
    """Unparseable input reverts to displayed value (no emit)."""
    spinner = LogScaleSpinner(value=42.0)
    captured = []
    spinner.valueChanged.connect(captured.append)
    spinner._edit.setText("this is not a number")
    spinner._on_edit_finished()
    assert spinner.value() == 42.0
    assert captured == []


def test_display_shows_scientific_form_for_small_values(_app):
    spinner = LogScaleSpinner(value=1.5e-10)
    assert "e-10" in spinner._edit.text() or "1.5e-10" in spinner._edit.text()


def test_display_shows_scientific_form_for_large_values(_app):
    spinner = LogScaleSpinner(value=1.5e15, max_value=1e30)
    assert "e+15" in spinner._edit.text() or "1.5e+15" in spinner._edit.text()


def test_set_range_validates(_app):
    spinner = LogScaleSpinner()
    with pytest.raises(ValueError):
        spinner.setRange(0, 10)
    with pytest.raises(ValueError):
        spinner.setRange(10, 1)  # max < min


def test_constructor_rejects_bad_base(_app):
    with pytest.raises(ValueError):
        LogScaleSpinner(value=1.0, base=1.0)
    with pytest.raises(ValueError):
        LogScaleSpinner(value=1.0, base=0.5)


def test_constructor_rejects_bad_range(_app):
    with pytest.raises(ValueError):
        LogScaleSpinner(value=1.0, min_positive=-1)
    with pytest.raises(ValueError):
        LogScaleSpinner(value=1.0, min_positive=10, max_value=1)


def test_nan_setvalue_preserves_current(_app):
    """NaN must not corrupt the widget state."""
    import math

    spinner = LogScaleSpinner(value=1.0)
    spinner.setValue(math.nan)
    # Should still be a valid number; either unchanged or clamped.
    assert not math.isnan(spinner.value())
