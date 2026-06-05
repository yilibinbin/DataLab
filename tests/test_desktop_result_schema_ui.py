from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    return win


def test_result_tabs_and_status_widgets_have_schema_metadata(window: Any) -> None:
    assert window.tabs.property("datalab_schema_key") == "main.result_tabs"
    assert window.tabs.property("datalab_schema_tabs") == {
        "result": "results.overview",
        "log": "results.log",
        "latex": "results.latex",
        "pdf": "results.pdf",
    }
    assert window.tabs.tabText(window.main_tabs_indices["result"]) == "结果"
    assert window.tabs.tabText(window.main_tabs_indices["log"]) == "日志"
    assert window.tabs.tabText(window.main_tabs_indices["latex"]) == "LaTeX"
    assert window.tabs.tabText(window.main_tabs_indices["pdf"]) == "PDF 预览"

    assert window.result_tabs.property("datalab_schema_key") == "results.tabs"
    assert window.result_tabs.property("datalab_schema_tabs") == {
        "numeric": "results.numeric",
        "image": "results.image",
    }
    assert window.result_tabs.tabText(0) == "数值结果"
    assert window.result_tabs.tabText(1) == "图片"

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
    assert window.tabs.tabText(window.main_tabs_indices["log"]) == "Log"
    assert window.tabs.tabText(window.main_tabs_indices["latex"]) == "LaTeX"
    assert window.tabs.tabText(window.main_tabs_indices["pdf"]) == "PDF Preview"
    assert window.result_tabs.tabText(0) == "Values"
    assert window.result_tabs.tabText(1) == "Image"
    assert window.export_csv_btn.accessibleName() == "Export CSV"
    assert window.result_export_btn.accessibleName() == "Export image"
    assert window.latex_open_button.accessibleName() == "Open LaTeX file"
    assert window.image_next_btn.accessibleName() == "Next image"
    assert "Image page" in window.image_page_spin.toolTip()

    window._apply_language("zh")

    assert window.tabs.tabText(window.main_tabs_indices["result"]) == "结果"
    assert window.tabs.tabText(window.main_tabs_indices["log"]) == "日志"
    assert window.tabs.tabText(window.main_tabs_indices["latex"]) == "LaTeX"
    assert window.tabs.tabText(window.main_tabs_indices["pdf"]) == "PDF 预览"
    assert window.result_tabs.tabText(0) == "数值结果"
    assert window.result_tabs.tabText(1) == "图片"
    assert window.export_csv_btn.accessibleName() == "导出 CSV"
    assert window.latex_open_button.accessibleName() == "打开 LaTeX 文件"
