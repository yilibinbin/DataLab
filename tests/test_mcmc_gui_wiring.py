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
- Explicit fit jobs remain the desktop fitting job surface after automatic
  fitting removal.
- Corner-plot rendering is stubbable via a helper function that
  never imports emcee at module load time.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


def test_removed_auto_fit_job_is_not_mcmc_contract(_window):
    """MCMC GUI wiring must not depend on the removed automatic fitting job."""
    import app_desktop.workers_core as workers_core

    assert not hasattr(workers_core, "AutoFitJob")
    assert hasattr(workers_core, "FitJob")


def test_prepare_explicit_fit_job_keeps_mcmc_checkbox_independent(_window):
    """Preparing an explicit fit job should use the remaining FitJob path."""
    from app_desktop.workers_core import FitJob
    from mpmath import mp

    _window.fit_model_combo.setCurrentIndex(_window.fit_model_combo.findData("polynomial"))
    _window.fit_mcmc_refine.setChecked(True)
    xs = [mp.mpf(v) for v in (1, 2, 3, 4, 5)]
    ys = [mp.mpf(v) for v in (2, 4, 6, 8, 10)]
    dataset = (["A", "B"], [(xs[i], ys[i]) for i in range(5)], [])

    job = _window._prepare_fit_job(
        dataset,
        generate_latex=False,
        output_path="",
        verbose=False,
        render_plots=False,
    )

    assert isinstance(job, FitJob)
    assert job.model_type == "polynomial"
    # The checkbox must actually propagate to the job — otherwise it is a shell
    # control that does nothing when ticked.
    assert job.refine_with_mcmc is True

    _window.fit_mcmc_refine.setChecked(False)
    job_off = _window._prepare_fit_job(
        dataset, generate_latex=False, output_path="", verbose=False, render_plots=False
    )
    assert job_off.refine_with_mcmc is False


def test_refine_with_mcmc_flag_triggers_refinement_in_worker(monkeypatch):
    """When job.refine_with_mcmc is True, the fit worker must invoke MCMC refinement
    on the fit result. When False, it must not. Guards against the flag being read
    but never acted on."""
    import app_desktop.workers_core as workers_core

    calls: list[bool] = []

    def _fake_attach(fit_result, job):
        calls.append(True)

    monkeypatch.setattr(workers_core, "_attach_mcmc_refinement_to_fit", _fake_attach)

    class _FakeOutput:
        def __init__(self):
            from fitting.hp_fitter import FitResult
            from mpmath import mp

            self.fit_result = FitResult(
                params={"a": mp.mpf("1")},
                param_errors={"a": mp.mpf("0.1")},
                chi2=mp.mpf("0"),
                reduced_chi2=mp.mpf("0"),
                aic=mp.mpf("0"),
                bic=mp.mpf("0"),
                r2=mp.mpf("1"),
                rmse=mp.mpf("0"),
                residuals=[mp.mpf("0")],
                fitted_curve=[mp.mpf("1")],
                covariance=[[mp.mpf("1")]],
                details={},
            )
            self.expression = "a"
            self.logs = []
            self.warnings = []

    monkeypatch.setattr(workers_core, "execute_direct_fit", lambda *a, **k: _FakeOutput())

    from app_desktop.workers_core import FitJob

    def _job(refine: bool) -> FitJob:
        return FitJob(
            model_type="polynomial",
            headers=["x", "y"],
            data_rows=[],
            sigma_rows=[],
            x_series=[],
            y_series=[],
            sigma_series=[],
            weights=None,
            variable_map={"x": "x"},
            variable_data={},
            target_series=[],
            target_column="y",
            model_expr="a",
            parameter_config={},
            parameter_names=["a"],
            refine_with_mcmc=refine,
        )

    calls.clear()
    workers_core._execute_fit_job_payload(_job(refine=True))
    assert calls == [True], "refine_with_mcmc=True must trigger MCMC refinement"

    calls.clear()
    workers_core._execute_fit_job_payload(_job(refine=False))
    assert calls == [], "refine_with_mcmc=False must NOT trigger MCMC refinement"


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
    """The desktop install must give users MCMC (emcee + numpy + corner) out of
    the box. Since P2-2 gui_requirements.txt is a thin pointer to pyproject
    extras, so this is delivered via the [mcmc] extra — whose contents are pinned
    by test_pyproject_mcmc_extra_still_lists_deps below."""
    from pathlib import Path

    reqs = (
        Path(__file__).resolve().parent.parent / "gui_requirements.txt"
    ).read_text(encoding="utf-8")
    non_comment = [
        line.strip()
        for line in reqs.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert any("mcmc" in line for line in non_comment), (
        "gui_requirements.txt must include the [mcmc] extra for MCMC support"
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
