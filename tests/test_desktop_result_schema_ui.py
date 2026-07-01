from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication
from app_desktop.result_view_titles import result_view_tab_title
from shared.ui_specs import DESKTOP_RESULT_VIEWS


RESULT_VIEW_ORDER = (
    "result.numeric",
    "result.image",
    "result.log",
    "result.latex",
    "result.pdf",
)


def _result_alias(view_key: str) -> str:
    return view_key.split(".", 1)[1]


def _result_schema_key(view_key: str) -> str:
    return view_key.replace("result.", "results.", 1)


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    # Pin the language so assertions are deterministic regardless of the runner's
    # system locale (CI defaults to English, local dev often to Chinese).
    win._apply_language("zh")
    qtbot.addWidget(win)
    return win


def test_result_tabs_and_status_widgets_have_schema_metadata(window: Any) -> None:
    assert window.tabs.property("datalab_schema_key") == "main.result_tabs"
    assert window.tabs.property("datalab_schema_tabs") == {
        "result": "results.overview",
    }
    assert window.tabs.tabText(window.main_tabs_indices["result"]) == "结果"

    assert window.result_tabs.property("datalab_schema_key") == "results.tabs"
    assert window.result_tabs.property("datalab_schema_tabs") == {
        _result_alias(view_key): _result_schema_key(view_key)
        for view_key in RESULT_VIEW_ORDER
    }
    assert window.result_tabs.property("datalab_result_view_specs")["pdf"]["attachment_key"] == "pdf"
    assert "latex.compile" in window.result_tabs.property("datalab_result_view_specs")["latex"]["controls"]
    assert "results.image.zoom_percent" in window.result_tabs.property("datalab_result_view_specs")["image"]["controls"]
    assert window.result_tabs.count() == len(RESULT_VIEW_ORDER)
    for index, view_key in enumerate(RESULT_VIEW_ORDER):
        spec = DESKTOP_RESULT_VIEWS[view_key]
        assert window.result_tabs.tabText(index) == result_view_tab_title(view_key, "zh")
        assert window.result_tabs.tabToolTip(index) == spec.title.zh

    assert window.result_edit.property("datalab_schema_key") == "results.numeric.markdown"
    assert window.log_edit.property("datalab_schema_key") == "results.log"
    assert window.latex_edit.property("datalab_schema_key") == "results.latex.source"
    assert window.result_plot_scroll.property("datalab_schema_key") == "results.image.preview"
    assert window.result_plot_label.property("datalab_schema_key") == "results.image.preview"
    assert window.image_status_label.property("datalab_schema_key") == "results.image.status"
    assert window.latex_status_label.property("datalab_schema_key") == "results.latex.status"
    assert window.pdf_status_label.property("datalab_schema_key") == "results.pdf.status"


def test_result_export_and_image_controls_have_schema_metadata(window: Any) -> None:
    assert window.export_csv_btn.property("datalab_schema_key") == "results.export.csv"
    assert window.export_csv_btn.accessibleName() == "导出 CSV"

    assert window.result_zoom_in_btn.property("datalab_schema_key") == "results.image.zoom_in"
    assert window.result_zoom_out_btn.property("datalab_schema_key") == "results.image.zoom_out"
    assert window.result_zoom_reset_btn.property("datalab_schema_key") == "results.image.zoom_reset"
    assert window.result_export_btn.property("datalab_schema_key") == "results.image.export"
    assert window.image_page_spin.property("datalab_schema_key") == "results.image.page"
    assert window.result_plot_zoom_spin is window.zoom_percent_spin
    assert window.result_plot_page_spin is window.image_page_spin
    assert window.image_prev_btn.property("datalab_schema_key") == "results.image.previous"
    assert window.image_next_btn.property("datalab_schema_key") == "results.image.next"


def test_latex_toolbar_controls_have_result_schema_metadata(window: Any) -> None:
    assert window.latex_open_button.property("datalab_schema_key") == "results.latex.open"
    assert window.latex_save_button.property("datalab_schema_key") == "results.latex.save"
    assert window.latex_reload_button.property("datalab_schema_key") == "results.latex.reload"
    assert window.latex_compile_button.property("datalab_schema_key") == "latex.compile"
    assert window.latex_view_pdf_button.property("datalab_schema_key") == "latex.view_pdf"


def test_result_schema_metadata_refreshes_with_language(window: Any) -> None:
    window._apply_language("en")

    assert window.tabs.tabText(window.main_tabs_indices["result"]) == "Result"
    for index, view_key in enumerate(RESULT_VIEW_ORDER):
        spec = DESKTOP_RESULT_VIEWS[view_key]
        assert window.result_tabs.tabText(index) == result_view_tab_title(view_key, "en")
        assert window.result_tabs.tabToolTip(index) == spec.title.en
    assert window.export_csv_btn.accessibleName() == "Export CSV"
    assert window.result_export_btn.accessibleName() == "Export image"
    assert window.latex_open_button.accessibleName() == "Open LaTeX file"
    assert window.image_next_btn.accessibleName() == "Next image"
    assert "Image page" in window.image_page_spin.toolTip()

    window._apply_language("zh")

    assert window.tabs.tabText(window.main_tabs_indices["result"]) == "结果"
    for index, view_key in enumerate(RESULT_VIEW_ORDER):
        spec = DESKTOP_RESULT_VIEWS[view_key]
        assert window.result_tabs.tabText(index) == result_view_tab_title(view_key, "zh")
        assert window.result_tabs.tabToolTip(index) == spec.title.zh
    assert window.export_csv_btn.accessibleName() == "导出 CSV"
    assert window.latex_open_button.accessibleName() == "打开 LaTeX 文件"
