"""On-demand LaTeX rebuild — extrapolation (4·2, the 'easy' mode; gap = table_segments).

Rebuild tex from the persisted result-data (headers/data_rows/results/table_segments in
_last_latex_inputs['extrapolation']) + LIVE format widgets. Golden test: the on-demand
rebuild == generate_latex_table's output from the same data + opts (byte-for-byte), and
honours live option changes. Uses a valid builder-shape fixture (results zip 1:1 with
data_rows; each row has len(headers) columns).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("pytestqt")
pytest.importorskip("PySide6")

import mpmath as mp
from PySide6.QtWidgets import QApplication


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("zh")
    qtbot.addWidget(win)
    return win


def _payload() -> dict[str, Any]:
    headers = ["A", "B", "C"]
    data_rows = [
        (mp.mpf("1.1"), mp.mpf("2.22"), mp.mpf("3.333")),
        (mp.mpf("4.4"), mp.mpf("5.55"), mp.mpf("6.666")),
        (mp.mpf("7.7"), mp.mpf("8.88"), mp.mpf("9.999")),
    ]
    results = [(mp.mpf("7.7777"), mp.mpf("0.12")) for _ in data_rows]
    # Two blocks over the 3 rows — exercises the table_segments gap (this is the datum the
    # window display path drops and the stash must retain).
    table_segments = [(0, 2), (2, 3)]
    return {
        "headers": headers,
        "data_rows": data_rows,
        "results": results,
        "table_segments": table_segments,
    }


def _seed(window: Any) -> dict[str, Any]:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("extrapolation"))
    QApplication.processEvents()
    p = _payload()
    window.remember_latex_inputs("extrapolation", p)
    return p


def _expected_tex(window: Any, p: dict[str, Any], tmp_path: Any) -> str:
    from datalab_latex.latex_tables_extrapolation import generate_latex_table

    out = tmp_path / "expected.tex"
    generate_latex_table(
        p["headers"],
        p["data_rows"],
        p["results"],
        str(out),
        caption=window._caption_value() if hasattr(window, "_caption_value") else None,
        precision=window.latex_input_precision_spin.value(),
        verbose=window.verbose_checkbox.isChecked(),
        use_dcolumn=window.dcolumn_checkbox.isChecked(),
        table_segments=p["table_segments"],
        result_uncertainty_digits=window._uncertainty_digits_value(),
        latex_group_size=window.latex_group_size_spin.value(),
    )
    return out.read_text(encoding="utf-8")


def test_extrapolation_ondemand_rebuild_matches_writer(window: Any, tmp_path: Any) -> None:
    p = _seed(window)
    window.latex_group_size_spin.setValue(3)
    window.dcolumn_checkbox.setChecked(True)
    window.verbose_checkbox.setChecked(False)

    expected = _expected_tex(window, p, tmp_path)
    tex_path = window.generate_extrapolation_latex_on_demand()
    assert tex_path is not None
    assert Path(tex_path).read_text(encoding="utf-8") == expected


def test_extrapolation_ondemand_honours_live_option_changes(window: Any, tmp_path: Any) -> None:
    p = _seed(window)
    window.dcolumn_checkbox.setChecked(False)
    tex_a = Path(window.generate_extrapolation_latex_on_demand()).read_text(encoding="utf-8")

    window.dcolumn_checkbox.setChecked(True)
    tex_b = Path(window.generate_extrapolation_latex_on_demand()).read_text(encoding="utf-8")
    assert tex_a != tex_b
    assert tex_b == _expected_tex(window, p, tmp_path)


def test_extrapolation_ondemand_returns_none_without_stash(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("extrapolation"))
    QApplication.processEvents()
    window._last_latex_inputs = {}
    assert window.generate_extrapolation_latex_on_demand() is None
