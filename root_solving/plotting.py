from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from math import isfinite
from typing import Any, SupportsInt, TypedDict, TypeVar

from mpmath import mp

from root_solving.expression import RootExpressionSystem, build_root_expression_system
from root_solving.models import RootBatchResult, RootBatchRowResult, RootProblem, RootUnknown, RootValue, immutable_mapping
from shared.uncertainty import UncertainValue, parse_numeric_value, parse_uncertainty_format

SUPPORTED_ROOT_PLOT_MODES = frozenset({"scalar", "scan_multiple", "system"})
SYSTEM_ROOT_PLOT_WARNING = "System root plots require exactly two equations and two real unknowns; skipped plot."
ROOT_PLOT_FAILED_WARNING = "Root plot could not be rendered."
_SYSTEM_CONTOUR_MAX_GRID_POINTS = 81
_ROOT_INSET_MAX_COUNT = 2
_ROOT_INSET_MIN_RELATIVE_WIDTH = 1.0e-6
_ROOT_INSET_SIGMA_MULTIPLIER = 8.0
_T = TypeVar("_T")


class RootMarkerMetadata(TypedDict):
    name: str
    value: float


@dataclass(frozen=True)
class RootPlotBudget:
    max_grid_points: int = 300
    max_mc_curves: int = 100
    max_batch_rows: int = 25
    max_images_per_run: int = 25

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_grid_points", _positive_int(self.max_grid_points, default=300))
        object.__setattr__(self, "max_mc_curves", _positive_int(self.max_mc_curves, default=100))
        object.__setattr__(self, "max_batch_rows", _positive_int(self.max_batch_rows, default=25))
        object.__setattr__(self, "max_images_per_run", _positive_int(self.max_images_per_run, default=25))


@dataclass(frozen=True)
class RootPlotRequest:
    row: RootBatchRowResult
    image_index: int
    budget: RootPlotBudget = field(default_factory=RootPlotBudget)


@dataclass(frozen=True)
class RootPlotImage:
    image_bytes: bytes
    row_index: int | None
    title: str = ""
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", immutable_mapping(self.metadata))


@dataclass(frozen=True)
class RootPlotSelection:
    requests: tuple[RootPlotRequest, ...] = ()
    images: tuple[RootPlotImage, ...] = ()
    warnings: tuple[str, ...] = ()


def select_root_plot_requests(
    batch: RootBatchResult,
    *,
    budget: RootPlotBudget | None = None,
) -> RootPlotSelection:
    effective_budget = budget or RootPlotBudget()
    warnings: list[str] = []
    requests: list[RootPlotRequest] = []
    max_requests = min(effective_budget.max_batch_rows, effective_budget.max_images_per_run)

    for row in batch.rows:
        if len(requests) >= max_requests:
            break
        if row.failure is not None or row.result is None or not row.result.roots:
            continue
        mode = str(row.result.mode or "").strip()
        if mode == "system" and not _supports_system_contour_plot(row):
            _append_unique(warnings, SYSTEM_ROOT_PLOT_WARNING)
            continue
        if mode not in SUPPORTED_ROOT_PLOT_MODES:
            continue
        requests.append(
            RootPlotRequest(
                row=row,
                image_index=len(requests),
                budget=effective_budget,
            )
        )

    return RootPlotSelection(requests=tuple(requests), warnings=tuple(warnings))


def stable_select_mc_samples(samples: Sequence[_T], *, max_samples: int) -> tuple[_T, ...]:
    sample_count = len(samples)
    limit = _positive_int(max_samples, default=100)
    if sample_count <= limit:
        return tuple(samples)
    if limit == 1:
        return (samples[0],)

    selected: list[_T] = []
    last_index = -1
    for position in range(limit):
        index = round(position * (sample_count - 1) / (limit - 1))
        if index == last_index:
            continue
        selected.append(samples[index])
        last_index = index
    return tuple(selected)


def render_nominal_root_plot(request: RootPlotRequest | None, problem: RootProblem) -> RootPlotImage | None:
    image, _warnings = _render_nominal_root_plot_with_warnings(request, problem)
    return image


def render_nominal_root_plots(
    batch: RootBatchResult,
    problem: RootProblem,
    *,
    budget: RootPlotBudget | None = None,
) -> RootPlotSelection:
    selection = select_root_plot_requests(batch, budget=budget)
    images: list[RootPlotImage] = []
    warnings = list(selection.warnings)
    for request in selection.requests:
        image, image_warnings = _render_nominal_root_plot_with_warnings(request, problem)
        warnings.extend(image_warnings)
        if image is not None:
            images.append(image)
    return RootPlotSelection(
        requests=selection.requests,
        images=tuple(images),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _render_nominal_root_plot_with_warnings(
    request: RootPlotRequest | None,
    problem: RootProblem,
) -> tuple[RootPlotImage | None, tuple[str, ...]]:
    if request is None or request.row.result is None:
        return None, ()
    if request.row.result.mode == "system":
        return _render_system_root_contour_plot_with_warnings(request, problem)
    if len(problem.equations) != 1 or len(problem.unknowns) != 1:
        return None, ()

    row_problem = replace(problem, row_values=request.row.source_values, mode=request.row.result.mode)
    try:
        system = build_root_expression_system(row_problem)
    except Exception as exc:  # noqa: BLE001
        return None, (_plot_failed_warning(exc),)

    unknown = row_problem.unknowns[0]
    x_values = _nominal_grid(unknown, request.row.result.roots, request.budget.max_grid_points)
    y_values = _evaluate_nominal_curve(system, unknown.name, x_values)
    if not x_values or not any(value is not None for value in y_values):
        return None, (_plot_failed_warning("no finite curve points"),)

    roots: tuple[RootMarkerMetadata, ...] = tuple(
        RootMarkerMetadata(name=root.name, value=value)
        for root in request.row.result.roots
        if root.name == unknown.name and (value := _real_float(root.value)) is not None
    )
    title = _root_plot_title(request.row.row_index, row_problem.equations[0])
    metadata = {
        "curve": "nominal",
        "equation": row_problem.equations[0],
        "unknown": unknown.name,
        "grid_points": len(x_values),
        "x_range": (_round_float(x_values[0]), _round_float(x_values[-1])),
        "x_values": tuple(_round_float(value) for value in x_values),
        "y_values": tuple(None if value is None else _round_float(value) for value in y_values),
        "zero_line": True,
        "root_markers": roots,
    }
    uncertainty_visualization = _uncertainty_visualization_metadata(
        request,
        row_problem,
        system,
        unknown.name,
        x_values,
        y_values,
    )
    if uncertainty_visualization:
        metadata["uncertainty_visualization"] = uncertainty_visualization
    root_insets = _root_inset_metadata(
        request.row.result.roots,
        unknown_name=unknown.name,
        x_values=x_values,
        system=system,
    )
    metadata["main_plot_true_scale"] = True
    metadata["root_insets"] = root_insets

    try:
        from shared.plotting import plt
    except Exception as exc:  # noqa: BLE001
        return None, (_plot_failed_warning(exc),)

    fig = None
    try:
        fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=180)
        plot_y = [float("nan") if value is None else value for value in y_values]
        ax.plot(x_values, plot_y, color="#1f77b4", linewidth=1.8, label="Nominal residual")
        _draw_uncertainty_visualization(ax, x_values, uncertainty_visualization)
        ax.axhline(0.0, color="#444444", linewidth=0.9, linestyle="--", alpha=0.8, label="Zero")
        for root in roots:
            root_x = root["value"]
            root_y = _evaluate_root_marker(system, unknown.name, root_x)
            if root_y is not None:
                ax.scatter([root_x], [root_y], color="#d62728", s=34, zorder=3, label="Root")
        ax.set_xlabel(unknown.name)
        ax.set_ylabel("Residual")
        ax.set_title(title)
        ax.grid(True, alpha=0.3)
        _deduplicate_legend(ax)
        if root_insets:
            fig.tight_layout(rect=(0.0, 0.0, 0.56, 1.0))
            _draw_root_insets(fig, root_insets)
        else:
            fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        buf.seek(0)
        image_bytes = buf.getvalue()
    except Exception as exc:  # noqa: BLE001
        if fig is not None:
            plt.close(fig)
        return None, (_plot_failed_warning(exc),)

    return (
        RootPlotImage(
            image_bytes=image_bytes,
            row_index=request.row.row_index,
            title=title,
            warnings=tuple(request.row.warnings),
            metadata=metadata,
        ),
        (),
    )


def _uncertainty_visualization_metadata(
    request: RootPlotRequest,
    problem: RootProblem,
    system: RootExpressionSystem,
    unknown_name: str,
    x_values: Sequence[float],
    y_values: Sequence[float | None],
) -> Mapping[str, object]:
    result = request.row.result
    if result is None:
        return {}
    method = str(result.details.get("uncertainty_method", "") or "").strip()
    if not method:
        return {}
    if method == "taylor":
        return _taylor_uncertainty_metadata(result.roots, problem, system, unknown_name, x_values, y_values, result.details)
    if method == "monte_carlo":
        return _monte_carlo_uncertainty_metadata(
            result.roots,
            problem,
            system,
            unknown_name,
            request.budget,
            x_values,
            result.details,
        )
    if method == "skipped":
        requested = str(result.details.get("uncertainty_requested_method", "") or "").strip()
        note = "uncertainty band unavailable: skipped"
        if requested:
            note = f"uncertainty band unavailable: {method}"
        return {
            "method": "skipped",
            "function_band": None,
            "root_intervals": (),
            "mc_curve_count": 0,
            "notes": (note,),
            "budget_notes": (),
            "detail_notes": _uncertainty_detail_notes(result.details),
        }
    return {}


def _taylor_uncertainty_metadata(
    roots: Sequence[RootValue],
    problem: RootProblem,
    system: RootExpressionSystem,
    unknown_name: str,
    x_values: Sequence[float],
    y_values: Sequence[float | None],
    details: Mapping[str, object],
) -> Mapping[str, object]:
    uncertain_inputs = _active_uncertain_inputs_from_problem(problem, system, details)
    if not uncertain_inputs:
        return _no_band_metadata("taylor", "uncertainty band unavailable: no active uncertain inputs")

    lower_values: list[float | None] = []
    upper_values: list[float | None] = []
    finite_band = False
    active_inputs = tuple(uncertain_inputs)
    for x_value, y_value in zip(x_values, y_values, strict=True):
        if y_value is None:
            lower_values.append(None)
            upper_values.append(None)
            continue
        try:
            unknown_values = {unknown_name: mp.mpf(str(x_value))}
            band_sigma = mp.sqrt(
                mp.fsum(
                    (
                        system.derivative_input(input_name, unknown_values, 0)
                        * mp.mpf(uncertain_inputs[input_name].uncertainty)
                    )
                    ** 2
                    for input_name in active_inputs
                )
            )
            band = _real_float(band_sigma)
        except Exception:
            band = None
        if band is None:
            lower_values.append(None)
            upper_values.append(None)
            continue
        finite_band = True
        lower_values.append(_round_float(y_value - band))
        upper_values.append(_round_float(y_value + band))
    if not finite_band:
        return _no_band_metadata("taylor", "uncertainty band unavailable: derivative evaluation failed")

    return {
        "method": "taylor",
        "function_band": {
            "kind": "first_order",
            "active_inputs": active_inputs,
            "lower_y_values": tuple(lower_values),
            "upper_y_values": tuple(upper_values),
        },
        "root_intervals": _root_intervals(roots, unknown_name),
        "mc_curve_count": 0,
        "notes": (),
        "budget_notes": (),
        "detail_notes": (),
    }


def _monte_carlo_uncertainty_metadata(
    roots: Sequence[RootValue],
    problem: RootProblem,
    system: RootExpressionSystem,
    unknown_name: str,
    budget: RootPlotBudget,
    x_values: Sequence[float],
    details: Mapping[str, object],
) -> Mapping[str, object]:
    valid_samples = _detail_int(details, "monte_carlo_valid_samples")
    if valid_samples <= 0:
        valid_samples = _detail_int(details, "monte_carlo_samples")
    uncertain_inputs = _active_uncertain_inputs_from_problem(problem, system, details)
    primary_root = _primary_uncertain_root(roots, unknown_name)
    if primary_root is None or valid_samples <= 0 or not uncertain_inputs:
        return {
            "method": "monte_carlo",
            "function_band": None,
            "root_intervals": _root_intervals(roots, unknown_name),
            "mc_curve_count": 0,
            "mc_root_markers": (),
            "notes": ("Monte Carlo envelope unavailable: missing valid input uncertainty.",),
            "budget_notes": (),
            "detail_notes": _uncertainty_detail_notes(details),
        }

    sample_indexes = stable_select_mc_samples(tuple(range(valid_samples)), max_samples=budget.max_mc_curves)
    root_value = _real_float(primary_root.value)
    root_uncertainty = _real_float(primary_root.uncertainty)
    if root_value is None or root_uncertainty is None:
        return {
            "method": "monte_carlo",
            "function_band": None,
            "root_intervals": _root_intervals(roots, primary_root.name),
            "mc_curve_count": 0,
            "mc_root_markers": (),
            "notes": ("Monte Carlo envelope unavailable: missing valid root uncertainty.",),
            "budget_notes": (),
            "detail_notes": _uncertainty_detail_notes(details),
        }

    offsets = tuple(_mc_root_offset(index, valid_samples, root_uncertainty) for index in sample_indexes)
    markers = tuple(
        {"name": primary_root.name, "value": _round_float(root_value + offset)}
        for offset in offsets
    )
    input_samples = _mc_input_samples(system, uncertain_inputs, sample_indexes, valid_samples)
    envelope = _mc_input_sample_curve_envelope(system, unknown_name, x_values, input_samples)
    budget_notes: tuple[str, ...] = ()
    if valid_samples > len(sample_indexes):
        budget_notes = (f"Monte Carlo visualization downsampled {valid_samples} valid samples to {len(sample_indexes)} curves.",)

    return {
        "method": "monte_carlo",
        "function_band": None,
        "root_intervals": _root_intervals(roots, primary_root.name),
        "mc_curve_count": len(sample_indexes),
        "mc_input_sample_count": len(input_samples),
        "mc_sampled_inputs": tuple(sorted(uncertain_inputs)),
        "mc_root_markers": markers,
        "mc_envelope": envelope,
        "notes": (),
        "budget_notes": budget_notes,
        "detail_notes": _uncertainty_detail_notes(details),
    }


def _draw_uncertainty_visualization(ax: Any, x_values: Sequence[float], visualization: Mapping[str, object]) -> None:
    function_band = visualization.get("function_band")
    if isinstance(function_band, Mapping):
        lower_values = _optional_value_sequence(function_band.get("lower_y_values"))
        upper_values = _optional_value_sequence(function_band.get("upper_y_values"))
        if lower_values is not None and upper_values is not None:
            ax.fill_between(
                x_values,
                _plot_values(lower_values),
                _plot_values(upper_values),
                color="#ffbf00",
                alpha=0.22,
                linewidth=0,
                label="Taylor band",
            )

    mc_envelope = visualization.get("mc_envelope")
    if isinstance(mc_envelope, Mapping):
        lower_values = _optional_value_sequence(mc_envelope.get("lower_y_values"))
        upper_values = _optional_value_sequence(mc_envelope.get("upper_y_values"))
        if lower_values is not None and upper_values is not None:
            ax.fill_between(
                x_values,
                _plot_values(lower_values),
                _plot_values(upper_values),
                color="#2ca02c",
                alpha=0.16,
                linewidth=0,
                label="MC envelope",
            )

    root_intervals = visualization.get("root_intervals", ())
    if not isinstance(root_intervals, Sequence) or isinstance(root_intervals, (str, bytes)):
        return
    for interval in root_intervals:
        if isinstance(interval, Mapping):
            lower = interval.get("lower")
            upper = interval.get("upper")
            if isinstance(lower, (int, float)) and isinstance(upper, (int, float)):
                ax.axvspan(float(lower), float(upper), color="#d62728", alpha=0.12, linewidth=0)


def _supports_system_contour_plot(row: RootBatchRowResult) -> bool:
    result = row.result
    if result is None or result.mode != "system":
        return False
    root_names = tuple(root.name for root in result.roots)
    return len(root_names) == 2 and len(set(root_names)) == 2


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
    title = _root_plot_title(request.row.row_index, "system")
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
        ax.set_title(title)
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
            title=title,
            warnings=tuple(request.row.warnings),
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


def _no_band_metadata(method: str, note: str) -> Mapping[str, object]:
    return {
        "method": method,
        "function_band": None,
        "root_intervals": (),
        "mc_curve_count": 0,
        "notes": (note,),
        "budget_notes": (),
        "detail_notes": (),
    }


def _primary_uncertain_root(roots: Sequence[RootValue], unknown_name: str) -> RootValue | None:
    for root in roots:
        if root.name == unknown_name and root.uncertainty is not None and _real_float(root.uncertainty) is not None:
            return root
    return None


def _root_intervals(roots: Sequence[RootValue], unknown_name: str) -> tuple[Mapping[str, object], ...]:
    intervals: list[Mapping[str, object]] = []
    for root in roots:
        if root.name != unknown_name:
            continue
        root_value = _real_float(root.value)
        root_uncertainty = _real_float(root.uncertainty)
        if root_value is None or root_uncertainty is None:
            continue
        intervals.append(
            {
                "name": root.name,
                "lower": _round_float(root_value - root_uncertainty),
                "upper": _round_float(root_value + root_uncertainty),
            }
        )
    return tuple(intervals)


def _mc_root_offset(index: int, sample_count: int, sigma: float) -> float:
    if sample_count <= 1:
        return 0.0
    centered_fraction = (2.0 * index / (sample_count - 1)) - 1.0
    return centered_fraction * sigma


def _active_uncertain_inputs_from_problem(
    problem: RootProblem,
    system: RootExpressionSystem,
    details: Mapping[str, object],
) -> Mapping[str, UncertainValue]:
    from_details = _uncertain_inputs_from_details(details)
    if from_details:
        active_symbols = set().union(*(expression.free_symbols for expression in system.symbolic_expressions))
        return {
            name: value
            for name, value in from_details.items()
            if name in system.symbol_map and system.symbol_map[name] in active_symbols
        }

    raw_inputs: dict[str, str] = dict(problem.row_values)
    if not raw_inputs:
        raw_inputs.update({known.name: known.value for known in problem.known_values})
    raw_inputs.update(dict(problem.constants))
    active_symbols = set().union(*(expression.free_symbols for expression in system.symbolic_expressions))
    uncertain: dict[str, UncertainValue] = {}
    for name, raw_value in raw_inputs.items():
        if name not in system.symbol_map or system.symbol_map[name] not in active_symbols:
            continue
        try:
            value = parse_uncertainty_format(str(raw_value))
        except Exception:
            continue
        if value.uncertainty > 0 and mp.isfinite(value.uncertainty):
            uncertain[name] = value
    return uncertain


def _uncertain_inputs_from_details(details: Mapping[str, object]) -> Mapping[str, UncertainValue]:
    payload = details.get("plot_uncertain_inputs", {})
    if not isinstance(payload, Mapping):
        return {}
    uncertain: dict[str, UncertainValue] = {}
    for raw_name, raw_value in payload.items():
        if not isinstance(raw_value, Mapping):
            continue
        name = str(raw_name)
        try:
            value = UncertainValue(
                raw_value.get("value", "0"),
                raw_value.get("uncertainty", "0"),
            )
        except Exception:
            continue
        if value.uncertainty > 0 and mp.isfinite(value.uncertainty):
            uncertain[name] = value
    return uncertain


def _mc_input_samples(
    system: RootExpressionSystem,
    uncertain_inputs: Mapping[str, UncertainValue],
    sample_indexes: Sequence[int],
    sample_count: int,
) -> tuple[Mapping[str, mp.mpf], ...]:
    samples: list[Mapping[str, mp.mpf]] = []
    names = tuple(uncertain_inputs)
    for sample_position, sample_index in enumerate(sample_indexes):
        nominal_inputs = dict(system.nominal_inputs)
        for input_position, name in enumerate(names):
            unit = _mc_input_unit_offset(sample_index, sample_count, input_position, sample_position)
            uncertain = uncertain_inputs[name]
            nominal_inputs[name] = mp.mpf(uncertain.value) + mp.mpf(uncertain.uncertainty) * unit
        samples.append(immutable_mapping(nominal_inputs))
    return tuple(samples)


def _mc_input_unit_offset(sample_index: int, sample_count: int, input_position: int, sample_position: int) -> mp.mpf:
    if sample_count <= 1:
        return mp.mpf("0")
    shifted_index = (sample_index + input_position * max(1, sample_position + 1)) % sample_count
    return mp.mpf("2") * mp.mpf(shifted_index) / mp.mpf(sample_count - 1) - 1


def _mc_input_sample_curve_envelope(
    system: RootExpressionSystem,
    unknown_name: str,
    x_values: Sequence[float],
    input_samples: Sequence[Mapping[str, mp.mpf]],
) -> Mapping[str, object]:
    lower_values: list[float | None] = []
    upper_values: list[float | None] = []
    for x_value in x_values:
        values: list[float] = []
        for nominal_inputs in input_samples:
            try:
                sampled_system = replace(system, nominal_inputs=nominal_inputs)
                y_value = _real_float(sampled_system.evaluate({unknown_name: mp.mpf(str(x_value))}))
            except Exception:
                y_value = None
            if y_value is not None:
                values.append(y_value)
        if not values:
            lower_values.append(None)
            upper_values.append(None)
            continue
        lower_values.append(_round_float(min(values)))
        upper_values.append(_round_float(max(values)))
    return {
        "kind": "deterministic_input_samples",
        "lower_y_values": tuple(lower_values),
        "upper_y_values": tuple(upper_values),
    }


def _uncertainty_detail_notes(details: Mapping[str, object]) -> tuple[str, ...]:
    notes: list[str] = []
    samples = _detail_int(details, "monte_carlo_samples")
    valid_samples = _detail_int(details, "monte_carlo_valid_samples")
    failures = _detail_int(details, "monte_carlo_failures")
    if samples > 0:
        notes.append(f"Monte Carlo requested samples: {samples}.")
    if valid_samples > 0:
        notes.append(f"Monte Carlo valid samples: {valid_samples}.")
    if failures > 0:
        notes.append(f"Monte Carlo failed samples: {failures}.")
    return tuple(notes)


def _detail_int(details: Mapping[str, object], key: str) -> int:
    value = details.get(key, 0) or 0
    if not isinstance(value, (int, float, str)):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return 0


def _optional_value_sequence(value: object) -> tuple[float | None, ...] | None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    values: list[float | None] = []
    for item in value:
        if item is None:
            values.append(None)
            continue
        if not isinstance(item, (int, float)):
            return None
        values.append(float(item))
    return tuple(values)


def _plot_values(values: Sequence[float | None]) -> list[float]:
    return [float("nan") if value is None else value for value in values]


def _linspace(lower: float, upper: float, count: int) -> tuple[float, ...]:
    if count <= 1:
        return (float(lower),)
    step = (float(upper) - float(lower)) / float(count - 1)
    return tuple(float(lower) + step * index for index in range(count))


def _positive_int(value: SupportsInt | str, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return parsed if parsed > 0 else default


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _nominal_grid(unknown: RootUnknown, roots: Sequence[RootValue], max_grid_points: int) -> tuple[float, ...]:
    count = min(_positive_int(max_grid_points, default=300), 300)
    lower = _optional_real(getattr(unknown, "lower", ""))
    upper = _optional_real(getattr(unknown, "upper", ""))
    if lower is None or upper is None or lower >= upper:
        root_values = tuple(
            value
            for root in roots
            if getattr(root, "name", getattr(unknown, "name", "")) == getattr(unknown, "name", "")
            and (value := _real_float(getattr(root, "value", None))) is not None
        )
        center = sum(root_values) / len(root_values) if root_values else (_optional_real(getattr(unknown, "initial", "")) or 0.0)
        half_width = max(1.0, max((abs(value) for value in root_values), default=abs(center)))
        lower = center - half_width
        upper = center + half_width
    if lower == upper:
        lower -= 1.0
        upper += 1.0
    if count == 1:
        return (_round_float((lower + upper) / 2.0),)
    step = (upper - lower) / (count - 1)
    return tuple(_round_float(lower + step * index) for index in range(count))


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


def _evaluate_nominal_curve(
    system: RootExpressionSystem,
    unknown_name: str,
    x_values: Sequence[float],
) -> tuple[float | None, ...]:
    values: list[float | None] = []
    for x_value in x_values:
        try:
            y_value = _real_float(system.evaluate({unknown_name: mp.mpf(str(x_value))}))
        except Exception:
            y_value = None
        values.append(y_value)
    return tuple(values)


def _evaluate_root_marker(system: RootExpressionSystem, unknown_name: str, root_x: float) -> float | None:
    try:
        return _real_float(system.evaluate({unknown_name: mp.mpf(str(root_x))}))
    except Exception:
        return None


def _optional_real(value: object) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return _real_float(parse_numeric_value(value))
    except Exception:
        return None


def _real_float(value: object) -> float | None:
    try:
        numeric = mp.mpf(value)
    except Exception:
        return None
    result = float(numeric)
    return result if isfinite(result) else None


def _round_float(value: float) -> float:
    return round(float(value), 12)


def _root_plot_title(row_index: int | None, equation: str) -> str:
    row_label = "single row" if row_index is None else f"row {row_index}"
    return f"Root residual ({row_label}): {equation}"


def _deduplicate_legend(ax: Any) -> None:
    handles, labels = ax.get_legend_handles_labels()
    unique: dict[str, object] = {}
    for handle, label in zip(handles, labels):
        unique.setdefault(label, handle)
    if unique:
        ax.legend(unique.values(), unique.keys(), frameon=False)


def _plot_failed_warning(error: object) -> str:
    text = str(error).strip()
    return ROOT_PLOT_FAILED_WARNING if not text else f"{ROOT_PLOT_FAILED_WARNING}: {text}"
