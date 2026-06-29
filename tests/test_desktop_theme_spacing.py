from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from app_desktop import theme


def test_spacing_tokens_and_legacy_aliases_consistent() -> None:
    # Unified scale exists and legacy names remain valid aliases.
    assert (theme.SPACE_XS, theme.SPACE_SM, theme.SPACE_MD, theme.SPACE_LG) == (4, 6, 8, 12)
    assert theme.CONTROL_SPACING == theme.SPACE_SM
    assert theme.SECTION_SPACING == theme.SPACE_MD
    assert theme.WORKSPACE_GUTTER == theme.SPACE_LG
    # Title clearance must be large enough to clear the rendered title band.
    assert theme.GROUPBOX_TITLE_CLEARANCE >= 18


@pytest.mark.parametrize("dark", [True, False])
def test_canvas_groupbox_reserves_title_band(dark: bool) -> None:
    # Regression for the title-overlaps-content bug: any styled (bordered) QGroupBox
    # reparented into the workbench canvas must reserve a title band, or the title
    # overlaps the first control (the user-reported "单位标注" overlap).
    qss = theme.workbench_region_style(dark=dark)
    assert "QFrame#workbench_workspace_canvas_content QGroupBox" in qss
    assert f"margin-top: {theme.GROUPBOX_TITLE_CLEARANCE}px" in qss
    assert "QFrame#workbench_workspace_canvas_content QGroupBox::title" in qss
    assert "subcontrol-origin: margin" in qss


@pytest.mark.parametrize("dark", [True, False])
def test_config_card_groupbox_still_reserves_title_band(dark: bool) -> None:
    # The working reference pattern must remain intact (it is what the canvas fix mirrors).
    qss = theme.config_card_style(dark=dark)
    assert 'QWidget[datalab_config_card="true"] QGroupBox' in qss
    assert "margin-top: 18px" in qss
    assert 'QWidget[datalab_config_card="true"] QGroupBox::title' in qss
    assert "subcontrol-origin: margin" in qss


def test_all_mode_section_cards_share_uniform_spacing() -> None:
    # V6 regression: the error view used to override the shared card layout to 4px,
    # making error rows visibly tighter than every other mode. All five mode section
    # cards must share the same spacing and margins (driven by the spacing tokens).
    from PySide6.QtWidgets import QApplication, QFrame

    from tools.capture_desktop_gui_screens import _create_window

    app = QApplication.instance() or QApplication([])  # noqa: F841
    window = _create_window()
    QApplication.processEvents()

    cards = [
        f
        for f in window.findChildren(QFrame)
        if f.property("datalab_workbench_section_card") and f.layout() is not None
    ]
    roles = {str(c.property("datalab_workbench_section_role")) for c in cards}
    # All five modes are present.
    assert {"error", "fitting", "statistics", "extrapolation", "root_solving"} <= roles

    spacings = {c.layout().spacing() for c in cards}
    margins = {
        (c.layout().contentsMargins().left(), c.layout().contentsMargins().top())
        for c in cards
    }
    assert spacings == {theme.SPACE_MD}, f"non-uniform card spacing: {spacings}"
    assert margins == {(theme.CARD_MARGIN_H, theme.CARD_MARGIN_V)}, f"non-uniform margins: {margins}"
