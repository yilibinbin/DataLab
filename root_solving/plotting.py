from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from math import isfinite
from typing import Any, SupportsInt, TypedDict, TypeVar

from mpmath import mp

from root_solving.expression import RootExpressionSystem, build_root_expression_system
from root_solving.models import RootBatchResult, RootBatchRowResult, RootProblem, RootUnknown, RootValue, immutable_mapping
from shared.uncertainty import parse_numeric_value

SUPPORTED_ROOT_PLOT_MODES = frozenset({"scalar", "scan_multiple"})
SYSTEM_ROOT_PLOT_WARNING = "System root plots are not supported."
ROOT_PLOT_FAILED_WARNING = "Root plot could not be rendered."
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
        if mode == "system":
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
        return None, (SYSTEM_ROOT_PLOT_WARNING,)
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

    try:
        from shared.plotting import plt
    except Exception as exc:  # noqa: BLE001
        return None, (_plot_failed_warning(exc),)

    fig = None
    try:
        fig, ax = plt.subplots(figsize=(6.0, 4.0), dpi=180)
        plot_y = [float("nan") if value is None else value for value in y_values]
        ax.plot(x_values, plot_y, color="#1f77b4", linewidth=1.8, label="Nominal residual")
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
