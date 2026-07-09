"""P2-4: an 800-line file-size ratchet.

Splitting the ~30 god-files (window.py at 3181 lines, workers_core.py at 2793,
statistics.py at 2768, …) is an XL effort done file-by-file. This test installs
the ratchet in the meantime: no NEW source file may exceed 800 lines, and no
existing god-file may grow past a frozen baseline. That stops the problem from
worsening and creates steady downward pressure without a risky mass-split.

To shrink a god-file: lower its baseline number here (or drop it once it's under
800). To (legitimately) grow one, you must consciously raise its baseline — which
surfaces the decision in review instead of letting files sprawl silently.
"""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_SOFT_LIMIT = 800
# Per-file headroom over the frozen baseline, so trivial one-line edits to a
# god-file don't trip the ratchet — but real growth does.
_HEADROOM = 40

# Frozen baseline: source files that already exceed the soft limit, with their
# current line count. New files must stay <= _SOFT_LIMIT; these must not grow
# past baseline + _HEADROOM. Shrink these numbers as god-files get split.
_BASELINE: dict[str, int] = {
    # Raised across the feat/toolbar-options-popup feature (adaptive workbench, on-demand
    # LaTeX, engine-adaptive digit grouping, toolbar status chip, file-precedence inputs,
    # design-review token pass). The growth is the sum of that approved multi-commit feature;
    # splitting these god-files is a separate XL effort.
    "app_desktop/window.py": 3467,
    "app_desktop/workers_core.py": 2793,
    "datalab_core/statistics.py": 2768,
    "datalab_core/uncertainty.py": 2407,
    "app_desktop/panels.py": 2478,
    "datalab_core/recipes.py": 2055,
    "shared/plotting.py": 2045,
    "app_desktop/workspace_controller.py": 2130,
    "app_desktop/window_statistics_mixin.py": 2003,
    "datalab_core/history_compare.py": 1765,
    "datalab_core/statistics_hypothesis.py": 1504,
    "shared/ui_specs.py": 1203,
    "datalab_core/statistics_grouped.py": 1200,
    "datalab_core/root_solving.py": 1195,
    "app_web/logic/fitting.py": 1143,
    "app_desktop/window_extrapolation_mixin.py": 1280,
    "datalab_core/report_bundle.py": 1079,
    "root_solving/solver.py": 1076,
    "root_solving/plotting.py": 970,
    "fitting/implicit_model.py": 957,
    "datalab_core/statistics_time_series.py": 950,
    "app_desktop/views/statistics.py": 932,
    "datalab_core/statistics_matrix.py": 932,
    "statistics_utils.py": 912,
    # Batch-10 Stage 3: the two LaTeX QThread workers (_TectonicInstallWorker,
    # _LatexCompileWorker) + helpers were consolidated here from
    # window_latex_pdf_mixin.py so every worker lives in one place (reviewer-
    # requested consistency). That growth pushed workers_qt.py just past the
    # 800-line soft limit; consciously baselined.
    "app_desktop/workers_qt.py": 807,
    "datalab_latex/latex_formatting.py": 890,
    # Crossed 800 during the design-review token pass (semantic color _TOKENS + _tok resolver,
    # radius/CARD_PADDING scale) — the growth is one theme's single source of truth; baselined.
    "app_desktop/theme.py": 802,
    # Crossed 800 when the batch-fit on-demand LaTeX builder + F1 group-size fixes landed
    # (fixing the user-reported "拟合无法生成 tex"); consciously baselined.
    "app_desktop/window_fitting_residuals_mixin.py": 813,
    "shared/pdf_preview.py": 831,
    "app_web/blueprints/collaborate.py": 830,
    "app_desktop/views/fitting.py": 821,
    # Raised 819 -> 890: R3-soft added the fit_custom_model docstring, typed
    # ModelSpecification-field access, and the J^T J matrix refactor. The growth
    # is almost entirely documentation; consciously re-baselined.
    "fitting/hp_fitter.py": 890,
    "fitting/plot_fitting.py": 817,
    "datalab_core/fitting.py": 803,
}

_SKIP_DIR_PARTS = {"tests", "tools", ".venv", "build", "dist", "site", "__pycache__", ".git"}


def _source_files() -> list[Path]:
    files: list[Path] = []
    for path in _ROOT.rglob("*.py"):
        if any(part in _SKIP_DIR_PARTS for part in path.relative_to(_ROOT).parts):
            continue
        files.append(path)
    return files


def _line_count(path: Path) -> int:
    return sum(1 for _ in path.open(encoding="utf-8", errors="replace"))


def test_no_new_file_exceeds_the_soft_limit():
    offenders: list[str] = []
    for path in _source_files():
        rel = str(path.relative_to(_ROOT))
        if rel in _BASELINE:
            continue
        count = _line_count(path)
        if count > _SOFT_LIMIT:
            offenders.append(f"{rel} ({count} lines)")
    assert not offenders, (
        f"New source file(s) exceed the {_SOFT_LIMIT}-line soft limit — split them, "
        f"or (consciously) add them to _BASELINE: {offenders}"
    )


def test_god_files_do_not_grow_past_baseline():
    grown: list[str] = []
    for rel, baseline in _BASELINE.items():
        path = _ROOT / rel
        if not path.is_file():
            continue  # file removed/renamed — fine, it left the god-file set
        count = _line_count(path)
        if count > baseline + _HEADROOM:
            grown.append(f"{rel}: {count} > baseline {baseline} (+{_HEADROOM} headroom)")
    assert not grown, (
        "God-file(s) grew past their frozen baseline — shrink them or raise the "
        f"baseline deliberately: {grown}"
    )


def test_baseline_has_no_stale_entries():
    # If a listed god-file has been split below the limit, drop it from _BASELINE
    # so the ratchet keeps tightening.
    stale: list[str] = []
    for rel in _BASELINE:
        path = _ROOT / rel
        if path.is_file() and _line_count(path) <= _SOFT_LIMIT:
            stale.append(rel)
    assert not stale, (
        f"These files are now <= {_SOFT_LIMIT} lines; remove them from _BASELINE: {stale}"
    )
