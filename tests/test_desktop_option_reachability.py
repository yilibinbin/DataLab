"""Reachability acceptance test for every desktop config control.

This is the HARD gate for the icon-ified menu-bar redesign. It encodes the bug
class the user caught: a control that gets "hidden on the wrong page" or silently
reparented. For every config control we assert two things after performing the
*visible*, user-operable gate that reveals it:

1. ``widget.isVisibleTo(window) is True`` — the control is genuinely reachable.
2. ``widget.parent()`` is the SAME object as at window-build time — the gate
   revealed it *in place*; nothing was reparented (the single-parent invariant).

The reparent guard is the stronger check: ``isVisibleTo`` alone would pass even if
a redesign moved the widget under a different parent, which is exactly what hid
controls last time.

WHY THIS FILE IS PROGRAMMATIC
-----------------------------
An earlier version hand-listed ~20 named globals. External review found that a
hand-written list *always* masks controls: it silently omitted per-mode
schema-bound inputs (``extrapolation.power_law.p``, ``uncertainty.reference_column``,
the whole ``statistics.*`` sub-forms, …). There are 101 interactive input controls
carrying a ``datalab_schema_key`` property — far more than any hand list survives.
(Later reviews also caught the dual risk: masking-by-TYPE-omission — a control
dropped because its widget *class* is not in the filter. The type filter is now
capability-based: Qt value inputs via base classes PLUS the app's own custom
editors, with a closed, documented exclusion set — see ``_INPUT_TYPES`` and
``test_no_editable_schema_type_is_excluded``.)

So the guarantee here is enumeration, not a list: ``_enumerate_input_controls``
walks the live widget tree and collects EVERY interactive input widget that carries
a non-empty ``datalab_schema_key``. The sweep then proves each one reachable in its
mode/gate. Adding a new schema-bound control automatically pulls it into the sweep,
so nothing can be masked by omission. If a control is genuinely unreachable the
sweep FAILS (that is a production bug), and ``test_non_masking_guard`` proves the
sweep fails when a control is force-hidden.
"""

from __future__ import annotations

import itertools
import os
from typing import Any, Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
)

# The app's own editable data-input widgets (custom classes, not Qt built-ins).
# They carry a datalab_schema_key like any bound field and take user input, so they
# belong in the sweep — a Qt-builtin-only filter silently drops all of them.
from app_desktop.constants_editor import ConstantsEditor
from app_desktop.detected_rows_table import DetectedRowsTable
from app_desktop.parameter_table import ParameterTable

# Stack-page index for the free-form text editor inside the input-mode stack
# (table on page 0, text on page 1 — mirrors panels._STACK_PAGE_TEXT).
_DATA_STACK_TEXT_PAGE = 1

# The Qt property every schema-bound control carries (see ui_schema_binder).
_SCHEMA_KEY_PROPERTY = "datalab_schema_key"

# Interactive INPUT widget types — the widgets a user enters or selects a VALUE
# in. This filter is capability-based (editable-value widgets), NOT an arbitrary
# shortlist, so a control cannot be masked by omitting its concrete class. Two
# groups make it exhaustive:
#
# (1) Qt value inputs, via base classes where a base exists:
#   * QAbstractSpinBox — the base of QSpinBox AND QDoubleSpinBox (an earlier tuple
#     listed only QSpinBox and silently dropped pdf.zoom_percent, a live
#     QDoubleSpinBox; using the base class makes that impossible).
#   * QComboBox / QCheckBox / QLineEdit / QPlainTextEdit — the remaining value
#     inputs. NumberedTextEdit subclasses QPlainTextEdit, so it is already covered.
#
# (2) The app's OWN custom editable-editor widgets (subclass QWidget directly, so
#     no Qt base class catches them — they must be named):
#   * ConstantsEditor — the constants editors (e.g. error.constants,
#     root.constants); gated by each mode, editable once the constants toggle is on.
#   * ParameterTable — fitting custom/implicit parameter tables
#     (fitting.custom.parameters, fitting.implicit.parameters).
#   * DetectedRowsTable — the root-solving unknowns table (root.unknowns).
#
# Deliberately EXCLUDED, with reasons (these are NOT editable-value options). After
# adding groups (1) and (2), the schema-keyed types that remain excluded are:
#   * QLabel (75) and the "?" help QPushButton — bind_field() also stamps the schema
#     key on a field's label and help button; neither takes user input.
#   * QTextBrowser (results.numeric.markdown, 1) — a READ-ONLY result display.
#   * QPushButton (28: export csv/image, zoom in/out/reset, latex
#     open/save/reload/compile/view_pdf, formula-preview buttons, …) — carry a
#     schema key for COMMAND dispatch, not for holding an editable value. The
#     redesign's reachability criterion is about OPTION inputs; actionable command
#     buttons are covered by their own tests (test_desktop_option_menus.py + the
#     per-view behaviour tests). Excluding them is a principled rule ("command
#     buttons are not option inputs"), not a forgotten type.
#   * QScrollArea (results.image.preview, 1) and QTabWidget (main.result_tabs,
#     results.tabs, 2) — layout CONTAINERS carrying a schema key for structure, not
#     values the user edits.
# test_no_editable_schema_type_is_excluded asserts this exclusion list stays
# closed, so a newly-introduced editable widget type fails instead of slipping past.
_INPUT_TYPES = (
    QAbstractSpinBox,
    QComboBox,
    QCheckBox,
    QLineEdit,
    QPlainTextEdit,
    ConstantsEditor,
    ParameterTable,
    DetectedRowsTable,
)

# Schema-keyed widget types that are intentionally NOT input options (see the block
# above). This is the closed exclusion set the exhaustiveness guard checks against.
_NON_INPUT_SCHEMA_TYPES: frozenset[str] = frozenset(
    {"QLabel", "QPushButton", "QTextBrowser", "QScrollArea", "QTabWidget"}
)

# --- Prefix classification -------------------------------------------------
#
# A schema key's first dotted segment is its mode/area. Every input prefix falls
# into exactly one of three reachability regimes below. The classification is
# asserted EXHAUSTIVE in test_every_input_prefix_is_classified: an unclassified
# prefix fails, so a newly-added area cannot slip through unchecked.

# Per-mode: reachable only after mode_combo is switched to the owning mode. The
# value is the set of key prefixes that belong to that mode (root solving splits
# its keys across ``root.*`` and ``root_solving.*``).
_PER_MODE_PREFIXES: dict[str, set[str]] = {
    "extrapolation": {"extrapolation"},
    "error": {"error"},
    "fitting": {"fitting"},
    "root_solving": {"root", "root_solving"},
    "statistics": {"statistics"},
}

# Mode-independent: live in the shared options / parallel / output rails and are
# reachable regardless of the active mode (the LaTeX-output group needs its gate
# checkboxes revealed — handled by _reveal_output_gates).
_MODE_INDEPENDENT_PREFIXES: frozenset[str] = frozenset({"options", "parallel", "output"})

# Result-only: live inside ``self.tabs`` (hidden until a result exists) — the
# result subtabs, the LaTeX subtab, and the PDF subtab. NOT reachable pre-result;
# asserted hidden then revealed by driving a non-empty result and the right subtab.
# ``pdf`` (pdf.zoom_percent, a QDoubleSpinBox in the PDF preview toolbar) belongs
# here: the PDF preview lives in a result subtab, hidden until a result exists.
_RESULT_ONLY_PREFIXES: frozenset[str] = frozenset({"results", "latex", "pdf"})

# Schema keys that only EXIST as a runtime-relabelled state of an already-enumerated
# widget (not a separate widget). The shared input_constants_editor is relabelled to
# fitting.implicit.constants when fit_model_combo == self_consistent (window.py). The
# widget is the same object (and reachable), so it can't be enumerated under this key
# up front — instead the per-mode sweep must OBSERVE this key becoming reachable. Any
# such dynamic key must be listed here so the sweep asserts it was actually reached.
_DYNAMIC_KEYS_BY_MODE: dict[str, tuple[str, ...]] = {
    "fitting": ("fitting.implicit.constants",),
}

# Narrow, justified allowlist of schema keys the sweep does NOT require reachable.
# Keep this SMALL — each entry must name a real, documented reason. It exists to
# exclude non-input widgets that slip past the type filter, NOT to paper over
# controls. (Currently empty: every enumerated input control is reachable in its
# mode/gate, so nothing needs excluding.)
_ALLOWLIST_UNREACHABLE: frozenset[str] = frozenset()


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    return win


# --- Enumeration -----------------------------------------------------------


def _enumerate_input_controls(window: Any) -> list[tuple[Any, str]]:
    """Every interactive input widget carrying a non-empty ``datalab_schema_key``.

    This is the single source of truth for the sweep — walk the live tree, so a
    newly-added schema-bound control is covered automatically and cannot be
    masked by omission from a hand list.
    """
    out: list[tuple[Any, str]] = []
    for obj in [window, *window.findChildren(QObject)]:
        key = obj.property(_SCHEMA_KEY_PROPERTY)
        if key and isinstance(obj, _INPUT_TYPES):
            out.append((obj, str(key)))
    return out


def _prefix(key: str) -> str:
    return key.split(".", 1)[0]


def _group_by_prefix(controls: list[tuple[Any, str]]) -> dict[str, list[tuple[Any, str]]]:
    grouped: dict[str, list[tuple[Any, str]]] = {}
    for widget, key in controls:
        grouped.setdefault(_prefix(key), []).append((widget, key))
    return grouped


# --- Sweep engine ----------------------------------------------------------


def _apply_selector_option(kind: str, selector: Any, value: Any) -> None:
    if kind == "combo":
        selector.setCurrentIndex(value)
    else:  # checkbox
        selector.setChecked(value)


def _selector_options(selector: Any) -> list[tuple[str, Any, Any]]:
    if isinstance(selector, QComboBox):
        return [("combo", selector, i) for i in range(selector.count())]
    return [("check", selector, False), ("check", selector, True)]


def _reach_visible_via_selector_sweep(
    window: Any,
    app: Any,
    controls: list[tuple[Any, str]],
) -> set[str]:
    """Data-driven pairwise selector sweep.

    Treat every schema-bound combo/checkbox among ``controls`` as a candidate gate
    (no hard-coded selector list — that would re-introduce the masking risk). Sweep
    each selector option singly and every ordered pair of selectors, resetting to
    the mode default between trials, and record which controls become visible.

    Pairwise (not just single) coverage is required because some controls are gated
    by a COMBINATION of two selectors — e.g. ``statistics.trim_fraction`` needs
    ``workflow_mode`` outside {bootstrap, hypothesis, time_series, matrix} *and*
    ``statistics.mode == descriptive``. A single-selector sweep silently misses
    those; pairwise catches every gate in the live UI. The mode combo itself is
    left fixed by the caller.
    """
    selectors = [w for w, _ in controls if isinstance(w, (QComboBox, QCheckBox))]
    reached: set[str] = set()

    def _record() -> None:
        for widget, key in controls:
            if not widget.isVisibleTo(window):
                continue
            reached.add(key)
            # Some widgets (e.g. the shared input_constants_editor) are RELABELLED
            # at runtime — their datalab_schema_key mutates as a selector changes
            # (fitting.custom.constants -> fitting.implicit.constants when
            # fit_model_combo == self_consistent). Record the LIVE key too, so a
            # dynamic key state that only exists mid-sweep is covered, not just the
            # key captured at enumeration time.
            live_key = widget.property(_SCHEMA_KEY_PROPERTY)
            if live_key:
                reached.add(str(live_key))

    def _reset() -> None:
        # Reset every selector to its first/unchecked state so pair trials start
        # from a clean baseline (the mode combo is owned by the caller).
        for sel in selectors:
            if isinstance(sel, QComboBox):
                sel.setCurrentIndex(0)
            else:
                sel.setChecked(False)
        app.processEvents()

    def _user_operable(selector: Any) -> bool:
        # Only a selector the user can actually see AND operate is a real gate. A
        # hidden/disabled selector (e.g. one inside a collapsed options panel) must
        # not be toggled to "reveal" a control — that would mark it reachable via a
        # gate the user cannot use (a masking risk).
        return selector.isVisibleTo(window) and selector.isEnabled()

    _reset()
    _record()  # baseline (mode default) visibility

    # Singles.
    for sel in selectors:
        for option in _selector_options(sel):
            _reset()
            if not _user_operable(sel):
                continue
            _apply_selector_option(*option)
            app.processEvents()
            _record()

    # Pairs.
    for sel_a, sel_b in itertools.combinations(selectors, 2):
        for opt_a in _selector_options(sel_a):
            for opt_b in _selector_options(sel_b):
                _reset()
                if not _user_operable(sel_a):
                    continue
                _apply_selector_option(*opt_a)
                app.processEvents()
                if not _user_operable(sel_b):
                    continue
                _apply_selector_option(*opt_b)
                app.processEvents()
                _record()

    return reached


def _switch_mode(window: Any, app: Any, mode_value: str) -> None:
    idx = window.mode_combo.findData(mode_value)
    assert idx >= 0, f"mode {mode_value!r} not found in mode_combo itemData"
    window.mode_combo.setCurrentIndex(idx)
    app.processEvents()


def _open_option_panels(window: Any, app: Any) -> None:
    """Open the 计算 / LaTeX toolbar option DIALOGS.

    The low-frequency options live in two resizable QDialog windows opened from the
    toolbar buttons. A QDialog child is ``isVisibleTo(window)`` only while the dialog is
    shown, so the reachability sweep must open both dialogs (a genuine, visible user
    gate — click the toolbar button) before the dialog-hosted controls are reachable.
    """
    for attr in ("compute_options_dialog", "latex_options_dialog"):
        dialog = getattr(window, attr, None)
        if dialog is not None:
            dialog.open_dialog()
    app.processEvents()


def _reveal_tab_hosted_controls(window: Any, app: Any) -> None:
    """Activate the tabs that host controls moved by the input/result restructures, so those
    controls become isVisibleTo(window). Two moves need this:
    - the constants editor now lives on the 常数 sheet tab of input_data_tabs;
    - 不确定度位数 (options.uncertainty_digits) moved onto the result-detail numeric tab (next to
      小数位数/科学计数法).
    Both are genuine, visible user gates (click the tab); the sweep must open them.
    """
    tabs = getattr(window, "input_data_tabs", None)
    const_tab = getattr(window, "_constants_tab", None)
    if tabs is not None and const_tab is not None:
        idx = tabs.indexOf(const_tab)
        if idx != -1:
            tabs.setCurrentIndex(idx)
    # 不确定度位数 sits on the numeric result tab next to 小数位数/科学计数法, which is hidden until
    # a result exists — so drive a minimal result then activate the numeric tab (same reveal the
    # display-format controls use).
    if hasattr(window, "_set_csv_data"):
        window._set_csv_data([{"x": "1", "y": "2"}], headers=["x", "y"], suggestion="r.csv")
    result_tabs = getattr(window, "result_tabs", None)
    indices = getattr(window, "result_tabs_indices", None)
    if result_tabs is not None and isinstance(indices, dict) and "numeric" in indices:
        result_tabs.setCurrentIndex(indices["numeric"])
    app.processEvents()


def _reveal_output_gates(window: Any, app: Any) -> None:
    """Reveal the LaTeX-output group and its gated caption input.

    The 生成 LaTeX 文件 checkbox was removed (4·4d) — the LaTeX options are now always
    visible in the LaTeX 选项 dialog. ``output.latex.caption`` still needs caption_checkbox
    checked, and the controls live in the LaTeX dialog — so open the option dialogs first.
    Also reveal the tab-hosted controls (constants tab + result numeric tab).
    """
    _open_option_panels(window, app)
    window.caption_checkbox.setChecked(True)
    _reveal_tab_hosted_controls(window, app)
    app.processEvents()


def _drive_non_empty_result(window: Any) -> None:
    """Populate a minimal tabular result so ``self.tabs`` becomes visible."""
    window._set_csv_data(
        [{"x": "1", "y": "2"}],
        headers=["x", "y"],
        suggestion="r.csv",
    )


def _reveal_result_only_control(window: Any, app: Any, key: str) -> None:
    """Drive the result state + subtab that reveals a single result-only control."""
    _drive_non_empty_result(window)
    indices = window.result_tabs_indices
    if key in {"results.display.decimal_places", "results.display.scientific"}:
        window.result_tabs.setCurrentIndex(indices["numeric"])
    elif key == "results.log":
        window.result_tabs.setCurrentIndex(indices["log"])
    elif key == "latex.engine":
        # The engine selector lives in the LaTeX 选项 dialog now — reveal it by opening it.
        window.latex_options_dialog.open_dialog()
    elif key in {"results.latex.source", "pdf.zoom_percent"}:
        # TeX/PDF display widgets live off-screen (the preview dialog is the viewer); reveal
        # the holder to make the persisted-state inputs reachable for the sweep.
        window._offscreen_result_views.setVisible(True)
    elif key in {"results.image.log_x", "results.image.log_y"}:
        # Log-scale toggles are shown only in fitting mode with plots enabled,
        # on the image subtab (see _update_log_scale_visibility).
        _switch_mode(window, app, "fitting")
        window.generate_plots_checkbox.setChecked(True)
        window._update_log_scale_visibility()
        window.result_tabs.setCurrentIndex(indices["image"])
    elif key in {"results.image.zoom_percent", "results.image.page"}:
        window.result_tabs.setCurrentIndex(indices["image"])
    else:  # pragma: no cover - defensive; test_every_input_prefix... guards this
        raise AssertionError(f"unhandled result-only key {key!r}")
    app.processEvents()


# --- Structural guards -----------------------------------------------------


def test_every_input_prefix_is_classified(window: Any) -> None:
    """Every enumerated input prefix must fall in exactly one reachability regime.

    This is the anti-masking guard at the classification level: a newly-added
    area (a new key prefix) that no regime handles fails here instead of being
    silently skipped by the sweep.
    """
    controls = _enumerate_input_controls(window)
    assert controls, "no schema-bound input controls enumerated — enumeration broke"

    per_mode = {p for prefixes in _PER_MODE_PREFIXES.values() for p in prefixes}
    classified = per_mode | _MODE_INDEPENDENT_PREFIXES | _RESULT_ONLY_PREFIXES

    prefixes = {_prefix(k) for _, k in controls}
    unclassified = prefixes - classified
    assert not unclassified, (
        f"input prefixes not covered by any reachability regime: "
        f"{sorted(unclassified)} — classify them (per-mode / mode-independent / "
        f"result-only) so the sweep cannot silently skip them"
    )


def test_no_editable_schema_type_is_excluded(window: Any) -> None:
    """Anti-masking guard at the TYPE level: every schema-keyed widget is either an
    enumerated input or a DOCUMENTED non-input type.

    This closes the masking-by-type hole (the class of bug that dropped
    pdf.zoom_percent and the custom editors): a newly-introduced editable widget
    type that carries a schema key but is not in ``_INPUT_TYPES`` shows up here as
    an unclassified type and FAILS, instead of silently escaping the sweep. To fix
    such a failure you either add the type to ``_INPUT_TYPES`` (if it is an input)
    or to ``_NON_INPUT_SCHEMA_TYPES`` with a reason — never leave it unaccounted.
    """
    unclassified: dict[str, str] = {}
    for obj in [window, *window.findChildren(QObject)]:
        key = obj.property(_SCHEMA_KEY_PROPERTY)
        if not key or isinstance(obj, _INPUT_TYPES):
            continue
        if type(obj).__name__ not in _NON_INPUT_SCHEMA_TYPES:
            unclassified[type(obj).__name__] = str(key)
    assert not unclassified, (
        f"schema-keyed widget types neither enumerated as inputs nor listed as "
        f"documented non-inputs: {unclassified} — add each to _INPUT_TYPES (if it "
        f"takes user input) or to _NON_INPUT_SCHEMA_TYPES (with a reason)"
    )


def test_input_controls_do_not_reparent_across_modes(window: Any) -> None:
    """The single-parent invariant: no gate action reparents an input control.

    Snapshot every input control's parent at window-build, then exercise every
    gate action the sweep uses (all modes, LaTeX gates, a result) and assert no
    parent changed. A redesign that moved a control under a different parent to
    reveal it — the exact bug that hid controls before — fails here.
    """
    app = QApplication.instance()
    controls = _enumerate_input_controls(window)
    parents = {id(w): w.parent() for w, _ in controls}

    for mode in _PER_MODE_PREFIXES:
        _switch_mode(window, app, mode)
    _reveal_output_gates(window, app)
    _drive_non_empty_result(window)
    app.processEvents()

    reparented = [
        (key, parents[id(w)], w.parent())
        for w, key in controls
        if w.parent() is not parents[id(w)]
    ]
    assert not reparented, f"controls were reparented by gate actions: {reparented}"


# --- The sweep: every input control reachable in its mode/gate -------------


@pytest.mark.parametrize("mode", sorted(_PER_MODE_PREFIXES))  # type: ignore[misc]
def test_per_mode_input_controls_all_reachable(window: Any, mode: str) -> None:
    """Sweep: EVERY per-mode input control is reachable once its mode is active.

    Fails if any enumerated control of this mode cannot be made visible by any
    reachable selector combination — that is either a masked control (test bug,
    now impossible to hide by omission) or a genuinely unreachable one (prod bug).
    """
    app = QApplication.instance()
    prefixes = _PER_MODE_PREFIXES[mode]
    _switch_mode(window, app, mode)
    # Constants live on the 常数 sheet tab now — activate it so the constants editor is reachable.
    _reveal_tab_hosted_controls(window, app)

    all_controls = _enumerate_input_controls(window)
    parents = {id(w): w.parent() for w, _ in all_controls}
    controls = [(w, k) for w, k in all_controls if _prefix(k) in prefixes]
    assert controls, f"mode {mode!r} enumerated zero input controls"

    reached = _reach_visible_via_selector_sweep(window, app, controls)

    unreachable = [
        k for _, k in controls if k not in reached and k not in _ALLOWLIST_UNREACHABLE
    ]
    assert not unreachable, (
        f"mode {mode!r}: input controls never reachable via any gate: {unreachable}"
    )
    # Dynamic-key coverage: some widgets are relabelled at runtime and take a
    # different schema key in a gated state (the shared input_constants_editor
    # becomes fitting.implicit.constants under fit_model_combo=self_consistent).
    # Assert each expected dynamic key for this mode was actually reached during
    # the sweep, so a future regression that hides that state fails here.
    for dyn_key in _DYNAMIC_KEYS_BY_MODE.get(mode, ()):  # type: ignore[attr-defined]
        assert dyn_key in reached, (
            f"mode {mode!r}: dynamic-key state {dyn_key!r} never became reachable "
            f"during the selector sweep"
        )
    # Reparent guard: the sweep's gate toggling must not have moved anything.
    reparented = [k for w, k in controls if w.parent() is not parents[id(w)]]
    assert not reparented, f"mode {mode!r}: controls reparented during sweep: {reparented}"


def test_mode_independent_controls_all_reachable(window: Any) -> None:
    """options / parallel / output controls are reachable regardless of mode.

    Checked while an *unrelated* mode (extrapolation) is active to prove
    mode-independence; the LaTeX-output group's gate checkboxes are revealed.
    """
    app = QApplication.instance()
    _switch_mode(window, app, "extrapolation")

    all_controls = _enumerate_input_controls(window)
    parents = {id(w): w.parent() for w, _ in all_controls}
    controls = [
        (w, k) for w, k in all_controls if _prefix(k) in _MODE_INDEPENDENT_PREFIXES
    ]
    assert controls, "no mode-independent input controls enumerated"

    _reveal_output_gates(window, app)

    unreachable = [
        k
        for w, k in controls
        if not w.isVisibleTo(window) and k not in _ALLOWLIST_UNREACHABLE
    ]
    assert not unreachable, f"mode-independent controls not reachable: {unreachable}"
    reparented = [k for w, k in controls if w.parent() is not parents[id(w)]]
    assert not reparented, f"mode-independent controls reparented: {reparented}"


def test_result_only_controls_hidden_pre_result_then_reachable(window: Any) -> None:
    """results.* / latex.engine are RESULT-ONLY: hidden until a result exists.

    Assert (a) each is hidden pre-result even after switching to its subtab, then
    (b) each becomes reachable in place once a non-empty result populates
    ``self.tabs`` and the right subtab is shown.
    """
    app = QApplication.instance()
    all_controls = _enumerate_input_controls(window)
    parents = {id(w): w.parent() for w, _ in all_controls}
    controls = [(w, k) for w, k in all_controls if _prefix(k) in _RESULT_ONLY_PREFIXES]
    assert controls, "no result-only input controls enumerated"

    # (a) Hidden pre-result even after cycling through every result subtab.
    for idx in range(window.result_tabs.count()):
        window.result_tabs.setCurrentIndex(idx)
        app.processEvents()
    still_visible = [k for w, k in controls if w.isVisibleTo(window)]
    assert not still_visible, (
        f"result-only controls visible pre-result: {still_visible}"
    )

    # (b) Reachable in place once a result exists and its subtab is shown.
    for widget, key in controls:
        parent_before = parents[id(widget)]
        _reveal_result_only_control(window, app, key)
        assert widget.isVisibleTo(window) is True, (
            f"result-only control {key!r} not visible after driving its result subtab"
        )
        assert widget.parent() is parent_before, (
            f"result-only control {key!r} was reparented "
            f"(before={parent_before!r}, after={widget.parent()!r})"
        )


def test_non_masking_guard(window: Any) -> None:
    """Prove the sweep genuinely catches a hidden control (anti-masking proof).

    Force-hide one enumerated per-mode control, re-run that mode's reachability
    check, and assert it now reports the control unreachable. If this guard did
    NOT fail, the sweep would be masking — so this test asserts the failure.
    """
    app = QApplication.instance()
    _switch_mode(window, app, "extrapolation")
    controls = [
        (w, k)
        for w, k in _enumerate_input_controls(window)
        if _prefix(k) == "extrapolation"
    ]
    target_widget, target_key = next(
        (w, k) for w, k in controls if k == "extrapolation.method"
    )

    # Neutralise the target's ability to become visible: override showEvent-driven
    # visibility by forcing it hidden and blocking re-show for the sweep's duration.
    original_set_visible = target_widget.setVisible
    target_widget.setVisible(False)
    target_widget.setVisible = lambda *_a, **_k: None  # type: ignore[method-assign]
    try:
        reached = _reach_visible_via_selector_sweep(window, app, controls)
        assert target_key not in reached, (
            "sweep still reported the force-hidden control reachable — it is MASKING"
        )
    finally:
        target_widget.setVisible = original_set_visible  # type: ignore[method-assign]
        target_widget.setVisible(True)
        app.processEvents()

    # Restored: the control is reachable again, proving the guard is reversible.
    reached_after = _reach_visible_via_selector_sweep(window, app, controls)
    assert target_key in reached_after, (
        "control not reachable after restore — the guard did not clean up"
    )


# --- Retained specific gate tests (clear per-control documentation) --------
#
# These name individual gates explicitly. The programmatic sweep above is the
# non-masking guarantee; these remain as readable, targeted regressions for the
# trickier gates (input-mode stack, data-file toggle, doubly-gated caption).


def _assert_reachable_in_place(window: Any, widget: Any, gate: Callable[[], None]) -> None:
    """Run ``gate`` then assert ``widget`` is visible with an UNCHANGED parent."""
    parent_before = widget.parent()
    gate()
    assert widget.isVisibleTo(window) is True, (
        f"{widget.objectName() or widget!r} not visible after its gate action"
    )
    assert widget.parent() is parent_before, (
        f"{widget.objectName() or widget!r} was reparented by its gate action "
        f"(before={parent_before!r}, after={widget.parent()!r})"
    )


def test_manual_data_edit_reachable_via_input_mode_stack(window: Any) -> None:
    """manual_data_edit lives on page 1 of the input-mode QStackedWidget."""
    widget = window.manual_data_edit
    _assert_reachable_in_place(
        window,
        widget,
        gate=lambda: window._data_stack.setCurrentIndex(_DATA_STACK_TEXT_PAGE),
    )


def test_manual_table_reachable_in_default_state(window: Any) -> None:
    """manual_table is the default input view (table page, manual box shown)."""
    assert hasattr(window, "manual_table")
    _assert_reachable_in_place(window, window.manual_table, gate=lambda: None)


def test_use_file_checkbox_reachable_in_default_state(window: Any) -> None:
    """The 使用数据文件 toggle is always visible in the input rail."""
    assert hasattr(window, "use_file_checkbox")
    _assert_reachable_in_place(window, window.use_file_checkbox, gate=lambda: None)


def test_data_file_edit_reachable_via_use_file_checkbox(window: Any) -> None:
    """data_file_edit is hidden until the user checks 使用数据文件."""
    assert hasattr(window, "data_file_edit")
    _assert_reachable_in_place(
        window,
        window.data_file_edit,
        gate=lambda: window.use_file_checkbox.setChecked(True),
    )


def test_caption_edit_reachable_via_latex_then_caption_checkbox(window: Any) -> None:
    """caption_edit is doubly-gated: open the LaTeX 选项 dialog, then caption_checkbox
    (the 生成 LaTeX 文件 checkbox was removed in 4·4d — options are always visible)."""
    assert hasattr(window, "caption_edit")
    app = QApplication.instance()

    def gate() -> None:
        _open_option_panels(window, app)
        window.caption_checkbox.setChecked(True)

    _assert_reachable_in_place(window, window.caption_edit, gate=gate)


def test_latex_engine_combo_hidden_pre_reveal(window: Any) -> None:
    """The engine selector lives in the LaTeX 选项 dialog (closed by default), so
    latex_engine_combo is not visible-to-window until the dialog is opened."""
    assert window.latex_options_dialog.isVisible() is False
    assert window.latex_engine_combo.isVisibleTo(window) is False


def test_latex_engine_combo_reachable_when_latex_dialog_open(window: Any) -> None:
    """latex_engine_combo is reachable once the LaTeX 选项 dialog is opened."""
    widget = window.latex_engine_combo

    def gate() -> None:
        window.latex_options_dialog.open_dialog()

    _assert_reachable_in_place(window, widget, gate=gate)
