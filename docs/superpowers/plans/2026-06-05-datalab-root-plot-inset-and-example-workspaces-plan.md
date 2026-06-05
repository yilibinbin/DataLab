# DataLab Root Plot Insets and Example Workspaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add honest, readable root-solving visualizations for tiny root uncertainty and 2D systems, prevent the left configuration pane from exposing a horizontal scrollbar after splitter dragging, then ship generated example workspaces and bilingual docs covering every visible DataLab module/method family.

**Architecture:** Deliver this as four independently testable slices: root plotting, left-panel layout hardening, example catalog/menu, and documentation. Root plotting stays inside `root_solving.plotting`; the main plot remains true scale and automatic insets are additive metadata/rendering. Left-panel layout hardening treats "no horizontal scrollbar" as a runtime invariant across visible modes/submodes, not just a one-time splitter clamp. Example workspaces use one importable catalog plus one generated JSON index so generator, tests, docs, and the desktop menu cannot drift.

**Tech Stack:** Python 3, PySide6/Qt, matplotlib/Agg via `shared.plotting`, mpmath/SciPy/SymPy root solving, DataLab `.datalab` ZIP workspaces, pytest/pytest-qt, ruff, compileall.

---

## Scope Rules

- Do not change root solver mathematics, fitting algorithms, uncertainty propagation formulas, or release packaging in this plan.
- Do not add a GUI option for root insets. Insets are automatic when uncertainty is below the readability threshold.
- Do not enlarge uncertainty bars on the main plot. The main root plot must keep the original true-scale axis limits.
- The left configuration pane must never expose a horizontal scrollbar after users drag the middle splitter. The splitter minimum must be derived from the currently visible controls after layout activation, including tables, help buttons, mode-specific widgets, vertical-scrollbar overhead, and language-dependent labels.
- Support system plots only for exactly two equations and exactly two real unknowns. Higher-dimensional systems emit one localized warning and no image. Missing, empty, invalid, or reversed 2D axis bounds fall back to an automatic range around the solved root instead of crashing.
- Example coverage is derived from visible UI registries/options, not from a manually maintained test-only set.
- Do not stage `.superpowers/` or any local temporary wrapper files during implementation.

## File Structure

### Slice A: Root Plotting

- Modify: `root_solving/plotting.py`
  - Add root inset metadata/drawing.
  - Replace the existing system-root early return with 2D contour rendering.
  - Update `SYSTEM_ROOT_PLOT_WARNING` to the new precise warning string.
  - Parse system bounds through existing safe helpers, not raw `mp.mpf(str(...))`.
- Modify: `root_solving/messages.py`
  - Localize the updated system-plot warning.
- Modify: `tests/test_root_solving_plotting.py`
  - Cover tiny-uncertainty inset metadata, true-scale main plots, scan insets, 2D contour rendering, invalid bounds, and high-dimensional warnings.
- Modify: `tests/test_app_desktop_workers_core.py`
  - Cover worker payload behavior for supported 2D system plots and unsupported system warnings.

### Slice B: Left Panel Splitter and Horizontal Scrollbar Hardening

- Modify: `app_desktop/panels.py`
  - Recompute left-pane minimum width from the active visible content after mode/submode/language changes and after splitter restore.
  - Include root-solving scan/multiple-root widgets and unknown table widths in the content-width floor.
  - Clamp the splitter immediately when a horizontal scrollbar would otherwise appear.
- Modify: `tools/scan_desktop_gui_schema.py`
  - Expand the scan so it checks every calculation mode and root-solving submode, not only the default screen.
  - Force the splitter to the smallest legal width and assert `horizontalScrollBar().maximum() == 0`.
- Modify: `tests/test_desktop_gui_schema_scan.py`
  - Add regression coverage for the user-observed root-solving scan-multiple layout with equation `x^2-A`, bounds table visible, plot/result tabs visible, and a forced narrow splitter.
- Modify: `tests/test_desktop_root_solving_ui.py`
  - Add focused GUI assertions that root-solving mode/submode transitions refresh the left-pane minimum and do not leave stale splitter bounds.

### Slice C: Example Catalog and Desktop Menu

- Create: `examples/catalog.py`
  - Define `ExampleSpec`, ordered `EXAMPLE_SPECS`, `EXAMPLE_NAMES`, `examples_by_category()`, and `example_index_payload()`.
  - This module must not import Qt or desktop GUI modules.
- Create: `shared/example_coverage.py`
  - Define visible module/method/mode requirements in one PySide-free place and reuse `shared.ui_specs.METHOD_DISPLAY_ORDER` for extrapolation.
- Modify: `app_desktop/panels.py`
  - Consume `shared.example_coverage` constants for root/error/statistics/fitting combo items so example tests and GUI choices share the same registry.
- Modify: `tools/generate_example_workspaces.py`
  - Consume `examples.catalog.EXAMPLE_SPECS`.
  - Regenerate every `.datalab` archive.
  - Write `examples/workspaces/example_catalog.json` for menu labels/docs.
  - Remove stale archives after confirming their names belong to the previous generated inventory.
- Modify: `app_desktop/window.py`
  - Replace the hardcoded `EXAMPLE_WORKSPACE_NAMES` tuple with catalog/index loading.
  - Read the single lightweight `example_catalog.json`; do not unzip every `.datalab` archive on the GUI thread for labels.
- Modify: `tests/test_example_workspaces.py`
  - Derive required coverage from visible registries/options.
  - Enforce ordered unique example names and generator determinism.
- Modify: `tests/test_desktop_example_workspace_menu.py`
  - Assert menu discoverability, category labels, and template save-as behavior.
- Modify: `examples/workspaces/*.datalab`
  - Regenerated artifacts from `tools/generate_example_workspaces.py`.
- Create: `examples/workspaces/example_catalog.json`
  - Generated lightweight index for the desktop menu and docs smoke tests.

### Slice D: Documentation

- Create: `docs/desktop/root-solving.zh.md`
- Create: `docs/desktop/root-solving.en.md`
- Modify: `docs/desktop/manifest.json`
- Modify: `desktop_doc_loader.py`
- Modify: `docs/desktop/index.zh.md`
- Modify: `docs/desktop/index.en.md`
- Modify: `docs/desktop/guide.zh.md`
- Modify: `docs/desktop/guide.en.md`
- Modify: `docs/desktop/theory.zh.md`
- Modify: `docs/desktop/theory.en.md`
- Modify: `examples/README.md`
- Modify: `README.md`
- Modify: `QUICK_START.md`
- Modify: `QUICK_START.en.md`
- Modify: `tests/test_desktop_docs_smoke.py`

---

## Slice A: Root Plotting

### Task A1: Add Tiny-Uncertainty Inset Contract

**Files:**
- Modify: `tests/test_root_solving_plotting.py`
- Modify: `root_solving/plotting.py`

- [ ] **Step 1: Add RED test for inset metadata without asserting impossible rounded bounds**

Append this test to `tests/test_root_solving_plotting.py`:

```python
def test_tiny_root_uncertainty_adds_inset_without_scaling_main_interval() -> None:
    problem = RootProblem(
        equations=("x^2 - A",),
        unknowns=(RootUnknown("x", initial="2", lower="1.999999", upper="2.000001"),),
        row_values={"A": "4.000000000000(1)"},
        mode="scalar",
        precision=60,
    )
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={"A": "4.000000000000(1)"},
                result=RootResult(
                    roots=(RootValue(name="x", value=mp.mpf("2"), uncertainty=mp.mpf("2.5e-13")),),
                    backend="mpmath",
                    mode="scalar",
                    details={"uncertainty_method": "taylor", "taylor_order": 1},
                ),
            ),
        )
    )
    selection = select_root_plot_requests(batch, budget=RootPlotBudget(max_grid_points=101))

    image = render_nominal_root_plot(selection.requests[0], problem)

    assert image is not None
    assert image.metadata["main_plot_true_scale"] is True
    visualization = cast(Mapping[str, object], image.metadata["uncertainty_visualization"])
    intervals = cast(tuple[Mapping[str, object], ...], visualization["root_intervals"])
    assert intervals == ({"name": "x", "lower": 2.0, "upper": 2.0},)
    insets = cast(tuple[Mapping[str, object], ...], image.metadata["root_insets"])
    assert len(insets) == 1
    inset = insets[0]
    assert inset["root_name"] == "x"
    assert inset["reason"] == "uncertainty_below_pixel_threshold"
    assert inset["true_interval"] == intervals[0]
    assert float(cast(tuple[float, float], inset["x_range"])[1]) > float(cast(tuple[float, float], inset["x_range"])[0])
```

Run:

```bash
PYTHONPATH=. pytest -q tests/test_root_solving_plotting.py::test_tiny_root_uncertainty_adds_inset_without_scaling_main_interval
```

Expected before implementation:

```text
FAILED ... KeyError: 'main_plot_true_scale'
```

- [ ] **Step 2: Implement inset metadata helpers**

In `root_solving/plotting.py`, add helpers near the existing plotting helpers:

```python
_ROOT_INSET_MAX_COUNT = 2
_ROOT_INSET_MIN_RELATIVE_WIDTH = 1.0e-6
_ROOT_INSET_SIGMA_MULTIPLIER = 8.0


def _linspace(lower: float, upper: float, count: int) -> tuple[float, ...]:
    if count <= 1:
        return (float(lower),)
    step = (float(upper) - float(lower)) / float(count - 1)
    return tuple(float(lower) + step * index for index in range(count))


def _root_inset_metadata(
    roots: Sequence[RootValue],
    *,
    unknown_name: str,
    x_values: Sequence[float],
    system: RootExpressionSystem,
) -> tuple[Mapping[str, object], ...]:
    if not x_values:
        return ()
    x_span = max(abs(float(x_values[-1] - x_values[0])), 1.0)
    pixel_threshold = x_span / 600.0
    insets: list[Mapping[str, object]] = []
    for root in roots:
        if root.name != unknown_name:
            continue
        center = _real_float(root.value)
        sigma = _real_float(root.uncertainty)
        if center is None or sigma is None or sigma <= 0.0 or sigma >= pixel_threshold:
            continue
        half_width = max(
            _ROOT_INSET_SIGMA_MULTIPLIER * sigma,
            _ROOT_INSET_MIN_RELATIVE_WIDTH * x_span,
        )
        local_x = _linspace(center - half_width, center + half_width, 81)
        local_y = _evaluate_nominal_curve(system, unknown_name, local_x)
        finite_y = [value for value in local_y if value is not None and isfinite(value)]
        if not finite_y:
            continue
        insets.append(
            {
                "root_name": root.name,
                "root_value": _round_float(center),
                "reason": "uncertainty_below_pixel_threshold",
                "true_interval": {
                    "name": root.name,
                    "lower": _round_float(center - sigma),
                    "upper": _round_float(center + sigma),
                },
                "x_range": (_round_float(local_x[0]), _round_float(local_x[-1])),
                "y_range": (_round_float(min(finite_y)), _round_float(max(finite_y))),
                "x_values": tuple(_round_float(value) for value in local_x),
                "y_values": tuple(None if value is None else _round_float(value) for value in local_y),
            }
        )
        if len(insets) >= _ROOT_INSET_MAX_COUNT:
            break
    return tuple(insets)
```

- [ ] **Step 3: Add true-scale metadata and draw insets**

In `_render_nominal_root_plot_with_warnings()`, after uncertainty metadata is calculated, add:

```python
root_insets = _root_inset_metadata(
    request.row.result.roots,
    unknown_name=unknown.name,
    x_values=x_values,
    system=system,
)
metadata["main_plot_true_scale"] = True
metadata["root_insets"] = root_insets
```

Replace the existing unconditional `fig.tight_layout()` in the scalar root plot renderer with:

```python
if root_insets:
    fig.tight_layout(rect=(0.0, 0.0, 0.56, 1.0))
    _draw_root_insets(fig, root_insets)
else:
    fig.tight_layout()
```

Add this helper:

```python
def _draw_root_insets(fig: Any, root_insets: Sequence[Mapping[str, object]]) -> None:
    for index, inset in enumerate(root_insets[:_ROOT_INSET_MAX_COUNT]):
        x_values_raw = _optional_value_sequence(inset.get("x_values"))
        y_values = _optional_value_sequence(inset.get("y_values"))
        if x_values_raw is None or y_values is None or any(value is None for value in x_values_raw):
            continue
        x_values = tuple(float(value) for value in x_values_raw if value is not None)
        inset_ax = fig.add_axes([0.62, 0.55 - index * 0.25, 0.32, 0.20])
        inset_ax.plot(x_values, _plot_values(y_values), color="#1f77b4", linewidth=1.2)
        inset_ax.axhline(0.0, color="#444444", linewidth=0.8, linestyle="--", alpha=0.8)
        root_value = inset.get("root_value")
        if isinstance(root_value, (int, float)):
            inset_ax.axvline(float(root_value), color="#d62728", linewidth=0.9, alpha=0.8)
        inset_ax.set_title("root zoom", fontsize=7)
        inset_ax.tick_params(labelsize=7)
        inset_ax.grid(True, alpha=0.25)
```

- [ ] **Step 4: Run focused inset tests**

Run:

```bash
PYTHONPATH=. pytest -q tests/test_root_solving_plotting.py::test_tiny_root_uncertainty_adds_inset_without_scaling_main_interval
```

Expected:

```text
1 passed
```

### Task A2: Add 2D System Contour Plot Contract

**Files:**
- Modify: `tests/test_root_solving_plotting.py`
- Modify: `root_solving/plotting.py`
- Modify: `root_solving/messages.py`
- Modify: `tests/test_app_desktop_workers_core.py`

- [ ] **Step 1: Add RED tests for 2D system contour and unsupported systems**

Append tests to `tests/test_root_solving_plotting.py`:

```python
def test_two_dimensional_system_root_renders_contour_plot() -> None:
    problem = RootProblem(
        equations=("x + y - 3", "x - y - 1"),
        unknowns=(
            RootUnknown("x", initial="2", lower="0", upper="4"),
            RootUnknown("y", initial="1", lower="-1", upper="3"),
        ),
        mode="system",
        precision=40,
    )
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={},
                result=RootResult(
                    roots=(
                        RootValue(name="x", value=mp.mpf("2")),
                        RootValue(name="y", value=mp.mpf("1")),
                    ),
                    backend="mpmath",
                    mode="system",
                ),
            ),
        )
    )

    selection = render_nominal_root_plots(batch, problem, budget=RootPlotBudget(max_grid_points=81))

    assert selection.warnings == ()
    assert len(selection.images) == 1
    image = selection.images[0]
    assert image.metadata["curve"] == "system_contour"
    assert image.metadata["unknowns"] == ("x", "y")
    assert image.metadata["equations"] == ("x + y - 3", "x - y - 1")
    assert image.metadata["grid_points"] == 81
    assert image.metadata["aspect"] == "equal"


def test_high_dimensional_system_root_plot_stays_unsupported_with_warning() -> None:
    problem = RootProblem(
        equations=("x + y + z - 1", "x - y", "z - 1"),
        unknowns=(
            RootUnknown("x", initial="0"),
            RootUnknown("y", initial="0"),
            RootUnknown("z", initial="1"),
        ),
        mode="system",
        precision=40,
    )
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={},
                result=RootResult(
                    roots=(
                        RootValue(name="x", value=mp.mpf("0")),
                        RootValue(name="y", value=mp.mpf("0")),
                        RootValue(name="z", value=mp.mpf("1")),
                    ),
                    backend="mpmath",
                    mode="system",
                ),
            ),
        )
    )

    selection = render_nominal_root_plots(batch, problem)

    assert selection.images == ()
    assert selection.warnings == ("System root plots require exactly two equations and two real unknowns; skipped plot.",)


def test_two_dimensional_system_plot_with_invalid_bounds_uses_auto_range() -> None:
    problem = RootProblem(
        equations=("x + y - 3", "x - y - 1"),
        unknowns=(
            RootUnknown("x", initial="2", lower="bad", upper=""),
            RootUnknown("y", initial="1", lower="4", upper="3"),
        ),
        mode="system",
        precision=40,
    )
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={},
                result=RootResult(
                    roots=(
                        RootValue(name="x", value=mp.mpf("2")),
                        RootValue(name="y", value=mp.mpf("1")),
                    ),
                    backend="mpmath",
                    mode="system",
                ),
            ),
        )
    )

    selection = render_nominal_root_plots(batch, problem, budget=RootPlotBudget(max_grid_points=31))

    assert selection.warnings == ()
    assert len(selection.images) == 1
    assert selection.images[0].metadata["curve"] == "system_contour"


def test_two_dimensional_system_plot_without_zero_contour_returns_warning() -> None:
    problem = RootProblem(
        equations=("x^2 + y^2 + 10", "x + y + 10"),
        unknowns=(
            RootUnknown("x", initial="0", lower="-1", upper="1"),
            RootUnknown("y", initial="0", lower="-1", upper="1"),
        ),
        mode="system",
        precision=40,
    )
    batch = RootBatchResult(
        rows=(
            RootBatchRowResult(
                row_index=0,
                source_values={},
                result=RootResult(
                    roots=(
                        RootValue(name="x", value=mp.mpf("0")),
                        RootValue(name="y", value=mp.mpf("0")),
                    ),
                    backend="mpmath",
                    mode="system",
                ),
            ),
        )
    )

    selection = render_nominal_root_plots(batch, problem, budget=RootPlotBudget(max_grid_points=31))

    assert selection.images == ()
    assert any(warning.startswith("Root plot could not be rendered.") for warning in selection.warnings)
```

Run:

```bash
PYTHONPATH=. pytest -q tests/test_root_solving_plotting.py::test_two_dimensional_system_root_renders_contour_plot tests/test_root_solving_plotting.py::test_high_dimensional_system_root_plot_stays_unsupported_with_warning tests/test_root_solving_plotting.py::test_two_dimensional_system_plot_with_invalid_bounds_uses_auto_range tests/test_root_solving_plotting.py::test_two_dimensional_system_plot_without_zero_contour_returns_warning
```

Expected before implementation:

```text
FAILED ... no contour image / old warning string
```

- [ ] **Step 2: Replace the system early return and update warning constant**

In `root_solving/plotting.py`, change the constants to:

```python
SUPPORTED_ROOT_PLOT_MODES = frozenset({"scalar", "scan_multiple", "system"})
SYSTEM_ROOT_PLOT_WARNING = "System root plots require exactly two equations and two real unknowns; skipped plot."
_SYSTEM_CONTOUR_MAX_GRID_POINTS = 81
```

In `select_root_plot_requests()`, replace the current system warning/continue block with:

```python
if mode == "system" and not _supports_system_contour_plot(row):
    _append_unique(warnings, SYSTEM_ROOT_PLOT_WARNING)
    continue
```

In `_render_nominal_root_plot_with_warnings()`, replace the existing `if request.row.result.mode == "system": return None, ...` block with:

```python
if request.row.result.mode == "system":
    return _render_system_root_contour_plot_with_warnings(request, problem)
```

- [ ] **Step 3: Implement safe 2D system support helpers**

Add these helpers in `root_solving/plotting.py`:

```python
def _supports_system_contour_plot(row: RootBatchRowResult) -> bool:
    result = row.result
    if result is None or result.mode != "system":
        return False
    root_names = tuple(root.name for root in result.roots)
    return len(root_names) == 2 and len(set(root_names)) == 2


def _system_axis_grid(unknown: RootUnknown, root: RootValue, max_grid_points: int) -> tuple[float, ...] | None:
    center = _real_float(root.value)
    if center is None:
        return None
    lower = _optional_real(getattr(unknown, "lower", ""))
    upper = _optional_real(getattr(unknown, "upper", ""))
    if lower is None or upper is None or lower >= upper:
        span = max(abs(center), 1.0)
        lower = center - span
        upper = center + span
    count = min(_positive_int(max_grid_points, default=81), _SYSTEM_CONTOUR_MAX_GRID_POINTS)
    return _linspace(lower, upper, count)
```

Add contour evaluation with bounded float conversion:

```python
def _evaluate_system_contours(
    system: RootExpressionSystem,
    x_name: str,
    y_name: str,
    x_values: Sequence[float],
    y_values: Sequence[float],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    residual_a: list[tuple[float, ...]] = []
    residual_b: list[tuple[float, ...]] = []
    for y_value in y_values:
        row_a: list[float] = []
        row_b: list[float] = []
        for x_value in x_values:
            try:
                values = system.residuals({x_name: mp.mpf(str(x_value)), y_name: mp.mpf(str(y_value))})
                first = _real_float(values[0])
                second = _real_float(values[1])
            except Exception:
                first = None
                second = None
            row_a.append(float("nan") if first is None else first)
            row_b.append(float("nan") if second is None else second)
        residual_a.append(tuple(row_a))
        residual_b.append(tuple(row_b))
    return tuple(residual_a), tuple(residual_b)


def _grid_has_zero_contour(values: Sequence[Sequence[float]]) -> bool:
    finite_values = [value for row in values for value in row if isfinite(value)]
    return bool(finite_values) and min(finite_values) <= 0.0 <= max(finite_values)
```

- [ ] **Step 4: Implement contour renderer**

Add `_render_system_root_contour_plot_with_warnings()` in `root_solving/plotting.py`:

```python
def _render_system_root_contour_plot_with_warnings(
    request: RootPlotRequest,
    problem: RootProblem,
) -> tuple[RootPlotImage | None, tuple[str, ...]]:
    if request.row.result is None or len(problem.equations) != 2 or len(problem.unknowns) != 2:
        return None, (SYSTEM_ROOT_PLOT_WARNING,)
    row_problem = replace(problem, row_values=request.row.source_values, mode="system")
    try:
        system = build_root_expression_system(row_problem)
    except Exception as exc:  # noqa: BLE001
        return None, (_plot_failed_warning(exc),)
    roots_by_name = {root.name: root for root in request.row.result.roots}
    x_unknown, y_unknown = row_problem.unknowns
    x_root = roots_by_name.get(x_unknown.name)
    y_root = roots_by_name.get(y_unknown.name)
    if x_root is None or y_root is None:
        return None, (SYSTEM_ROOT_PLOT_WARNING,)
    x_values = _system_axis_grid(x_unknown, x_root, request.budget.max_grid_points)
    y_values = _system_axis_grid(y_unknown, y_root, request.budget.max_grid_points)
    if x_values is None or y_values is None:
        return None, (SYSTEM_ROOT_PLOT_WARNING,)
    try:
        residual_a, residual_b = _evaluate_system_contours(system, x_unknown.name, y_unknown.name, x_values, y_values)
    except Exception as exc:  # noqa: BLE001
        return None, (_plot_failed_warning(exc),)
    if not _grid_has_zero_contour(residual_a) or not _grid_has_zero_contour(residual_b):
        return None, (_plot_failed_warning("no zero contour in plot range"),)

    try:
        from shared.plotting import plt
    except Exception as exc:  # noqa: BLE001
        return None, (_plot_failed_warning(exc),)
    fig = None
    try:
        fig, ax = plt.subplots(figsize=(6.0, 4.8), dpi=180)
        ax.contour(x_values, y_values, residual_a, levels=[0.0], colors=["#1f77b4"], linewidths=1.5)
        ax.contour(x_values, y_values, residual_b, levels=[0.0], colors=["#d62728"], linewidths=1.5)
        root_x = _real_float(x_root.value)
        root_y = _real_float(y_root.value)
        if root_x is not None and root_y is not None:
            ax.scatter([root_x], [root_y], color="#111111", s=36, zorder=3)
        ax.set_xlabel(x_unknown.name)
        ax.set_ylabel(y_unknown.name)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title(_root_plot_title(request.row.row_index, "system"))
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
    except Exception as exc:  # noqa: BLE001
        if fig is not None:
            plt.close(fig)
        return None, (_plot_failed_warning(exc),)
    return (
        RootPlotImage(
            image_bytes=buf.getvalue(),
            row_index=request.row.row_index,
            title=_root_plot_title(request.row.row_index, "system"),
            metadata={
                "curve": "system_contour",
                "equations": tuple(row_problem.equations),
                "unknowns": (x_unknown.name, y_unknown.name),
                "grid_points": len(x_values),
                "aspect": "equal",
                "x_range": (_round_float(x_values[0]), _round_float(x_values[-1])),
                "y_range": (_round_float(y_values[0]), _round_float(y_values[-1])),
            },
        ),
        (),
    )
```

- [ ] **Step 5: Localize the updated warning**

In `root_solving/messages.py`, map the exact updated English warning in the existing `ROOT_MESSAGE_ZH: dict[str, str]` shape:

```python
"System root plots require exactly two equations and two real unknowns; skipped plot.": "方程组绘图需要正好两个方程和两个实数未知量；已跳过绘图。",
```

Do not change `localize_root_message()` to return nested dictionaries. The current contract is `language == "zh"` returns the mapped Chinese string, and English returns the original warning.

- [ ] **Step 6: Add concrete worker payload tests**

In `tests/test_app_desktop_workers_core.py`, add tests that execute the root worker payload path for supported and unsupported system plots:

```python
def test_root_worker_payload_includes_supported_system_plot_bytes() -> None:
    job = RootSolvingJob(
        equations=("x + y - 3", "x - y - 1"),
        unknown_rows=(
            {"name": "x", "initial": "2", "lower": "0", "upper": "4"},
            {"name": "y", "initial": "1", "lower": "-1", "upper": "3"},
        ),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="system",
        scan_config={},
        precision=40,
        display_digits=12,
        language="en",
        render_plots=True,
    )
    payload = _execute_root_solving_job_payload(job)

    assert payload["plot_bytes"]
    assert "System root plots require exactly two equations" not in "\n".join(payload.get("warnings", ()))


def test_root_worker_payload_localizes_unsupported_system_plot_warning() -> None:
    job = RootSolvingJob(
        equations=("x + y + z - 1", "x - y", "z - 1"),
        unknown_rows=(
            {"name": "x", "initial": "0", "lower": "", "upper": ""},
            {"name": "y", "initial": "0", "lower": "", "upper": ""},
            {"name": "z", "initial": "1", "lower": "", "upper": ""},
        ),
        data_headers=(),
        data_rows=(),
        constants_enabled=False,
        constants_rows=(),
        constants_view="table",
        constants_text="",
        mode="system",
        scan_config={},
        precision=40,
        display_digits=12,
        language="zh",
        render_plots=True,
    )
    payload = _execute_root_solving_job_payload(job)

    assert not payload.get("plot_bytes")
    assert "方程组绘图需要正好两个方程和两个实数未知量" in "\n".join(payload.get("warnings", ()))
```

- [ ] **Step 7: Run Slice A verification**

Run:

```bash
PYTHONPATH=. pytest -q tests/test_root_solving_plotting.py tests/test_app_desktop_workers_core.py
PYTHONPATH=. ruff check root_solving/plotting.py root_solving/messages.py tests/test_root_solving_plotting.py tests/test_app_desktop_workers_core.py
python -m compileall -q root_solving app_desktop/workers_core.py
```

Expected:

```text
all selected tests pass; ruff passes; compileall exits 0
```

---

## Slice B: Left Panel Splitter and Horizontal Scrollbar Hardening

### Task B1: Reproduce and Fix Root-Mode Horizontal Scrollbar

**Files:**
- Modify: `tools/scan_desktop_gui_schema.py`
- Modify: `tests/test_desktop_gui_schema_scan.py`
- Modify: `app_desktop/panels.py`
- Modify: `tests/test_desktop_root_solving_ui.py`

- [ ] **Step 1: Add RED scan test for the user-observed root-solving layout**

In `tests/test_desktop_gui_schema_scan.py`, add:

```python
def test_scan_catches_root_solving_scan_mode_horizontal_scrollbar(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    _select_combo_data(window.mode_combo, "root_solving")
    _select_combo_data(window.root_mode_combo, "scan_multiple")
    window.root_equation_edit.setPlainText("x^2-A")
    window.root_unknown_table.setItem(0, 0, QTableWidgetItem("x"))
    window.root_unknown_table.setItem(0, 1, QTableWidgetItem(""))
    window.root_unknown_table.setItem(0, 2, QTableWidgetItem("-2"))
    window.root_unknown_table.setItem(0, 3, QTableWidgetItem("2"))
    window.result_tabs.setCurrentWidget(window.result_tab)
    window.result_content_tabs.setCurrentWidget(window.result_plot_tab)
    window._left_scroll.verticalScrollBar().setValue(window._left_scroll.verticalScrollBar().maximum())

    report = scan_window(window, refresh_language=True)

    assert report["checks"]["left_panel_no_horizontal_scrollbar"] is True
```

If `_select_combo_data()` is not already available in this test file, add:

```python
def _select_combo_data(combo: QComboBox, data: str) -> None:
    index = combo.findData(data)
    assert index >= 0
    combo.setCurrentIndex(index)
```

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q tests/test_desktop_gui_schema_scan.py::test_scan_catches_root_solving_scan_mode_horizontal_scrollbar
```

Expected before implementation:

```text
FAILED ... left_panel_no_horizontal_scrollbar is False
```

- [ ] **Step 2: Expand GUI scan to all relevant left-panel states**

In `tools/scan_desktop_gui_schema.py`, replace the single `_has_no_horizontal_scrollbar(window)` check with a state-driven scan:

```python
_LEFT_PANEL_STATES: tuple[tuple[str, str | None], ...] = (
    ("extrapolation", None),
    ("error", None),
    ("statistics", None),
    ("fitting", None),
    ("root_solving", "scalar"),
    ("root_solving", "scan_multiple"),
    ("root_solving", "polynomial"),
    ("root_solving", "system"),
)


def _select_combo_data(combo: Any, data: str) -> bool:
    index = combo.findData(data)
    if index < 0:
        return False
    combo.setCurrentIndex(index)
    return True


def _left_panel_horizontal_scrollbar_states(window: Any) -> dict[str, bool]:
    results: dict[str, bool] = {}
    app = QApplication.instance()
    for mode, root_mode in _LEFT_PANEL_STATES:
        if not _select_combo_data(window.mode_combo, mode):
            results[f"{mode}:{root_mode or ''}"] = False
            continue
        if mode == "root_solving" and root_mode is not None:
            _select_combo_data(window.root_mode_combo, root_mode)
        if app is not None:
            app.processEvents()
        if hasattr(window, "_refresh_main_splitter_left_min_width"):
            window._refresh_main_splitter_left_min_width()
        window._main_splitter.setSizes([1, max(1, window.width() - 1)])
        if app is not None:
            app.processEvents()
        bar = window._left_scroll.horizontalScrollBar()
        results[f"{mode}:{root_mode or ''}"] = bar.maximum() == 0
    return results
```

Update `scan_window()` so:

```python
left_states = _left_panel_horizontal_scrollbar_states(window)
left_ok = all(left_states.values())
if not left_ok:
    failed = ", ".join(name for name, ok in left_states.items() if not ok)
    issues.append(f"left panel horizontal scrollbar is visible after splitter clamp: {failed}")
report["checks"]["left_panel_no_horizontal_scrollbar"] = left_ok
report["checks"]["left_panel_horizontal_scrollbar_states"] = left_states
```

- [ ] **Step 3: Make left-pane minimum width a live content invariant**

In `app_desktop/panels.py`, update `_refresh_main_splitter_left_min_width(self)` so it performs layout activation and measures the active left content after mode/submode visibility changes:

```python
def _refresh_main_splitter_left_min_width(self) -> None:
    left_scroll = getattr(self, "_left_scroll", None)
    left_container = getattr(self, "_left_container", None)
    if left_scroll is None or left_container is None:
        return
    left_container.ensurePolished()
    left_container.updateGeometry()
    if left_container.layout() is not None:
        left_container.layout().activate()
    content_width = max(
        320,
        left_container.minimumSizeHint().width(),
        _visible_left_content_width_floor(left_container),
    )
    viewport_overhead = (
        left_scroll.frameWidth() * 2
        + left_scroll.verticalScrollBar().sizeHint().width()
        + 12
    )
    left_min_width = content_width + viewport_overhead
    self._main_splitter_left_min_width = left_min_width
    left_scroll.setMinimumWidth(left_min_width)
    left_scroll.widget().setMinimumWidth(content_width)
    splitter = getattr(self, "_main_splitter", None)
    if splitter is None or splitter.count() < 2:
        return
    sizes = splitter.sizes()
    right_width = max(1, sum(sizes) - left_min_width)
    if not sizes or sizes[0] < left_min_width or left_scroll.horizontalScrollBar().maximum() > 0:
        splitter.setSizes([left_min_width, right_width])
```

Add a helper that measures visible tables and control rows without using unconstrained formula text as the global width:

```python
def _visible_left_content_width_floor(container: QWidget) -> int:
    floor = 0
    for table in container.findChildren(QTableWidget):
        if not table.isVisible():
            continue
        header = table.horizontalHeader()
        width = table.verticalHeader().width() + table.frameWidth() * 2 + 24
        for column in range(table.columnCount()):
            width += max(table.columnWidth(column), header.sectionSizeHint(column))
        floor = max(floor, width)
    for group in container.findChildren(QGroupBox):
        if group.isVisible():
            floor = max(floor, group.minimumSizeHint().width())
    return floor
```

- [ ] **Step 4: Refresh the invariant after mode/submode/language changes**

In `app_desktop/panels.py`, after each mode or root-mode visibility update, call:

```python
self._refresh_main_splitter_left_min_width()
```

Apply this after:

- calculation mode changes;
- root-solving mode changes;
- constants editor show/hide changes;
- language refresh;
- restoring splitter state.

Do not set `Qt.ScrollBarAlwaysOff` to hide the scrollbar. The fix must make the content actually fit.

- [ ] **Step 5: Add focused GUI regression for mode transitions**

In `tests/test_desktop_root_solving_ui.py`, add:

```python
def test_root_mode_changes_recompute_left_splitter_minimum(qtbot: Any) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    _select_combo_data(window.mode_combo, "root_solving")

    observed: list[int] = []
    for root_mode in ("scalar", "scan_multiple", "polynomial", "system"):
        _select_combo_data(window.root_mode_combo, root_mode)
        window._refresh_main_splitter_left_min_width()
        observed.append(window._main_splitter_left_min_width)
        window._main_splitter.setSizes([1, max(1, window.width() - 1)])
        qtbot.wait(10)
        assert window._left_scroll.horizontalScrollBar().maximum() == 0

    assert all(width > 0 for width in observed)
```

- [ ] **Step 6: Run Slice B verification**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q tests/test_desktop_gui_schema_scan.py tests/test_desktop_root_solving_ui.py
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python tools/scan_desktop_gui_schema.py
PYTHONPATH=. ruff check tools/scan_desktop_gui_schema.py tests/test_desktop_gui_schema_scan.py app_desktop/panels.py tests/test_desktop_root_solving_ui.py
python -m compileall -q tools/scan_desktop_gui_schema.py app_desktop/panels.py
```

Expected:

```text
tests pass; scan reports issues: []; left_panel_no_horizontal_scrollbar: true; every left_panel_horizontal_scrollbar_states entry is true
```

---

## Slice C: Complete Generated Example Workspaces

### Task C1: Introduce a Single Example Catalog

**Files:**
- Create: `examples/catalog.py`
- Modify: `tools/generate_example_workspaces.py`
- Modify: `tests/test_example_workspaces.py`

- [ ] **Step 1: Add catalog contract tests**

In `tests/test_example_workspaces.py`, replace the test-local `EXAMPLE_NAMES` set with imports:

```python
from examples.catalog import EXAMPLE_NAMES, EXAMPLE_SPECS, example_index_payload, examples_by_category
```

Add:

```python
def test_example_catalog_names_are_ordered_and_unique() -> None:
    assert isinstance(EXAMPLE_NAMES, tuple)
    assert len(EXAMPLE_NAMES) == len(set(EXAMPLE_NAMES))
    assert EXAMPLE_NAMES == tuple(spec.filename for spec in EXAMPLE_SPECS)


def test_example_catalog_has_visible_categories() -> None:
    categories = examples_by_category()
    assert set(categories) == {"extrapolation", "error", "statistics", "fitting", "root_solving"}
    for category, specs in categories.items():
        assert specs, category
```

Run:

```bash
PYTHONPATH=. pytest -q tests/test_example_workspaces.py::test_example_catalog_names_are_ordered_and_unique tests/test_example_workspaces.py::test_example_catalog_has_visible_categories
```

Expected before implementation:

```text
FAILED ... ModuleNotFoundError: No module named 'examples.catalog'
```

- [ ] **Step 2: Create `examples/catalog.py`**

Create:

```python
from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ExampleSpec:
    filename: str
    category: str
    method: str
    title_zh: str
    title_en: str
    description_zh: str
    description_en: str
    variants: tuple[str, ...] = ()


EXAMPLE_SPECS: tuple[ExampleSpec, ...] = (
    ExampleSpec("extrapolation-power-law.datalab", "extrapolation", "power_law", "幂律外推", "Power-law extrapolation", "展示幂律收敛序列的外推。", "Shows extrapolation of a power-law convergent sequence."),
    ExampleSpec("extrapolation-richardson.datalab", "extrapolation", "richardson", "Richardson 外推", "Richardson extrapolation", "展示步长序列的 Richardson 外推。", "Shows Richardson extrapolation for a step-size sequence."),
    ExampleSpec("extrapolation-shanks.datalab", "extrapolation", "shanks", "Shanks 变换", "Shanks transform", "展示交替收敛序列的 Shanks 加速。", "Shows Shanks acceleration for an alternating convergent sequence."),
    ExampleSpec("extrapolation-levin-u.datalab", "extrapolation", "levin_u", "Levin u 变换", "Levin u transform", "展示带余项估计的 Levin u 加速。", "Shows Levin u acceleration with remainder estimates."),
    ExampleSpec("extrapolation-custom.datalab", "extrapolation", "custom", "自定义外推", "Custom extrapolation", "展示自定义外推表达式。", "Shows a custom extrapolation expression."),
    ExampleSpec("error-taylor-first-order.datalab", "error", "taylor", "一阶误差传播", "First-order error propagation", "展示常见公式的一阶 Taylor 不确定度传播。", "Shows first-order Taylor uncertainty propagation."),
    ExampleSpec("error-taylor-second-order.datalab", "error", "taylor", "二阶误差传播", "Second-order error propagation", "展示非线性公式的二阶 Taylor 修正。", "Shows second-order Taylor correction for a nonlinear expression.", ("second_order",)),
    ExampleSpec("error-monte-carlo.datalab", "error", "monte_carlo", "蒙特卡洛误差传播", "Monte Carlo error propagation", "展示非线性比值的蒙特卡洛传播。", "Shows Monte Carlo propagation for a nonlinear ratio."),
    ExampleSpec("statistics-mean.datalab", "statistics", "mean", "均值统计", "Mean statistics", "展示普通均值和标准误。", "Shows ordinary mean and standard error."),
    ExampleSpec("statistics-weighted-sigma.datalab", "statistics", "weighted_sigma", "加权统计", "Weighted statistics", "展示带不确定度数据的加权均值。", "Shows weighted mean for values with uncertainty."),
    ExampleSpec("fitting-custom.datalab", "fitting", "custom", "自定义拟合", "Custom fitting", "展示用户表达式拟合。", "Shows fitting with a user expression."),
    ExampleSpec("fitting-self-consistent.datalab", "fitting", "self_consistent", "自洽隐式拟合", "Self-consistent implicit fitting", "展示通用自洽变量拟合。", "Shows a general self-consistent variable fit."),
    ExampleSpec("fitting-polynomial.datalab", "fitting", "polynomial", "多项式拟合", "Polynomial fitting", "展示二次多项式拟合。", "Shows a quadratic polynomial fit."),
    ExampleSpec("fitting-inverse-power.datalab", "fitting", "inverse_power", "反幂拟合", "Inverse-power fitting", "展示极限加反幂修正模型。", "Shows a limit plus inverse-power correction model."),
    ExampleSpec("fitting-pade.datalab", "fitting", "pade", "Padé 拟合", "Padé fitting", "展示有理函数拟合。", "Shows rational-function fitting."),
    ExampleSpec("fitting-power-limit.datalab", "fitting", "power_limit", "幂律极限拟合", "Power-limit fitting", "展示极限值和幂律修正拟合。", "Shows fitting a limit with power-law correction."),
    ExampleSpec("root-scalar-no-uncertainty.datalab", "root_solving", "scalar", "标量求根", "Scalar root solving", "展示单方程单根求解。", "Shows one equation with one root."),
    ExampleSpec("root-scalar-taylor-uncertainty.datalab", "root_solving", "scalar", "带不确定度标量求根", "Scalar root with Taylor uncertainty", "展示 x^2-A=0 的一阶 Taylor 根不确定度。", "Shows first-order Taylor root uncertainty for x^2-A=0.", ("taylor",)),
    ExampleSpec("root-scalar-taylor-second-order.datalab", "root_solving", "scalar", "二阶 Taylor 根不确定度", "Second-order Taylor root uncertainty", "展示非线性方程的二阶 Taylor 根不确定度。", "Shows second-order Taylor root uncertainty for a nonlinear equation.", ("taylor_second_order",)),
    ExampleSpec("root-scan-multiple.datalab", "root_solving", "scan_multiple", "扫描多根", "Scan multiple roots", "展示区间扫描寻找多个根。", "Shows interval scanning for multiple roots."),
    ExampleSpec("root-polynomial.datalab", "root_solving", "polynomial", "多项式求根", "Polynomial roots", "展示多项式全部根。", "Shows polynomial roots."),
    ExampleSpec("root-system-2d.datalab", "root_solving", "system", "二维方程组求根", "2D system roots", "展示两个方程两个未知量的交点。", "Shows a two-equation two-unknown intersection."),
    ExampleSpec("root-monte-carlo-uncertainty.datalab", "root_solving", "scalar", "蒙特卡洛根不确定度", "Monte Carlo root uncertainty", "展示根的不确定度蒙特卡洛传播。", "Shows Monte Carlo propagation for root uncertainty.", ("monte_carlo",)),
    ExampleSpec("root-batch-quadratic.datalab", "root_solving", "scalar", "批量求根", "Batch root solving", "展示数据列驱动的批量 x^2-A=0 求根。", "Shows data-column-driven batch solving for x^2-A=0.", ("batch",)),
)

EXAMPLE_NAMES: tuple[str, ...] = tuple(spec.filename for spec in EXAMPLE_SPECS)

LEGACY_GENERATED_NAMES: frozenset[str] = frozenset(
    {
        "extrapolation.datalab",
        "error-propagation.datalab",
        "statistics.datalab",
        "fitting.datalab",
        "quantum-defect-implicit.datalab",
        "root-scalar-with-uncertainty.datalab",
        "root-monte-carlo-uncertainty.datalab",
        "root-batch-quadratic.datalab",
    }
)


def examples_by_category() -> Mapping[str, tuple[ExampleSpec, ...]]:
    grouped: dict[str, list[ExampleSpec]] = defaultdict(list)
    for spec in EXAMPLE_SPECS:
        grouped[spec.category].append(spec)
    return {category: tuple(specs) for category, specs in grouped.items()}


def example_index_payload() -> dict[str, object]:
    return {
        "schema": 1,
        "examples": [
            {
                "filename": spec.filename,
                "category": spec.category,
                "method": spec.method,
                "title": {"zh": spec.title_zh, "en": spec.title_en},
                "description": {"zh": spec.description_zh, "en": spec.description_en},
                "variants": list(spec.variants),
            }
            for spec in EXAMPLE_SPECS
        ],
    }
```

- [ ] **Step 3: Move generator inventory to the catalog**

In `tools/generate_example_workspaces.py`:

```python
import json
from examples.catalog import EXAMPLE_NAMES, EXAMPLE_SPECS, LEGACY_GENERATED_NAMES, example_index_payload
```

Remove the generator-local `EXAMPLE_NAMES` set.

Change `build_examples()` so its returned keys exactly match `EXAMPLE_NAMES`. Implement the example data/config recipes below with existing builder helpers and current worker snapshot helpers:

| filename | recipe |
|---|---|
| `extrapolation-power-law.datalab` | data `n=4..12`, `value=1+2/n^2`; mode `power_law`; target limit near `1`. |
| `extrapolation-richardson.datalab` | data step sizes `h=1/2,1/4,1/8,1/16`, `value=1+h^2`; mode `richardson`. |
| `extrapolation-shanks.datalab` | alternating sequence `1 + (-1)^n/(n+1)`; mode `shanks`. |
| `extrapolation-levin-u.datalab` | slowly convergent partial sums with remainder estimates; mode `levin_u`. |
| `extrapolation-custom.datalab` | reuse the current custom extrapolation example formula and data, renamed through the catalog. |
| `error-taylor-first-order.datalab` | expression `A*B/C`, constants/data with uncertainty, method `taylor`, order `1`. |
| `error-taylor-second-order.datalab` | expression `sqrt(A^2+B^2)`, method `taylor`, order `2`. |
| `error-monte-carlo.datalab` | expression `A/B`, method `monte_carlo`, fixed seed `42`, samples `2000`. |
| `statistics-mean.datalab` | one value column without uncertainty, mode `mean`. |
| `statistics-weighted-sigma.datalab` | one value column with compact uncertainty notation, mode `weighted_sigma`. |
| `fitting-custom.datalab` | data from `y=a*x+b`, fitting model `custom`, expression `a*x+b`. |
| `fitting-self-consistent.datalab` | general self-consistent model `u = c/(x+u)`, output `y = a*u+b`, no quantum-specific parameter names. |
| `fitting-polynomial.datalab` | quadratic data, fitting model `polynomial`, degree `2`. |
| `fitting-inverse-power.datalab` | data `y=L+a/x^2`, fitting model `inverse_power`. |
| `fitting-pade.datalab` | data from `(a+b*x)/(1+c*x)`, fitting model `pade`. |
| `fitting-power-limit.datalab` | data `y=L+a*x^p`, fitting model `power_limit`. |
| `root-scalar-no-uncertainty.datalab` | equation `x^2-2=0`, mode `scalar`, unknown `x`, uncertainty off. |
| `root-scalar-taylor-uncertainty.datalab` | equation `x^2-A=0`, data/constant `A=4.0(1)`, mode `scalar`, Taylor order `1`. |
| `root-scalar-taylor-second-order.datalab` | equation `exp(x)-A=0`, `A=2.0(1)`, mode `scalar`, Taylor order `2`. |
| `root-scan-multiple.datalab` | equation `sin(x)=0`, mode `scan_multiple`, bounds around `0..4*pi`. |
| `root-polynomial.datalab` | polynomial coefficients for `(x-1)*(x-2)*(x-3)`, mode `polynomial`. |
| `root-system-2d.datalab` | equations `x+y-3=0`, `x-y-1=0`, mode `system`, solved root `(2,1)`. |
| `root-monte-carlo-uncertainty.datalab` | equation `x^2-A=0`, `A=9.0(3)`, mode `scalar`, Monte Carlo seed `42`. |
| `root-batch-quadratic.datalab` | data column `A = 1.0(1), 4.0(2), 9.0(3)`, equation `x^2-A=0`, mode `scalar`, Taylor order `1`. |

Every generated workspace must include a result snapshot when the current project has a deterministic worker/helper path for that module. For fitting examples where optimization noise can vary, assert success status, parameter names, and CSV headers instead of byte-identical numeric values.

- [ ] **Step 4: Fix stale archive ordering with previous index discovery**

Before writing generated examples in `main()`, replace the current unknown-file guard with helpers that read the existing generated index first and fall back to the one-time legacy list only when no index exists:

```python
def _previous_index_names() -> set[str]:
    index_path = EXAMPLE_ROOT / "example_catalog.json"
    if not index_path.is_file():
        return set(LEGACY_GENERATED_NAMES)
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except Exception:
        return set(LEGACY_GENERATED_NAMES)
    names: set[str] = set()
    for item in payload.get("examples", []):
        if isinstance(item, dict):
            name = str(item.get("filename", "")).strip()
            if name:
                names.add(name)
    return names | set(LEGACY_GENERATED_NAMES)


current_names = set(EXAMPLE_NAMES)
previous_names = _previous_index_names()
for stale in EXAMPLE_ROOT.glob("*.datalab"):
    if stale.name in current_names:
        continue
    if stale.name in previous_names:
        stale.unlink()
        continue
    raise RuntimeError(f"Refusing to overwrite unexpected example workspace: {stale}")
```

After archive writes, add:

```python
(EXAMPLE_ROOT / "example_catalog.json").write_text(
    json.dumps(example_index_payload(), ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
```

- [ ] **Step 5: Add shared visible-option registry**

Create `shared/example_coverage.py`:

```python
from __future__ import annotations

from shared.ui_specs import METHOD_DISPLAY_ORDER

VISIBLE_EXTRAPOLATION_METHODS: tuple[str, ...] = tuple(METHOD_DISPLAY_ORDER)
VISIBLE_ERROR_METHODS: tuple[str, ...] = ("taylor", "monte_carlo")
VISIBLE_STATISTICS_MODES: tuple[str, ...] = ("mean", "weighted_sigma")
VISIBLE_FITTING_MODELS: tuple[str, ...] = ("custom", "self_consistent", "polynomial", "inverse_power", "pade", "power_limit")
VISIBLE_ROOT_MODES: tuple[str, ...] = ("scalar", "scan_multiple", "polynomial", "system")
VISIBLE_ROOT_UNCERTAINTY_VARIANTS: tuple[str, ...] = ("off", "taylor", "taylor_second_order", "monte_carlo")
```

Update `app_desktop/panels.py` so the root/error/statistics/fitting combo construction uses these constants for item data. Keep the current localized labels unchanged; only replace duplicated data-value tuples.

- [ ] **Step 6: Add UI-derived coverage tests**

In `tests/test_example_workspaces.py`, add:

```python
from shared.example_coverage import (
    VISIBLE_ERROR_METHODS,
    VISIBLE_EXTRAPOLATION_METHODS,
    VISIBLE_FITTING_MODELS,
    VISIBLE_ROOT_MODES,
    VISIBLE_ROOT_UNCERTAINTY_VARIANTS,
    VISIBLE_STATISTICS_MODES,
)


def _catalog_methods(category: str) -> set[str]:
    return {spec.method for spec in EXAMPLE_SPECS if spec.category == category}


def test_example_catalog_covers_visible_extrapolation_methods() -> None:
    assert set(VISIBLE_EXTRAPOLATION_METHODS) <= _catalog_methods("extrapolation")


def test_example_catalog_covers_visible_root_modes() -> None:
    assert set(VISIBLE_ROOT_MODES) <= _catalog_methods("root_solving")


def test_example_catalog_covers_visible_root_uncertainty_variants() -> None:
    variants = {variant for spec in EXAMPLE_SPECS if spec.category == "root_solving" for variant in spec.variants}
    required_non_off = set(VISIBLE_ROOT_UNCERTAINTY_VARIANTS) - {"off"}
    assert required_non_off <= variants
    if "off" in VISIBLE_ROOT_UNCERTAINTY_VARIANTS:
        assert any(spec.category == "root_solving" and not spec.variants for spec in EXAMPLE_SPECS)


def test_example_catalog_covers_visible_error_statistics_and_fitting_methods() -> None:
    assert set(VISIBLE_ERROR_METHODS) <= _catalog_methods("error")
    assert set(VISIBLE_STATISTICS_MODES) <= _catalog_methods("statistics")
    assert set(VISIBLE_FITTING_MODELS) <= _catalog_methods("fitting")
```

- [ ] **Step 7: Add generated JSON consistency test**

In `tests/test_example_workspaces.py`, add:

```python
def test_example_catalog_json_matches_catalog_payload() -> None:
    payload = json.loads(Path("examples/workspaces/example_catalog.json").read_text(encoding="utf-8"))
    assert payload == example_index_payload()
```

- [ ] **Step 8: Rewrite legacy filename-coupled tests**

In `tests/test_example_workspaces.py`, update tests that directly reference old filenames:

- Replace `manifests["extrapolation.datalab"]`, `manifests["error-propagation.datalab"]`, `manifests["statistics.datalab"]`, `manifests["fitting.datalab"]`, and `manifests["quantum-defect-implicit.datalab"]` with the matching new catalog filenames.
- Replace reads of `root-scalar-with-uncertainty.datalab` with `root-scalar-taylor-uncertainty.datalab`.
- Replace reads of `quantum-defect-implicit.datalab` with `fitting-self-consistent.datalab`, or delete the quantum-defect-specific assertion if the new self-consistent example intentionally uses a general non-quantum preset.
- Add assertions for `root-scalar-taylor-second-order.datalab`, `root-scan-multiple.datalab`, `root-polynomial.datalab`, and `root-system-2d.datalab` so every newly generated artifact has at least one content/snapshot check.

Use catalog lookups rather than string literals where possible:

```python
def _workspace_named(name: str) -> WorkspaceReadResult:
    assert name in EXAMPLE_NAMES
    return read_workspace(Path("examples/workspaces") / name)
```

- [ ] **Step 9: Regenerate and verify examples**

Run:

```bash
PYTHONPATH=. python tools/generate_example_workspaces.py
PYTHONPATH=. pytest -q tests/test_example_workspaces.py
git diff --name-only -- examples/workspaces tools/generate_example_workspaces.py examples/catalog.py shared/example_coverage.py app_desktop/panels.py tests/test_example_workspaces.py
```

Expected:

```text
example tests pass; the final diff-name command lists only planned files and generated artifacts
```

During implementation, if the final command reports differences, inspect them. Regenerate once after fixing the generator; do not hand-edit generated `.datalab` archives.

### Task C2: Wire Desktop Example Menu to Catalog Index

**Files:**
- Modify: `app_desktop/window.py`
- Modify: `tests/test_desktop_example_workspace_menu.py`

- [ ] **Step 1: Add menu index tests**

In `tests/test_desktop_example_workspace_menu.py`, add:

```python
def test_example_menu_uses_generated_catalog_index() -> None:
    from app_desktop.window import list_example_menu_entries

    from examples.catalog import EXAMPLE_NAMES

    entries = list_example_menu_entries(language="en")

    assert tuple(entry.filename for entry in entries) == EXAMPLE_NAMES
    assert all(entry.title for entry in entries)
    assert any(entry.category == "root_solving" for entry in entries)


def test_example_workspace_paths_still_match_catalog_names() -> None:
    from app_desktop.window import list_example_workspaces

    from examples.catalog import EXAMPLE_NAMES

    examples = list_example_workspaces()

    assert tuple(path.name for path in examples) == EXAMPLE_NAMES
```

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q tests/test_desktop_example_workspace_menu.py::test_example_menu_uses_generated_catalog_index
```

Expected before implementation:

```text
FAILED ... list_example_menu_entries missing or root examples hidden
```

- [ ] **Step 2: Add menu-entry index loading without changing path API**

In `app_desktop/window.py`, replace the hardcoded `EXAMPLE_WORKSPACE_NAMES` tuple with imports from the catalog, but keep `list_example_workspaces()` returning `list[Path]` because `_is_example_workspace_path()`, `copy_example_workspace()`, and template-save protection already depend on that API.

Add a separate menu-entry dataclass and loader:

```python
@dataclass(frozen=True)
class ExampleMenuEntry:
    filename: str
    category: str
    title: str
    description: str


def list_example_menu_entries(*, language: str = "en") -> tuple[ExampleMenuEntry, ...]:
    from examples.catalog import EXAMPLE_NAMES

    index_path = _example_catalog_index_path()
    if not index_path.exists():
        return tuple(ExampleMenuEntry(filename=name, category="", title=name, description="") for name in EXAMPLE_NAMES)
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    entries: list[ExampleMenuEntry] = []
    for item in payload.get("examples", []):
        filename = str(item.get("filename", "")).strip()
        if filename not in EXAMPLE_NAMES:
            continue
        title_map = item.get("title", {})
        description_map = item.get("description", {})
        if not isinstance(title_map, dict):
            title_map = {}
        if not isinstance(description_map, dict):
            description_map = {}
        entries.append(
            ExampleMenuEntry(
                filename=filename,
                category=str(item.get("category", "")),
                title=str(title_map.get(language) or title_map.get("en") or filename),
                description=str(description_map.get(language) or description_map.get("en") or ""),
            )
        )
    return tuple(entries)


def _example_catalog_index_path() -> Path:
    rel = Path("examples") / "workspaces" / "example_catalog.json"
    resolved = resolve_resource_path(rel)
    if resolved is not None:
        return resolved
    return Path(__file__).resolve().parent.parent / rel
```

Update `list_example_workspaces()` to iterate `EXAMPLE_NAMES` and return existing `Path` objects in catalog order. Update `copy_example_workspace()` to validate against `EXAMPLE_NAMES`. Update the menu-building code inside `ExtrapolationWindow.open_example_workspace()` so it displays `entry.title` and resolves the selected `entry.filename` through `list_example_workspaces()`.

- [ ] **Step 3: Preserve example template save-as behavior**

Keep `open_example_workspace()` loading from `examples/workspaces/<filename>` and marking example-origin workspaces as templates so direct Save routes to Save As. Use the existing `_workspace_template_source` behavior; do not introduce a nonexistent `workspace_controller.is_template_workspace` property. Add this assertion if missing:

```python
def test_opened_example_workspace_requires_save_as(qtbot: Any, tmp_path: Path) -> None:
    window = ExtrapolationWindow()
    qtbot.addWidget(window)
    source = next(path for path in list_example_workspaces() if path.name == "root-scalar-no-uncertainty.datalab")
    assert window._open_workspace_from_path(source, as_template=True)

    assert window._workspace_path is None
    assert window._workspace_template_source == source
```

- [ ] **Step 4: Run Slice C verification**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q tests/test_example_workspaces.py tests/test_desktop_example_workspace_menu.py
PYTHONPATH=. ruff check examples/catalog.py tools/generate_example_workspaces.py app_desktop/window.py tests/test_example_workspaces.py tests/test_desktop_example_workspace_menu.py
PYTHONPATH=. ruff check shared/example_coverage.py app_desktop/panels.py
python -m compileall -q examples shared/example_coverage.py tools/generate_example_workspaces.py app_desktop/window.py app_desktop/panels.py
```

Expected:

```text
all selected tests pass; ruff passes; compileall exits 0
```

---

## Slice D: Documentation and Smoke Tests

### Task D1: Add Root-Solving Desktop Docs

**Files:**
- Create: `docs/desktop/root-solving.zh.md`
- Create: `docs/desktop/root-solving.en.md`
- Modify: `docs/desktop/manifest.json`
- Modify: `desktop_doc_loader.py`
- Modify: `tests/test_desktop_docs_smoke.py`

- [ ] **Step 1: Add docs manifest tests**

In `tests/test_desktop_docs_smoke.py`, ensure these imports exist:

```python
import json
from pathlib import Path

import pytest
```

Then add tests that preserve the current desktop docs manifest schema: a top-level list of entries with `slug`, `title_zh`, and `title_en`.

```python
def test_desktop_docs_manifest_contains_root_solving() -> None:
    manifest = json.loads(Path("docs/desktop/manifest.json").read_text(encoding="utf-8"))
    slugs = {entry["slug"] for entry in manifest}
    assert "root-solving" in slugs


def test_default_desktop_docs_manifest_contains_root_solving() -> None:
    from desktop_doc_loader import _default_manifest

    slugs = {entry["slug"] for entry in _default_manifest()}
    assert "root-solving" in slugs


def test_load_desktop_manifest_fallback_contains_root_solving(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import desktop_doc_loader

    monkeypatch.setattr(desktop_doc_loader, "get_resource_root", lambda: tmp_path)

    slugs = {entry["slug"] for entry in desktop_doc_loader.load_desktop_manifest()}

    assert "root-solving" in slugs


def test_load_desktop_doc_reads_root_solving_in_both_languages() -> None:
    from desktop_doc_loader import load_desktop_doc

    assert "求根" in load_desktop_doc("root-solving", "zh")
    assert "Root Solving" in load_desktop_doc("root-solving", "en")


def test_root_solving_docs_mention_plot_limits_and_examples() -> None:
    zh = Path("docs/desktop/root-solving.zh.md").read_text(encoding="utf-8")
    en = Path("docs/desktop/root-solving.en.md").read_text(encoding="utf-8")
    assert "二维" in zh
    assert "放大" in zh
    assert "示例工作区" in zh
    assert "2D" in en
    assert "inset" in en
    assert "example workspace" in en


def test_examples_readme_mentions_every_generated_example() -> None:
    from examples.catalog import EXAMPLE_NAMES

    readme = Path("examples/README.md").read_text(encoding="utf-8")
    for filename in EXAMPLE_NAMES:
        assert filename in readme
```

Run:

```bash
PYTHONPATH=. pytest -q tests/test_desktop_docs_smoke.py::test_desktop_docs_manifest_contains_root_solving tests/test_desktop_docs_smoke.py::test_default_desktop_docs_manifest_contains_root_solving tests/test_desktop_docs_smoke.py::test_load_desktop_manifest_fallback_contains_root_solving tests/test_desktop_docs_smoke.py::test_load_desktop_doc_reads_root_solving_in_both_languages tests/test_desktop_docs_smoke.py::test_root_solving_docs_mention_plot_limits_and_examples tests/test_desktop_docs_smoke.py::test_examples_readme_mentions_every_generated_example
```

Expected before implementation:

```text
FAILED ... root-solving missing or docs missing
```

- [ ] **Step 2: Create root-solving docs**

Create `docs/desktop/root-solving.zh.md` with sections:

```markdown
# 求根

求根模块用于求解一个或多个方程的未知量。标量模式适合单方程单未知量；扫描多根模式适合一个变量区间内的多个实根；多项式模式适合多项式全部根；方程组模式适合多个方程的联合求解。

## 不确定度

当输入数据或常数带有不确定度时，求根模块复用 DataLab 的误差传播配置。Taylor 传播使用隐函数导数估计根的不确定度；Monte Carlo 传播按输入分布重复求根并统计根分布。

## 绘图

标量和扫描多根模式绘制残差曲线、零线和根标记。主图保持真实比例；如果根的不确定度小到在主图上不可读，DataLab 会自动添加根附近放大图，不会放大主图误差条。

二维方程组会绘制两个方程残差等于零的等高线交点。超过两个未知量的方程组不默认绘图，并会在结果中提示原因。

## 示例工作区

从“示例工作区”菜单可以打开标量求根、批量求根、扫描多根、多项式求根、二维方程组和 Monte Carlo 根不确定度示例。示例是只读模板，修改后保存会要求选择自定义路径。
```

Create `docs/desktop/root-solving.en.md` with the English equivalent:

```markdown
# Root Solving

The root-solving module solves unknown variables from one or more equations. Scalar mode is for one equation and one unknown; scan mode finds multiple real roots in an interval; polynomial mode finds polynomial roots; system mode solves coupled equations.

## Uncertainty

When data or constants include uncertainty, root solving reuses DataLab's uncertainty-propagation configuration. Taylor propagation estimates root uncertainty through implicit derivatives. Monte Carlo propagation repeatedly solves the equation with sampled inputs and summarizes the root distribution.

## Plots

Scalar and scan modes plot the residual curve, zero line, and root markers. The main plot stays at true scale. If root uncertainty is too small to read on the main plot, DataLab automatically adds a local inset around the root instead of enlarging the main error bar.

Two-dimensional systems plot the zero-contour intersection of the two residual equations. Systems with more than two unknowns are not plotted by default and report a clear warning.

## Example Workspaces

The Example Workspaces menu includes scalar roots, batch roots, multi-root scans, polynomial roots, 2D systems, and Monte Carlo root uncertainty. Examples are read-only templates; saving a modified example requires choosing a custom path.
```

- [ ] **Step 3: Update manifest and fallback manifest**

Add this object to the existing top-level list in `docs/desktop/manifest.json`:

```json
{
  "slug": "root-solving",
  "title_zh": "求根",
  "title_en": "Root Solving"
}
```

Add the same `{"slug": "root-solving", "title_zh": "求根", "title_en": "Root Solving"}` entry to `desktop_doc_loader._default_manifest()`. Do not add a `paths` field; `load_desktop_doc()` already resolves docs as `docs/desktop/<slug>.<lang>.md`.

- [ ] **Step 4: Update overview docs after Slice A lands**

Slice D depends on Slice A. Do not merge or publish the new root plot documentation before Slice A tests pass, because these docs describe automatic insets and 2D contour plots.

Update overview docs:

Update:

- `docs/desktop/index.zh.md` and `docs/desktop/index.en.md` to list five main modules including root solving.
- `docs/desktop/guide.zh.md` and `docs/desktop/guide.en.md` to mention the Example Workspaces menu.
- `docs/desktop/theory.zh.md` and `docs/desktop/theory.en.md` to summarize root residual equations, Taylor/Monte Carlo uncertainty, and the 2D-only system plot limit.
- `examples/README.md`, `README.md`, `QUICK_START.md`, `QUICK_START.en.md` to point users to generated `.datalab` examples instead of implying all examples are raw text files.

- [ ] **Step 5: Run Slice D verification**

Run:

```bash
PYTHONPATH=. pytest -q tests/test_desktop_docs_smoke.py
PYTHONPATH=. ruff check tests/test_desktop_docs_smoke.py
python -m compileall -q desktop_doc_loader.py
```

Expected:

```text
all selected tests pass; ruff passes; compileall exits 0
```

---

## Final Validation

- [ ] **Step 1: Run focused test suite**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. pytest -q \
  tests/test_root_solving_plotting.py \
  tests/test_app_desktop_workers_core.py \
  tests/test_desktop_gui_schema_scan.py \
  tests/test_desktop_root_solving_ui.py \
  tests/test_example_workspaces.py \
  tests/test_desktop_example_workspace_menu.py \
  tests/test_desktop_docs_smoke.py
```

Expected:

```text
all selected tests pass
```

- [ ] **Step 2: Run focused static checks**

Run:

```bash
PYTHONPATH=. ruff check \
  root_solving/plotting.py \
  root_solving/messages.py \
  examples/catalog.py \
  shared/example_coverage.py \
  tools/scan_desktop_gui_schema.py \
  tools/generate_example_workspaces.py \
  app_desktop/panels.py \
  app_desktop/window.py \
  tests/test_root_solving_plotting.py \
  tests/test_app_desktop_workers_core.py \
  tests/test_desktop_gui_schema_scan.py \
  tests/test_desktop_root_solving_ui.py \
  tests/test_example_workspaces.py \
  tests/test_desktop_example_workspace_menu.py \
  tests/test_desktop_docs_smoke.py
python -m compileall -q root_solving examples shared/example_coverage.py tools/generate_example_workspaces.py app_desktop desktop_doc_loader.py
git diff --check
```

Expected:

```text
ruff passes; compileall exits 0; git diff --check reports no whitespace errors
```

- [ ] **Step 3: Run GUI smoke for example menu and root plot panel**

Run:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. python tools/scan_desktop_gui_schema.py
```

Expected:

```text
issues: []
left_panel_no_horizontal_scrollbar: true
left_panel_horizontal_scrollbar_states: all true
```

- [ ] **Step 4: Review generated artifacts**

Run:

```bash
git status --short
git diff --name-only
```

Expected changed paths are limited to the files listed in this plan plus generated files under `examples/workspaces/`. Untracked `.superpowers/` is ignored.

## Review Checklist

- Every accepted Codex/Gemini/Claude finding is reflected in the tasks above:
  - Rounded tiny-uncertainty intervals assert `2.0/2.0`, while inset range distinctness proves readability.
  - Stale example archives are removed before regeneration.
  - The existing system early return is replaced, not shadowed.
  - `SYSTEM_ROOT_PLOT_WARNING` is updated at the emitting constant and localization layer.
  - System bounds use `_optional_real()` and fall back safely.
  - Example inventory is defined once in `examples/catalog.py`.
  - The left configuration pane scrollbar invariant is tested across calculation modes and root-solving submodes.
  - The desktop menu reads `example_catalog.json` instead of opening every workspace ZIP.
  - System contour grid is capped at 81 points for interactive cost control.
  - Inset metadata count and drawn inset count both cap at 2.
- The plan intentionally does not modify solver algorithms or packaging.
- The plan is split into four independently testable slices. Slice D documentation is merge/publish-gated on Slice A root-plot tests passing because the docs describe inset and 2D contour behavior.
