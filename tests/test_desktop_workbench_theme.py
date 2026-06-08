from __future__ import annotations


def test_workbench_region_width_tokens_match_visual_contract() -> None:
    from app_desktop.theme import (
        CONFIG_RAIL_WIDTH,
        RESULT_RAIL_WIDTH,
        STATUS_STRIP_HEIGHT,
        TOOLBAR_HEIGHT,
        WORKSPACE_GUTTER,
    )

    assert 260 <= CONFIG_RAIL_WIDTH <= 340
    assert 320 <= RESULT_RAIL_WIDTH <= 440
    assert 44 <= TOOLBAR_HEIGHT <= 64
    assert 22 <= STATUS_STRIP_HEIGHT <= 32
    assert 8 <= WORKSPACE_GUTTER <= 16


def test_workbench_styles_expose_named_regions() -> None:
    from app_desktop.theme import workbench_region_style, workbench_toolbar_style

    toolbar = workbench_toolbar_style(dark=False)
    region = workbench_region_style(dark=False)

    assert "QFrame#workbench_toolbar" in toolbar
    assert "QScrollArea#workbench_config_rail" in region
    assert "QScrollArea#workbench_workspace_canvas" in region
    assert "QFrame#workbench_result_rail" in region
    assert "QFrame#workbench_workspace_canvas_content QGroupBox" in region
    assert "QWidget#workbench_result_overview_panel" in region
