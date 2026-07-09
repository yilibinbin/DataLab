"""Round-trip serialization of the on-demand-tex stash (_last_latex_inputs).

The stash holds mpmath-heavy, mode-specific structures (mp.mpf scalars, FitResult dataclasses,
UncertainValue objects, nested lists/tuples/dicts). Persisting it in the workspace lets 生成 TeX
work after reopening WITHOUT recomputing. Serialization must be full-precision and lossless.
"""

from __future__ import annotations

import mpmath as mp

from app_desktop.latex_inputs_serialization import (
    decode_latex_inputs,
    encode_latex_inputs,
)
from fitting.hp_fitter import FitResult
from shared.uncertainty import UncertainValue


def _is_json_safe(obj: object) -> bool:
    import json

    json.dumps(obj)  # raises if not JSON-serializable
    return True


def test_mpf_roundtrips_at_full_precision() -> None:
    with mp.workdps(60):
        v = mp.mpf("1.234567890123456789012345678901234567890")
        store = {"error": {"x": v}}
        encoded = encode_latex_inputs(store)
        assert _is_json_safe(encoded)
        decoded = decode_latex_inputs(encoded)
        assert isinstance(decoded["error"]["x"], mp.mpf)
        assert decoded["error"]["x"] == v  # exact, no precision loss


def test_mpf_high_precision_survives_decode_at_low_dps() -> None:
    """Review S1: encoding stored a fixed 50-digit decimal string and decode reparsed at the
    ambient mp.dps, so a high-precision workspace reopened at low dps lost precision. The value is
    now stored as exact (sign, mantissa, exp) and reconstructed under high workdps — lossless
    regardless of the session's mp.dps."""
    prev = mp.mp.dps
    try:
        mp.mp.dps = 80
        v = mp.mpf("1.2345678901234567890123456789012345678901234567890123456789012345")
        encoded = encode_latex_inputs({"error": {"x": v}})
        mp.mp.dps = 15  # reopen in a LOW-precision session
        decoded = decode_latex_inputs(encoded)["error"]["x"]
        mp.mp.dps = 80
        assert decoded == v  # exact — not truncated to ~16 digits

        # A value beyond the old 50-digit encode cap also survives.
        mp.mp.dps = 130
        big = mp.mpf("3." + "14159265358979323846" * 6)
        assert decode_latex_inputs(encode_latex_inputs({"e": {"x": big}}))["e"]["x"] == big
    finally:
        mp.mp.dps = prev


def test_mpf_special_values_roundtrip() -> None:
    for sv in (mp.inf, -mp.inf, mp.mpf("0"), mp.mpf("-2.5"), mp.mpf("1e-50")):
        out = decode_latex_inputs(encode_latex_inputs({"e": {"x": sv}}))["e"]["x"]
        assert out == sv
    nan_out = decode_latex_inputs(encode_latex_inputs({"e": {"x": mp.nan}}))["e"]["x"]
    assert mp.isnan(nan_out)


def test_tuple_list_dict_nesting_roundtrips() -> None:
    store = {
        "error": {
            "rows": [(mp.mpf("1"), None), (mp.mpf("2"), mp.mpf("3"))],
            "headers": ["A", "B"],
            "flag": True,
            "n": 5,
            "note": None,
        }
    }
    decoded = decode_latex_inputs(encode_latex_inputs(store))
    rows = decoded["error"]["rows"]
    assert isinstance(rows[0], tuple)  # tuples preserved, not coerced to list
    assert rows[0][1] is None
    assert rows[1][0] == mp.mpf("2")
    assert decoded["error"]["headers"] == ["A", "B"]
    assert decoded["error"]["flag"] is True and decoded["error"]["n"] == 5


def test_uncertain_value_roundtrips() -> None:
    uv = UncertainValue(mp.mpf("4.0"), mp.mpf("0.4"), uncertainty_digits=2)
    decoded = decode_latex_inputs(encode_latex_inputs({"error": {"u": uv}}))
    out = decoded["error"]["u"]
    assert isinstance(out, UncertainValue)
    assert out.value == mp.mpf("4.0")
    assert out.uncertainty == mp.mpf("0.4")
    assert out.uncertainty_digits == 2


def test_fit_result_roundtrips() -> None:
    fr = FitResult(
        params={"A": mp.mpf("2")}, param_errors={"A": mp.mpf("0.1")},
        chi2=mp.mpf("0.5"), reduced_chi2=mp.mpf("0.25"), aic=mp.mpf("0"), bic=mp.mpf("0"),
        r2=mp.mpf("1"), rmse=mp.mpf("0.1"), residuals=[mp.mpf("0.1")], fitted_curve=[],
        covariance=[[mp.mpf("0.01")]], param_errors_stat={"A": mp.mpf("0.1")},
        param_errors_sys={}, param_errors_total={"A": mp.mpf("0.1")}, details={"dof": 1},
    )
    encoded = encode_latex_inputs({"fit_single": {"fit_result": fr}})
    assert _is_json_safe(encoded)
    out = decode_latex_inputs(encoded)["fit_single"]["fit_result"]
    assert isinstance(out, FitResult)
    assert out.params["A"] == mp.mpf("2")
    assert out.covariance[0][0] == mp.mpf("0.01")
    assert out.details["dof"] == 1


def test_empty_store_roundtrips() -> None:
    assert decode_latex_inputs(encode_latex_inputs({})) == {}
    assert encode_latex_inputs(None) == {}


def test_workspace_roundtrip_lets_generate_tex_work_after_reopen(qtbot) -> None:
    """The end-to-end goal: after saving+reopening a workspace, 生成 TeX works WITHOUT a
    recompute because the tex-rebuild stash is persisted in the manifest and rehydrated."""
    import os

    import pytest

    # This is the only Qt-dependent test in the file — skip cleanly (not fixture-not-found) when
    # pytest-qt / PySide6 are absent, rather than gating the whole (non-Qt) module.
    pytest.importorskip("pytestqt")
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from shared.uncertainty import parse_uncertainty_format

    from app_desktop import workspace_controller as wc
    from app_desktop.window import ExtrapolationWindow

    src = ExtrapolationWindow()
    qtbot.addWidget(src)
    src.mode_combo.setCurrentIndex(src.mode_combo.findData("error"))
    src._last_latex_inputs = {
        "error": {
            "headers": ["A", "B"],
            "parsed_data": [[parse_uncertainty_format("1.0(1)"), parse_uncertainty_format("2.0(2)")]],
            "results": [parse_uncertainty_format("4.0(4)")],
            "constants": {"k": parse_uncertainty_format("9.8(1)")},
            "used_columns": ["B"],
            "formula": "A + B * k",
            "units": None,
        }
    }
    src._last_result_kind = "error"
    bundle = wc.capture_workspace(src, title="t")
    assert "latex_inputs" in bundle.manifest  # persisted

    dst = ExtrapolationWindow()
    qtbot.addWidget(dst)
    dst.mode_combo.setCurrentIndex(dst.mode_combo.findData("error"))
    wc.restore_workspace(dst, bundle.manifest, bundle.attachments)
    dst._last_result_kind = "error"

    # No recompute — generate straight from the rehydrated stash.
    path = dst.generate_latex_for_current_result()
    assert path is not None
    assert "tabular" in dst.latex_edit.toPlainText()
