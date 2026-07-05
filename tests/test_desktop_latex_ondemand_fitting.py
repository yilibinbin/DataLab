"""On-demand LaTeX rebuild — fitting single-fit (4·2; gaps = group_size/uncertainty_digits
on FitJob + target_column/variable_pairs from the RUN, not edited widgets).

Builder-level golden test: seed _last_latex_inputs['fit_single'] with a FitResult + the
run's data, then assert the on-demand rebuild == _write_fitting_latex output for the same
data (with widgets set to match), and that the rebuild is immune to post-run widget edits
because it uses the stash's target_column/variable_pairs.
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

from fitting.hp_fitter import FitResult


@pytest.fixture  # type: ignore[untyped-decorator]
def window(qtbot: Any) -> Any:
    from app_desktop.window import ExtrapolationWindow

    QApplication.instance() or QApplication([])
    win = ExtrapolationWindow()
    win._apply_language("en")
    qtbot.addWidget(win)
    return win


def _fit_result() -> FitResult:
    params = {"A": mp.mpf("2"), "B": mp.mpf("1")}
    return FitResult(
        params=params,
        param_errors={"A": mp.mpf("0.1"), "B": mp.mpf("0.2")},
        chi2=mp.mpf("0.5"),
        reduced_chi2=mp.mpf("0.25"),
        aic=mp.mpf("0"),
        bic=mp.mpf("0"),
        r2=mp.mpf("1"),
        rmse=mp.mpf("0.1"),
        residuals=[mp.mpf("0.1"), mp.mpf("-0.1")],
        fitted_curve=[],
        covariance=[[mp.mpf("0.01"), mp.mpf("0")], [mp.mpf("0"), mp.mpf("0.04")]],
        param_errors_stat={"A": mp.mpf("0.1"), "B": mp.mpf("0.2")},
        param_errors_sys={},
        param_errors_total={"A": mp.mpf("0.1"), "B": mp.mpf("0.2")},
        details={"dof": 2, "covariance_parameters": ["A", "B"]},
    )


def _seed(window: Any) -> dict[str, Any]:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()
    inputs = {
        "headers": ["x", "y"],
        "rows": [(mp.mpf("0"), mp.mpf("1")), (mp.mpf("1"), mp.mpf("3"))],
        "sigma_rows": [(None, None), (None, None)],
        "fit_result": _fit_result(),
        "expression": "A*x + B",
        "substituted": "2*x + 1",
        "units": None,
        "target_column": "y",
        "variable_pairs": [("x", "x")],
        "latex_group_size": 3,
        "uncertainty_digits": 1,
        "latex_digits": 16,
        "use_dcolumn": True,
        "caption": None,
    }
    window.remember_latex_inputs("fit_single", inputs)
    return inputs


def _writer_tex(window: Any, inputs: dict[str, Any], tmp_path: Any) -> str:
    """Reference tex from _write_fitting_latex with widgets set to match the stash."""
    window.fit_target_edit.setText(inputs["target_column"])
    variable_edit, column_edit, *_ = window.variable_rows[0]
    variable_edit.setText(inputs["variable_pairs"][0][0])
    column_edit.setText(inputs["variable_pairs"][0][1])
    window.latex_input_precision_spin.setValue(inputs["latex_digits"])
    window.latex_group_size_spin.setValue(inputs["latex_group_size"])
    window.dcolumn_checkbox.setChecked(inputs["use_dcolumn"])
    QApplication.processEvents()
    out = tmp_path / "writer.tex"
    window._write_fitting_latex(
        inputs["headers"],
        inputs["rows"],
        inputs["sigma_rows"],
        inputs["fit_result"],
        inputs["expression"],
        inputs["substituted"],
        None,
        str(out),
        inputs["use_dcolumn"],
        units=inputs["units"],
    )
    return out.read_text(encoding="utf-8")


def test_fitting_ondemand_rebuild_matches_writer(window: Any, tmp_path: Any) -> None:
    inputs = _seed(window)
    expected = _writer_tex(window, inputs, tmp_path)

    tex_path = window.generate_fitting_latex_on_demand()
    assert tex_path is not None
    assert Path(tex_path).read_text(encoding="utf-8") == expected


def test_fitting_ondemand_immune_to_post_run_widget_edits(window: Any, tmp_path: Any) -> None:
    inputs = _seed(window)
    expected = _writer_tex(window, inputs, tmp_path)

    # Corrupt the target/variable widgets AFTER seeding — on-demand must use the stash.
    window.fit_target_edit.setText("x")
    variable_edit, column_edit, *_ = window.variable_rows[0]
    variable_edit.setText("zzz")
    column_edit.setText("y")
    QApplication.processEvents()

    rebuilt = Path(window.generate_fitting_latex_on_demand()).read_text(encoding="utf-8")
    assert rebuilt == expected


def test_fitting_ondemand_returns_none_without_stash(window: Any) -> None:
    window.mode_combo.setCurrentIndex(window.mode_combo.findData("fitting"))
    QApplication.processEvents()
    window._last_latex_inputs = {}
    assert window.generate_fitting_latex_on_demand() is None
