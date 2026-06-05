from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import SupportsInt, TypeVar

from root_solving.models import RootBatchResult, RootBatchRowResult

SUPPORTED_ROOT_PLOT_MODES = frozenset({"scalar", "scan_multiple"})
SYSTEM_ROOT_PLOT_WARNING = "System root plots are not supported."
_T = TypeVar("_T")


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


def _positive_int(value: SupportsInt | str, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return parsed if parsed > 0 else default


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)
