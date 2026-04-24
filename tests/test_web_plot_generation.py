from __future__ import annotations

import pytest

import mpmath as mp

from app_web.logic import plots


def test_web_plot_generation_produces_png_bytes_when_matplotlib_available():
    pytest.importorskip("matplotlib")

    extrap = plots._render_extrapolation_plot(
        row_values=(mp.mpf("1.0"), mp.mpf("1.1"), mp.mpf("1.2")),
        extrap_value=mp.mpf("1.25"),
        sigma=mp.mpf("0.05"),
        idx=1,
        lang="en",
    )
    assert extrap is not None
    assert extrap.startswith(b"\x89PNG")

    class _Res:
        def __init__(self, contributions):
            self.contributions = contributions

    contrib = plots._render_contribution_plot(
        results=[_Res({"A": mp.mpf("1"), "B": mp.mpf("2")})],
        lang="en",
    )
    assert contrib is not None
    assert contrib.startswith(b"\x89PNG")

    stats = plots._render_statistics_plot(
        values=[mp.mpf("1"), mp.mpf("2"), mp.mpf("3")],
        sigmas=[mp.mpf("0.1"), mp.mpf("0.2"), mp.mpf("0.1")],
        stats_result={"mean": mp.mpf("2"), "std_mean": mp.mpf("0.1")},
        lang="en",
    )
    assert stats is not None
    assert stats.startswith(b"\x89PNG")
