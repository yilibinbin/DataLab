"""Icon option menus (计算 / LaTeX) for the desktop workbench.

These menus are an ADDITIONAL entry point to config controls that already live in
the config rail — never a second copy of the REAL control. Two rules keep the
single-parent invariant the earlier redesign broke:

* Value items (spin/combo/line-edit) are IN-MENU editors: each is a
  ``QWidgetAction`` hosting a NEW *mirror* widget two-way synced to the SAME
  in-rail control (see :mod:`app_desktop.menu_option_editors`). The real control
  never moves — nothing is reparented — while the menu offers real adjustment.
* Checkbox items are ``checkable`` QActions kept in two-way sync with the real
  checkbox via ``blockSignals``-guarded ``toggled`` connections. The action drives
  the same checkbox object, so there is exactly one checkbox per option.

Build order matters: ``build_menu`` runs before ``build_ui`` (window.__init__),
so the config widgets do not exist yet when the menus are created. We therefore
create the menus + checkable actions in :func:`build_option_menus` and defer every
connection (and the value-item mirror editors, which need the real widgets) to
:func:`wire_option_menus`, called at the end of ``build_ui`` once the widgets exist
("lazy/after-build" per the design spec).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QStyle

from app_desktop.menu_option_editors import build_editor_action

# Compute-menu items in display order. Each entry: (attr, zh, en, gate).
# ``gate`` is "none" or "latex" (check generate_latex_checkbox first). A separator
# is inserted before the first parallel item to split 精度 from 并行/资源.
# Result-OUTPUT controls are deliberately absent (they only exist once a run
# populates ``self.tabs``): ``latex_engine_combo`` (LaTeX result subtab) and
# ``display_digits_spin`` / ``scientific_checkbox`` (numeric result subtab) stay in
# the result tabs; their reachability is covered by test_desktop_option_reachability.
_COMPUTE_ITEMS = (
    ("mpmath_precision_spin", "精度位数", "Precision digits", "none"),
    ("uncertainty_digits_spin", "不确定度位数", "Uncertainty digits", "none"),
    ("parallel_mode_combo", "资源策略", "Resource policy", "none"),
    ("parallel_max_workers_spin", "最大 workers", "Max workers", "none"),
    ("parallel_reserve_cores_spin", "保留核心", "Reserve cores", "none"),
    ("parallel_nested_policy_combo", "嵌套策略", "Nested policy", "none"),
)

# LaTeX-menu items in display order. ``is_checkbox`` marks a control mirrored as a
# checkable action; the rest are value items (in-menu mirror editors).
# ``generate_latex_checkbox`` is both a checkbox mirror and the gate for the others.
_LATEX_ITEMS = (
    ("generate_latex_checkbox", "生成 LaTeX 文件", "Generate LaTeX", "none", True),
    ("output_file_edit", "输出路径", "Output path", "latex", False),
    ("latex_input_precision_spin", "输入列位数", "Input digits", "latex", False),
    ("dcolumn_checkbox", "使用 dcolumn 排版", "Use dcolumn", "latex", True),
    ("latex_group_size_spin", "分组位数", "Group size", "latex", False),
    ("caption_checkbox", "使用标题", "Use caption", "latex", True),
)


def _icon(owner: Any, pixmap: QStyle.StandardPixmap):
    return owner.style().standardIcon(pixmap)


def build_option_menus(owner: Any, menubar: Any) -> tuple[QMenu, QMenu]:
    """Create the 计算 and LaTeX menus + checkable actions (no widget wiring yet).

    Value items (the in-menu mirror editors) are added later in
    :func:`wire_option_menus`, once the real config widgets exist. State stashed on
    ``owner`` so wiring and tests can find it:
      * ``owner._compute_menu`` / ``owner._latex_menu``
      * ``owner._option_menu_check_actions``   {checkbox_attr: checkable QAction}
      * ``owner._option_menu_editors``          {value_attr: mirror widget}
      * ``owner._option_menu_editor_actions``   {value_attr: QWidgetAction}
      * ``owner._option_menu_gates``            {attr: "none"|"latex"}
    """
    check_actions: dict[str, QAction] = {}
    owner._option_menu_check_actions = check_actions
    owner._option_menu_editors = {}
    owner._option_menu_editor_actions = {}
    owner._option_menu_gates = {}

    compute_menu = menubar.addMenu("计算")
    compute_menu.setIcon(_icon(owner, QStyle.StandardPixmap.SP_ComputerIcon))
    owner._register_text(compute_menu, "计算", "Compute", "setTitle")
    owner._compute_menu = compute_menu

    latex_menu = menubar.addMenu("LaTeX")
    latex_menu.setIcon(_icon(owner, QStyle.StandardPixmap.SP_FileDialogDetailedView))
    owner._register_text(latex_menu, "LaTeX", "LaTeX", "setTitle")
    owner._latex_menu = latex_menu

    # Pre-create the checkable actions so their bilingual text is registered at
    # build time (matching the other menus). They are added to the menu in the
    # correct interleaved order during wiring, alongside the value editors.
    for attr, zh, en, _gate, is_checkbox in _LATEX_ITEMS:
        if not is_checkbox:
            continue
        action = QAction(zh, owner)
        action.setMenuRole(QAction.NoRole)
        action.setCheckable(True)
        owner._register_text(action, zh, en, "setText")
        check_actions[attr] = action

    return compute_menu, latex_menu


def wire_option_menus(owner: Any) -> None:
    """Populate the menus with value editors + wire two-way sync (widgets exist)."""
    check_actions: dict[str, QAction] = getattr(owner, "_option_menu_check_actions", {})
    gates: dict[str, str] = getattr(owner, "_option_menu_gates", {})

    # -- 计算 (Compute) : all value editors, separator before 并行/资源 ------
    compute_menu: QMenu = owner._compute_menu
    for attr, zh, en, gate in _COMPUTE_ITEMS:
        if attr == "parallel_mode_combo":
            compute_menu.addSeparator()
        _add_value_editor(owner, compute_menu, attr, zh, en, gate)
        gates[attr] = gate

    # -- LaTeX : interleave checkable actions and value editors in order -----
    latex_menu: QMenu = owner._latex_menu
    for attr, zh, en, gate, is_checkbox in _LATEX_ITEMS:
        gates[attr] = gate
        if is_checkbox:
            action = check_actions[attr]
            latex_menu.addAction(action)
            checkbox = getattr(owner, attr, None)
            if checkbox is not None:
                _bind_check_action(action, checkbox, owner, gate)
        else:
            _add_value_editor(owner, latex_menu, attr, zh, en, gate)


def _add_value_editor(
    owner: Any, menu: QMenu, attr: str, zh: str, en: str, gate: str
) -> None:
    """Build + add the in-menu mirror editor QWidgetAction for one value control."""
    real = getattr(owner, attr, None)
    if real is None:
        return
    reveal = (lambda: _reveal_gate(owner, gate)) if gate != "none" else None
    action, mirror = build_editor_action(owner, menu, real, zh, en, reveal)
    menu.addAction(action)
    owner._option_menu_editor_actions[attr] = action
    owner._option_menu_editors[attr] = mirror


def _bind_check_action(action: QAction, checkbox: Any, owner: Any, gate: str) -> None:
    """Two-way sync between a checkable QAction and the SAME checkbox.

    ``blockSignals`` on the receiver prevents the echo from re-emitting and
    recursing. Initial state is seeded from the checkbox (single source of truth).

    A gated checkbox (e.g. ``dcolumn_checkbox`` / ``caption_checkbox`` with
    gate="latex") is hidden until its gate is revealed. Triggering the menu action
    must not silently flip a control the user cannot see, so on *check* we reveal
    the gate first (``generate_latex_checkbox``) — the same action both reveals the
    group and ticks the box.
    """
    action.blockSignals(True)
    action.setChecked(checkbox.isChecked())
    action.blockSignals(False)

    def on_action(checked: bool) -> None:
        if checked and gate != "none":
            _reveal_gate(owner, gate)
        if checkbox.isChecked() == checked:
            return
        checkbox.blockSignals(True)
        checkbox.setChecked(checked)
        checkbox.blockSignals(False)
        # Re-fire the checkbox's own slots (e.g. _toggle_latex_options) that the
        # blockSignals suppressed, so the gated group still reveals.
        checkbox.toggled.emit(checked)

    def on_checkbox(checked: bool) -> None:
        if action.isChecked() == checked:
            return
        action.blockSignals(True)
        action.setChecked(checked)
        action.blockSignals(False)

    action.toggled.connect(on_action)
    checkbox.toggled.connect(on_checkbox)


def _reveal_gate(owner: Any, gate: str) -> None:
    if gate == "latex":
        checkbox = getattr(owner, "generate_latex_checkbox", None)
        if checkbox is not None and not checkbox.isChecked():
            checkbox.setChecked(True)
