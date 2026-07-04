"""In-menu mirror editors for the 计算 / LaTeX icon menus.

Per the 2026-07-04 spec amendment, each value option (spin/combo/line-edit) is
adjustable *inside the menu*: the menu item is a ``QWidgetAction`` hosting a NEW
mirror widget two-way synced to the SAME in-rail control. The real control never
moves — this preserves the single-parent invariant the reachability sweep guards
(no reparenting), while giving genuine in-menu adjustment.

Sync rules (recursion-safe, ``blockSignals``-guarded both directions):

* The REAL control is the single source of truth; the mirror is a view/editor.
* mirror -> real: set the real control's value with the real's signals LIVE so
  its downstream slots (schema push, dependent updates) still run — we only guard
  against the echo by comparing values before writing and blocking the *mirror*
  during the reflected update.
* real -> mirror: update the mirror with the mirror's signals blocked, so it can
  never loop back into the real control.
* Gated LaTeX editors (``latex_input_precision_spin`` / ``latex_group_size_spin``
  / ``output_file_edit``) reveal their gate (check ``generate_latex_checkbox``)
  before applying an edit, so the real control is live/visible — reusing the same
  reveal path the nav actions used.

A ``QWidgetAction`` keeps the menu open while the embedded widget has focus, so
adjustment does not dismiss the menu on every keystroke.
"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QWidget,
    QWidgetAction,
)


def build_editor_action(
    owner: Any,
    menu: Any,
    real: QWidget,
    label_zh: str,
    label_en: str,
    reveal_gate: Callable[[], None] | None,
) -> tuple[QWidgetAction, QWidget]:
    """Build a ``QWidgetAction`` hosting a labelled mirror editor for ``real``.

    ``reveal_gate`` (or ``None``) is called before a mirror edit is pushed to the
    real control, so gated controls are revealed first. Returns the action and the
    mirror widget (so callers/tests can reach the mirror).
    """
    container = QWidget(menu)
    row = QHBoxLayout(container)
    row.setContentsMargins(8, 2, 8, 2)
    row.setSpacing(8)

    label = QLabel(label_zh, container)
    owner._register_text(label, label_zh, label_en, "setText")
    row.addWidget(label)

    mirror = _build_mirror(real, container)
    row.addStretch(1)
    row.addWidget(mirror)

    # Combos carry bilingual item labels. Register the mirror with the SAME
    # translation table as the real combo so the shared _apply_language relabel
    # loop re-labels it too (the real combo's relabel blockSignals its own signals,
    # so a signal-driven refresh never fires — registration is the reliable path).
    if isinstance(mirror, QComboBox) and isinstance(real, QComboBox):
        _register_mirror_combo_i18n(owner, real, mirror)

    _wire_mirror(mirror, real, reveal_gate)

    action = QWidgetAction(menu)
    action.setDefaultWidget(container)
    return action, mirror


def _build_mirror(real: QWidget, parent: QWidget) -> QWidget:
    """Create a fresh mirror widget matching ``real``'s type and range/items."""
    if isinstance(real, QSpinBox):
        mirror = QSpinBox(parent)
        mirror.setRange(real.minimum(), real.maximum())
        mirror.setSingleStep(real.singleStep())
        mirror.setValue(real.value())
        return mirror
    if isinstance(real, QComboBox):
        mirror = QComboBox(parent)
        _sync_combo_items(real, mirror)
        mirror.setCurrentIndex(real.currentIndex())
        return mirror
    if isinstance(real, QLineEdit):
        mirror = QLineEdit(parent)
        mirror.setText(real.text())
        return mirror
    raise TypeError(f"unsupported mirror source type: {type(real).__name__}")


def _register_mirror_combo_i18n(owner: Any, real: QComboBox, mirror: QComboBox) -> None:
    """Register the mirror combo with the real combo's bilingual translation table.

    ``owner._combo_translations`` holds ``(combo, items)`` where ``items`` is the
    ``(zh, en, data)`` spec used by ``_apply_language`` to relabel on language
    change. Reusing the real combo's spec for the mirror keeps the two bilingual
    without a second translation table — matching the codebase convention.
    """
    translations = getattr(owner, "_combo_translations", None)
    if translations is None:
        return
    for combo, items in translations:
        if combo is real:
            owner._register_combo(mirror, items)
            return


def _sync_combo_items(real: QComboBox, mirror: QComboBox) -> None:
    """Rebuild ``mirror``'s items to match ``real``'s current item texts.

    Called on build and whenever the real combo is relabelled (language change),
    so the mirror stays bilingual without duplicating the translation table. The
    mirror's current index is preserved across the rebuild.
    """
    keep = mirror.currentIndex()
    mirror.blockSignals(True)
    mirror.clear()
    for i in range(real.count()):
        mirror.addItem(real.itemText(i), real.itemData(i))
    if 0 <= keep < mirror.count():
        mirror.setCurrentIndex(keep)
    mirror.blockSignals(False)


def _wire_mirror(
    mirror: QWidget, real: QWidget, reveal_gate: Callable[[], None] | None
) -> None:
    """Two-way, recursion-safe sync between ``mirror`` and ``real``."""
    if isinstance(real, QSpinBox):
        _wire_spin(mirror, real, reveal_gate)
    elif isinstance(real, QComboBox):
        _wire_combo(mirror, real, reveal_gate)
    elif isinstance(real, QLineEdit):
        _wire_line_edit(mirror, real, reveal_gate)


def _wire_spin(
    mirror: QSpinBox, real: QSpinBox, reveal_gate: Callable[[], None] | None
) -> None:
    def on_mirror(value: int) -> None:
        if reveal_gate is not None:
            reveal_gate()
        if real.value() == value:
            return
        real.setValue(value)  # real's signals stay live so downstream slots run

    def on_real(value: int) -> None:
        if mirror.value() == value:
            return
        mirror.blockSignals(True)
        mirror.setValue(value)
        mirror.blockSignals(False)

    mirror.valueChanged.connect(on_mirror)
    real.valueChanged.connect(on_real)


def _wire_combo(
    mirror: QComboBox, real: QComboBox, reveal_gate: Callable[[], None] | None
) -> None:
    def on_mirror(index: int) -> None:
        if reveal_gate is not None:
            reveal_gate()
        if real.currentIndex() == index:
            return
        real.setCurrentIndex(index)

    def on_real(index: int) -> None:
        if mirror.currentIndex() == index:
            return
        mirror.blockSignals(True)
        mirror.setCurrentIndex(index)
        mirror.blockSignals(False)

    mirror.currentIndexChanged.connect(on_mirror)
    real.currentIndexChanged.connect(on_real)
    # Item RELABELLING on language change is handled separately by registering the
    # mirror with the shared _combo_translations table (see build_editor_action) —
    # the real combo blockSignals its own relabel, so a signal-driven refresh here
    # would never fire.


def _wire_line_edit(
    mirror: QLineEdit, real: QLineEdit, reveal_gate: Callable[[], None] | None
) -> None:
    def on_mirror(text: str) -> None:
        if reveal_gate is not None:
            reveal_gate()
        if real.text() == text:
            return
        real.setText(text)

    def on_real(text: str) -> None:
        if mirror.text() == text:
            return
        mirror.blockSignals(True)
        mirror.setText(text)
        mirror.blockSignals(False)

    mirror.textChanged.connect(on_mirror)
    real.textChanged.connect(on_real)
