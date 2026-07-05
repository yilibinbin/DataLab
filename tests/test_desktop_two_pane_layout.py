"""Stage ② of the layout refactor: the workbench is TWO panes, not three.

Per the 2026-07-05 spec: the left config rail merges into the workspace pane so the
splitter has exactly 2 panes — [输入 + 配置, stacked] | [结果]. The result pane widens.
The merged pane is ``workbench_workspace_*`` (the new left-pane source of truth);
``workbench_config_rail``/``_content`` survive only as detached compatibility attributes,
never as a visible splitter pane.

These tests encode WHY: the input controls and per-mode config must be reachable in ONE
merged pane, the result pane must be index 1 of 2, and nothing may be stranded.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    win.show()
    return win


def test_splitter_has_exactly_two_panes(window: Any) -> None:
    """The main splitter drops from 3 panes to 2: merged-left | result."""
    splitter = window._main_splitter
    assert splitter.count() == 2, "workbench must be a two-pane splitter"
    assert len(splitter.sizes()) == 2


def test_result_rail_is_the_second_pane(window: Any) -> None:
    """The result rail is pane index 1 (the right pane of two)."""
    splitter = window._main_splitter
    from app_desktop.workbench_visual_contract import RESULT_RAIL_OBJECT

    assert splitter.widget(1).objectName() == RESULT_RAIL_OBJECT


def test_merged_pane_is_the_first_pane_and_holds_input_and_config(window: Any) -> None:
    """Pane 0 is the merged workspace pane and contains BOTH the input section and the
    per-mode config (mode_stack) — the two halves that used to be in separate panes."""
    splitter = window._main_splitter
    left_pane = splitter.widget(0)
    left_descendants = set(left_pane.findChildren(QWidget))
    assert window.input_section in left_descendants, (
        "input_section must live in the merged left pane"
    )
    assert window.mode_stack in left_descendants, (
        "the per-mode config (mode_stack) must live in the merged left pane"
    )


def test_input_section_is_above_the_mode_stack(window: Any) -> None:
    """Vertical stack order: 输入 (input_section) sits ABOVE 配置 (mode_stack) in the
    merged pane, per the confirmed layout decision."""
    input_top = window.input_section.mapTo(window, window.input_section.rect().topLeft()).y()
    stack_top = window.mode_stack.mapTo(window, window.mode_stack.rect().topLeft()).y()
    assert input_top < stack_top, "输入 section must be above the per-mode config stack"


def test_config_rail_is_not_a_splitter_pane(window: Any) -> None:
    """The old config rail must NOT be a pane of the splitter anymore (that is the space
    freed for the result area). It may survive as a detached compatibility attribute."""
    splitter = window._main_splitter
    config_rail = getattr(window, "workbench_config_rail", None)
    pane_widgets = {splitter.widget(i) for i in range(splitter.count())}
    assert config_rail not in pane_widgets, (
        "workbench_config_rail must no longer be a splitter pane"
    )


def test_visual_contract_passes_for_two_panes(window: Any) -> None:
    """The rewritten 2-pane visual contract must report NO issues for the live window
    (merged pane + result pane both present, ordered, wide enough)."""
    from app_desktop.workbench_visual_contract import visual_contract_issues

    window.resize(1440, 900)
    QApplication.processEvents()
    assert visual_contract_issues(window) == [], (
        "the two-pane visual contract must pass for a normally-sized window"
    )


def test_left_min_width_is_driven_by_the_merged_pane(window: Any) -> None:
    """``_main_splitter_left_min_width`` must be derived from the MERGED pane, not the
    detached config rail — otherwise the left pane could be sized from the wrong widget."""
    window._refresh_main_splitter_left_min_width()
    QApplication.processEvents()
    sizes = window._main_splitter.sizes()
    assert len(sizes) == 2
    assert sizes[0] >= window._main_splitter_left_min_width, (
        "the merged left pane must honour _main_splitter_left_min_width"
    )
