"""Phase 4 #20 — centralised matplotlib backend regression tests.

Pins the rule that every module importing matplotlib.pyplot must
route through shared.plotting, so the backend stays Agg in all
contexts (headless CI, Qt threads, web workers).
"""

from __future__ import annotations

import importlib
import sys


def test_shared_plotting_exposes_plt_and_rcparams():
    from shared.plotting import plt, rcParams

    assert plt is not None
    assert rcParams is not None


def test_backend_is_agg_after_shared_plotting_import():
    import matplotlib

    import shared.plotting  # noqa: F401

    assert matplotlib.get_backend().lower() == "agg"


def test_assert_agg_backend_does_not_raise():
    from shared.plotting import assert_agg_backend

    # Should not raise in the test environment
    assert_agg_backend()


def test_business_module_import_preserves_agg_backend():
    """Import an arbitrary business module that uses matplotlib and
    verify the backend stays Agg. Regressions where a module calls
    ``matplotlib.use("QtAgg")`` locally would fail this."""
    import matplotlib

    # Force re-imports so a stale sys.modules entry doesn't hide a bug
    for mod in list(sys.modules.keys()):
        if mod.startswith("fitting.plot_fitting") or mod == "shared.plotting":
            del sys.modules[mod]

    importlib.import_module("fitting.plot_fitting")
    assert matplotlib.get_backend().lower() == "agg"


def test_rcparams_have_cjk_fallback():
    """Post-import check: the CJK fallback chain is set, so plots
    with Chinese labels don't fall back to missing-glyph boxes."""
    from shared.plotting import rcParams

    fallback = rcParams["font.sans-serif"]
    assert any("YaHei" in font or "PingFang" in font or "SimHei" in font
               for font in fallback), (
        "CJK font fallback chain missing; Chinese labels would render "
        "as glyph-missing boxes"
    )


def test_unicode_minus_disabled():
    """Axis labels must use ASCII minus so LaTeX exports (siunitx)
    don't trip over U+2212."""
    from shared.plotting import rcParams

    assert rcParams["axes.unicode_minus"] is False
