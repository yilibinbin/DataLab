"""On-demand LaTeX rebuild — error propagation (4·2; gaps = table_segments + constants +
used_columns, the last being local-only until we retained it in the payload).

Golden test: on-demand rebuild == generate_error_propagation_table output byte-for-byte
from the same stashed data + live format widgets; honours live option changes.
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

from shared.uncertainty import parse_uncertainty_format


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
    parsed_data = [
        [parse_uncertainty_format("1.0(1)"), parse_uncertainty_format("2.0(2)"), parse_uncertainty_format("3.0(3)")],
        [parse_uncertainty_format("1.1(1)"), parse_uncertainty_format("2.1(2)"), parse_uncertainty_format("3.1(3)")],
    ]
    results = [parse_uncertainty_format("4.0(4)")] * len(parsed_data)
    constants = {"k": parse_uncertainty_format("9.8(1)")}
    return {
        "headers": headers,
        "parsed_data": parsed_data,
        "results": results,
        "constants": constants,
        "used_columns": ["B"],
        "formula": "A + B * k",
        "units": None,
    }


def _seed(window: Any) -> dict[str, Any]:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    QApplication.processEvents()
    p = _payload()
    window.remember_latex_inputs("error", p)
    return p


def _expected_tex(window: Any, p: dict[str, Any], tmp_path: Any) -> str:
    from datalab_latex.latex_tables_error_propagation import generate_error_propagation_table

    out = tmp_path / "expected.tex"
    generate_error_propagation_table(
        p["headers"],
        p["parsed_data"],
        p["results"],
        p["constants"],
        p["formula"],
        str(out),
        caption=window._caption_value() if hasattr(window, "_caption_value") else None,
        verbose=window.verbose_checkbox.isChecked(),
        use_dcolumn=window.dcolumn_checkbox.isChecked(),
        table_segments=[(0, 1), (1, 2)],
        precision=window.latex_input_precision_spin.value(),
        result_uncertainty_digits=window._uncertainty_digits_value(),
        used_columns=p["used_columns"],
        latex_group_size=window.latex_group_size_spin.value(),
    )
    return out.read_text(encoding="utf-8")


def test_error_ondemand_rebuild_matches_writer(window: Any, tmp_path: Any) -> None:
    p = _seed(window)
    window.latex_group_size_spin.setValue(3)
    window.dcolumn_checkbox.setChecked(True)
    window.verbose_checkbox.setChecked(False)

    # Seed table_segments too (the display path drops it; the stash must retain it).
    p["table_segments"] = [(0, 1), (1, 2)]
    window.remember_latex_inputs("error", p)

    expected = _expected_tex(window, p, tmp_path)
    tex_path = window.generate_error_latex_on_demand()
    assert tex_path is not None
    assert Path(tex_path).read_text(encoding="utf-8") == expected


def test_error_ondemand_honours_live_option_changes(window: Any, tmp_path: Any) -> None:
    _seed(window)
    window.dcolumn_checkbox.setChecked(False)
    tex_a = Path(window.generate_error_latex_on_demand()).read_text(encoding="utf-8")
    window.dcolumn_checkbox.setChecked(True)
    tex_b = Path(window.generate_error_latex_on_demand()).read_text(encoding="utf-8")
    assert tex_a != tex_b


def test_error_ondemand_returns_none_without_stash(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("error"))
    QApplication.processEvents()
    window._last_latex_inputs = {}
    assert window.generate_error_latex_on_demand() is None
