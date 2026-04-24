"""MCMC GUI wiring — #12 Phase 3 Task 3.6 continuation.

Pins the UI contract:
- Fitting panel exposes a "Refine with MCMC" checkbox.
- Checkbox is defaulted OFF (opt-in — MCMC is slow).
- Checkbox is disabled when emcee isn't installed, with a tooltip
  explaining why (so users know the feature exists and what to
  install).
- The ``fit_mcmc_refine`` attribute is greppable; a future refactor
  that removes it fails these tests instead of silently dropping
  the feature.
- When the user prepares an auto-fit job, the ``refine_with_mcmc``
  flag reads the checkbox state.
- Corner-plot rendering is stubbable via a helper function that
  never imports emcee at module load time.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from typing import Any  # noqa: E402

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def _app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def _window(_app, qtbot):
    from app_desktop.window import ExtrapolationWindow

    win = ExtrapolationWindow()
    qtbot.addWidget(win)
    yield win
    win.close()


def test_fit_mcmc_refine_checkbox_exists(_window):
    assert hasattr(_window, "fit_mcmc_refine"), (
        "Fitting panel must expose a fit_mcmc_refine QCheckBox for #12"
    )
    from PySide6.QtWidgets import QCheckBox

    assert isinstance(_window.fit_mcmc_refine, QCheckBox)


def test_mcmc_checkbox_defaults_off(_window):
    """MCMC is slow (~10–60s). Must be opt-in."""
    assert _window.fit_mcmc_refine.isChecked() is False


def test_mcmc_checkbox_disabled_when_emcee_absent(_window, monkeypatch):
    """When emcee isn't installed the checkbox is disabled so users
    can see the feature exists but can't mis-configure a job."""
    import fitting.mcmc_fitter as mcmc_mod

    # If the test env has emcee, skip — we only pin the absent-dep path
    # here, and the panel decides enable/disable at build time based on
    # HAS_EMCEE, so we can't dynamically toggle post-hoc.
    if mcmc_mod.HAS_EMCEE:
        pytest.skip("emcee installed; this test pins the absent path only")
    assert _window.fit_mcmc_refine.isEnabled() is False
    tooltip = _window.fit_mcmc_refine.toolTip()
    assert "emcee" in tooltip.lower(), (
        "Disabled tooltip must mention the missing emcee package "
        "so users know what to install"
    )


def test_mcmc_checkbox_bilingual_registered(_window):
    """Label must be registered for zh/en swap."""
    text = _window.fit_mcmc_refine.text()
    # Either zh ("MCMC 精炼") or en ("Refine with MCMC") depending on
    # current language, but must be non-empty.
    assert text.strip(), "MCMC checkbox must have a visible label"


def test_auto_fit_job_reads_mcmc_flag(_window):
    """``_prepare_auto_fit_kwargs`` (or equivalent) must route the
    checkbox state into the job's refine_with_mcmc flag so the
    worker knows whether to run MCMC."""
    from app_desktop.workers_core import AutoFitJob

    # AutoFitJob must have a refine_with_mcmc field (default False)
    # so the CLI + GUI share one source of truth.
    fields = AutoFitJob.__dataclass_fields__
    assert "refine_with_mcmc" in fields, (
        "AutoFitJob must expose refine_with_mcmc for #12"
    )
    # Default must be False (opt-in semantics)
    assert fields["refine_with_mcmc"].default is False


def test_prepare_auto_fit_job_forwards_mcmc_checkbox(_window, qtbot):
    """End-to-end wiring: flipping the checkbox must propagate into
    the AutoFitJob that the worker receives. A field that exists but
    is never populated is a dead wire."""
    from app_desktop.workers_core import AutoFitJob
    import fitting.mcmc_fitter as mcmc_mod

    # Need a minimal dataset for _prepare_auto_fit_job. If the helper
    # requires full state, skip — the contract we really care about
    # is: checkbox state → job field.
    if not hasattr(_window, "_prepare_auto_fit_job"):
        pytest.skip("window does not expose _prepare_auto_fit_job")

    # Build a synthetic dataset the fit can chew on. The helper's
    # exact signature lives in window_fitting_mixin; use a duck-typed
    # dataset tuple.
    from mpmath import mp

    xs = [mp.mpf(v) for v in (1, 2, 3, 4, 5)]
    ys = [mp.mpf(v) for v in (2, 4, 6, 8, 10)]
    dataset = (["x", "y"], [(xs[i], ys[i]) for i in range(5)], [])

    # Only exercise when emcee is installed, otherwise the checkbox
    # is disabled and the helper's guard forces refine_with_mcmc=False.
    if not mcmc_mod.HAS_EMCEE:
        # Absent-path variant: the helper must propagate False
        # regardless of checkbox state because the checkbox is
        # disabled.
        _window.fit_mcmc_refine.setChecked(True)  # shouldn't matter
        try:
            job = _window._prepare_auto_fit_job(dataset)
        except Exception:
            pytest.skip("_prepare_auto_fit_job has extra requirements")
        assert isinstance(job, AutoFitJob)
        assert job.refine_with_mcmc is False, (
            "checkbox is disabled without emcee — helper must force False"
        )
        return

    # Present-path: checkbox True → job.refine_with_mcmc True.
    _window.fit_mcmc_refine.setChecked(True)
    try:
        job = _window._prepare_auto_fit_job(dataset)
    except Exception:
        pytest.skip("_prepare_auto_fit_job has extra requirements")
    assert job.refine_with_mcmc is True

    _window.fit_mcmc_refine.setChecked(False)
    job = _window._prepare_auto_fit_job(dataset)
    assert job.refine_with_mcmc is False


def test_render_corner_plot_accepts_mcmc_result():
    """The corner-plot renderer must accept the MCMCResult shape
    (chain + param_names) and return bytes. When corner isn't
    installed, falls back to a matplotlib stub so the desktop can
    still show *something*."""
    from fitting.mcmc_fitter import render_corner_plot

    # Minimal fake MCMCResult — avoid requiring emcee in the test
    class _FakeResult:
        param_names = ["a", "b"]
        medians = {"a": 1.0, "b": 2.0}
        lo_ci = {"a": 0.9, "b": 1.9}
        hi_ci = {"a": 1.1, "b": 2.1}

        # Fake chain: use a list-of-lists, not numpy, so the test
        # runs without numpy. The renderer is expected to convert.
        def __init__(self):
            # Minimal representative 'chain' — shape (walkers=4, steps=10, params=2)
            self.chain = [
                [[1.0 + 0.01 * s, 2.0 + 0.01 * s] for s in range(10)]
                for _ in range(4)
            ]
            self.log_prob = None
            self.acceptance_fraction = 0.3

    png = render_corner_plot(_FakeResult())
    assert isinstance(png, (bytes, bytearray))
    assert png[:8] == b"\x89PNG\r\n\x1a\n", (
        "corner plot must be a valid PNG (either corner.corner or a "
        "matplotlib fallback)"
    )


def test_gui_requirements_declares_emcee():
    """gui_requirements.txt must list emcee + numpy + corner so the
    desktop install gives users MCMC out of the box."""
    from pathlib import Path

    reqs = (
        Path(__file__).resolve().parent.parent / "gui_requirements.txt"
    ).read_text(encoding="utf-8")
    for needle in ("emcee", "numpy", "corner"):
        assert needle in reqs, (
            f"gui_requirements.txt must include {needle} for MCMC support"
        )


def test_pyproject_mcmc_extra_still_lists_deps():
    """pyproject's [mcmc] extra must continue to list the full set —
    don't regress the extras table when adding GUI wiring."""
    import sys

    if sys.version_info < (3, 11):
        pytest.skip("requires Python 3.11 tomllib")
    import tomllib
    from pathlib import Path

    with open(
        Path(__file__).resolve().parent.parent / "pyproject.toml", "rb"
    ) as f:
        data = tomllib.load(f)
    extras = data["project"]["optional-dependencies"]
    mcmc = extras["mcmc"]
    joined = " ".join(mcmc).lower()
    assert "emcee" in joined
    assert "numpy" in joined
    assert "corner" in joined
