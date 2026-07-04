"""Icon option menus (计算 / LaTeX) for the desktop workbench.

These menus are an ADDITIONAL entry point to config controls that already live in
the config rail — never a second copy. Two rules keep the single-parent invariant
the earlier redesign broke:

* Nav actions do ``reveal-gate + focus + ensureWidgetVisible`` on the SAME in-rail
  widget; they never reparent or duplicate it.
* Checkbox mirror actions are ``checkable`` QActions kept in two-way sync with the
  real checkbox via ``blockSignals``-guarded ``toggled`` connections. The action
  drives the same checkbox object, so there is exactly one widget per option.

Build order matters: ``build_menu`` runs before ``build_ui`` (window.__init__),
so the config widgets do not exist yet when the menus are created. We therefore
create the menu + actions in :func:`build_option_menus` and defer every connection
that touches a config widget to :func:`wire_option_menus`, called at the end of
``build_ui`` once the widgets exist ("lazy/after-build" per the design spec).
"""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QStyle, QWidget

# Nav actions: menu action key -> (target widget attr, zh, en, gate kind).
# ``gate`` is one of: "none" or "latex" (check generate_latex_checkbox first).
# Result-OUTPUT controls are deliberately absent from these config menus because
# they only exist once a run populates ``self.tabs``: ``latex_engine_combo`` (LaTeX
# result subtab) and ``display_digits_spin`` / ``scientific_checkbox`` (numeric
# result subtab) all stay in the result tabs, not the menu — a menu entry would
# have to fabricate a result to reveal them. Their reachability is covered by the
# result-tab tests in test_desktop_option_reachability.py instead.
_COMPUTE_NAV = (
    ("mpmath_precision_spin", "精度位数", "Precision digits", "none"),
    ("uncertainty_digits_spin", "不确定度位数", "Uncertainty digits", "none"),
    ("parallel_mode_combo", "资源策略", "Resource policy", "none"),
    ("parallel_max_workers_spin", "最大 workers", "Max workers", "none"),
    ("parallel_reserve_cores_spin", "保留核心", "Reserve cores", "none"),
    ("parallel_nested_policy_combo", "嵌套策略", "Nested policy", "none"),
)

# LaTeX menu entries. ``checkbox`` marks a control mirrored as a checkable action;
# the rest are plain nav actions. ``generate_latex_checkbox`` is both a checkbox
# mirror (its own toggle) and the gate for the others.
_LATEX_NAV = (
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
    """Create the 计算 and LaTeX menus and their actions (no widget wiring yet).

    Returns the two menus. Actions are stashed on ``owner`` so the deferred
    :func:`wire_option_menus` (and tests) can find them:
      * ``owner._compute_menu`` / ``owner._latex_menu``
      * ``owner._option_menu_nav_actions``   {widget_attr: QAction}
      * ``owner._option_menu_check_actions``  {checkbox_attr: checkable QAction}
    """
    nav_actions: dict[str, QAction] = {}
    check_actions: dict[str, QAction] = {}
    owner._option_menu_nav_actions = nav_actions
    owner._option_menu_check_actions = check_actions
    owner._option_menu_gates = {}

    # -- 计算 (Compute) -----------------------------------------------------
    compute_menu = menubar.addMenu("计算")
    compute_menu.setIcon(_icon(owner, QStyle.StandardPixmap.SP_ComputerIcon))
    owner._register_text(compute_menu, "计算", "Compute", "setTitle")
    owner._compute_menu = compute_menu

    # 精度 group (precision + uncertainty) then a separator, then 并行/资源.
    for attr, zh, en, gate in _COMPUTE_NAV:
        if attr == "parallel_mode_combo":
            compute_menu.addSeparator()
        action = QAction(zh, owner)
        action.setMenuRole(QAction.NoRole)
        compute_menu.addAction(action)
        owner._register_text(action, zh, en, "setText")
        nav_actions[attr] = action
        owner._option_menu_gates[attr] = gate

    # -- LaTeX --------------------------------------------------------------
    latex_menu = menubar.addMenu("LaTeX")
    latex_menu.setIcon(_icon(owner, QStyle.StandardPixmap.SP_FileDialogDetailedView))
    owner._register_text(latex_menu, "LaTeX", "LaTeX", "setTitle")
    owner._latex_menu = latex_menu

    for attr, zh, en, gate, is_checkbox in _LATEX_NAV:
        action = QAction(zh, owner)
        action.setMenuRole(QAction.NoRole)
        if is_checkbox:
            action.setCheckable(True)
            check_actions[attr] = action
        else:
            nav_actions[attr] = action
        latex_menu.addAction(action)
        owner._register_text(action, zh, en, "setText")
        owner._option_menu_gates[attr] = gate

    return compute_menu, latex_menu


def wire_option_menus(owner: Any) -> None:
    """Connect nav triggers and two-way checkbox sync (widgets now exist)."""
    nav_actions: dict[str, QAction] = getattr(owner, "_option_menu_nav_actions", {})
    check_actions: dict[str, QAction] = getattr(owner, "_option_menu_check_actions", {})
    gates: dict[str, str] = getattr(owner, "_option_menu_gates", {})

    for attr, action in nav_actions.items():
        gate = gates.get(attr, "none")
        action.triggered.connect(
            lambda _checked=False, a=attr, g=gate: _navigate_to_control(owner, a, g)
        )

    for attr, action in check_actions.items():
        checkbox = getattr(owner, attr, None)
        if checkbox is None:
            continue
        _bind_check_action(action, checkbox, owner, gates.get(attr, "none"))


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


def _navigate_to_control(owner: Any, attr: str, gate: str) -> None:
    """Reveal the control's gate, then focus + scroll it into view — in place."""
    _reveal_gate(owner, gate)
    widget: QWidget | None = getattr(owner, attr, None)
    if widget is None:
        return
    scroll = getattr(owner, "workbench_config_rail", None)
    if scroll is not None and hasattr(scroll, "ensureWidgetVisible"):
        scroll.ensureWidgetVisible(widget)
    widget.setFocus()


def _reveal_gate(owner: Any, gate: str) -> None:
    if gate == "latex":
        checkbox = getattr(owner, "generate_latex_checkbox", None)
        if checkbox is not None and not checkbox.isChecked():
            checkbox.setChecked(True)
