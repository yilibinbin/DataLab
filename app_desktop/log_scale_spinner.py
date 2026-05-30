"""Log-scale numeric spinner widget (Phase 2 #9).

QDoubleSpinBox + wheel/arrow keys step by a **multiplicative** factor
rather than the additive step standard QDoubleSpinBox provides. Fit
parameter guesses routinely span many orders of magnitude (``k = 1e-8``
for chemistry rate constants; ``N = 1e23`` for Avogadro-scale counts),
so ``0.01``-step linear tweaking is useless. A log-step spinner lets
the user halve/double, or ±10%, with a single click or scroll.

Design goals:
- Scroll / arrow key → step by ``base`` multiplier (default 1.1).
- Shift-modifier → coarser step (``base ** shift_coarse``).
- Ctrl-modifier → finer step (``base ** ctrl_fine``).
- Zero/negative values are clamped to ``min_positive`` on a step; the
  widget is intended for positive-valued fit parameters. Callers with
  potentially-zero parameters should use a different widget.
- Scientific-notation display (``{val:.6g}``) so 1.5e-8 stays readable.
- ``valueChanged`` emits on every step so the fit-preview can repaint
  live.

Not a drop-in QDoubleSpinBox replacement — the rendering is a plain
``QLineEdit`` with decoration buttons, not a spin box with
QAbstractSpinBox internals. Chose this path because QDoubleSpinBox
forces a linear-step API that can't be cleanly subclassed on PySide6
6.10 (the step functions are called recursively from Qt's C++ layer).
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator, QKeyEvent, QWheelEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QWidget,
)

__all__ = ["LogScaleSpinner"]


class LogScaleSpinner(QWidget):
    """Positive-valued numeric input with multiplicative step buttons."""

    valueChanged = Signal(float)

    # Default step multipliers. 1.1 ≈ 10 %; the modifier scales take
    # that to ~2× (shift) and ~1 % (ctrl) per step.
    DEFAULT_BASE = 1.1
    DEFAULT_SHIFT_EXP = 7.27  # 1.1 ** 7.27 ≈ 2.0
    DEFAULT_CTRL_EXP = 0.10  # 1.1 ** 0.10 ≈ 1.01

    def __init__(
        self,
        value: float = 1.0,
        min_positive: float = 1e-30,
        max_value: float = 1e30,
        base: float = DEFAULT_BASE,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        if base <= 1.0:
            raise ValueError(f"base must be > 1, got {base}")
        if min_positive <= 0:
            raise ValueError(
                f"min_positive must be positive, got {min_positive}"
            )
        if max_value <= min_positive:
            raise ValueError("max_value must exceed min_positive")
        self._base = float(base)
        self._min = float(min_positive)
        self._max = float(max_value)
        self._value = max(self._min, min(self._max, abs(float(value)) or self._min))

        self._edit = QLineEdit(self)
        self._edit.setValidator(
            QDoubleValidator(-math.inf, math.inf, 12, self)
        )
        self._edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._edit.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._edit.installEventFilter(self)
        self._edit.editingFinished.connect(self._on_edit_finished)

        self._down = QPushButton("÷", self)
        self._up = QPushButton("×", self)
        for btn in (self._down, self._up):
            btn.setFixedWidth(24)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._down.clicked.connect(lambda: self._step(-1))
        self._up.clicked.connect(lambda: self._step(+1))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self._edit, 1)
        layout.addWidget(self._down)
        layout.addWidget(self._up)

        self._refresh_display()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def value(self) -> float:
        return self._value

    def setValue(self, value: float) -> None:  # noqa: N802 - Qt naming
        """Set without emitting ``valueChanged`` — use ``_set_and_emit``
        for user-driven updates."""
        v = self._clamp(float(value))
        if v == self._value:
            return
        self._value = v
        self._refresh_display()

    def setRange(self, min_positive: float, max_value: float) -> None:  # noqa: N802
        if min_positive <= 0 or max_value <= min_positive:
            raise ValueError("invalid range")
        self._min = float(min_positive)
        self._max = float(max_value)
        self.setValue(self._value)  # re-clamp

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):  # noqa: N802 - Qt naming
        """Intercept wheel / arrow-up / arrow-down on the QLineEdit.

        Qt emits these to the focused child widget; we route them into
        the step logic with modifier-aware scaling.
        """
        if obj is self._edit:
            et = event.type()
            if et == event.Type.Wheel:
                self._handle_wheel(event)
                return True
            if et == event.Type.KeyPress:
                key = event.key()
                if key == Qt.Key.Key_Up:
                    self._handle_key_step(event, +1)
                    return True
                if key == Qt.Key.Key_Down:
                    self._handle_key_step(event, -1)
                    return True
        return super().eventFilter(obj, event)

    def _handle_wheel(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        direction = 1 if delta > 0 else -1
        exp = self._modifier_exponent(event.modifiers())
        self._step(direction, exp=exp)

    def _handle_key_step(self, event: QKeyEvent, direction: int) -> None:
        exp = self._modifier_exponent(event.modifiers())
        self._step(direction, exp=exp)

    def _modifier_exponent(self, mods) -> float:
        # Shift → coarser; Ctrl (Cmd on macOS) → finer. Both together
        # cancel out to the base step.
        has_shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        has_ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        if has_shift and not has_ctrl:
            return self.DEFAULT_SHIFT_EXP
        if has_ctrl and not has_shift:
            return self.DEFAULT_CTRL_EXP
        return 1.0

    def _step(self, direction: int, exp: float = 1.0) -> None:
        if direction == 0:
            return
        factor = self._base ** (exp * direction)
        self._set_and_emit(self._value * factor)

    def _set_and_emit(self, value: float) -> None:
        v = self._clamp(value)
        if v == self._value:
            return
        self._value = v
        self._refresh_display()
        self.valueChanged.emit(v)

    def _clamp(self, value: float) -> float:
        if math.isnan(value):
            return self._value
        # Only support positive values — a user typing 0 or negative
        # gets clamped to min_positive. Callers that need signed
        # values should use a plain QLineEdit + QDoubleValidator.
        return max(self._min, min(self._max, abs(value) or self._min))

    def _on_edit_finished(self) -> None:
        text = self._edit.text().strip()
        if not text:
            self._refresh_display()
            return
        # Accept scientific notation and locale-EU comma decimals.
        # Reuse ``shared.parsing`` for consistency with the clipboard
        # paste flow so a user can paste a number as well as type it.
        from shared.parsing import LocaleHint, _parse_numeric

        parsed = _parse_numeric(text, LocaleHint.US)
        if parsed is None:
            parsed = _parse_numeric(text, LocaleHint.EU)
        if parsed is None:
            self._refresh_display()
            return
        self._set_and_emit(parsed)

    def _refresh_display(self) -> None:
        # "{:.6g}" keeps big and small numbers readable without the
        # trailing .0 that "{:g}" keeps for integers.
        self._edit.blockSignals(True)
        self._edit.setText(f"{self._value:.6g}")
        self._edit.blockSignals(False)
