"""On-demand LaTeX rebuild — statistics (4·2; plain-stats gap = rows/sigma_rows).

Golden test via a real (synchronous) statistics run: run with LaTeX to a temp path, capture
the run-time tex, then rebuild ON DEMAND from the stash (_last_latex_inputs['statistics']:
rows/sigma_rows/display_batches) + live format widgets, and assert byte-identical.
"""

from __future__ import annotations

import os
from pathlib import Path
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
    win._apply_language("en")
    qtbot.addWidget(win)
    return win


def _setup_single_stats(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("statistics"))
    QApplication.processEvents()
    window.manual_data_edit.setPlainText("A sigma\n1 0.1\n2 0.2\n3 0.3\n")
    window._data_stack.setCurrentIndex(1)
    window.stats_workflow_combo.setCurrentIndex(window.stats_workflow_combo.findData("standard"))
    window.stats_value_column_edit.setText("A")
    window.stats_sigma_column_edit.setText("sigma")
    window.stats_mode_combo.setCurrentIndex(window.stats_mode_combo.findData("weighted_sigma"))


def test_statistics_ondemand_rebuild_matches_runtime(window: Any, tmp_path: Any) -> None:
    _setup_single_stats(window)
    window.dcolumn_checkbox.setChecked(True)
    window.latex_group_size_spin.setValue(3)

    run_tex = tmp_path / "runtime.tex"
    window._run_statistics_mode(True, str(run_tex))
    runtime = run_tex.read_text(encoding="utf-8")
    assert runtime.strip()

    tex_path = window.generate_statistics_latex_on_demand()
    assert tex_path is not None
    rebuilt = Path(tex_path).read_text(encoding="utf-8")
    assert rebuilt == runtime


def test_statistics_ondemand_honours_live_option_changes(window: Any, tmp_path: Any) -> None:
    _setup_single_stats(window)
    window.dcolumn_checkbox.setChecked(False)
    window._run_statistics_mode(False, "")  # populate the stash without writing

    tex_a = Path(window.generate_statistics_latex_on_demand()).read_text(encoding="utf-8")
    window.dcolumn_checkbox.setChecked(True)
    tex_b = Path(window.generate_statistics_latex_on_demand()).read_text(encoding="utf-8")
    assert tex_a != tex_b


def test_statistics_ondemand_returns_none_without_stash(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("statistics"))
    QApplication.processEvents()
    window._last_latex_inputs = {}
    assert window.generate_statistics_latex_on_demand() is None
