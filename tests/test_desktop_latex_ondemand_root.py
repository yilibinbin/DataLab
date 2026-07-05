"""On-demand LaTeX rebuild — root_solving (4·2, the stash-reader template).

The tex is rebuilt from the persisted result-data (`_last_latex_inputs['root_solving']`:
raw_rows + units) plus LIVE format-option widgets — never recomputing and never depending
on run-time-only intent flags. These golden tests prove:

* rebuild-on-demand tex == the tex ``write_root_latex`` produces from the same data + opts;
* flipping a live option widget (group_size / dcolumn) changes the rebuilt tex, proving the
  builder honours CURRENT options rather than stale run-time ones.
"""

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
    win._apply_language("zh")
    qtbot.addWidget(win)
    return win


# A minimal but multi-root raw-rows payload (the shape _serialize_root_batch_raw_rows emits).
_RAW_ROWS = [
    {
        "input_row_index": "1",
        "root_index": "1",
        "name": "x",
        "value": "1.4142135623730951",
        "uncertainty": "0.01",
        "backend": "mpmath",
        "mode": "scalar",
    },
    {
        "input_row_index": "1",
        "root_index": "2",
        "name": "x",
        "value": "-1.4142135623730951",
        "uncertainty": "0.01",
        "backend": "mpmath",
        "mode": "scalar",
    },
]
_UNITS = {"x": ""}


def _seed_root_latex_inputs(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()
    window.remember_latex_inputs("root_solving", {"raw_rows": _RAW_ROWS, "units": _UNITS})


def _expected_tex(window: Any, tmp_path: Any) -> str:
    from app_desktop.root_latex_writer import write_root_latex
    from app_desktop.window_extrapolation_mixin import _root_units_for_rows

    out = tmp_path / "expected.tex"
    write_root_latex(
        output_path=str(out),
        rows=_RAW_ROWS,
        caption=window._caption_value() if hasattr(window, "_caption_value") else "",
        digits=window.latex_input_precision_spin.value(),
        uncertainty_digits=window._uncertainty_digits_value(),
        group_size=window.latex_group_size_spin.value(),
        include_dcolumn=window.dcolumn_checkbox.isChecked(),
        language="en" if window._is_en() else "zh",
        root_units=_root_units_for_rows(_RAW_ROWS, _UNITS),
    )
    return out.read_text(encoding="utf-8")


def test_root_ondemand_rebuild_matches_writer_output(window: Any, tmp_path: Any) -> None:
    _seed_root_latex_inputs(window)
    window.latex_group_size_spin.setValue(3)
    window.dcolumn_checkbox.setChecked(True)

    expected = _expected_tex(window, tmp_path)
    tex_path = window.generate_root_latex_on_demand()
    assert tex_path is not None
    from pathlib import Path

    rebuilt = Path(tex_path).read_text(encoding="utf-8")
    assert rebuilt == expected


def test_root_ondemand_honours_live_option_changes(window: Any, tmp_path: Any) -> None:
    """Changing a live option widget must change the rebuilt tex (no recompute) — proving
    the builder reads CURRENT options, not stale run-time ones."""
    _seed_root_latex_inputs(window)
    from pathlib import Path

    window.latex_group_size_spin.setValue(3)
    window.dcolumn_checkbox.setChecked(False)
    tex_a = Path(window.generate_root_latex_on_demand()).read_text(encoding="utf-8")

    # Flip dcolumn on — no recompute, just regenerate.
    window.dcolumn_checkbox.setChecked(True)
    tex_b = Path(window.generate_root_latex_on_demand()).read_text(encoding="utf-8")

    assert tex_a != tex_b
    assert tex_b == _expected_tex(window, tmp_path)  # matches the writer with dcolumn on


def test_root_ondemand_returns_none_without_stashed_inputs(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("root_solving"))
    QApplication.processEvents()
    window._last_latex_inputs = {}
    assert window.generate_root_latex_on_demand() is None
