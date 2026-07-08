from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from app_desktop.workbench_results import MAX_RESULT_OVERVIEW_ROWS


def _window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    return window


def test_result_view_titles_use_compact_tabs_and_full_tooltips() -> None:
    from app_desktop.result_view_titles import result_view_tab_title, result_view_tooltip
    from shared.ui_specs import DESKTOP_RESULT_VIEWS

    expected_compact_titles = {
        "result.numeric": ("数值", "Data"),
        "result.image": ("图像", "Image"),
        "result.log": ("日志", "Log"),
        "result.latex": ("TeX", "TeX"),
        "result.pdf": ("PDF", "PDF"),
    }

    assert set(expected_compact_titles) == set(DESKTOP_RESULT_VIEWS)
    for view_key, (title_zh, title_en) in expected_compact_titles.items():
        spec = DESKTOP_RESULT_VIEWS[view_key]
        assert result_view_tab_title(view_key, "zh") == title_zh
        assert result_view_tab_title(view_key, "en") == title_en
        assert result_view_tooltip(view_key, "zh") == spec.title.zh
        assert result_view_tooltip(view_key, "en") == spec.title.en

    assert result_view_tab_title("result.numeric", "en") != result_view_tooltip(
        "result.numeric",
        "en",
    )
    with pytest.raises(ValueError, match="Unknown result view key"):
        result_view_tab_title("result.unknown", "en")
    with pytest.raises(ValueError, match="Unknown result view key"):
        result_view_tooltip("result.unknown", "zh")


def test_result_rail_has_overview_and_data_table(qtbot: Any) -> None:
    window = _window(qtbot)

    assert window.workbench_result_overview_title.text() in {"结果概览", "Result overview"}
    assert window.workbench_result_overview is not None
    assert window.workbench_result_overview_meta.text() in {"等待计算", "Waiting for calculation"}
    assert window.workbench_result_status_badge.text() in {"等待", "Waiting"}
    assert window.workbench_result_status_badge.property("datalab_result_status") == "waiting"
    assert "border-radius" in window.workbench_result_overview_panel.styleSheet()
    assert "QLabel#workbench_result_status_badge" in window.workbench_result_overview_panel.styleSheet()
    assert window.workbench_result_summary_grid.parentWidget() is window.workbench_result_overview_panel
    assert window.workbench_result_summary_rows_label.text() in {"行数", "Rows"}
    assert window.workbench_result_summary_rows_value.text() == "0"
    assert window.workbench_result_summary_columns_value.text() == "0"
    assert window.workbench_result_summary_outputs_value.text() in {"无", "None"}
    assert not hasattr(window, "workbench_result_table")
    assert window.workbench_result_details_panel.parentWidget() is window.workbench_result_rail
    assert window.workbench_result_details_title.text() in {"结果详情", "Result details"}
    assert window.workbench_result_details_empty_panel.parentWidget() is window.workbench_result_details_panel
    assert window.workbench_result_details_empty_label.text() in {"暂无结果详情", "No result details"}
    assert not window.workbench_result_details_empty_label.isHidden()
    assert window.workbench_result_details_empty_panel.isVisibleTo(window.workbench_result_details_panel)
    window._apply_language("en")
    assert window.workbench_result_details_empty_label.text() == "No result details"
    window._apply_language("zh")
    assert window.workbench_result_details_empty_label.text() == "暂无结果详情"
    assert window.workbench_result_details_empty_label.alignment() & Qt.AlignmentFlag.AlignHCenter
    assert window.workbench_result_details_empty_label.alignment() & Qt.AlignmentFlag.AlignVCenter
    assert window.workbench_result_details_panel.property("datalab_result_detail_card") is True
    assert "QWidget#workbench_result_details_panel" in window.workbench_result_details_panel.styleSheet()
    assert window.tabs.parentWidget() is window.workbench_result_details_panel
    assert window.tabs.isHidden()
    assert window.tabs.property("datalab_state_role") == "result_tabs_owner"
    assert window.tabs.tabBar().isHidden()
    assert window.result_tabs.parentWidget() is window.tabs.widget(window.result_tab_index)
    assert window.result_tabs.objectName() == "result_detail_tabs"
    assert window.result_tabs.tabBar().usesScrollButtons() is False
    assert "QTabWidget#result_detail_tabs" in window.workbench_result_details_panel.styleSheet()
    assert window.result_tabs.tabText(window.result_tabs_indices["numeric"]) == "数值"
    assert window.result_tabs.tabToolTip(window.result_tabs_indices["numeric"]) == "数值结果"


def test_uncertainty_digits_lives_in_result_panel_and_live_rerenders(qtbot: Any) -> None:
    """不确定度位数 moved from the toolbar compute-options into the result panel: it must be
    parented under the result tabs AND live-re-render the on-screen result when changed (user
    request — adjustable post-run like decimal places, no recompute)."""
    from shared.uncertainty import parse_uncertainty_format

    window = _window(qtbot)
    spin = window.uncertainty_digits_spin
    # Parented under the result tabs, not the toolbar options.
    names = []
    p = spin.parentWidget()
    for _ in range(8):
        if p is None:
            break
        names.append(p.objectName())
        p = p.parentWidget()
    assert any("result" in n for n in names), f"spin not under result panel: {names}"

    # Changing it live-re-renders the error-propagation result (formatter reads the value).
    kw = dict(
        headers=["A", "B"],
        data_rows=[[parse_uncertainty_format("1.0(1)"), parse_uncertainty_format("2.0(2)")]],
        results=[parse_uncertainty_format("4.123456(789)")],
        formula="A+B",
        units=None,
    )
    spin.setValue(1)
    t1, _ = window._format_error_display(**kw)
    spin.setValue(4)
    t4, _ = window._format_error_display(**kw)
    assert t1 != t4
    assert "4.1235(8)" in t1
    assert "4.1234560(7890)" in t4


def test_fit_model_line_honours_display_digits(qtbot: Any) -> None:
    """The substituted model line (numbers OUTSIDE the result table) must respond to the
    display digits / scientific toggles, not stay frozen at the fit's output digits
    (user-reported)."""
    import mpmath as mp
    from fitting.hp_fitter import FitResult

    window = _window(qtbot)
    fr = FitResult(
        params={"A": mp.mpf("2.123456789"), "B": mp.mpf("1.987654321")},
        param_errors={"A": mp.mpf("0.1"), "B": mp.mpf("0.1")},
        chi2=mp.mpf("0.5"), reduced_chi2=mp.mpf("0.25"), aic=mp.mpf("0"), bic=mp.mpf("0"),
        r2=mp.mpf("1"), rmse=mp.mpf("0.1"), residuals=[mp.mpf("0.1")], fitted_curve=[],
        covariance=[[mp.mpf("0.01")]], param_errors_stat={"A": mp.mpf("0.1")},
        param_errors_sys={}, param_errors_total={"A": mp.mpf("0.1")}, details={"dof": 1},
    )
    window.scientific_checkbox.setChecked(False)
    window.display_digits_spin.setValue(3)
    text3, _ = window._format_fit_display(fr, "A*x + B", "STALE", units=None)
    window.display_digits_spin.setValue(6)
    text6, _ = window._format_fit_display(fr, "A*x + B", "STALE", units=None)

    # Isolate the substituted MODEL line (CodeRabbit CR): asserting on the whole text would
    # pass via the parameter table, which independently formats A at the same digits — that
    # wouldn't prove the model-line rebuild itself responds. Assert on the model line only.
    def _model_line(text: str) -> str:
        return next(
            ln for ln in text.splitlines() if "代入参数" in ln or "With params" in ln
        )

    # The passed-in "STALE" substituted must be ignored; the model line reflects live digits.
    assert "STALE" not in text3
    assert "2.123" in _model_line(text3)
    assert "2.123457" in _model_line(text6)
    assert text3 != text6


def test_result_font_size_survives_content_rerender(qtbot: Any) -> None:
    """Changing the result font size must live-update the output AND survive the next result
    render. setMarkdown resets the document's default font, so without re-applying the chosen
    size, every new result would silently revert to the app default (user-reported)."""
    window = _window(qtbot)
    registry = getattr(window, "_editor_font_spins", {})
    entry = registry.get(id(window.result_edit))
    assert entry is not None, "result_edit has no registered font-size spin"
    _editor, spin = entry

    window._set_result_text("# Result\n\nModel: A*x", final_result=True)
    spin.setValue(20)
    assert window.result_edit.document().defaultFont().pointSize() == 20

    # A new result re-renders via setMarkdown — the chosen size must persist.
    window._set_result_text("# New Result\n\nModel: B*x", final_result=True)
    assert window.result_edit.document().defaultFont().pointSize() == 20


def test_latex_pdf_tabs_removed_from_result_tabs_but_widgets_survive(qtbot: Any) -> None:
    """The TeX/PDF result tabs are gone (the on-demand preview dialog is the viewer),
    but the underlying widgets stay alive off-screen so the dialog, workspace round-trip,
    and compile paths keep reading them.

    WHY: latex_edit holds results.latex.source (persisted + read by the preview dialog);
    latex_engine_combo/pdf_zoom_spin are compile/preview state. Removing the visible tabs
    must NOT delete these widgets — only relocate them out of result_tabs."""
    window = _window(qtbot)

    # result_tabs now carries exactly numeric/image/log — no TeX/PDF tab.
    titles = {window.result_tabs.tabText(i) for i in range(window.result_tabs.count())}
    assert "TeX" not in titles
    assert "PDF" not in titles
    assert window.result_tabs.count() == 3
    assert set(window.result_tabs_indices) == {"numeric", "image", "log"}

    # The load-bearing widgets still exist and keep their schema keys.
    assert window.latex_edit.property("datalab_schema_key") == "results.latex.source"
    assert window.latex_engine_combo.property("datalab_schema_key") == "latex.engine"
    assert window.pdf_zoom_spin.property("datalab_schema_key") == "pdf.zoom_percent"

    # They live in the off-screen holder, not in result_tabs.
    holder = window._offscreen_result_views
    assert window.latex_edit in holder.findChildren(type(window.latex_edit))
    assert window.pdf_zoom_spin in holder.findChildren(type(window.pdf_zoom_spin))
    # holder is a child of the window (so findChildren/schema scan see it) but hidden.
    assert holder.parentWidget() is not None
    assert holder.isVisibleTo(window) is False


def test_result_rail_uses_csv_state_without_hidden_table_projection(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3", "y": "2.46e-6"}], ["k", "y"], "result.csv")
    window.refresh_workbench_result_rail()

    assert window._csv_rows == [{"k": "2.47e-3", "y": "2.46e-6"}]
    assert window._csv_headers == ["k", "y"]
    assert "1" in window.workbench_result_overview.text()
    assert window.workbench_result_details_empty_panel.isHidden()
    assert window.tabs.isVisibleTo(window.workbench_result_details_panel)


def test_result_rail_hidden_projection_stays_empty_when_result_shape_changes(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3", "y": "2.46e-6"}], ["k", "y"], "result.csv")
    window._set_csv_data([{"k": "3.14"}], ["k"], "result.csv")

    assert window._csv_rows == [{"k": "3.14"}]
    assert window._csv_headers == ["k"]
    assert "1" in window.workbench_result_overview.text()


def test_result_rail_caps_visible_rows_but_reports_total(qtbot: Any) -> None:
    window = _window(qtbot)
    rows = [{"i": str(index)} for index in range(MAX_RESULT_OVERVIEW_ROWS + 3)]

    window._set_csv_data(rows, ["i"], "result.csv")
    window._apply_language("en")

    assert f"Result data: {len(rows)} rows, 1 column" in window.workbench_result_overview.text()
    assert f"showing first {MAX_RESULT_OVERVIEW_ROWS}" in window.workbench_result_overview.text()


def test_result_rail_clears_when_csv_data_resets(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3"}], ["k"], "result.csv")
    window._reset_csv_data()

    assert window.workbench_result_overview.text() in {"暂无结果", "No results"}


def test_result_rail_summary_relocalizes_on_language_switch(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"k": "2.47e-3"}], ["k"], "result.csv")

    window._apply_language("en")
    assert window.workbench_result_overview_title.text() == "Result overview"
    assert "Result data: 1 row, 1 column" in window.workbench_result_overview.text()
    assert window.workbench_result_overview_meta.text() == "Includes: table"
    assert window.workbench_result_summary_rows_label.text() == "Rows"
    assert window.workbench_result_summary_rows_value.text() == "1"
    assert window.workbench_result_summary_columns_label.text() == "Columns"
    assert window.workbench_result_summary_columns_value.text() == "1"
    assert window.workbench_result_summary_outputs_label.text() == "Outputs"
    assert window.workbench_result_summary_outputs_value.text() == "Table"
    assert window.workbench_result_status_badge.text() == "Ready"
    assert window.workbench_result_status_badge.property("datalab_result_status") == "ready"
    assert not window.workbench_result_details_empty_label.isVisible()
    assert not window.tabs.isHidden()
    assert window.result_tabs.tabText(window.result_tabs_indices["numeric"]) == "Data"
    assert window.result_tabs.tabToolTip(window.result_tabs_indices["numeric"]) == "Numeric results"
    window._apply_language("zh")
    assert window.workbench_result_overview_title.text() == "结果概览"
    assert "结果数据：1 行" in window.workbench_result_overview.text()
    assert window.workbench_result_overview_meta.text() == "包含：表格"
    assert window.workbench_result_summary_rows_label.text() == "行数"
    assert window.workbench_result_summary_rows_value.text() == "1"
    assert window.workbench_result_summary_columns_label.text() == "列数"
    assert window.workbench_result_summary_columns_value.text() == "1"
    assert window.workbench_result_summary_outputs_label.text() == "输出"
    assert window.workbench_result_summary_outputs_value.text() == "表格"
    assert window.workbench_result_status_badge.text() == "已就绪"
    assert window.result_tabs.tabText(window.result_tabs_indices["numeric"]) == "数值"


def test_result_overview_meta_tracks_available_artifacts(qtbot: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window._set_csv_data([{"x": "1"}], ["x"])
    window._last_result_rendered_text = "summary"
    window.result_plot_bytes = b"plot-bytes"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window._apply_language("en")

    assert window.workbench_result_overview_meta.text() == "Includes: table / plot / text"
    assert window.workbench_result_summary_outputs_value.text() == "Table / Plot / Text"


def test_result_overview_meta_reports_generated_artifact_files(qtbot: Any, tmp_path: Any) -> None:
    tex_path = tmp_path / "analysis.tex"
    pdf_path = tmp_path / "analysis.pdf"
    fit_plot = tmp_path / "fit-plot.png"
    stats_plot = tmp_path / "stats-plot.png"
    tex_path.write_text("% DataLab test", encoding="utf-8")
    pdf_path.write_bytes(b"%PDF-1.4\n")
    fit_plot.write_bytes(_tiny_png_bytes())
    stats_plot.write_bytes(_tiny_png_bytes())

    window = _window(qtbot)
    window.current_latex_path = tex_path
    window.last_pdf_path = pdf_path
    window.current_fit_figures = [fit_plot]
    window.current_stats_figures = [stats_plot]
    window.current_error_figures = [tmp_path / "missing-error-plot.png"]
    window._set_csv_data([{"x": "1"}], ["x"])

    window._apply_language("en")
    meta_en = window.workbench_result_overview_meta.text()
    assert (
        meta_en
        == "Includes: table / plot; Artifacts: LaTeX: analysis.tex / PDF: analysis.pdf / Image files: 2 files"
    )
    assert str(tmp_path) not in meta_en
    assert "missing-error-plot.png" not in meta_en

    window._apply_language("zh")
    meta_zh = window.workbench_result_overview_meta.text()
    assert meta_zh == "包含：表格 / 图片；产物：LaTeX：analysis.tex / PDF：analysis.pdf / 图片文件：2 个"
    assert str(tmp_path) not in meta_zh
    assert "missing-error-plot.png" not in meta_zh


def test_result_overview_meta_skips_empty_and_directory_artifact_paths(qtbot: Any, tmp_path: Any) -> None:
    window = _window(qtbot)
    window.current_latex_path = ""
    window.last_pdf_path = tmp_path
    window.current_fit_figures = [tmp_path]
    window._set_csv_data([{"x": "1"}], ["x"])

    window._apply_language("en")

    assert window.workbench_result_overview_meta.text() == "Includes: table / plot"


def test_result_overview_deduplicates_symlinked_figure_artifacts(qtbot: Any, tmp_path: Any) -> None:
    plot_path = tmp_path / "plot.png"
    plot_alias = tmp_path / "plot-alias.png"
    plot_path.write_bytes(_tiny_png_bytes())
    try:
        plot_alias.symlink_to(plot_path)
    except OSError as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    window = _window(qtbot)
    window.current_fit_figures = [plot_path, plot_alias]
    window._set_csv_data([{"x": "1"}], ["x"])

    window._apply_language("en")

    assert window.workbench_result_overview_meta.text().endswith("Artifacts: Image file: plot.png")


def _tiny_png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\xff"
        b"\xff?\x00\x05\xfe\x02\xfeA\xe2\xa1\xb5\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def test_result_rail_distinguishes_plot_only_result(qtbot: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window._reset_csv_data()
    window._last_result_rendered_text = ""
    window.result_plot_bytes = b"plot-bytes"
    window._result_plot_base_pixmap = QPixmap(8, 8)

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Result ready; no tabular data"
    assert window.workbench_result_summary_rows_value.text() == "0"
    assert window.workbench_result_summary_columns_value.text() == "0"
    assert window.workbench_result_summary_outputs_value.text() == "Plot"


def test_result_rail_distinguishes_text_only_result(qtbot: Any) -> None:
    window = _window(qtbot)
    window._reset_csv_data()
    window._last_result_rendered_text = "x = 1.0"

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"
    assert window.workbench_result_summary_outputs_value.text() == "Text"


def test_result_rail_distinguishes_plot_and_text_without_tabular_data(qtbot: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window._reset_csv_data()
    window._last_result_rendered_text = "diagnostic text"
    window.result_plot_bytes = b"plot-bytes"
    window._result_plot_base_pixmap = QPixmap(8, 8)

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Result ready; plot and text available; no tabular data"
    assert window.workbench_result_summary_outputs_value.text() == "Plot / Text"


def test_result_rail_distinguishes_failed_result(qtbot: Any) -> None:
    window = _window(qtbot)
    window._reset_csv_data()
    window._mark_workbench_result_failed()

    window.refresh_workbench_result_rail()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation failed"
    assert window.workbench_result_status_badge.text() == "Failed"
    assert window.workbench_result_status_badge.property("datalab_result_status") == "failed"
    assert not window.workbench_result_details_empty_label.isVisible()
    assert not window.tabs.isHidden()
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["log"]


def test_failed_result_language_refresh_keeps_user_selected_result_tab(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_failed()
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["log"]

    window.result_tabs.setCurrentIndex(window.result_tabs_indices["numeric"])
    window._apply_language("en")

    assert window.result_tabs.currentIndex() == window.result_tabs_indices["numeric"]


def test_failed_result_survives_ordinary_csv_reset(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_failed()
    window._reset_csv_data()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_hard_reset_clears_failed_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_failed()
    window._reset_csv_data(clear_non_tabular_result=True)
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "No results"


def test_hard_reset_clears_display_format_result_cache(qtbot: Any) -> None:
    window = _window(qtbot)
    window._last_result_kind = "fitting"
    window._last_result_payloads = {"fitting": {"kind": "fitting", "text": "stale"}}

    window._reset_csv_data(clear_non_tabular_result=True)

    assert window._last_result_kind is None
    assert window._last_result_payloads == {}


def test_result_rail_shows_running_while_worker_is_in_flight(qtbot: Any) -> None:
    window = _window(qtbot)
    window._reset_csv_data(clear_non_tabular_result=True)
    window._mark_workbench_result_running()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Running"
    assert window.workbench_result_status_badge.text() == "Running"
    assert window.workbench_result_status_badge.property("datalab_result_status") == "running"
    assert not window.workbench_result_details_empty_label.isVisible()
    assert not window.tabs.isHidden()
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["log"]


def test_result_rail_plot_only_success_does_not_stay_running(qtbot: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window._mark_workbench_result_running()
    window.result_plot_bytes = b"plot-bytes"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window._reset_csv_data()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Result ready; no tabular data"


def test_result_rail_plot_success_clears_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._update_result_plot(_tiny_png_bytes(), final_result=True)
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Result ready; no tabular data"


def test_result_rail_text_success_clears_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._set_result_text("text-only result", final_result=True)
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_result_rail_running_to_tabular_success_selects_data_tab(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["log"]

    window._set_csv_data([{"x": "1"}], ["x"])

    assert window.workbench_result_overview.text() in {
        "结果数据：1 行，1 列",
        "Result data: 1 row, 1 column",
    }
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["numeric"]


def test_result_rail_running_to_plot_success_selects_image_tab(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["log"]

    window._update_result_plot(_tiny_png_bytes(), final_result=True)

    assert window.workbench_result_overview.text() in {
        "结果已生成；无表格数据",
        "Result ready; no tabular data",
    }
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["image"]


def test_result_rail_running_to_text_success_selects_data_tab(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["log"]

    window._set_result_text("text-only result", final_result=True)

    assert window.workbench_result_overview.text() in {
        "文本结果已生成；无表格数据",
        "Text result ready; no tabular data",
    }
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["numeric"]


def test_result_rail_running_to_plot_text_success_selects_image_tab(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["log"]

    window._last_result_rendered_text = "diagnostic text"
    window._update_result_plot(_tiny_png_bytes(), final_result=True)

    assert window.workbench_result_overview.text() in {
        "结果已生成；有图片和文本；无表格数据",
        "Result ready; plot and text available; no tabular data",
    }
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["image"]


def test_result_rail_result_refresh_keeps_user_selected_subtab(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._set_csv_data([{"x": "1"}], ["x"])
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["numeric"]

    window.result_tabs.setCurrentIndex(window.result_tabs_indices["log"])
    window._apply_language("en")

    assert window.result_tabs.currentIndex() == window.result_tabs_indices["log"]


def test_result_rail_tabular_result_mentions_available_plot(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"x": "1", "y": "2"}], ["x", "y"])
    window.result_plot_bytes = b"plot-bytes"
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Result data: 1 row, 2 columns; plot also available"


def test_result_rail_empty_tabular_schema_is_still_tabular(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([], ["x", "y"])
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Result data: 0 rows, 2 columns"


def test_result_overview_copies_only_preview_rows(qtbot: Any) -> None:
    from app_desktop.workbench_results import _overview_state

    window = _window(qtbot)
    window._set_csv_data([{"x": str(i)} for i in range(500)], ["x"])

    state = _overview_state(window)

    assert state.total_rows == 500
    assert len(state.preview_rows) == 100


def test_result_overview_summary_reports_displayed_row_count(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"x": str(i)} for i in range(500)], ["x"])
    window._apply_language("en")

    assert "Result data: 500 rows, 1 column" in window.workbench_result_overview.text()
    assert "showing first 50 rows" in window.workbench_result_overview.text()


def test_result_rail_intermediate_text_does_not_clear_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._set_result_text("intermediate progress")
    window._apply_language("en")

    assert window._workbench_result_state == "running"
    assert window.workbench_result_overview.text() == "Running"


def test_result_rail_empty_success_is_not_no_results(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._mark_workbench_result_complete()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"
    assert window.workbench_result_status_badge.text() == "Complete"
    assert window.workbench_result_status_badge.property("datalab_result_status") == "complete"
    assert not window.workbench_result_details_empty_label.isVisible()
    assert not window.tabs.isHidden()
    assert window.result_tabs.currentIndex() == window.result_tabs_indices["log"]


def test_reset_csv_preserves_empty_success_unless_hard_reset(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_complete()
    window._reset_csv_data()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"

    window._reset_csv_data(clear_non_tabular_result=True)
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "No results"


def test_root_solving_empty_success_uses_empty_success_overview(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    window._on_root_solving_finished({"markdown": "", "csv_rows": [], "csv_headers": []})
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_set_image_list_empty_success_is_not_no_results(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._set_image_list("fit", [])
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_fit_batches_tabular_success_clears_running_state(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window._mark_workbench_result_running()
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "_build_substituted_expression", lambda *args, **kwargs: "A*x")
    monkeypatch.setattr(window, "_format_fit_result_text", lambda *args, **kwargs: "fit summary")
    monkeypatch.setattr(window, "_render_fit_plot_bytes", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        window,
        "_build_fit_csv_rows",
        lambda *args, **kwargs: [{"section": "parameters", "name": "A", "value": "1"}],
    )
    payload = SimpleNamespace(
        job=SimpleNamespace(
            model_expr="A*x",
            headers=["x", "y"],
            data_rows=[],
            sigma_rows=[],
            render_plots=False,
        ),
        expression="A*x",
        fit_result=SimpleNamespace(params={"A": "1"}),
        units=None,
    )

    window._on_fit_batches_finished([SimpleNamespace(index=1, kind="fit", fit_payload=payload, error=None, captured_log="")])
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Result data: 1 row, 8 columns; text also available"


def test_fit_batches_text_only_success_clears_running_state(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window._mark_workbench_result_running()
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    window._on_fit_batches_finished([SimpleNamespace(index=1, kind="error", fit_payload=None, error="bad input", captured_log="")])
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_reset_csv_rejects_conflicting_hard_reset_and_preserve_running(qtbot: Any) -> None:
    window = _window(qtbot)
    window._set_csv_data([{"x": "1"}], ["x"])
    window._mark_workbench_result_running()
    window._apply_language("en")

    with pytest.raises(ValueError, match="preserve_workbench_running"):
        window._reset_csv_data(preserve_workbench_running=True, clear_non_tabular_result=True)

    assert window._csv_rows == [{"x": "1"}]
    assert window._csv_headers == ["x"]
    assert window.workbench_result_overview.text() == "Running"


def test_set_csv_empty_payload_preserves_empty_success(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_complete()

    window._set_csv_data([], [])
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_set_csv_intermediate_rows_can_preserve_running_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()

    window._set_csv_data([{"x": "1"}], ["x"], final_result=False)
    window._apply_language("en")

    assert window._workbench_result_state == "running"
    assert window.workbench_result_overview.text() == "Running"


def test_worker_start_failure_does_not_leave_running_overview(qtbot: Any) -> None:
    class BrokenWorker:
        def start(self) -> None:
            raise RuntimeError("boom")

    window = _window(qtbot)
    window._apply_language("en")

    with pytest.raises(RuntimeError):
        window._start_worker_with_workbench_result_state(BrokenWorker())

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_worker_async_failure_signal_does_not_leave_running_overview(qtbot: Any) -> None:
    class Worker(QObject):
        failed = Signal(str)

        def start(self) -> None:
            pass

    window = _window(qtbot)
    window._apply_language("en")
    worker = Worker()

    window._start_worker_with_workbench_result_state(worker)
    assert window.workbench_result_overview.text() == "Running"

    worker.failed.emit("boom")

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_worker_start_refreshes_result_rail_once(qtbot: Any, monkeypatch: Any) -> None:
    class Worker:
        def start(self) -> None:
            pass

    window = _window(qtbot)
    calls = 0

    def refresh() -> None:
        nonlocal calls
        calls += 1

    monkeypatch.setattr(window, "refresh_workbench_result_rail", refresh)
    window._start_worker_with_workbench_result_state(Worker())

    assert calls == 1


def test_worker_start_clears_stale_existing_figure_artifacts(qtbot: Any, tmp_path: Any) -> None:
    class Worker:
        def start(self) -> None:
            pass

    old_plot = tmp_path / "old-fit.png"
    old_plot.write_bytes(_tiny_png_bytes())

    window = _window(qtbot)
    window.current_fit_figures = [old_plot]
    window._set_csv_data([{"x": "1"}], ["x"])
    window._apply_language("en")
    assert "old-fit.png" in window.workbench_result_overview_meta.text()

    window._start_worker_with_workbench_result_state(Worker())
    window._apply_language("en")

    assert window.current_fit_figures == []
    assert window.workbench_result_overview_meta.text() == "In progress"


def test_calc_success_handler_exception_marks_result_failed(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        window,
        "_show_extrapolation_results",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("render boom")),
    )
    window._mark_workbench_result_running()

    window._on_calc_finished(
        SimpleNamespace(
            mode="extrapolation",
            logs=[],
            latex_path=None,
            warnings=[],
            payload={"headers": [], "data_rows": [], "results": []},
        )
    )
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_calc_core_request_snapshot_is_not_cached_as_user_result(
    qtbot: Any,
    monkeypatch: Any,
) -> None:
    from types import SimpleNamespace

    import mpmath as mp
    from PySide6.QtWidgets import QMessageBox

    from datalab_core.jobs import ComputeJobRequest, JobMode
    from data_extrapolation_latex_latest import ExtrapolationResult

    window = _window(qtbot)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    core_request = ComputeJobRequest(
        mode=JobMode.EXTRAPOLATION,
        inputs={"values": ["1"]},
        request_id="worker-snapshot",
    )

    window._on_calc_finished(
        SimpleNamespace(
            mode="extrapolation",
            logs=[],
            latex_path=None,
            warnings=[],
            payload={
                "headers": ["A", "B", "C"],
                "data_rows": [(mp.mpf("1.0"), mp.mpf("1.5"), mp.mpf("1.75"))],
                "results": [ExtrapolationResult(value=mp.mpf("2.0"), uncertainty=mp.mpf("0.25"))],
                "render_plots": False,
                "core_request": core_request,
            },
        )
    )

    cached = window._last_result_payloads["extrapolation"]
    assert "core_request" not in cached
    assert cached["headers"] == ["A", "B", "C"]


def test_fit_success_handler_exception_marks_result_failed(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        window,
        "_format_fit_result_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fit render boom")),
    )
    window._mark_workbench_result_running()

    window._on_fit_finished(
        SimpleNamespace(
            job=SimpleNamespace(model_expr="A*x", render_plots=False, generate_latex=False, output_path=""),
            fit_result=SimpleNamespace(params={"A": "1"}, details={}),
            expression="A*x",
            logs=[],
            warnings=[],
        )
    )
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation failed"


def test_fit_batch_success_handler_exception_marks_result_failed(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window._fit_batch_context = {"generate_latex": False}
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        window,
        "_format_fit_result_text",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("batch render boom")),
    )
    window._mark_workbench_result_running()
    payload = SimpleNamespace(
        job=SimpleNamespace(model_expr="A*x", render_plots=False),
        expression="A*x",
        fit_result=SimpleNamespace(params={"A": "1"}, details={}),
        units=None,
    )

    window._on_fit_batches_finished(
        [SimpleNamespace(index=1, kind="fit", fit_payload=payload, error=None, captured_log="")]
    )
    window._apply_language("en")

    assert window._fit_batch_context is None
    assert window.workbench_result_overview.text() == "Calculation failed"


def test_fit_success_post_processing_error_keeps_success_overview(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "_build_substituted_expression", lambda *args, **kwargs: "A*x")
    monkeypatch.setattr(window, "_format_fit_result_text", lambda *args, **kwargs: "fit summary")
    monkeypatch.setattr(window, "_render_fit_plot_bytes", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "_build_fit_csv_rows", lambda *args, **kwargs: [])
    monkeypatch.setattr(window, "_write_fitting_latex", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("latex boom")))
    window._mark_workbench_result_running()

    window._on_fit_finished(
        SimpleNamespace(
            job=SimpleNamespace(
                model_expr="A*x",
                render_plots=False,
                generate_latex=True,
                output_path="result.tex",
                headers=[],
                data_rows=[],
                sigma_rows=[],
                use_dcolumn=True,
            ),
            fit_result=SimpleNamespace(params={"A": "1"}, details={}),
            expression="A*x",
            units=None,
            logs=[],
            warnings=[],
        )
    )
    window._apply_language("en")

    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_fit_batch_post_processing_error_keeps_success_overview(qtbot: Any, monkeypatch: Any) -> None:
    from types import SimpleNamespace

    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window._fit_batch_context = {"generate_latex": True, "output_path": "result.tex"}
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "_build_substituted_expression", lambda *args, **kwargs: "A*x")
    monkeypatch.setattr(window, "_format_fit_result_text", lambda *args, **kwargs: "fit summary")
    monkeypatch.setattr(window, "_render_fit_plot_bytes", lambda *args, **kwargs: None)
    monkeypatch.setattr(window, "_build_fit_csv_rows", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        window,
        "_write_fitting_latex_batches",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("batch latex boom")),
    )
    window._mark_workbench_result_running()
    payload = SimpleNamespace(
        job=SimpleNamespace(model_expr="A*x", render_plots=False, headers=[], data_rows=[], sigma_rows=[]),
        expression="A*x",
        fit_result=SimpleNamespace(params={"A": "1"}, details={}),
        units=None,
    )

    window._on_fit_batches_finished(
        [SimpleNamespace(index=1, kind="fit", fit_payload=payload, error=None, captured_log="")]
    )
    window._apply_language("en")

    assert window._fit_batch_context is None
    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_fit_setup_error_preserves_previous_valid_result_overview(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    window._set_csv_data([{"x": "1"}], ["x"])
    window._apply_language("en")
    assert window.workbench_result_overview.text() == "Result data: 1 row, 1 column"

    monkeypatch.setattr(window, "_active_data_source", lambda: (None, "x y\n"))
    monkeypatch.setattr(
        window,
        "_run_fitting_mode",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("No data available for fitting.")),
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    window.run_calculation()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Result data: 1 row, 1 column"
    assert window._csv_rows == [{"x": "1"}]


def test_statistics_empty_batches_use_empty_success_overview(qtbot: Any) -> None:
    window = _window(qtbot)

    window._display_statistics_batches([], "value")
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_statistics_empty_result_uses_empty_success_overview(qtbot: Any, monkeypatch: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    monkeypatch.setattr(window, "_format_statistics_display", lambda **kwargs: ("", []))

    window._display_statistics_result({}, "value", 0, render_plots=False)
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "Calculation complete; no displayable result"


def test_statistics_nonempty_batch_without_csv_reports_text_result(qtbot: Any, monkeypatch: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()
    window._apply_language("en")
    captured_text: dict[str, str] = {}
    original_set_result_text = window._set_result_text

    def capture_result_text(text: str, *args: Any, **kwargs: Any) -> None:
        captured_text["text"] = text
        original_set_result_text(text, *args, **kwargs)

    monkeypatch.setattr(window, "_set_result_text", capture_result_text)
    monkeypatch.setattr(window, "_render_statistics_text", lambda *args, **kwargs: "")
    monkeypatch.setattr(window, "_build_stats_csv_rows", lambda *args, **kwargs: [])

    window._display_statistics_batches([{"index": 1, "result": {}, "rows": []}], "value", render_plots=False)
    window._apply_language("en")

    assert captured_text["text"].strip()
    assert "Batch" in captured_text["text"]
    assert window._workbench_result_state == "none"
    assert window.workbench_result_overview.text() == "Text result ready; no tabular data"


def test_run_validation_error_does_not_leave_result_overview_running(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    window._apply_language("en")

    window.run_calculation()

    assert window.workbench_result_overview.text() == "No results"


def test_run_validation_error_does_not_reset_results_before_worker(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    # A bare root_solving window (no equations/unknowns) fails validation on run — the
    # trigger for "results must not be reset before the worker starts". (The
    # generate_latex_checkbox setup was vestigial; removed in 4·4d.)
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)
    reset_called = False

    def reset_csv_data(*args: object, **kwargs: object) -> None:
        nonlocal reset_called
        reset_called = True

    monkeypatch.setattr(window, "_reset_csv_data", reset_csv_data)

    window.run_calculation()

    assert reset_called is False


def test_worker_cancellation_clears_running_result_state(qtbot: Any) -> None:
    window = _window(qtbot)
    window._mark_workbench_result_running()

    window._on_worker_cancelled()
    window._apply_language("en")

    assert window.workbench_result_overview.text() == "No results"


def test_worker_cancellation_after_old_plot_does_not_restore_stale_plot(qtbot: Any) -> None:
    from pathlib import Path

    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    window.result_plot_bytes = b"old-plot"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window.current_fit_figures = [Path("old-fit.png")]
    window._image_mode = "fit"
    window._workbench_result_state = "running"

    window._on_worker_cancelled()
    window._apply_language("en")

    assert window.result_plot_bytes is None
    assert window._result_plot_base_pixmap is None
    assert window.current_fit_figures == []
    assert window.workbench_result_overview.text() == "No results"


def test_run_validation_error_preserves_previous_valid_result_overview(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QMessageBox

    window = _window(qtbot)
    window.result_plot_bytes = b"old-plot"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window._last_result_rendered_text = "old text result"
    window.refresh_workbench_result_rail()
    window._apply_language("en")
    assert window.workbench_result_overview.text() == "Result ready; plot and text available; no tabular data"

    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    window.run_calculation()

    assert window.workbench_result_overview.text() == "Result ready; plot and text available; no tabular data"


def test_new_workspace_hard_clears_previous_result_overview(qtbot: Any, monkeypatch: Any) -> None:
    from PySide6.QtGui import QPixmap

    window = _window(qtbot)
    monkeypatch.setattr(window, "_confirm_workspace_discard_or_save", lambda: True)
    window._last_result_rendered_text = "old text"
    window.result_plot_bytes = b"old-plot"
    window._result_plot_base_pixmap = QPixmap(8, 8)
    window._mark_workbench_result_failed()
    window.refresh_workbench_result_rail()
    window._apply_language("en")
    assert window.workbench_result_overview.text() == "Calculation failed"

    assert window.new_workspace()
    window._apply_language("en")

    assert window._last_result_rendered_text == ""
    assert window.result_plot_bytes is None
    assert window._result_plot_base_pixmap is None
    assert window.workbench_result_overview.text() == "No results"
