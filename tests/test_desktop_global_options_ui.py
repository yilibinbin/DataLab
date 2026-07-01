from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from app_desktop.ui_schema_binder import find_unbound_required_widgets
from shared.parallel_config import NestedParallelPolicy, ParallelMode


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


def _combo_data(combo: Any) -> list[object]:
    return [combo.itemData(index) for index in range(combo.count())]


def test_global_precision_and_parallel_controls_have_schema_metadata(window: Any) -> None:
    assert window.mpmath_precision_spin.property("datalab_schema_key") == "options.precision_digits"
    assert window.mpmath_precision_spin.property("datalab_schema_required") is True
    assert window.mpmath_precision_spin.toolTip()

    assert window.uncertainty_digits_spin.property("datalab_schema_key") == "options.uncertainty_digits"
    assert window.uncertainty_digits_spin.property("datalab_schema_required") is True
    assert window.uncertainty_digits_spin.toolTip()

    assert window.parallel_mode_combo.property("datalab_schema_key") == "parallel.mode"
    assert window.parallel_mode_combo.property("datalab_schema_choices") is True
    assert _combo_data(window.parallel_mode_combo) == [
        ParallelMode.AUTO.value,
        ParallelMode.SERIAL.value,
        ParallelMode.THREAD.value,
        ParallelMode.PROCESS.value,
    ]
    assert window.parallel_mode_combo.toolTip()

    assert window.parallel_max_workers_spin.property("datalab_schema_key") == "parallel.max_workers"
    assert window.parallel_max_workers_spin.toolTip()
    assert window.parallel_reserve_cores_spin.property("datalab_schema_key") == "parallel.reserve_cores"
    assert window.parallel_reserve_cores_spin.toolTip()
    assert window.parallel_nested_policy_combo.property("datalab_schema_key") == "parallel.nested_policy"
    assert _combo_data(window.parallel_nested_policy_combo) == [
        NestedParallelPolicy.SERIAL_WHEN_NESTED.value,
        NestedParallelPolicy.ALLOW.value,
    ]


def test_global_latex_plot_and_log_controls_have_schema_metadata(window: Any) -> None:
    assert window.generate_latex_checkbox.property("datalab_schema_key") == "output.latex.enabled"
    assert window.output_file_edit.property("datalab_schema_key") == "output.latex.path"
    assert window.output_file_edit.toolTip()
    assert window.output_browse_button.property("datalab_schema_key") == "output.latex.path"
    assert window.output_browse_button.accessibleName() == "选择 LaTeX 输出路径"

    assert window.latex_input_precision_spin.property("datalab_schema_key") == "output.latex.input_digits"
    assert window.dcolumn_checkbox.property("datalab_schema_key") == "output.latex.dcolumn"
    assert window.latex_group_size_spin.property("datalab_schema_key") == "output.latex.group_size"
    assert window.caption_checkbox.property("datalab_schema_key") == "output.latex.caption.enabled"
    assert window.caption_edit.property("datalab_schema_key") == "output.latex.caption"

    assert window.generate_plots_checkbox.property("datalab_schema_key") == "output.plots.enabled"
    assert window.verbose_checkbox.property("datalab_schema_key") == "options.verbose_log"


def test_result_and_pdf_controls_have_schema_metadata(window: Any) -> None:
    assert window.scientific_checkbox.property("datalab_schema_key") == "results.display.scientific"
    assert window.display_digits_spin.property("datalab_schema_key") == "results.display.decimal_places"
    assert window.zoom_percent_spin.property("datalab_schema_key") == "results.image.zoom_percent"
    assert window.log_x_checkbox.property("datalab_schema_key") == "results.image.log_x"
    assert window.log_y_checkbox.property("datalab_schema_key") == "results.image.log_y"

    assert window.latex_compile_button.property("datalab_schema_key") == "latex.compile"
    assert window.latex_view_pdf_button.property("datalab_schema_key") == "latex.view_pdf"
    assert window.latex_engine_combo.property("datalab_schema_key") == "latex.engine"
    assert window.latex_engine_path_button.property("datalab_schema_key") == "latex.engine_path"

    assert window.pdf_zoom_spin.property("datalab_schema_key") == "pdf.zoom_percent"
    assert window.pdf_zoom_in_button.property("datalab_schema_key") == "pdf.zoom_in"
    assert window.pdf_zoom_out_button.property("datalab_schema_key") == "pdf.zoom_out"
    assert window.pdf_zoom_reset_button.property("datalab_schema_key") == "pdf.zoom_reset"


def test_global_schema_tooltips_and_choices_refresh_with_language(window: Any) -> None:
    window.parallel_mode_combo.setCurrentIndex(window.parallel_mode_combo.findData(ParallelMode.THREAD.value))
    window.parallel_nested_policy_combo.setCurrentIndex(
        window.parallel_nested_policy_combo.findData(NestedParallelPolicy.ALLOW.value)
    )

    window._apply_language("en")

    assert window.parallel_mode_combo.currentData() == ParallelMode.THREAD.value
    assert window.parallel_mode_combo.itemText(window.parallel_mode_combo.findData(ParallelMode.PROCESS.value)) == (
        "Prefer processes"
    )
    assert window.parallel_nested_policy_combo.currentData() == NestedParallelPolicy.ALLOW.value
    assert "Numerical precision" in window.mpmath_precision_spin.toolTip()
    assert "0 means automatic" in window.parallel_max_workers_spin.toolTip()
    assert window.output_browse_button.accessibleName() == "Choose LaTeX output path"
    assert window.latex_compile_button.accessibleName() == "Compile PDF"
    assert window.pdf_zoom_reset_button.accessibleName() == "Reset PDF zoom"

    window._apply_language("zh")

    assert window.parallel_mode_combo.currentData() == ParallelMode.THREAD.value
    assert window.parallel_mode_combo.itemText(window.parallel_mode_combo.findData(ParallelMode.PROCESS.value)) == (
        "进程优先"
    )
    assert "数值计算精度" in window.mpmath_precision_spin.toolTip()
    assert window.output_browse_button.accessibleName() == "选择 LaTeX 输出路径"


def test_global_options_have_no_unbound_required_schema_widgets(window: Any) -> None:
    assert find_unbound_required_widgets(window.options_box) == []
